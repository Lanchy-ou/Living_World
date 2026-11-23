"""Resident-local period boundaries, driven by committed world deaths and deliveries."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Self, cast

from living_island.agents.v2.calls.contracts import Selection, json_bytes
from living_island.agents.v2.calls.guard import Part
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.agents.v2.context.delivery import FilteredDelivery
from living_island.agents.v2.context.entries import DayEntry
from living_island.agents.v2.context.prefix import FrozenPrefix
from living_island.agents.v2.context.working import FrozenPeriod, WorkingContext
from living_island.memory.v2.changes import OperationEffects, Verdict
from living_island.memory.v2.kinds import KindRegistry
from living_island.memory.v2.mechanical import AgreementFact, MechanicalWrite, MechanicalWriter
from living_island.memory.v2.pending import PendingPeriod, PendingPeriods
from living_island.memory.v2.provenance import RelabelFlag
from living_island.memory.v2.records import MemoryRecord
from living_island.memory.v2.store import MemoryStore, Snapshot, StoreWrite
from living_island.sim.v2.harness.agreement_facts import mechanical_delivery
from living_island.world.v2.protocol import Intent

from .checkpoint import AttemptState, LogState, PeriodCheckpoint, PeriodLog, StoreImage
from .inputs import FixedInput
from .settlement import PendingState, VersionConflict, commit_rebased, finish_pending
from .workflow import Workflow

K = 36
type Outcome = Literal["committed", "failed", "abandoned", "off_arm"]
type Halt = Literal["dead", "stopped_unfit"]


class ConsolidationRecord(Fact):
    record_schema: Literal["mf/0.1"] = "mf/0.1"
    resident_id: str
    period_id: str
    arm: Literal["on", "off"]
    s_tick: int
    started_tick: int
    confirming_delivery: str
    boundary_tick: int
    outcome: Outcome
    reason: str | None
    base_version: int
    result_version: int | None
    store_hash: str
    selection_call_id: str | None
    change_set_call_id: str | None
    selection: Selection | None
    change_set: dict[str, Any] | None
    verdicts: tuple[Verdict, ...]
    relabel_flags: tuple[RelabelFlag, ...]
    pending: tuple[PendingState, ...]
    pending_after: tuple[str, ...]
    closed_context: str | None
    effects: tuple[OperationEffects, ...]
    episodic_created: int
    write: StoreWrite | None


class PacketReceipt(Fact):
    period_id: str
    delivery_id: str
    entries: tuple[str, ...]
    writes: tuple[MechanicalWrite, ...]


@dataclass(frozen=True)
class BoundaryResult:
    status: Literal["delivered", "waiting", "stopped_unfit", "dead"]
    record: ConsolidationRecord | None = None
    entries: tuple[DayEntry, ...] = ()
    writes: tuple[MechanicalWrite, ...] = ()


@dataclass
class _Cycle:
    s_tick: int
    started_tick: int
    confirming_delivery: str
    fixed: FixedInput
    base: Snapshot
    workflow: Workflow | None
    later_ids: set[str] = field(default_factory=set)
    disposition: str | None = None

    def checkpoint(self) -> AttemptState:
        return AttemptState(
            s_tick=self.s_tick,
            started_tick=self.started_tick,
            confirming_delivery=self.confirming_delivery,
            frozen=self.fixed.period,
            pending=self.fixed.pending,
            mechanical_ids=tuple(sorted(self.fixed.mechanical_ids)),
            base=StoreImage.capture(self.base),
            later_ids=tuple(sorted(self.later_ids)),
            workflow=self.workflow.checkpoint() if self.workflow else None,
            disposition=self.disposition,
        )


class PeriodCoordinator:
    """Consume a resident's deliveries in order. The host services workflow work independently.

    A waiting delivery stays pending at the host until the workflow is ready. Death is a
    separate committed world notification, since a dead resident has no delivery at K.
    If publication fails, resume the last completed boundary and reconcile its journal
    prefix. A partial boundary cannot supply a checkpoint or acknowledge a redelivery.
    """

    def __init__(
        self,
        store: MemoryStore,
        journal: Journal,
        prefix: FrozenPrefix,
        *,
        memory_on: bool = True,
        phenomena: Mapping[str, str] = MappingProxyType({}),
    ) -> None:
        self.store = store
        self.journal = journal
        self.memory_on = memory_on
        self.phenomena = phenomena
        self.number = 1
        self.log = PeriodLog(prefix.period_id, journal, phenomena=phenomena)
        self.context: WorkingContext | None = WorkingContext(prefix, self.log)
        self.writer = MechanicalWriter(store)
        self.pending = PendingPeriods[FrozenPeriod](store.snapshot.owner_id)
        self._cycle: _Cycle | None = None
        self._changed: set[str] = set()
        self._last_delivery: str | None = None
        self._last_record: str | None = None
        self._halt: Halt | None = None
        self._publishing = False

    def _require_completed_boundary(self) -> None:
        if self._publishing:
            raise RuntimeError("incomplete period boundary; restore its previous checkpoint")

    @contextmanager
    def _publication(self) -> Iterator[None]:
        self._require_completed_boundary()
        self._publishing = True
        yield
        self._publishing = False

    @property
    def period_id(self) -> str:
        return self.log.period_id

    @property
    def workflow(self) -> Workflow | None:
        return self._cycle.workflow if self._cycle else None

    def open(self, prefix: FrozenPrefix) -> WorkingContext:
        """Attach DL-02's first awake prefix to the new period's existing delivery log."""
        if self.context is None:
            self.context = WorkingContext(prefix, self.log)
        return self.context

    def _confirm(self, s: int, tick: int, delivery_id: str, context: WorkingContext) -> None:
        base = self.store.snapshot
        fixed = FixedInput(
            context.freeze(),
            self.pending.read(),
            base.resident(memory_on=self.memory_on),
            base.version,
            frozenset(self._changed),
        )
        flow = (
            Workflow.start(
                fixed,
                resident_id=base.owner_id,
                period_id=self.period_id,
                tick=tick,
                journal=self.journal,
            )
            if self.memory_on
            else None
        )
        self._cycle = _Cycle(s, tick, delivery_id, fixed, base, flow)

    def _record(
        self,
        cycle: _Cycle,
        tick: int,
        outcome: Outcome,
        reason: str | None,
        *,
        closed: str | None = None,
        write: StoreWrite | None = None,
        verdicts: tuple[Verdict, ...] = (),
        pending: tuple[PendingState, ...] = (),
        flags: tuple[RelabelFlag, ...] = (),
        effects: tuple[OperationEffects, ...] = (),
    ) -> ConsolidationRecord:
        state = cycle.workflow.checkpoint() if cycle.workflow else None
        calls = state.calls if state else ()
        change = state.change_set if state else None
        record = ConsolidationRecord(
            resident_id=cycle.base.owner_id,
            period_id=self.period_id,
            arm="on" if self.memory_on else "off",
            s_tick=cycle.s_tick,
            started_tick=cycle.started_tick,
            confirming_delivery=cycle.confirming_delivery,
            boundary_tick=tick,
            outcome=outcome,
            reason=reason,
            base_version=cycle.base.version,
            result_version=write.after_version if write else None,
            store_hash=self.store.snapshot.store_hash,
            selection_call_id=calls[0].call.call_id if calls else None,
            change_set_call_id=calls[1].call.call_id if len(calls) == 2 else None,
            selection=state.selection if state else None,
            change_set={
                "base_version": cycle.base.version,
                **change.model_dump(mode="json", exclude_unset=True),
            }
            if change is not None
            else None,
            verdicts=verdicts,
            relabel_flags=flags,
            pending=pending,
            pending_after=tuple(p.period_id for p in self.pending.read()),
            closed_context=closed,
            effects=effects,
            episodic_created=sum(
                isinstance(edit, MemoryRecord)
                and edit.kind == "episodic"
                and edit.id == effect.produced_id
                for effect in effects
                for edit in effect.edits
            ),
            write=write,
        )
        cycle.disposition = reason or outcome
        self._last_record = self.journal.blob(json_bytes(record.model_dump(mode="json")))
        self.journal.fact(f"{self.period_id}:{cycle.started_tick}", "consolidation", record)
        return record

    def _archive(self, tick: int) -> str:
        context = self.context.freeze() if self.context else None
        archive = _ClosedPeriod(
            closed_tick=tick,
            last_delivery=self._last_delivery,
            log=self.log.checkpoint(),
            prefix=context.prefix if context else None,
            current_state=context.current_state if context else (),
        )
        return self.journal.blob(json_bytes(archive.model_dump(mode="json")))

    def _abandon(
        self,
        cycle: _Cycle,
        tick: int,
        reason: Literal["woken", "death"],
    ) -> ConsolidationRecord:
        if cycle.workflow:
            cycle.workflow.cancel(reason)
        closed = self._death_archive(tick) if reason == "death" else None
        retained = tuple(PendingState(p.period_id, "retained") for p in cycle.fixed.pending)
        return self._record(cycle, tick, "abandoned", reason, closed=closed, pending=retained)

    def _close(self, cycle: _Cycle, tick: int) -> ConsolidationRecord:
        flow = cycle.workflow
        outcome: Outcome
        reason: str | None = None
        write = None
        verdicts: tuple[Verdict, ...] = ()
        flags: tuple[RelabelFlag, ...] = ()
        effects: tuple[OperationEffects, ...] = ()
        states: tuple[PendingState, ...] = ()
        if flow is None:
            outcome = "off_arm"
            write = self.store.end_intention(tick=tick, turn_id=None)
        else:
            reason = flow.state.reason
            if reason is None:
                frozen_store = MemoryStore.from_snapshot(cycle.base, self.store.registry)
                staged = flow.staged(frozen_store, tick)
                verdicts = staged.verdicts
                try:
                    committed = commit_rebased(self.store, staged)
                except VersionConflict:
                    reason = "version"
                else:
                    write, flags, effects = (
                        committed.write,
                        committed.relabel_flags,
                        committed.effects,
                    )
            outcome = "failed" if reason else "committed"
            flow.publish()

        closed = self._archive(tick)
        if flow is not None:
            period = FrozenPeriod(
                cycle.fixed.period.prefix, self.log.entries, cycle.fixed.period.current_state
            )
            disposition = finish_pending(
                self.pending,
                PendingPeriod(cycle.base.owner_id, self.period_id, period),
                committed=outcome == "committed",
                sent_period_ids=flow.sent_pending_ids,
            )
            states = disposition.states
            if disposition.evicted is not None:
                self.journal.fact(
                    disposition.evicted.period_id,
                    "evicted",
                    _PeriodArchive(period=disposition.evicted.context),
                )
        record = self._record(
            cycle,
            tick,
            outcome,
            reason,
            closed=closed,
            write=write,
            verdicts=verdicts,
            flags=flags,
            effects=effects,
            pending=states,
        )
        self.number += 1
        self.log = PeriodLog(
            f"p:{cycle.base.owner_id}:{self.number}",
            self.journal,
            phenomena=self.phenomena,
            prior_awareness=self.log.awareness,
        )
        self.context = None
        self._changed = cycle.later_ids.copy()
        self._cycle = None
        if reason == "stopped_unfit":
            self._halt = "stopped_unfit"
        return record

    def deliver(
        self,
        delivery: FilteredDelivery,
        *,
        intents: Mapping[str, Intent] = MappingProxyType({}),
        agreements: Sequence[AgreementFact] = (),
    ) -> BoundaryResult:
        """A filtered living packet; intents are the coordinator's bound submissions."""
        with self._publication():
            return self._deliver(delivery, intents, agreements)

    def _deliver(
        self,
        delivery: FilteredDelivery,
        intents: Mapping[str, Intent],
        agreements: Sequence[AgreementFact],
    ) -> BoundaryResult:
        if self._halt:
            return BoundaryResult(self._halt)
        packet = delivery.packet
        if packet.observed_tick <= self.writer.checkpoint().tick:
            return BoundaryResult("delivered")
        tick = packet.observed_tick
        view = packet.perception
        cycle = self._cycle
        record = None
        if cycle is not None and cycle.disposition is None:
            if tick == cycle.s_tick + K:
                if cycle.workflow is not None and cycle.workflow.state.stage != "ready":
                    return BoundaryResult("waiting")
                record = self._close(cycle, tick)
            elif view.awareness == "awake":
                record = self._abandon(cycle, tick, "woken")

        prior = self.log.awareness
        entries = self.log.deliver(delivery)
        writes = self.writer.deliver(
            mechanical_delivery(delivery, entries, intents), agreements=agreements
        )
        changed = {edit.id for result in writes for edit in result.write.changes}
        self._changed.update(changed)
        if cycle is not None and cycle.disposition is None:
            cycle.later_ids.update(changed)
        receipt = PacketReceipt(
            period_id=self.period_id,
            delivery_id=packet.delivery_id,
            entries=tuple(entry.revision for entry in entries),
            writes=writes,
        )
        self.journal.fact(packet.delivery_id, "period_members", receipt)
        self._last_delivery = packet.delivery_id

        if prior == "awake" and self.context is not None:
            if view.awareness == "unconscious":
                self._confirm(tick, tick, packet.delivery_id, self.context)
            elif view.awareness == "asleep" and (running := view.running_action) is not None:
                start = running.tick_started
                if (
                    tick == start + 1
                    and cast(int, intents[running.intent_id].params["duration_ticks"]) >= K
                ):
                    self._confirm(start, tick, packet.delivery_id, self.context)
        return BoundaryResult(self._halt or "delivered", record, entries, writes)

    def _death_archive(self, tick: int) -> str:
        closed = self._archive(tick)
        self.journal.fact(self.period_id, "death", _Death(tick=tick, closed_context=closed))
        return closed

    def death(self, tick: int) -> BoundaryResult:
        """Called for a committed world death before any survivor K delivery."""
        with self._publication():
            if self._halt:
                return BoundaryResult(self._halt)
            record = None
            if self._cycle and self._cycle.disposition is None:
                record = self._abandon(self._cycle, tick, "death")
            else:
                self._death_archive(tick)
            self.context = None
            self._halt = "dead"
            return BoundaryResult("dead", record)

    def checkpoint(self) -> PeriodCheckpoint:
        self._require_completed_boundary()
        context = self.context.freeze() if self.context else None
        return PeriodCheckpoint(
            store=StoreImage.capture(self.store.snapshot),
            memory_on=self.memory_on,
            number=self.number,
            log=self.log.checkpoint(),
            prefix=context.prefix if context else None,
            current_state=context.current_state if context else (),
            writer=self.writer.checkpoint(),
            changed_ids=tuple(sorted(self._changed)),
            pending=self.pending.read(),
            attempt=self._cycle.checkpoint() if self._cycle else None,
            last_delivery=self._last_delivery,
            last_record=self._last_record,
            halt=self._halt,
        )

    @classmethod
    def restore(
        cls,
        checkpoint: PeriodCheckpoint,
        journal: Journal,
        *,
        registry: KindRegistry | None = None,
        phenomena: Mapping[str, str] = MappingProxyType({}),
    ) -> Self:
        registry = registry or KindRegistry()
        store = MemoryStore.from_snapshot(checkpoint.store.restore(registry), registry)
        result = cls.__new__(cls)
        result.store, result.journal = store, journal
        result.phenomena, result.memory_on = phenomena, checkpoint.memory_on
        result.number = checkpoint.number
        result.log = PeriodLog.restore(checkpoint.log, journal, phenomena)
        result.context = checkpoint.working_context(result.log)
        result.writer = MechanicalWriter(store, restored=checkpoint.writer)
        result.pending = PendingPeriods(store.snapshot.owner_id)
        for pending in checkpoint.pending:
            result.pending.append(pending)
        result._changed = set(checkpoint.changed_ids)
        result._last_delivery, result._last_record = (
            checkpoint.last_delivery,
            checkpoint.last_record,
        )
        result._halt = checkpoint.halt
        result._publishing = False
        result._cycle = None
        if (attempt := checkpoint.attempt) is not None:
            base = attempt.base.restore(registry)
            fixed = FixedInput(
                attempt.frozen,
                attempt.pending,
                base.resident(memory_on=result.memory_on),
                base.version,
                frozenset(attempt.mechanical_ids),
            )
            flow = Workflow.resume(fixed, attempt.workflow, journal) if attempt.workflow else None
            result._cycle = _Cycle(
                attempt.s_tick,
                attempt.started_tick,
                attempt.confirming_delivery,
                fixed,
                base,
                flow,
                set(attempt.later_ids),
                attempt.disposition,
            )
        return result


class _PeriodArchive(Fact):
    period: FrozenPeriod


class _ClosedPeriod(Fact):
    closed_tick: int
    last_delivery: str | None
    log: LogState
    prefix: FrozenPrefix | None
    current_state: tuple[Part, ...]


class _Death(Fact):
    tick: int
    closed_context: str
