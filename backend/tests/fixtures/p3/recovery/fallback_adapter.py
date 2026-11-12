"""Stage OQ-083 transitions around the unchanged rule-based-v0 policy.

Each call owns a disposable rule instance. Finishing that instance extracts its
proposed successor; only the caller may publish the returned private state.
"""

from __future__ import annotations

from living_island.agents.p3.ports import InvalidFallbackPlan
from living_island.agents.p3.types import DecisionRequestP3, P3PolicyPrivateState
from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.types import (
    DecisionContext,
    DecisionRequest,
    Goal,
    PersonalityProfile,
    PolicyConfig,
    ResidentRuntimeState,
    RuleStateV0_1,
    build_intent_id,
    build_plan_id,
)
from living_island.world.protocol import ActionPlan


def return_to_llm(state: P3PolicyPrivateState) -> P3PolicyPrivateState:
    """Stage primary return without executing or refreshing the frozen rule."""
    state = P3PolicyPrivateState.model_validate(state.model_dump(mode="json"))
    data = state.model_dump(mode="json")
    data["mode"] = "llm"
    return P3PolicyPrivateState.model_validate(data)


def project_request(request: DecisionRequestP3) -> DecisionRequest:
    """Expose raw own perception and the specified legacy identity fields."""
    request = DecisionRequestP3.model_validate(request.model_dump(mode="json"))
    identity = request.context.identity
    return DecisionRequest(
        actor_id=request.actor_id,
        tick=request.tick,
        decision_ordinal=request.decision_ordinal,
        triggers=list(request.triggers),
        context=DecisionContext(
            perception=request.context.perception.model_copy(deep=True),
            personality_profile=PersonalityProfile(profile_id=identity.profile_id, values=[]),
            current_goals=[Goal(goal_id="initial", text=identity.initial_direction, priority=0)],
            recalled_episodes=[],
            beliefs=[],
            current_plan_summary=None,
        ),
    )


class FrozenRuleFallbackAdapter:
    """Implement the frozen FallbackAdapter port without retaining resident state."""

    adapter_id = "fallback-adapter-v0.1"

    def __init__(self, config: PolicyConfig) -> None:
        config = PolicyConfig.model_validate(config.model_dump(mode="json"))
        params = config.rule_params
        if (
            config.policy_id != "rule-based-v0"
            or params is None
            or (
                params.canteen_use,
                params.cue_use,
                params.fruit_carry_target,
                params.failed_target_retry_ticks,
            )
            != ("enabled", "enabled", 2, 36)
        ):
            raise ValueError("P3 fallback requires the frozen base rule configuration")
        self._config = config

    def decide(
        self, request: DecisionRequestP3, state: P3PolicyPrivateState
    ) -> tuple[ActionPlan, P3PolicyPrivateState]:
        legacy = project_request(request)
        state = P3PolicyPrivateState.model_validate(state.model_dump(mode="json"))
        last = state.last_fallback_ordinal
        if last is not None and last >= legacy.decision_ordinal:
            raise ValueError("fallback ordinal must precede the current global ordinal")
        rule_state = state.fallback_state
        self._validate_state(rule_state, legacy, legacy.decision_ordinal)
        if last is None and rule_state != RuleStateV0_1(
            rule_state_version="0.1",
            commitment=None,
            issued_intents=[],
            failed_targets=[],
            cue_impressions=[],
            canteen_capacity=None,
        ):
            raise ValueError("unexecuted fallback requires the initial rule state")
        if rule_state.issued_intents and last is not None:
            expected = build_plan_id(legacy.actor_id, last)
            if rule_state.issued_intents[0].intent_id != build_intent_id(expected, 0):
                raise ValueError("rule references must identify the last fallback ordinal")
        if state.mode == "llm":
            # Clear stale references before consuming the current packet once.
            # Shared experience and earlier LLM output never enter rule learning.
            rule_state = RuleStateV0_1(
                rule_state_version="0.1",
                commitment=None,
                issued_intents=[],
                failed_targets=[
                    entry
                    for entry in rule_state.failed_targets
                    if entry.retry_after_tick > legacy.tick
                ],
                cue_impressions=rule_state.cue_impressions,
                canteen_capacity=rule_state.canteen_capacity,
            )
        policy = RuleBasedPolicy(self._config.model_copy(deep=True), rule_state)
        outcome = policy.decide(legacy)
        try:
            plan = ActionPlan.model_validate(outcome.plan.model_dump(mode="json"))
            expected = build_plan_id(legacy.actor_id, legacy.decision_ordinal)
            if (
                plan.actor_id != legacy.actor_id
                or plan.plan_id != expected
                or plan.created_at_tick != legacy.tick
                or len(plan.intents) > self._config.max_plan_actions
                or [intent.intent_id for intent in plan.intents]
                != [build_intent_id(expected, i) for i in range(len(plan.intents))]
            ):
                raise ValueError("rule plan identity or action limit mismatch")
        except (AttributeError, TypeError, ValueError) as exc:
            policy.finish_decision(False)
            raise InvalidFallbackPlan("malformed rule proposal") from exc
        policy.finish_decision(True)
        successor = RuleStateV0_1.model_validate(policy.export_state())
        self._validate_state(successor, legacy, legacy.decision_ordinal + 1)
        return plan, P3PolicyPrivateState(
            private_schema_version="0.1",
            mode="fallback",
            fallback_state=successor,
            last_fallback_ordinal=legacy.decision_ordinal,
        )

    def _validate_state(
        self, state: RuleStateV0_1, request: DecisionRequest, next_ordinal: int
    ) -> None:
        ResidentRuntimeState(
            actor_id=request.actor_id,
            policy_config=self._config,
            next_decision_ordinal=next_ordinal,
            latest_perception_tick=request.tick,
            policy_state=state.model_dump(mode="json"),
        )
