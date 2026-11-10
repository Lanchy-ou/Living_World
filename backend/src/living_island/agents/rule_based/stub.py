"""Wait-only rule policy used to verify configuration and save wiring."""

from typing import cast

from pydantic import JsonValue

from living_island.agents.policies._plans import WAIT, make_plan
from living_island.agents.types import DecisionRequest, IssuedIntent, OkOutcome, RuleStateV0_1


class RuleBasedPolicy:
    policy_id = "rule-based-v0"

    def __init__(self, state: RuleStateV0_1 | None = None) -> None:
        self._state = (
            state
            if state is not None
            else RuleStateV0_1(
                rule_state_version="0.1",
                commitment=None,
                issued_intents=[],
                failed_targets=[],
                cue_impressions=[],
                canteen_capacity=None,
            )
        )
        self._pending: RuleStateV0_1 | None = None

    def decide(self, request: DecisionRequest) -> OkOutcome:
        if self._pending is not None:
            raise ValueError("rule policy decision still awaiting commitment")
        plan = make_plan(request, [WAIT])
        (intent,) = plan.intents
        self._pending = self._state.model_copy(
            update={
                "issued_intents": [
                    IssuedIntent(intent_id=intent.intent_id, action_type="wait", target=None)
                ]
            }
        )
        return OkOutcome(status="ok", policy_id=self.policy_id, plan=plan)

    def finish_decision(self, accepted: bool) -> None:
        if accepted:
            if self._pending is None:
                raise ValueError("rule policy has no pending state to commit")
            self._state = self._pending
        self._pending = None

    def export_state(self) -> dict[str, JsonValue]:
        if self._pending is not None:
            raise ValueError("cannot save an uncommitted rule policy decision")
        return cast(dict[str, JsonValue], self._state.model_dump(mode="json"))
