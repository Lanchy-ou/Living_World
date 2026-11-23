"""Drive one resident from a filtered delivery to a staged model decision."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import Literal, cast

from living_island.agents.v2.calls.contracts import ActStep, MorningIDs, SetIntention
from living_island.agents.v2.calls.guard import Call, Prepared, Ref
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.agents.v2.context.delivery import FilteredDelivery
from living_island.agents.v2.context.dialogue import DialogueState
from living_island.agents.v2.context.entries import DayEntry
from living_island.agents.v2.context.prefix import (
    FrozenPrefix,
    MorningStop,
    ResidentIdentity,
    VerbDescription,
    open_prefix,
)
from living_island.agents.v2.context.state import (
    CurrentState,
    NotificationClass,
    TurnReason,
    render_current_state,
)
from living_island.agents.v2.decision.caller import Caller, ResidentReply
from living_island.agents.v2.decision.notifications import notifications
from living_island.agents.v2.recall.attribution import bind_adopted_act, store_credit
from living_island.agents.v2.recall.recipes import RecipeCues, RecipeRegistry
from living_island.agents.v2.recall.sequence import RecallTurn, run_recall_turn
from living_island.memory.v2.mechanical import AgreementFact
from living_island.memory.v2.profiles import TraitValues
from living_island.memory.v2.projections import ResidentView, RevisionRef
from living_island.memory.v2.records import Observed, Personality
from living_island.memory.v2.store import DecisionDispatch, MemoryStore, StoreWrite
from living_island.sim.v2.compat.policy_host import UseFallback
from living_island.sim.v2.harness.consolidation.coordinator import PeriodCoordinator
from living_island.sim.v2.harness.consolidation.workflow import Workflow
from living_island.sim.v2.manifest import FallbackTurn, TerminalStop
from living_island.world.v2 import protocol as wap


class StageTelemetry(Fact):
    call_id: str
    full_tokens: int
    pressure_band: str
    pressure_text: str
    omitted: tuple[Ref, ...]


class Telemetry(Fact):
    delivery_id: str
    awake_ticks: int
    fatigue_band: wap.NeedBand | None
    stages: tuple[StageTelemetry, ...]


class UsedRevision(Fact):
    record_id: str
    revision: RevisionRef
    call_id: str
    before_version: int
    after_version: int


class CitedPart(Fact):
    id: str
    act_call_id: str
    sent_part_sha256: str
    revision: str | None


class FallbackRecord(Fact):
    used: bool
    policy_id: str | None
    reason: str | None


class DecisionRecord(Fact):
    record_schema: Literal["dr/0.1"] = "dr/0.1"
    turn_id: str
    resident_id: str
    tick: int
    period_id: str
    reasons: tuple[TurnReason, ...]
    telemetry: Telemetry
    call_ids: tuple[str, ...]
    prepared_cursors: tuple[str, ...]
    new_entries: tuple[str, ...]
    output: ActStep | None
    valid_cites: tuple[str, ...]
    invalid_cites: tuple[str, ...]
    cited_parts: tuple[CitedPart, ...]
    use_updates: tuple[UsedRevision, ...]
    used_memories: tuple[str, ...]
    origin: Literal["model", "fallback"] | None
    fallback: FallbackRecord
    submission: wap.TurnSubmission | None


@dataclass
class ResidentLoop:
    identity: ResidentIdentity
    verbs: tuple[VerbDescription, ...]
    period: PeriodCoordinator
    dialogue: DialogueState
    caller: Caller
    recipes: RecipeRegistry = field(default_factory=RecipeRegistry)
    muted: tuple[NotificationClass, ...] = ()
    awake_ticks: int = 0
    delivery: FilteredDelivery = field(init=False)
    entries: tuple[DayEntry, ...] = ()
    classes: frozenset[NotificationClass] = frozenset()
    staged: RecallTurn | None = None
    stopped: TerminalStop | None = None
    use_updates: list[UsedRevision] = field(default_factory=list)

    def credit(
        self, batch: DecisionDispatch, publish: Callable[[StoreWrite], None]
    ) -> StoreWrite | None:
        write = store_credit(self.period.store)(batch, publish)
        if write is not None:
            self.use_updates.extend(
                UsedRevision(
                    record_id=ref.id,
                    revision=ref,
                    call_id=batch.call_id,
                    before_version=write.before_version,
                    after_version=write.after_version,
                )
                for ref in write.credited
            )
        return write

    @classmethod
    def start(
        cls,
        *,
        resident_id: str,
        identity: ResidentIdentity,
        verbs: tuple[VerbDescription, ...],
        journal: Journal,
        memory_on: bool,
        gap_ticks: int,
        phenomena: Mapping[str, str],
        caller: Caller,
    ) -> "ResidentLoop":
        store = MemoryStore(resident_id)
        identity.profile.initialize(store)
        period_id = f"p:{resident_id}:1"
        prefix = open_prefix(
            call=Call(
                call_id=f"{period_id}:opening", period_id=period_id, resident_id=resident_id, tick=0
            ),
            identity=identity,
            verbs=verbs,
            traits=identity.profile.document.traits,
            view=store.snapshot.resident(memory_on=memory_on),
            store_version=store.snapshot.version,
            memory_on=memory_on,
            waking=CurrentState((), 0),
            journal=journal,
            select=lambda _: None,
        )
        period = PeriodCoordinator(
            store, journal, cast(FrozenPrefix, prefix), memory_on=memory_on, phenomena=phenomena
        )
        return cls(identity, verbs, period, DialogueState(resident_id, gap_ticks), caller)

    def memory(self) -> tuple[int, ResidentView]:
        snapshot = self.period.store.snapshot
        return snapshot.version, snapshot.resident(memory_on=self.period.memory_on)

    def deliver(
        self,
        delivery: FilteredDelivery,
        intents: Mapping[str, wap.Intent],
        agreements: tuple[AgreementFact, ...],
    ) -> bool:
        period = self.period
        packet = delivery.packet
        prior = period.log.awareness
        result = period.deliver(delivery, intents=intents, agreements=agreements)
        if result.status == "waiting":
            flow = cast(Workflow, period.workflow)
            while flow.state.stage != "ready":
                seconds = flow.advance(self.caller.transport, self.caller.clock)
                if seconds:
                    self.caller.delay(seconds)
            result = period.deliver(delivery, intents=intents, agreements=agreements)
        self.delivery, self.entries = delivery, result.entries
        if result.status == "stopped_unfit":
            self.stopped = TerminalStop("stopped_unfit", packet.delivery_id)
        closed = result.record is not None and result.record.outcome != "abandoned"
        if closed:
            self.dialogue.end_period()
        self.dialogue.receive(delivery)
        self.awake_ticks = (
            self.awake_ticks + int(packet.observed_tick > 0)
            if (prior == "awake" and packet.perception.awareness == "awake")
            else 0
        )
        if packet.perception.running_action is None or closed:
            self.muted = ()
        self.classes = notifications(packet.reports, self.muted)
        return bool(self.classes)

    def decide(
        self,
        turn_id: str,
        reasons: tuple[TurnReason, ...],
        time_of_day: str,
        act_ids: frozenset[str],
    ) -> ActStep | UseFallback | TerminalStop:
        period = self.period
        journal = period.journal
        packet = self.delivery.packet
        running = packet.perception.running_action is not None
        dispatch = partial(self.caller.dispatch, running=running)
        version, view = self.memory()
        state = render_current_state(
            packet,
            reasons=reasons,
            time_of_day=time_of_day,
            mute=self.muted,
            intention=view.current_intention,
            dialogue=self.dialogue.sessions,
        )
        context = period.context
        if context is None:

            def select(prepared: Prepared) -> MorningIDs | None:
                return cast(MorningIDs | None, dispatch(prepared, journal).parsed)

            traits = self.identity.profile.document.traits
            if period.memory_on:
                personality = next(
                    r.record.content for r in view.live() if r.record.kind == "personality"
                )
                traits = TraitValues.model_construct(
                    None, **{t.trait_id: t.value for t in cast(Personality, personality).traits}
                )
            prefix = open_prefix(
                call=Call(
                    call_id=f"{period.period_id}:morning",
                    resident_id=packet.actor_id,
                    tick=packet.observed_tick,
                    period_id=period.period_id,
                ),
                identity=self.identity,
                verbs=self.verbs,
                traits=traits,
                view=view,
                store_version=version,
                memory_on=period.memory_on,
                waking=state,
                journal=journal,
                select=select,
            )
            if isinstance(prefix, MorningStop):
                return TerminalStop("stopped_unfit", prefix.prepared.cursor)
            context = period.open(prefix)
        if self.staged is None:
            cues = RecipeCues.from_delivery(
                self.delivery, reasons=frozenset((*reasons, *self.classes)), act_intent_ids=act_ids
            )
            self.staged = run_recall_turn(
                resident_id=packet.actor_id,
                turn_id=turn_id,
                cues=cues,
                recipes=self.recipes,
                context=context,
                state=state,
                memory_on=period.memory_on,
                read_memory=self.memory,
                journal=journal,
                dispatch=dispatch,
                credit=self.credit,
            )
        stage = self.staged.stages[-1]
        if stage.returned is None:
            return TerminalStop("stopped_unfit", stage.prepared.cursor)
        if (error := stage.returned.terminal.error_class) is not None:
            return UseFallback(error)
        return cast(ActStep, stage.returned.parsed)

    def publish(
        self,
        turn_id: str,
        reasons: tuple[TurnReason, ...],
        submission: wap.TurnSubmission | None,
        fallback: FallbackTurn | None,
    ) -> DecisionRecord:
        packet = self.delivery.packet
        tick = packet.observed_tick
        period = self.period
        stages = self.staged.stages if self.staged else ()
        added = [*self.entries, *(self.staged.entries if self.staged else ())]
        citations = None
        output = None
        origin: Literal["model", "fallback"] | None = None
        if fallback is not None:
            origin = "fallback"
            if fallback.submission.action.kind == "intent":
                self.muted = ()
        elif submission is not None:
            origin = "model"
            returned = cast(ResidentReply, stages[-1].returned)
            output = cast(ActStep, returned.parsed)
            citations = bind_adopted_act(returned, period.log.entries, period.journal)
            response = cast(DayEntry, period.log.response(tick, turn_id, returned.response_text))
            added.append(response)
            if output.action.kind == "intent":
                self.muted = tuple(output.mute)
            if isinstance(output.intention, SetIntention):
                period.store.set_intention(
                    turn_id=turn_id,
                    tick=tick,
                    text=output.intention.set,
                    source=Observed(entry_id=response.id),
                )
            elif output.intention is not None:
                period.store.end_intention(tick=tick, turn_id=turn_id)
        telemetry = []
        for stage in stages:
            prepared = stage.prepared.record
            full = prepared.candidates[0].manifest
            for pressure in full.derived:
                index = prepared.admitted_candidate
                candidate = prepared.candidates[
                    prepared.floor_candidate if index is None else index
                ]
                telemetry.append(
                    StageTelemetry(
                        call_id=prepared.call.call_id,
                        full_tokens=full.tokens_total,
                        pressure_band=pressure.band,
                        pressure_text=pressure.text,
                        omitted=candidate.omitted,
                    )
                )
        record = DecisionRecord(
            turn_id=turn_id,
            resident_id=packet.actor_id,
            tick=tick,
            period_id=period.period_id,
            reasons=reasons,
            telemetry=Telemetry(
                delivery_id=packet.delivery_id,
                awake_ticks=self.awake_ticks,
                stages=tuple(telemetry),
                fatigue_band=next(
                    (n.band for n in packet.perception.needs if n.need_id == "mental_fatigue"), None
                ),
            ),
            call_ids=tuple(s.prepared.record.call.call_id for s in stages),
            prepared_cursors=tuple(s.prepared.cursor for s in stages),
            new_entries=tuple(e.id for e in added),
            valid_cites=tuple(c.id for c in citations.valid) if citations else (),
            invalid_cites=citations.invalid if citations else (),
            cited_parts=tuple(
                CitedPart(
                    id=c.id,
                    act_call_id=citations.call_id,
                    sent_part_sha256=f.sha256,
                    revision=f.source.version,
                )
                for c in citations.valid
                for f in c.fragments
            )
            if citations
            else (),
            use_updates=tuple(self.use_updates),
            used_memories=tuple(u.record_id for u in self.use_updates),
            output=output,
            origin=origin,
            fallback=FallbackRecord(
                used=fallback is not None,
                policy_id=fallback.policy_id if fallback else None,
                reason=fallback.reason if fallback else None,
            ),
            submission=submission,
        )
        period.journal.fact(turn_id, "decision", record)
        self.staged = None
        self.use_updates.clear()
        return record
