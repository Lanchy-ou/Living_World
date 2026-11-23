"""Publish a frozen transaction at K and settle the resident's failed periods."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from typing import Literal

from living_island.memory.v2.changes import (
    CommittedChangeSet,
    Edit,
    OperationEffects,
    StagedChangeSet,
)
from living_island.memory.v2.pending import PendingPeriod, PendingPeriods
from living_island.memory.v2.projections import RevisionRef
from living_island.memory.v2.provenance import relabel_flags
from living_island.memory.v2.records import (
    Inferred,
    MemoryRecord,
    Personality,
    Skill,
    Social,
    Source,
    _source_key,
)
from living_island.memory.v2.store import MemoryStore


class VersionConflict(ValueError):
    """The store offered at K has a model-owned change since confirmation."""


@dataclass(frozen=True)
class SettledChangeSet(CommittedChangeSet):
    effects: tuple[OperationEffects, ...]


def _with_mechanical_fields(record: MemoryRecord, live: MemoryRecord) -> MemoryRecord:
    """Only social facts, skill evidence and use counters can advance on existing records."""
    content = record.content
    match content, live.content:
        case Social(), Social(facts=facts):
            content = content.model_copy(update={"facts": facts})
        case Skill(), Skill(evidence=evidence):
            content = content.model_copy(update={"evidence": evidence})
    return record.model_copy(
        update={
            "content": content,
            "use_count": live.use_count,
            "last_used_tick": live.last_used_tick,
        }
    )


def _check_mechanical_interval(
    frozen: Mapping[str, MemoryRecord], live: Mapping[str, MemoryRecord]
) -> None:
    """Compare the two coordinator-supplied snapshots before publishing any operation."""
    for key, original in frozen.items():
        current = live.get(key)
        if current is None:
            raise VersionConflict(f"frozen record removed: {key}")
        permitted = _with_mechanical_fields(original, current).model_copy(
            update={"updated_tick": current.updated_tick}
        )
        # The mechanical social writer regenerates the gist whenever it writes facts.
        if (
            isinstance(current.content, Social)
            and isinstance(original.content, Social)
            and current.content.facts != original.content.facts
            and current.gist == current.content.mechanical_gist()
        ):
            permitted = permitted.model_copy(update={"gist": current.gist})
        if permitted != current:
            raise VersionConflict(f"model-owned field changed: {key}")
    for key in live.keys() - frozen.keys():
        if live[key].kind not in ("social", "commitment"):
            raise VersionConflict(f"non-mechanical record created: {key}")


def _remap_source(source: Source, ids: Mapping[str, str]) -> Source:
    if isinstance(source, Inferred):
        return source.model_copy(
            update={"memory_ids": sorted(ids.get(key, key) for key in source.memory_ids)}
        )
    return source


def _remap_sources(sources: list[Source], ids: Mapping[str, str]) -> list[Source]:
    # Allocation can cross a digit boundary and change the lexical order of inferred IDs.
    return sorted((_remap_source(s, ids) for s in sources), key=_source_key)


def _remap_record(record: MemoryRecord, ids: Mapping[str, str]) -> MemoryRecord:
    """Bind producer references to IDs allocated after intervening mechanical creations."""
    content = record.content
    if isinstance(content, Personality):
        traits = []
        for trait in content.traits:
            changes = [
                change.model_copy(update={"sources": _remap_sources(change.sources, ids)})
                for change in trait.changes
            ]
            traits.append(trait.model_copy(update={"changes": changes}))
        content = content.model_copy(update={"traits": traits})
    return record.model_copy(
        update={
            "id": ids.get(record.id, record.id),
            "sources": _remap_sources(record.sources, ids),
            "supersedes": ids.get(record.supersedes, record.supersedes)
            if record.supersedes
            else None,
            "superseded_by": ids.get(record.superseded_by, record.superseded_by)
            if record.superseded_by
            else None,
            "content": content,
        }
    )


def commit_rebased(store: MemoryStore, staged: StagedChangeSet) -> SettledChangeSet:
    """Commit once; keep sent revisions fixed and rebind staged revisions to the real write."""
    latest = store.snapshot
    if latest is staged.base or latest.store_hash == staged.base.store_hash:
        committed = staged.commit(store)
        return SettledChangeSet(committed.write, committed.relabel_flags, staged.effects)

    before = {r.id: r for r in staged.base.records()}
    live = {r.id: r for r in latest.records()}
    _check_mechanical_interval(before, live)
    produced = [e.produced_id for e in staged.effects if e.produced_id is not None]
    ids = {key: latest.next_id(offset) for offset, key in enumerate(produced)}
    updates = {op.op_id for op in staged.change_set.ops if op.name == "update"}
    refs: dict[RevisionRef, RevisionRef] = {}
    settled: list[OperationEffects] = []
    for effect in staged.effects:
        carried = tuple(refs.get(ref, ref) for ref in effect.carried_from)
        bindings = tuple(
            replace(
                binding,
                source=_remap_source(binding.source, ids),
                revisions=tuple(
                    sorted(
                        (refs.get(ref, ref) for ref in binding.revisions), key=lambda ref: ref.id
                    )
                ),
            )
            for binding in effect.bindings
        )
        edits: list[Edit] = []
        for edit in effect.edits:
            if isinstance(edit, str):
                edits.append(ids.get(edit, edit))
                continue
            record = _remap_record(edit, ids)
            if record.id in live:
                current = live[record.id]
                record = _with_mechanical_fields(record, current)
                if effect.op_id not in updates and isinstance(record.content, Social):
                    record = record.model_copy(update={"gist": current.gist})
            edits.append(record)
            live[record.id] = record
            refs[RevisionRef(edit.id, staged.base.version + 1, edit.content_hash())] = RevisionRef(
                record.id, latest.version + 1, record.content_hash()
            )
        settled.append(
            replace(
                effect,
                edits=tuple(edits),
                produced_id=ids[effect.produced_id] if effect.produced_id else None,
                evictions=tuple(ids.get(key, key) for key in effect.evictions),
                carried_from=carried,
                bindings=bindings,
            )
        )

    write = store.apply(latest.version, "change_set", (e for op in settled for e in op.edits))
    flags = relabel_flags(store.snapshot, ids.values(), staged.sent.call_id)
    return SettledChangeSet(write, flags, tuple(settled))


@dataclass(frozen=True)
class PendingState:
    period_id: str
    state: Literal["included", "omitted", "retained", "evicted"]


@dataclass(frozen=True)
class PendingDisposition[T]:
    states: tuple[PendingState, ...]
    pending_after: tuple[str, ...]
    evicted: PendingPeriod[T] | None


def finish_pending[T](
    pending: PendingPeriods[T],
    closed: PendingPeriod[T],
    *,
    committed: bool,
    sent_period_ids: Collection[str] = (),
) -> PendingDisposition[T]:
    """Use full membership from the committed change-set wire, in pending insertion order."""
    previous = [p.period_id for p in pending.read()]
    if committed:
        consumed = {p.period_id for p in pending.consume(sent_period_ids)}
        states = tuple(
            PendingState(p, "included" if p in consumed else "omitted") for p in previous
        )
        return PendingDisposition(states, tuple(p for p in previous if p not in consumed), None)
    evicted = pending.append(closed)
    after = tuple(p.period_id for p in pending.read())
    states = tuple(
        PendingState(p, "evicted" if evicted is not None and p == evicted.period_id else "retained")
        for p in [*previous, closed.period_id]
    )
    return PendingDisposition(states, after, evicted)
