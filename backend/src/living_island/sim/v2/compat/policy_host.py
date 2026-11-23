"""Run the frozen policy behind the v2 coordinator, with private checkpoints."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import JsonValue

from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.runtime import Runtime
from living_island.agents.types import (
    DecisionRecord,
    DecisionRequest,
    OkOutcome,
    OwnProfile,
    PolicyConfig,
    ResidentRuntimeState,
    RuleStateV0_1,
)
from living_island.persistence.v2.journal import PacketJournal
from living_island.sim.decisions import decision_record
from living_island.world import protocol as v1
from living_island.world.v2 import protocol as v2
from living_island.world.v2.engine import TickResult, World
from living_island.world.v2.rules.schema import canonical_json_bytes

from ..manifest import FallbackTurn, TerminalStop
from ..runner import Runner
from ..turns import TurnRequest
from .adapters import adapt_intent, project_perception
from .bridge import LegacyBridge, legacy_result, visible_result
from .receipts import LegacyReceipts, interrupt_reason, observed_triggers

type PolicyFactory = Callable[[PolicyConfig, RuleStateV0_1 | None], RuleBasedPolicy]


class _Issued(v2.ProtocolModel):
    intent: v1.ActionIntent
    started: int
    suppressed_talk: bool


class PolicyCheckpoint(v2.ProtocolModel):
    """Sim-private data for one resident. Serialize beside the world snapshot."""

    cursor: int = -1
    last_decision_tick: int = -1
    ordinal: int = 0
    policy_state: RuleStateV0_1 | None = None
    receipts: LegacyReceipts = LegacyReceipts()
    queue: tuple[v1.ActionIntent, ...] = ()
    deferred: tuple[v1.DecisionTrigger, ...] = ()
    issued: dict[str, _Issued] = {}
    handled_stops: tuple[str, ...] = ()
    pending_bridge: dict[str, v1.ActionResult | None] = {}
    boundary_results: tuple[v1.ActionResult, ...] = ()
    boundary_triggers: tuple[v1.DecisionTrigger, ...] = ()
    boundary_private_ids: tuple[str, ...] = ()
    terminal_results: tuple[v1.ActionResult, ...] = ()


def restore_policies(data: Mapping[str, v2.IntegerJson]) -> dict[str, PolicyCheckpoint]:
    """Decode the private policy state from an EN-07 checkpoint."""
    return {
        actor: PolicyCheckpoint.model_validate_json(canonical_json_bytes(state))
        for actor, state in data.items()
    }


def _ordered(triggers: set[v1.DecisionTrigger]) -> tuple[v1.DecisionTrigger, ...]:
    return tuple(trigger for trigger in v1.DECISION_TRIGGERS if trigger in triggers)


@dataclass(frozen=True)
class PolicyDecisionTrace:
    record: DecisionRecord
    scheduling_marker: Literal["native_fallback"] | None


@dataclass(frozen=True)
class _Decision:
    trace: PolicyDecisionTrace
    state: RuleStateV0_1


@dataclass(frozen=True)
class _Proposal:
    submission: v2.TurnSubmission
    decision: _Decision | None
    intent: v1.ActionIntent | None
    queue: tuple[v1.ActionIntent, ...]
    suppressed_talk: bool = False
    replaces: str | None = None
    model_resumed: bool = False
    legacy_stop: v1.ActionResult | None = None


@dataclass(frozen=True)
class _LegacyPlanner:
    """Adapt only the call to the frozen rule-based planner."""

    policy: RuleBasedPolicy
    feedback: v1.ActionFeedback | None

    @property
    def policy_id(self) -> str:
        return self.policy.policy_id

    def decide(self, request: DecisionRequest) -> OkOutcome:
        if self.feedback is not None:
            # CR-P3.5-PR-06-B3: the frozen planner reads feedback only from this
            # typed slot. Runtime.decide gives the planner a private request.
            # Detach the injected feedback from the host's checkpoint data.
            context = request.context
            private_view = context.perception.model_copy(
                update={"last_action_feedback": self.feedback.model_copy(deep=True)}
            )
            private_context = context.model_copy(update={"perception": private_view})
            request = request.model_copy(update={"context": private_context})
        return self.policy.decide(request)

    def finish_decision(self, accepted: bool) -> None:
        self.policy.finish_decision(accepted)

    def export_state(self) -> dict[str, JsonValue]:
        return self.policy.export_state()


class NeutralActionEnd(v2.ProtocolModel):
    kind: Literal["action_ended"] = "action_ended"
    subject_id: None = None


class ModelBoundary(v2.ProtocolModel):
    """Consumer view. A fallback end can schedule without identifying a result."""

    delivery_id: str
    actor_id: str
    observed_tick: v2.Tick
    perception: v2.Perception
    reports: list[v2.WorldReport | NeutralActionEnd]


class PolicyHost:
    """Own one actor's v1 policy and translation state inside sim."""

    def __init__(
        self,
        config: PolicyConfig,
        profile: OwnProfile,
        sleep_ticks: int,
        *,
        bridge: LegacyBridge | None = None,
        restored: PolicyCheckpoint | None = None,
        policy_factory: PolicyFactory = RuleBasedPolicy,
    ) -> None:
        self.config = config
        self._profile = profile
        self._sleep_ticks = sleep_ticks
        self.bridge = bridge
        self._factory = policy_factory
        self._state = PolicyCheckpoint() if restored is None else restored.model_copy(deep=True)
        self._view: v1.Perception | None = None
        self.decision_trace: list[PolicyDecisionTrace] = []

    @property
    def decision_records(self) -> list[DecisionRecord]:
        return [entry.record for entry in self.decision_trace]

    def checkpoint(self) -> PolicyCheckpoint:
        return self._state.model_copy(deep=True)

    def ingest(self, packet: v2.BoundaryDelivery) -> None:
        """Consume a journal-verified packet and retain its observed trigger bits."""
        state = self._state
        if packet.observed_tick < state.cursor:
            return
        if packet.observed_tick == state.cursor:
            if self._view is None:
                self._view = project_perception(packet.perception)
            return
        view = project_perception(packet.perception)
        receipts, novel = state.receipts.ingest(view)
        current = observed_triggers(packet, view, novel)
        queue = state.queue
        issued, pending = dict(state.issued), dict(state.pending_bridge)
        handled = set(state.handled_stops)
        results = []
        private_ids = set()
        for feedback in packet.perception.action_feedback:
            intent_id = feedback.intent_id
            if intent_id in handled:
                handled.remove(intent_id)
                private_ids.add(intent_id)
                continue
            binding = issued.pop(intent_id, None)
            if binding is None:
                continue
            private_ids.add(intent_id)
            if self.bridge is None:
                result = visible_result(
                    binding.intent,
                    binding.started,
                    packet.observed_tick,
                    feedback,
                    packet.perception.last_utterance_feedback,
                    suppressed=binding.suppressed_talk,
                )
            else:
                result = pending.pop(intent_id)
            if result is not None:
                results.append(result)
            if result is None or result.status == "interrupted":
                current.add("ACTION_INTERRUPTED")
                queue = ()
            elif result.status == "failure":
                current.add("ACTION_FAILED")
                queue = ()
            elif not queue:
                current.add("PLAN_FINISHED")

        self._state = state.model_copy(
            update={
                "cursor": packet.observed_tick,
                "receipts": receipts,
                "queue": queue,
                "deferred": _ordered(set(state.deferred) | current),
                "issued": issued,
                "handled_stops": tuple(sorted(handled)),
                "pending_bridge": pending,
                "boundary_results": tuple(results),
                "boundary_triggers": _ordered(current),
                "boundary_private_ids": tuple(sorted(private_ids)),
            }
        )
        self._view = view

    def interruption(self, packet: v2.BoundaryDelivery) -> v1.InterruptionReason | None:
        running = packet.perception.running_action
        if packet.perception.awareness != "awake" or running is None:
            return None
        binding = self._state.issued.get(running.intent_id)
        if binding is None:
            return None
        return interrupt_reason(binding.intent.action_type, set(self._state.boundary_triggers))

    def model_packet(self, packet: v2.BoundaryDelivery) -> ModelBoundary:
        """The model and its memory consumers receive only their allowed public data."""
        state = self._state
        private = {*state.boundary_private_ids, *state.issued, *state.handled_stops}
        view = packet.perception
        running = view.running_action
        running_id = running.intent_id if running is not None else None
        if running is not None and running_id in private:
            running = running.model_copy(update={"start_target": None, "items": []})
        reports: list[v2.WorldReport | NeutralActionEnd] = []
        for report in packet.reports:
            if report.subject_id in private:
                if report.kind == "action_ended":
                    reports.append(NeutralActionEnd())
                    continue
                if report.kind == "action_observed" or (
                    report.kind == "progress_step" and report.subject_id != running_id
                ):
                    continue
            reports.append(report)
        # ProtocolModel revalidates the supplied view and builds consumer-owned lists.
        return ModelBoundary(
            delivery_id=packet.delivery_id,
            actor_id=packet.actor_id,
            observed_tick=packet.observed_tick,
            perception=view.model_copy(
                update={
                    "action_feedback": [
                        entry for entry in view.action_feedback if entry.intent_id not in private
                    ],
                    "observed_actions": [
                        entry for entry in view.observed_actions if entry.intent_id not in private
                    ],
                    "running_action": running,
                }
            ),
            reports=reports,
        )

    def _decision(
        self,
        packet: v2.BoundaryDelivery,
        run_id: str,
        *,
        fallback: bool = False,
        legacy_stop: v1.ActionResult | None = None,
    ) -> _Decision:
        state = self._state
        view = cast(v1.Perception, self._view)
        result = legacy_stop or (state.boundary_results[-1] if state.boundary_results else None)
        tick = packet.observed_tick
        policy = self._factory(self.config, state.policy_state)
        runtime = Runtime(
            packet.actor_id,
            self.config,
            self._profile,
            _LegacyPlanner(policy, None if result is None else result.visible_feedback),
            ResidentRuntimeState.model_construct(
                actor_id=packet.actor_id,
                policy_config=self.config,
                next_decision_ordinal=state.ordinal,
                policy_state=policy.export_state(),
                latest_perception_tick=tick - 1,
            ),
        )
        triggers = list(state.deferred) if tick else []
        if legacy_stop is not None:
            triggers = list(_ordered({*triggers, "ACTION_INTERRUPTED"}))
        synthetic = fallback and tick != 0 and not triggers
        if synthetic:
            # CR-P3.5-PR-06: native scheduling can invoke fallback without a legacy action.
            triggers.append("PLAN_FINISHED")
        runtime.ingest(
            v1.BoundaryPerceptionDelivery(
                delivery_id=v1.format_delivery_id(run_id, tick, packet.actor_id),
                actor_id=packet.actor_id,
                observed_tick=tick,
                perception=view,
                decision_triggers=[],
            )
        )
        request = runtime.make_request(tick, triggers)
        record = decision_record(run_id, request, runtime.decide(request))
        runtime.commit_decision(record)
        trace = PolicyDecisionTrace(record, "native_fallback" if synthetic else None)
        return _Decision(trace, RuleStateV0_1.model_validate(policy.export_state()))

    def propose(self, request: TurnRequest, run_id: str, *, fallback: bool = False) -> _Proposal:
        state = self._state
        packet = request.delivery
        running = packet.perception.running_action
        legacy_stop = None
        if running is not None and (binding := state.issued.get(running.intent_id)) is not None:
            reason = self.interruption(packet)
            if reason is None:
                choice = v2.ModelTurn(action=v2.ContinueAction(kind="continue"), utterance=None)
                return _Proposal(request.bind(choice), None, None, state.queue)
            legacy_stop = legacy_result(
                binding.intent, binding.started, packet.observed_tick, reason=reason
            )
        queue, decision = state.queue, None
        if legacy_stop is not None or state.deferred or not queue:
            decision = self._decision(packet, run_id, fallback=fallback, legacy_stop=legacy_stop)
            queue = tuple(decision.trace.record.plan.intents)
        intent, *tail = queue
        choice = adapt_intent(intent, self._sleep_ticks)
        suppressed = fallback and intent.action_type == "talk"
        if suppressed:
            choice = choice.model_copy(update={"utterance": None})
            tail.clear()
        return _Proposal(
            request.bind(choice),
            decision,
            intent,
            tuple(tail),
            suppressed,
            running.intent_id if running is not None else None,
            legacy_stop=legacy_stop,
        )

    def resume_model(self, request: TurnRequest, run_id: str, choice: v2.ModelTurn) -> _Proposal:
        state = self._state
        running = request.delivery.perception.running_action
        if (
            choice.action.kind == "continue"
            and running is not None
            and running.intent_id in state.issued
        ):
            # A model turn abandons the fallback tail even when the action continues.
            return _Proposal(request.bind(choice), None, None, ())
        # Apply a fallback failure to the private policy state before dropping its tail.
        decision = None
        if any(result.status == "failure" for result in state.boundary_results):
            decision = self._decision(request.delivery, run_id)
        return _Proposal(
            request.bind(choice),
            decision,
            None,
            (),
            replaces=running.intent_id
            if running is not None and choice.action.kind == "intent"
            else None,
            model_resumed=True,
        )

    def commit(self, proposal: _Proposal) -> None:
        state = self._state
        issued, handled = dict(state.issued), set(state.handled_stops)
        if proposal.replaces is not None and issued.pop(proposal.replaces, None) is not None:
            handled.add(proposal.replaces)
        decision = proposal.decision
        if decision is not None:
            self.decision_trace.append(decision.trace)
            state = state.model_copy(
                update={
                    "ordinal": state.ordinal + 1,
                    "policy_state": decision.state,
                    "last_decision_tick": decision.trace.record.tick,
                    "deferred": (),
                }
            )
        if proposal.intent is not None:
            action = cast(v2.IntentAction, proposal.submission.action)
            issued[action.intent.intent_id] = _Issued(
                intent=proposal.intent,
                started=proposal.submission.observed_tick,
                suppressed_talk=proposal.suppressed_talk,
            )
        if proposal.legacy_stop is not None:
            state = state.model_copy(
                update={
                    "boundary_results": (*state.boundary_results, proposal.legacy_stop),
                    "boundary_triggers": _ordered({*state.boundary_triggers, "ACTION_INTERRUPTED"}),
                }
            )
        self._state = state.model_copy(
            update={
                "issued": issued,
                "queue": proposal.queue,
                "handled_stops": tuple(sorted(handled)),
                "deferred": () if proposal.model_resumed else state.deferred,
            }
        )

    def capture(
        self, result: v2.ActionResult, speech: v2.UtteranceFeedback | None, alive: bool
    ) -> None:
        """Capture only a bridge host's own authoritative result at world commit."""
        binding = self._state.issued.get(result.intent_id)
        if binding is None or self.bridge is None:
            return
        translated = self.bridge.translate(
            binding.intent,
            result,
            speech,
            suppressed=binding.suppressed_talk,
        )
        if not alive:
            if translated is not None:
                self._state = self._state.model_copy(
                    update={"terminal_results": (*self._state.terminal_results, translated)}
                )
            return
        self._state = self._state.model_copy(
            update={"pending_bridge": {**self._state.pending_bridge, result.intent_id: translated}}
        )

    def retire(self) -> None:
        self._state = self._state.model_copy(
            update={
                "queue": (),
                "deferred": (),
                "issued": {},
                "handled_stops": (),
                "pending_bridge": {},
            }
        )


@dataclass(frozen=True)
class UseFallback:
    reason: str


type ModelChoice = Callable[[ModelBoundary], v2.ModelTurn | UseFallback | TerminalStop]
type ModelDelivery = Callable[[ModelBoundary], bool]


class PolicySession:
    """Integrate private policy delivery and commits with the policy-neutral runner."""

    def __init__(
        self,
        world: World,
        hosts: Mapping[str, PolicyHost],
        journal: PacketJournal,
        *,
        model: ModelChoice | None = None,
        model_delivery: ModelDelivery | None = None,
    ) -> None:
        for host in hosts.values():
            if host.bridge is not None and host.bridge.pack_hash != world.state.library.pack_hash:
                raise ValueError("legacy bridge requires its admitted compatibility pack")
        self.world = world
        self._hosts = dict(hosts)
        self._bridged = {actor: host for actor, host in hosts.items() if host.bridge is not None}
        self._model = model
        self._model_delivery = model_delivery
        self._staged: dict[str, _Proposal] = {}
        self.runner = Runner(world, self._choose, deliver=self._deliver, journal=journal)

    def checkpoint(self) -> dict[str, v2.IntegerJson]:
        """Serialize the private state beside the next pending world delivery."""
        return {
            actor: host.checkpoint().model_dump(mode="json") for actor, host in self._hosts.items()
        }

    def _deliver(self, packet: v2.BoundaryDelivery) -> bool:
        host = self._hosts[packet.actor_id]
        host.ingest(packet)
        if self._model is None:
            return host.interruption(packet) is not None
        if self._model_delivery is None:
            return False
        return self._model_delivery(host.model_packet(packet))

    def _choose(self, request: TurnRequest) -> v2.TurnSubmission | FallbackTurn | TerminalStop:
        actor = request.delivery.actor_id
        host = self._hosts[actor]
        if self._model is None:
            proposal = host.propose(request, self.world.run_id)
            self._staged[actor] = proposal
            return proposal.submission
        choice = self._model(host.model_packet(request.delivery))
        if isinstance(choice, TerminalStop):
            return choice
        if isinstance(choice, UseFallback):
            proposal = host.propose(request, self.world.run_id, fallback=True)
            self._staged[actor] = proposal
            return FallbackTurn(proposal.submission, choice.reason, host.config.policy_id)
        proposal = host.resume_model(request, self.world.run_id, choice)
        self._staged[actor] = proposal
        return proposal.submission

    def advance(self) -> TickResult | None:
        self._staged.clear()
        result = self.runner.advance()
        if result is None:
            return None
        for actor, proposal in self._staged.items():
            self._hosts[actor].commit(proposal)
        if self._bridged:
            for action in result.actions:
                host = self._bridged.get(action.actor_id)
                if host is not None:
                    host.capture(
                        action,
                        result.utterances.get(action.actor_id),
                        self.world.state.residents[action.actor_id].alive,
                    )
        for actor, resident in self.world.state.residents.items():
            if not resident.alive:
                self._hosts[actor].retire()
        return result
