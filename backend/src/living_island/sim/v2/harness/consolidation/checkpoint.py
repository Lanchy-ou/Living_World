"""Resident continuation payloads for the coordinator's persistence port."""

from collections.abc import Mapping
from typing import Any, Literal

from living_island.agents.v2.calls.guard import Part
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.agents.v2.context.day_log import Awareness, DayLog, LookSignature
from living_island.agents.v2.context.entries import DayEntry
from living_island.agents.v2.context.prefix import FrozenPrefix
from living_island.agents.v2.context.working import FrozenPeriod, WorkingContext
from living_island.memory.v2.kinds import KindRegistry
from living_island.memory.v2.mechanical import WriterCheckpoint
from living_island.memory.v2.pending import PendingPeriod
from living_island.memory.v2.store import Head, Snapshot

from .workflow import WorkflowState


class StoreImage(Fact):
    owner_id: str
    version: int
    next_number: int
    records: tuple[dict[str, Any], ...]
    current_intention_id: str | None
    credited_turn_id: str | None
    credited_ids: tuple[str, ...]

    @classmethod
    def capture(cls, snapshot: Snapshot) -> "StoreImage":
        intention = snapshot.current_intention()
        return cls(
            owner_id=snapshot.owner_id,
            version=snapshot.version,
            next_number=snapshot.next_number,
            records=tuple(record.model_dump(mode="json") for record in snapshot.records()),
            current_intention_id=intention.id if intention else None,
            credited_turn_id=snapshot.credited_turn_id,
            credited_ids=tuple(sorted(snapshot.credited_ids)),
        )

    def restore(self, registry: KindRegistry) -> Snapshot:
        heads = {}
        blobs = {}
        for fields in self.records:
            record = registry.parse(fields)
            key = record.content_hash()
            heads[record.id] = Head(key, record.last_used_tick, record.use_count)
            blobs[key] = record.model_copy(update={"last_used_tick": None, "use_count": 0})
        return Snapshot(
            self.owner_id,
            self.version,
            self.next_number,
            heads,
            blobs,
            self.current_intention_id,
            self.credited_turn_id,
            frozenset(self.credited_ids),
        )


class LogState(Fact):
    period_id: str
    awareness: Awareness
    looks: dict[str, LookSignature]
    entries: tuple[DayEntry, ...]


class PeriodLog(DayLog):
    """Keep DL-02's live change detector with its entries, including before first wake."""

    @property
    def awareness(self) -> Awareness:
        return self._awareness

    def checkpoint(self) -> LogState:
        return LogState(
            period_id=self.period_id,
            awareness=self._awareness,
            looks=self._looks,
            entries=self.entries,
        )

    @classmethod
    def restore(
        cls, state: LogState, journal: Journal, phenomena: Mapping[str, str]
    ) -> "PeriodLog":
        log = cls(state.period_id, journal, phenomena=phenomena, prior_awareness=state.awareness)
        log._entries.extend(state.entries)
        log._looks.update(state.looks)
        return log


class AttemptState(Fact):
    s_tick: int
    started_tick: int
    confirming_delivery: str
    frozen: FrozenPeriod
    pending: tuple[PendingPeriod[FrozenPeriod], ...]
    mechanical_ids: tuple[str, ...]
    base: StoreImage
    later_ids: tuple[str, ...]
    workflow: WorkflowState | None
    disposition: str | None


class PeriodCheckpoint(Fact):
    checkpoint_schema: Literal["mf-checkpoint/0.1"] = "mf-checkpoint/0.1"
    store: StoreImage
    memory_on: bool
    number: int
    log: LogState
    prefix: FrozenPrefix | None
    current_state: tuple[Part, ...]
    writer: WriterCheckpoint
    changed_ids: tuple[str, ...]
    pending: tuple[PendingPeriod[FrozenPeriod], ...]
    attempt: AttemptState | None
    last_delivery: str | None
    last_record: str | None
    halt: Literal["stopped_unfit", "dead"] | None

    def working_context(self, log: PeriodLog) -> WorkingContext | None:
        if self.prefix is None:
            return None
        context = WorkingContext(self.prefix, log)
        context._last_state = self.current_state
        return context
