"""Resident-private observation and decision transactions (Agent Interface §2)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic_core import PydanticSerializationError

from living_island.agents.base import Policy, ResidentRuntime
from living_island.agents.policies.random_policy import RandomPolicy
from living_island.agents.policies.recorded import RecordedPolicy, ReplayDiverged, request_sha256
from living_island.agents.policies.scripted import ScriptedPolicy
from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.types import (
    ActorScript,
    DecisionContext,
    DecisionOutcome,
    DecisionRecord,
    DecisionRequest,
    ErrorOutcome,
    Goal,
    OwnProfile,
    PersonalityProfile,
    PolicyConfig,
    ResidentRuntimeState,
    RuleStateV0_1,
    build_intent_id,
    build_plan_id,
)
from living_island.world.protocol import (
    ActionPlan,
    BoundaryPerceptionDelivery,
    DecisionTrigger,
    Perception,
    format_delivery_id,
)


@runtime_checkable
class _TransactionalPolicy(Protocol):
    def finish_decision(self, accepted: bool) -> None: ...


def _validate_plan(plan: ActionPlan, request: DecisionRequest, limit: int) -> ActionPlan:
    if not isinstance(plan, ActionPlan):
        raise ValueError("policy must return an ActionPlan")
    # Revalidate nested shapes even if a policy bypassed model construction.
    plan = ActionPlan.model_validate(plan.model_dump(mode="json", warnings="error"))
    plan_id = build_plan_id(request.actor_id, request.decision_ordinal)
    if (plan.actor_id, plan.created_at_tick, plan.plan_id) != (
        request.actor_id,
        request.tick,
        plan_id,
    ):
        raise ValueError("plan actor, tick or ID does not match the request")
    if len(plan.intents) > limit:
        raise ValueError(f"plan exceeds the limit of {limit} intents")
    for index, intent in enumerate(plan.intents):
        if intent.intent_id != build_intent_id(plan_id, index):
            raise ValueError(f"invalid intent ID at index {index}")
    return plan


class Runtime:
    """Implements the frozen ResidentRuntime port; policies see only their request."""

    def __init__(
        self,
        actor_id: str,
        config: PolicyConfig,
        profile: OwnProfile,
        policy: Policy,
        restored_state: ResidentRuntimeState | None = None,
    ) -> None:
        if restored_state is not None and (
            restored_state.actor_id != actor_id or restored_state.policy_config != config
        ):
            raise ValueError(f"{actor_id}: restored actor or policy config mismatch")
        self._actor_id = actor_id
        self._config = config
        self._profile = profile
        self._policy = policy
        self._ordinal = restored_state.next_decision_ordinal if restored_state else 0
        self._latest_tick = restored_state.latest_perception_tick if restored_state else -1
        self._perception: Perception | None = None
        self._run_id: str | None = None
        self._decided_tick = -1
        self._request: DecisionRequest | None = None
        self._outcome: DecisionOutcome | None = None

    @property
    def actor_id(self) -> str:
        return self._actor_id

    def ingest(self, delivery: BoundaryPerceptionDelivery) -> None:
        if self._request is not None:
            raise ValueError(f"{self.actor_id}: decision still awaiting commitment")
        if delivery.actor_id != self.actor_id or delivery.perception.actor_id != self.actor_id:
            raise ValueError(f"{self.actor_id}: delivery belongs to another actor")
        tick = self._latest_tick + 1
        if delivery.observed_tick != tick or delivery.perception.tick != tick:
            raise ValueError(f"{self.actor_id}: expected consecutive delivery at tick {tick}")
        suffix = format_delivery_id("", tick, self.actor_id)
        run_id = (
            self._run_id if self._run_id is not None else delivery.delivery_id.removesuffix(suffix)
        )
        if not run_id or delivery.delivery_id != format_delivery_id(run_id, tick, self.actor_id):
            raise ValueError(f"{self.actor_id}: invalid delivery_id")
        self._perception = delivery.perception.model_copy(deep=True)
        self._latest_tick = tick
        self._run_id = run_id

    def make_request(self, tick: int, triggers: list[DecisionTrigger]) -> DecisionRequest:
        if self._request is not None or self._decided_tick == tick:
            raise ValueError(f"{self.actor_id}: only one decision per boundary")
        if self._perception is None or tick != self._latest_tick:
            raise ValueError(f"{self.actor_id}: no ingested perception for tick {tick}")
        if tick == 0 and triggers:
            raise ValueError("the tick-zero request must have no triggers")
        request = DecisionRequest(
            actor_id=self.actor_id,
            tick=tick,
            decision_ordinal=self._ordinal,
            triggers=triggers,
            context=DecisionContext(
                perception=self._perception.model_copy(deep=True),
                personality_profile=PersonalityProfile(
                    profile_id=self._profile.profile_id, values=[]
                ),
                current_goals=[
                    Goal(goal_id="initial", text=self._profile.initial_goal, priority=0)
                ],
                recalled_episodes=[],
                beliefs=[],
                current_plan_summary=None,
            ),
        )
        self._request = request.model_copy(deep=True)
        return request

    def decide(self, request: DecisionRequest) -> DecisionOutcome:
        if self._request is None or request != self._request or self._outcome is not None:
            raise ValueError(f"{self.actor_id}: expected the outstanding undecided request")
        outcome = self._policy.decide(request.model_copy(deep=True))
        if outcome.status == "ok":
            try:
                plan = _validate_plan(outcome.plan, request, self._config.max_plan_actions)
                outcome = outcome.model_copy(update={"plan": plan})
            except (ValueError, PydanticSerializationError) as exc:
                outcome = ErrorOutcome(
                    status="error",
                    policy_id=outcome.policy_id,
                    error_kind="INVALID_PLAN",
                    detail=str(exc),
                )
        if outcome.status == "replayed":
            try:
                source = outcome.source_record
                _validate_plan(source.plan, request, self._config.max_plan_actions)
                DecisionRecord.model_validate(source.model_dump(mode="json", warnings="error"))
            except (ValueError, PydanticSerializationError) as exc:
                outcome = ErrorOutcome(
                    status="error",
                    policy_id=outcome.policy_id,
                    error_kind="REPLAY_DIVERGED",
                    detail=str(exc),
                )
        self._outcome = outcome.model_copy(deep=True)
        return outcome

    def commit_decision(self, record: DecisionRecord) -> None:
        request, outcome = self._request, self._outcome
        if request is None or outcome is None:
            raise ValueError(f"{self.actor_id}: no decision to commit")
        if (
            record.actor_id != self.actor_id
            or record.run_id != self._run_id
            or record.decision_ordinal != self._ordinal
            or record.tick != request.tick
            or record.triggers != request.triggers
            or record.request_sha256 != request_sha256(request)
        ):
            raise ValueError(f"{self.actor_id}: decision record does not match its request")
        if outcome.status == "ok" and (
            record.status != "ok"
            or record.policy_id != outcome.policy_id
            or record.plan != outcome.plan
        ):
            raise ValueError(f"{self.actor_id}: decision record does not match the policy plan")
        if outcome.status == "error" and (
            record.status != "error"
            or record.policy_id != outcome.policy_id
            or record.error_kind != outcome.error_kind
        ):
            raise ValueError(f"{self.actor_id}: decision record does not match the policy error")
        if outcome.status == "replayed" and record != outcome.source_record:
            raise ValueError(f"{self.actor_id}: replay must preserve the original record")
        if isinstance(self._policy, _TransactionalPolicy):
            self._policy.finish_decision(outcome.status == "ok")
        elif isinstance(self._policy, ScriptedPolicy):
            self._policy.commit()
        self._ordinal += 1
        self._decided_tick = request.tick
        self._request = self._outcome = None

    def export_state(self) -> ResidentRuntimeState:
        if self._request is not None:
            raise ValueError(f"{self.actor_id}: cannot save an uncommitted decision")
        return ResidentRuntimeState(
            actor_id=self.actor_id,
            policy_config=self._config,
            next_decision_ordinal=self._ordinal,
            policy_state=self._policy.export_state(),
            latest_perception_tick=self._latest_tick,
        )


def create_runtime(
    actor_id: str,
    policy_config: PolicyConfig,
    own_profile: OwnProfile,
    own_script: ActorScript | None,
    own_records: Sequence[DecisionRecord] | None,
    restored_state: ResidentRuntimeState | None,
) -> ResidentRuntime:
    """Accept only the actor slice of inputs already verified by persistence."""
    if restored_state is not None and (
        restored_state.actor_id != actor_id or restored_state.policy_config != policy_config
    ):
        raise ValueError(f"{actor_id}: restored actor or policy config mismatch")
    policy: Policy
    match policy_config.policy_id:
        case "random-v0":
            if own_script is not None or own_records is not None:
                raise ValueError(f"{actor_id}: random policy takes neither a script nor records")
            policy = RandomPolicy(policy_config)
        case "rule-based-v0":
            if own_script is not None or own_records is not None:
                raise ValueError(
                    f"{actor_id}: rule-based policy takes neither a script nor records"
                )
            state = (
                RuleStateV0_1.model_validate(restored_state.policy_state)
                if restored_state is not None
                else None
            )
            policy = RuleBasedPolicy(state)
        case "scripted-v0":
            if own_script is None or own_script.actor_id != actor_id or own_records is not None:
                raise ValueError(f"{actor_id}: scripted policy requires its own actor script")
            if any(len(plan) > policy_config.max_plan_actions for plan in own_script.plans):
                raise ValueError(f"{actor_id}: script exceeds the plan action limit")
            cursor = 0
            if restored_state is not None:
                saved_cursor = restored_state.policy_state.get("cursor")
                expected = min(restored_state.next_decision_ordinal, len(own_script.plans))
                if type(saved_cursor) is not int or saved_cursor != expected:
                    raise ValueError(
                        f"{actor_id}: restored script cursor does not match its ordinal"
                    )
                cursor = saved_cursor
            policy = ScriptedPolicy(own_script, cursor)
        case "recorded-v0":
            if own_records is None or own_script is not None:
                raise ReplayDiverged(f"{actor_id}: recorded policy requires its own actor records")
            if restored_state is not None and restored_state.next_decision_ordinal > len(
                own_records
            ):
                raise ReplayDiverged(f"{actor_id}: restored ordinal exceeds source records")
            policy = RecordedPolicy(actor_id, own_records)
        case _:
            raise ValueError(f"{actor_id}: unknown policy {policy_config.policy_id!r}")
    return Runtime(actor_id, policy_config, own_profile, policy, restored_state)
