"""Capture the resident and policy continuations at the runner's completed boundaries."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from living_island.agents.v2.calls.contracts import digest, json_bytes
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.memory.v2.records import MemoryRecord
from living_island.memory.v2.store import DecisionDispatch, MemoryStore, StoreWrite
from living_island.persistence.v2.audit import AuditReader
from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
from living_island.persistence.v2.journal import PacketJournal
from living_island.sim.v2.compat.policy_host import PolicyCheckpoint, restore_policies
from living_island.sim.v2.harness.session import Incomplete, ResidentContinuation, ResidentSession
from living_island.sim.v2.manifest import FallbackTurn, StopRecord
from living_island.world.v2.engine import TickResult, World
from living_island.world.v2.engine.snapshot import encode_snapshot
from living_island.world.v2.protocol import TurnSubmission
from living_island.world.v2.rules import Pack


class Edit(Fact):
    id: str
    body: str | None


class Revision(Fact):
    kind: Literal["mechanical", "change_set", "use"]
    before: int
    after: int
    store_hash: str
    edits: tuple[Edit, ...]
    dispatch: DecisionDispatch | None


class RecordingStore(MemoryStore):
    journal: Journal

    def apply(
        self,
        base_version: int,
        kind: Literal["mechanical", "change_set"],
        edits: Iterable[MemoryRecord | str],
    ) -> StoreWrite:
        ordered = tuple(edits)
        write = super().apply(base_version, kind, ordered)
        parts = tuple(
            Edit(id=item, body=None)
            if isinstance(item, str)
            else Edit(id=item.id, body=self.journal.blob(json_bytes(item.model_dump(mode="json"))))
            for item in ordered
        )
        self._record(write, parts)
        return write

    def credit_dispatch(self, dispatch: DecisionDispatch) -> StoreWrite | None:
        write = super().credit_dispatch(dispatch)
        if write is not None:
            self._record(write, ())
        return write

    def _record(self, write: StoreWrite, edits: tuple[Edit, ...]) -> None:
        self.journal.fact(
            write.owner_id,
            f"v{write.after_version}.revision",
            Revision(
                kind=write.kind,
                before=write.before_version,
                after=write.after_version,
                edits=edits,
                dispatch=write.dispatch,
                store_hash=write.store_hash,
            ),
        )


class Boundary(Fact):
    tick: int
    through: int
    committed: bool
    submissions: tuple[TurnSubmission, ...]
    fallbacks: tuple[FallbackTurn, ...]
    events: str
    world_hash: str
    store_version: int
    store_hash: str
    decision: str | None
    stop: StopRecord | None
    incomplete: Incomplete | None


class Runtime(Fact):
    policies: dict[str, PolicyCheckpoint]
    resident: ResidentContinuation
    cursor: int
    stop: StopRecord | None

    @property
    def continuation(self) -> tuple[dict[str, PolicyCheckpoint], ResidentContinuation]:
        return self.policies, self.resident


class Bookmark(Fact):
    runtime: str


def observe_revisions(session: ResidentSession) -> None:
    period = session.resident.period
    store = RecordingStore.from_snapshot(period.store.snapshot, period.store.registry)
    store.journal = period.journal
    period.store = period.writer.store = store


@dataclass
class Recording:
    session: ResidentSession
    packets: PacketJournal
    audit: AuditReader
    _completed: bool = True

    def __post_init__(self) -> None:
        observe_revisions(self.session)

    @classmethod
    def opening(
        cls, session: ResidentSession, packets: PacketJournal, audit: AuditReader
    ) -> "Recording":
        """Retain the founding profile write made by compose before the first delivery."""
        recording = cls(session, packets, audit)
        period = session.resident.period
        seed = period.store.snapshot
        records = tuple(
            Edit(id=r.id, body=period.journal.blob(json_bytes(r.model_dump(mode="json"))))
            for r in seed.records()
        )
        period.journal.fact(
            seed.owner_id,
            "v1.revision",
            Revision(
                kind="mechanical",
                before=0,
                after=seed.version,
                store_hash=seed.store_hash,
                edits=records,
                dispatch=None,
            ),
        )
        return recording

    def save(self, path: Path) -> None:
        if not self._completed:
            raise RuntimeError("cannot save an incomplete resident boundary")
        session = self.session
        runtime = Runtime(
            policies=restore_policies(session.checkpoint()),
            resident=session.continuation(),
            cursor=self.audit.cursor(),
            stop=session.runner.manifest.stop,
        )
        ref = session.resident.period.journal.blob(json_bytes(runtime.model_dump(mode="json")))
        save_checkpoint(path, session.world, self.packets, {"runtime": ref})

    def advance(self) -> TickResult | None:
        session = self.session
        if not self._completed:
            raise RuntimeError("restore the last completed resident boundary")
        if session.incomplete:
            return None
        self._completed = False
        tick = session.world.tick
        result = session.advance()
        period = session.resident.period
        snapshot = period.store.snapshot
        commit = session.runner.manifest.boundaries[-1] if result is not None else None
        decision = session.records[-1] if session.request is not None else None
        journal = period.journal
        events = journal.blob(commit.event_lines if commit else b"")
        boundary = Boundary(
            tick=tick,
            through=self.audit.cursor(),
            committed=commit is not None,
            submissions=commit.submissions if commit else (),
            fallbacks=commit.fallback_turns if commit else (),
            events=events,
            world_hash=digest(encode_snapshot(session.world)),
            store_version=snapshot.version,
            store_hash=snapshot.store_hash,
            decision=journal.cursor(decision.turn_id, "decision") if decision else None,
            stop=session.runner.manifest.stop,
            incomplete=session.incomplete,
        )
        journal.fact(session.world.run_id, f"{tick}.boundary", boundary)
        self._completed = True
        return result


def load(
    path: Path, pack: Pack, packets: PacketJournal, audit: AuditReader
) -> tuple[World, Runtime]:
    saved = load_checkpoint(path, pack, packets)
    bookmark = Bookmark.model_validate(saved.sim_checkpoint)
    return saved.world, Runtime.model_validate_json(audit.read(bookmark.runtime))
