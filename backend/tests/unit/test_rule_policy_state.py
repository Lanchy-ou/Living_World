"""Rule Policy §7.2 restore validation and §7.3 transaction tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from test_engine_actions import content_with
from test_sim_policies import PROFILE

from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.runtime import Runtime
from living_island.agents.types import PolicyConfig, ResidentRuntimeState, RuleParams
from living_island.sim.boundary import BoundaryLoop
from living_island.world.ports import create_engine

PARAMS = RuleParams(
    rule_params_version="0.1",
    canteen_use="enabled",
    cue_use="enabled",
    fruit_carry_target=2,
    failed_target_retry_ticks=2,
)


def _config():
    return PolicyConfig(
        policy_id="rule-based-v0",
        seed=1,
        map_width=8,
        map_height=5,
        max_plan_actions=2,
        script_sha256=None,
        source_trace_sha256=None,
        rule_params=PARAMS,
    )


def _tile(x=1, y=1):
    return {"kind": "tile", "position": {"x": x, "y": y}}


def _resident(actor="ryan"):
    return {"kind": "resident", "id": actor}


def _intent(intent_id="ella:p000000:i0", action_type="move_to", target=None):
    return {"intent_id": intent_id, "action_type": action_type, "target": target}


def _failure(action="move_to", target=None, code="NO_PATH", retry_after_tick=4):
    return {
        "action": action,
        "target": _tile() if target is None else target,
        "code": code,
        "retry_after_tick": retry_after_tick,
    }


def _cue(cue_id="moss", detail="near", direction="unrecognized"):
    return {
        "cue_id": cue_id,
        "position": {"x": 1, "y": 1},
        "detail_level": detail,
        "direction": direction,
    }


def _saved(**state_updates):
    return {
        "actor_id": "ella",
        "policy_config": _config(),
        "next_decision_ordinal": 2,
        "latest_perception_tick": 2,
        "policy_state": {
            "rule_state_version": "0.1",
            "commitment": {"goal": "water", "target": {"x": 7, "y": 4}, "set_at_tick": 2},
            "issued_intents": [
                _intent(target=_tile()),
                _intent("ella:p000000:i1", "give", _resident()),
            ],
            "failed_targets": [
                _failure("gather", {"kind": "self"}, "INVENTORY_FULL"),
                _failure("gather", _tile(), "OBSERVED_EMPTY"),
                _failure(),
                _failure("request", _resident(), "REQUESTED"),
            ],
            "cue_impressions": [_cue()],
            "canteen_capacity": 0,
            **state_updates,
        },
    }


def test_rule_state_accepts_canonical_state_without_repair():
    raw = _saved()
    state = ResidentRuntimeState.model_validate(raw)
    assert state.model_dump(mode="json")["policy_state"] == raw["policy_state"]


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"rule_state_version": "0.2"}, "rule_state_version"),
        ({"extra": 0}, "Extra inputs"),
        ({"issued_intents": {}}, "valid list"),
        ({"canteen_capacity": True}, "valid integer"),
        ({"failed_targets": [_failure(target=_tile(y=1)), _failure(target=_tile(y=0))]}, "sorted"),
        ({"failed_targets": [_failure(), _failure(code="INVALID_TARGET")]}, "unique"),
        ({"failed_targets": [_failure(target=_tile(x)) for x in range(3)]}, "entry limit"),
        (
            {
                "failed_targets": [
                    _failure("request", _resident(f"{x:02d}"), "REFUSED") for x in range(65)
                ]
            },
            "entry limit",
        ),
        ({"cue_impressions": [_cue(), _cue()]}, "duplicate-free"),
        ({"cue_impressions": [_cue("a"), _cue("b")]}, "at most one"),
        (
            {"commitment": {"goal": "water", "target": {"x": 8, "y": 0}, "set_at_tick": 2}},
            "outside the grid",
        ),
        ({"issued_intents": [_intent(target=_tile(y=5))]}, "outside the grid"),
        ({"failed_targets": [_failure(target=_tile(y=5))]}, "outside the grid"),
        ({"cue_impressions": [{**_cue(), "position": {"x": 0, "y": 5}}]}, "outside the grid"),
        ({"issued_intents": [_intent(target=_tile())] * 3}, "plan action limit"),
        ({"issued_intents": [_intent("mia:p000000:i0", target=_tile())]}, "plan of this actor"),
        ({"issued_intents": [_intent("ella:p000002:i0", target=_tile())]}, "committed plan"),
        ({"issued_intents": [_intent("ella:p0:i0", target=_tile())]}, "committed plan"),
        ({"issued_intents": [_intent("ella:p000000:i1", target=_tile())]}, "contiguous indices"),
        (
            {
                "issued_intents": [
                    _intent(target=_tile()),
                    _intent("ella:p000001:i1", target=_tile()),
                ]
            },
            "one plan",
        ),
        ({"issued_intents": [_intent(target=_resident())]}, "target kind"),
        ({"issued_intents": [_intent(action_type="wait", target=_tile())]}, "target kind"),
        ({"failed_targets": [_failure(retry_after_tick=0)]}, "retry_after_tick"),
        ({"failed_targets": [_failure(retry_after_tick=5)]}, "retry window"),
        (
            {"commitment": {"goal": "water", "target": {"x": 0, "y": 0}, "set_at_tick": -1}},
            "set_at_tick",
        ),
        (
            {"commitment": {"goal": "water", "target": {"x": 0, "y": 0}, "set_at_tick": 3}},
            "latest perception",
        ),
        ({"failed_targets": [_failure(code="MADE_UP")]}, "action, target kind and code"),
        ({"failed_targets": [_failure(code="EXHAUSTED")]}, "action, target kind and code"),
        ({"failed_targets": [_failure(code="OBSERVED_EMPTY")]}, "action, target kind and code"),
        ({"failed_targets": [_failure(target={"kind": "self"})]}, "action, target kind and code"),
        ({"cue_impressions": [_cue(detail="distant")]}, "distant cue"),
        ({"canteen_capacity": -1}, "canteen_capacity"),
    ],
)
def test_rule_state_refuses_invalid_data(updates, message):
    with pytest.raises(ValidationError, match=message):
        ResidentRuntimeState.model_validate(_saved(**updates))


def test_rule_state_requires_all_fields_and_no_intents_before_first_decision():
    raw = _saved()
    del raw["policy_state"]["canteen_capacity"]
    with pytest.raises(ValidationError, match="canteen_capacity"):
        ResidentRuntimeState.model_validate(raw)
    with pytest.raises(ValidationError, match="committed plan"):
        ResidentRuntimeState.model_validate({**_saved(), "next_decision_ordinal": 0})


def test_rule_policy_commits_only_accepted_plans():
    class RejectSecondPlan(RuleBasedPolicy):
        def decide(self, request):
            outcome = super().decide(request)
            with pytest.raises(ValueError, match="uncommitted"):
                self.export_state()
            if request.decision_ordinal == 1:
                return outcome.model_copy(update={"plan": object()})
            return outcome

    content = content_with({"ella": (2, 3)})
    policy = RejectSecondPlan()
    runtime = Runtime("ella", _config(), PROFILE, policy)
    loop = BoundaryLoop(create_engine(content, None), [runtime])
    assert runtime.export_state().policy_state["issued_intents"] == []
    _, first = loop.advance()
    assert first[0].status == "ok"
    state = runtime.export_state().policy_state
    assert state["issued_intents"] == [_intent(action_type="wait")]
    _, second = loop.advance()
    assert second[0].status == "error"
    assert second[0].substituted
    assert runtime.export_state().policy_state == state
    _, third = loop.advance()
    assert third[0].status == "ok"
    assert runtime.export_state().policy_state["issued_intents"] == [
        _intent("ella:p000002:i0", "wait")
    ]
