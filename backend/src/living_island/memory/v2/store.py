"""Copy-on-write resident store. The coordinator owns writes and any retained snapshots."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Literal, Self

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as validated_dataclass

from living_island.memory.v2.kinds import KindRegistry
from living_island.memory.v2.projections import (
    ProjectedRevision,
    ResidentView,
    RevisionRef,
    _project,
)
from living_island.memory.v2.records import (
    Commitment,
    Intention,
    MemoryRecord,
    Observed,
    Social,
    digest,
    single_line,
)
from living_island.world.v2.protocol import Tick

type WriteKind = Literal["mechanical", "change_set", "use"]


@dataclass(frozen=True)
class Head:
    content_hash: str
    last_used_tick: int | None
    use_count: int


@dataclass(frozen=True)
class Change:
    id: str
    before: Head | None
    after: Head | None


@validated_dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DecisionDispatch:
    """Prefix and recall refs from the sent manifest, supplied only upon actual dispatch."""

    stage: Literal["decision", "decision_after_recall"]
    turn_id: str
    call_id: str
    tick: Tick
    revisions: tuple[RevisionRef, ...]


@dataclass(frozen=True)
class StoreWrite:
    owner_id: str
    kind: WriteKind
    before_version: int
    after_version: int
    store_hash: str
    changes: tuple[Change, ...]
    # Content-addressed bodies for the coordinator. Changes carry the two use counters.
    blobs: Mapping[str, MemoryRecord]
    dispatch: DecisionDispatch | None = None
    credited: tuple[RevisionRef, ...] = ()


@dataclass(frozen=True)
class Snapshot:
    owner_id: str
    version: int
    next_number: int
    _heads: Mapping[str, Head]
    _blobs: Mapping[str, MemoryRecord]
    _current_intention_id: str | None = None
    credited_turn_id: str | None = None
    credited_ids: frozenset[str] = frozenset()

    def next_id(self, offset: int = 0) -> str:
        """Preview an ID in a change set based on this snapshot."""
        return f"m:{self.owner_id}:{self.next_number + offset}"

    def ref(self, record_id: str) -> RevisionRef:
        return RevisionRef(record_id, self.version, self._heads[record_id].content_hash)

    def _record(self, record_id: str) -> MemoryRecord:
        head = self._heads[record_id]
        return self._blobs[head.content_hash].model_copy(
            update={"last_used_tick": head.last_used_tick, "use_count": head.use_count}
        )

    def read(self, ref: RevisionRef) -> MemoryRecord:
        if ref != self.ref(ref.id):
            raise ValueError("revision does not match this snapshot")
        return self._record(ref.id).model_copy(deep=True)

    def records(self) -> tuple[MemoryRecord, ...]:
        """Writer/inspection read, including archived records. All returned data is detached."""
        return tuple(self._record(key).model_copy(deep=True) for key in sorted(self._heads))

    @property
    def store_hash(self) -> str:
        return digest(
            {
                "owner_id": self.owner_id,
                "version": self.version,
                "next_number": self.next_number,
                "credited_turn_id": self.credited_turn_id,
                "credited_ids": sorted(self.credited_ids),
                "records": [{"id": key, **asdict(self._heads[key])} for key in sorted(self._heads)],
            }
        )

    def current_intention(self) -> MemoryRecord | None:
        key = self._current_intention_id
        return None if key is None else self.read(self.ref(key))

    def resident(self, *, memory_on: bool) -> ResidentView:
        if not memory_on:
            current = self.current_intention()
            intention = _project(self.ref(current.id), current, {}) if current else None
            return ResidentView((), intention)

        links = {
            record.content.agreement_id: record.id
            for record in self._blobs.values()
            if isinstance(record.content, Commitment)
        }
        visible: list[ProjectedRevision] = []
        intention = None
        for key in sorted(self._heads):
            record = self._record(key)
            if not record.archived:
                entry = _project(self.ref(key), record, links)
                visible.append(entry)
                if isinstance(record.content, Intention) and not record.history:
                    intention = entry
        return ResidentView(tuple(visible), intention)


class MemoryStore:
    def __init__(self, owner_id: str, registry: KindRegistry | None = None) -> None:
        self.registry = registry if registry is not None else KindRegistry()
        self._snapshot = Snapshot(owner_id, 0, 1, {}, {})

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot, registry: KindRegistry | None = None) -> Self:
        """Resume from a retained snapshot, using the coordinator's registered kinds."""
        store = cls(snapshot.owner_id, registry)
        store._snapshot = snapshot
        return store

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshot

    def apply(
        self,
        base_version: int,
        kind: Literal["mechanical", "change_set"],
        edits: Iterable[MemoryRecord | str],
    ) -> StoreWrite:
        """Apply validated records/removal IDs in order, then publish exactly one version."""
        base = self.snapshot
        if base_version != base.version:
            raise ValueError("stale store version")
        heads = dict(base._heads)
        blobs = dict(base._blobs)
        added: dict[str, MemoryRecord] = {}
        changes: list[Change] = []
        next_number = base.next_number
        current = base._current_intention_id
        for edit in edits:
            if isinstance(edit, str):
                changes.append(Change(edit, heads.pop(edit), None))
                if edit == current:
                    current = None
                continue
            previous = heads.get(edit.id)
            if previous is None:
                if edit.id != f"m:{base.owner_id}:{next_number}":
                    raise ValueError("new record must use the next resident-local ID")
                next_number += 1
            elif blobs[previous.content_hash].kind != edit.kind:
                raise ValueError("cannot change a record's kind")
            if type(edit.content) is not self.registry[edit.kind].schema:
                raise ValueError("record content differs from registered schema")
            if isinstance(edit.content, Commitment):
                edit = edit.model_copy(update={"gist": edit.content.summary(), "text": None})
            elif kind == "mechanical" and isinstance(edit.content, Social):
                edit = edit.model_copy(update={"gist": edit.content.mechanical_gist()})
            if isinstance(edit.content, Intention):
                if not edit.history:
                    if previous is not None and blobs[previous.content_hash].history:
                        raise ValueError("historical intention cannot become current")
                    if current is not None and current != edit.id:
                        raise ValueError("resident already has a current intention")
                    current = edit.id
                elif current == edit.id:
                    current = None
            key = edit.content_hash()
            if key not in blobs:
                body = edit.model_copy(deep=True, update={"last_used_tick": None, "use_count": 0})
                added[key] = blobs[key] = body
            head = Head(key, edit.last_used_tick, edit.use_count)
            heads[edit.id] = head
            changes.append(Change(edit.id, previous, head))

        current_hashes = {head.content_hash for head in heads.values()}
        after = replace(
            base,
            version=base.version + 1,
            next_number=next_number,
            _heads=heads,
            _blobs={key: blobs[key] for key in current_hashes},
            _current_intention_id=current,
        )
        receipt = StoreWrite(
            base.owner_id,
            kind,
            base.version,
            after.version,
            after.store_hash,
            tuple(changes),
            {key: body.model_copy(deep=True) for key, body in added.items()},
        )
        self._snapshot = after
        return receipt

    def credit_dispatch(self, dispatch: DecisionDispatch) -> StoreWrite | None:
        """Credit each newly sent ID in one batch and retain the revision actually sent."""
        base = self.snapshot
        seen = set(base.credited_ids) if base.credited_turn_id == dispatch.turn_id else set()
        heads = dict(base._heads)
        changes = []
        credited = []
        for ref in dispatch.revisions:
            if ref.id in seen:
                continue
            old = heads[ref.id]
            seen.add(ref.id)
            new = Head(old.content_hash, dispatch.tick, old.use_count + 1)
            heads[ref.id] = new
            changes.append(Change(ref.id, old, new))
            credited.append(ref)
        if not changes:
            return None
        after = replace(
            base,
            version=base.version + 1,
            _heads=heads,
            credited_turn_id=dispatch.turn_id,
            credited_ids=frozenset(seen),
        )
        receipt = StoreWrite(
            base.owner_id,
            "use",
            base.version,
            after.version,
            after.store_hash,
            tuple(changes),
            {},
            dispatch,
            tuple(credited),
        )
        self._snapshot = after
        return receipt

    def set_intention(
        self,
        *,
        turn_id: str,
        tick: int,
        text: str,
        source: Observed,
    ) -> StoreWrite:
        base = self.snapshot
        old = base.current_intention()
        record = MemoryRecord(
            id=base.next_id(),
            owner_id=base.owner_id,
            kind="intention",
            created_tick=tick,
            updated_tick=tick,
            about_tick=None,
            sources=[source],
            confidence=3,
            last_used_tick=None,
            use_count=0,
            needs_review=False,
            speech_derived=False,
            supersedes=old.id if old else None,
            superseded_by=None,
            text=text,
            gist=single_line(text),
            content=Intention(set_turn=turn_id, state="current", ended_turn=None),
        )
        edits = [_end(old, "replaced", turn_id, tick, record.id)] if old else []
        return self._write_intention(base, [*edits, record])

    def end_intention(self, *, tick: int, turn_id: str | None) -> StoreWrite | None:
        """An adopted clear has a turn ID. An off-arm period reset has none."""
        base = self.snapshot
        old = base.current_intention()
        if old is None:
            return None
        state: Literal["reset", "cleared"] = "reset" if turn_id is None else "cleared"
        return self._write_intention(base, [_end(old, state, turn_id, tick, None)])

    def _write_intention(self, base: Snapshot, revisions: Sequence[MemoryRecord]) -> StoreWrite:
        # Intentions are mechanical. Their bounded history also applies in the off arm.
        history = [
            record
            for record in base._blobs.values()
            if record.kind == "intention" and record.history
        ]
        history.extend(record for record in revisions if record.history)
        history.sort(key=lambda r: (r.created_tick, r.id))
        overflow = len(history) - self.registry["intention"].history_capacity
        evicted = [record.id for record in history[: max(0, overflow)]]
        return self.apply(base.version, "mechanical", [*revisions, *evicted])


def _end(
    record: MemoryRecord,
    state: Literal["replaced", "cleared", "reset"],
    turn_id: str | None,
    tick: int,
    successor: str | None,
) -> MemoryRecord:
    return record.model_copy(
        update={
            "updated_tick": tick,
            "superseded_by": successor,
            "content": record.content.model_copy(update={"state": state, "ended_turn": turn_id}),
        }
    )
