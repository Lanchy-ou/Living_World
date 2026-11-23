"""Mix standalone policies and one resident loop on a single Runner boundary."""

from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from living_island.agents.v2.calls.journal import Fact
from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery, OwnSpeech
from living_island.agents.v2.context.dialogue import DialogueSession
from living_island.agents.v2.context.state import NotificationClass
from living_island.memory.v2.mechanical import AgreementFact
from living_island.persistence.v2.journal import PacketJournal
from living_island.sim.v2.compat.policy_host import (
    ModelBoundary,
    PolicyHost,
    PolicySession,
    UseFallback,
)
from living_island.sim.v2.harness.agreement_facts import project_agreement_facts
from living_island.sim.v2.harness.consolidation.checkpoint import PeriodCheckpoint
from living_island.sim.v2.harness.loop import DecisionRecord, ResidentLoop
from living_island.sim.v2.manifest import FallbackTurn, StopRecord, TerminalStop
from living_island.sim.v2.turns import TurnRequest
from living_island.world.v2 import protocol as wap
from living_island.world.v2.engine import TickResult, World


class ResidentPolicyHost(PolicyHost):
    def reset_period(self, memory_on: bool) -> None:
        # Live intent bindings still filter a delayed private outcome at wake.
        self._state = self._state.model_copy(
            update={
                "queue": (),
                "policy_state": self._state.policy_state if memory_on else None,
                "deferred": (),
                "boundary_results": (),
            }
        )


def filtered_delivery(
    raw: wap.BoundaryDelivery,
    model: ModelBoundary,
    intents: Mapping[str, wap.Intent],
    spoken: wap.Utterance | None,
) -> FilteredDelivery:
    # Runner retains the neutral reason. Only reports with resident-visible members
    # are needed by the recipe and day-log projections.
    reports = [r for r in model.reports if isinstance(r, wap.WorldReport)]
    positions = {(r.kind, r.subject_id): i for i, r in enumerate(raw.reports)}
    slots = {f.intent_id: i for i, f in enumerate(raw.perception.action_feedback)}
    sources = {
        f.intent_id: FeedbackSource(
            intents[f.intent_id].verb or intents[f.intent_id].action, slots[f.intent_id]
        )
        for f in model.perception.action_feedback
    }
    feedback = model.perception.last_utterance_feedback
    return FilteredDelivery(
        raw.model_copy(update={"perception": model.perception, "reports": reports}),
        sources,
        OwnSpeech(feedback, spoken) if feedback is not None and spoken is not None else None,
        tuple(positions[r.kind, r.subject_id] for r in reports),
    )


def clock_words(world: World) -> str:
    hour, minute = divmod(world.state.clock.minute_at(world.tick), 60)
    return f"{hour:02}:{minute:02}"


class Incomplete(Fact):
    status: Literal["incomplete"] = "incomplete"
    reason: str
    tick: int


class ResidentContinuation(Fact):
    """Resident state beside PolicySession's adapter states at a completed boundary."""

    period: PeriodCheckpoint
    dialogue: tuple[DialogueSession, ...]
    muted: tuple[NotificationClass, ...]
    awake_ticks: int
    intents: dict[str, wap.Intent]
    spoken: wap.Utterance | None
    agreements: tuple[AgreementFact, ...]
    incomplete: Incomplete | None


class _PeriodStop(Exception):
    """A confirmed period can stop the run even without an eligible turn."""


class ResidentSession(PolicySession):
    def __init__(
        self,
        world: World,
        hosts: Mapping[str, PolicyHost],
        journal: PacketJournal,
        resident: ResidentLoop,
        model_host: ResidentPolicyHost,
        *,
        stop_file: Path | None = None,
    ) -> None:
        self.resident = resident
        self.actor = resident.period.store.snapshot.owner_id
        self.model_host = model_host
        super().__init__(world, {**hosts, self.actor: model_host}, journal)
        self.intents: dict[str, wap.Intent] = {}
        self._finished: tuple[str, ...] = ()
        self.spoken: wap.Utterance | None = None
        self.agreements: tuple[AgreementFact, ...] = ()
        self.request: TurnRequest | None = None
        self.records: list[DecisionRecord] = []
        self.stop_file = stop_file
        self.stop_requested = False
        self.incomplete: Incomplete | None = None

    def continuation(self) -> ResidentContinuation:
        return ResidentContinuation(
            period=self.resident.period.checkpoint(),
            dialogue=self.resident.dialogue.sessions,
            muted=self.resident.muted,
            awake_ticks=self.resident.awake_ticks,
            intents=self.intents,
            spoken=self.spoken,
            agreements=self.agreements,
            incomplete=self.incomplete,
        )

    def _deliver(self, packet: wap.BoundaryDelivery) -> bool:
        if packet.actor_id != self.actor:
            return super()._deliver(packet)
        self.model_host.ingest(packet)
        delivery = filtered_delivery(
            packet, self.model_host.model_packet(packet), self.intents, self.spoken
        )
        period = self.resident.period
        number = period.number
        notified = self.resident.deliver(delivery, self.intents, self.agreements)
        self._finished = tuple(feedback.intent_id for feedback in packet.perception.action_feedback)
        if period.number != number:
            self.model_host.reset_period(period.memory_on)
        if self.resident.stopped:
            raise _PeriodStop
        return notified

    def _choose(self, request: TurnRequest) -> wap.TurnSubmission | FallbackTurn | TerminalStop:
        if request.delivery.actor_id != self.actor:
            return super()._choose(request)
        self.request = request
        choice = self.resident.decide(
            request.turn_id,
            request.reasons,
            clock_words(self.world),
            frozenset(
                key
                for key in self.resident.delivery.feedback_sources
                if self.intents[key].action == "act"
            ),
        )
        if isinstance(choice, TerminalStop):
            return choice
        if isinstance(choice, UseFallback):
            proposal = self.model_host.propose(request, self.world.run_id, fallback=True)
            self._staged[self.actor] = proposal
            return FallbackTurn(
                proposal.submission, choice.reason, self.model_host.config.policy_id
            )
        proposal = self.model_host.resume_model(request, self.world.run_id, choice)
        self._staged[self.actor] = proposal
        return proposal.submission

    def _stop(self, reason: str) -> None:
        self.incomplete = Incomplete(reason=reason, tick=self.world.tick)
        self.resident.period.journal.fact(self.world.run_id, "incomplete", self.incomplete)

    def advance(self) -> TickResult | None:
        if self.incomplete:
            return None
        self.request = None
        try:
            result = super().advance()
        except _PeriodStop:
            self._stop("stopped_unfit")
            return None
        request = self.request
        if result is None:
            if request is not None:
                self.records.append(
                    self.resident.publish(request.turn_id, request.reasons, None, None)
                )
            stop = cast(StopRecord, self.runner.manifest.stop)
            self._stop(stop.stop.reason)
            return None
        boundary = self.runner.manifest.boundaries[-1]
        self.agreements = project_agreement_facts(result.events, self.actor)
        for intent_id in self._finished:
            del self.intents[intent_id]
        self._finished = ()
        self.spoken = None
        if request is not None:
            submission = self._staged[self.actor].submission
            fallback = next(iter(boundary.fallback_turns), None)
            self.records.append(
                self.resident.publish(request.turn_id, request.reasons, submission, fallback)
            )
            if submission.action.kind == "intent":
                intent = submission.action.intent
                self.intents[intent.intent_id] = intent
            self.spoken = submission.utterance
        if not self.world.state.residents[self.actor].alive:
            self.resident.period.death(self.world.tick)
        if self.stop_requested or (self.stop_file and self.stop_file.exists()):
            self._stop("operator_stop")
        return result
