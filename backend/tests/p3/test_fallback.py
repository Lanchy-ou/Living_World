"""Offline OQ-083 lifecycle vectors against the frozen rule implementation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from rule_policy_builders import (
    config,
    empty_state,
    ent_t,
    failed,
    params,
    perception,
    ref,
    res_t,
    success,
    tile_t,
)

import living_island.agents.llm.fallback as fallback
from living_island.agents.llm.fallback import (
    FrozenRuleFallbackAdapter,
    InvalidFallbackPlan,
    project_request,
    return_to_llm,
)
from living_island.agents.p3.types import (
    DecisionContextP3,
    DecisionRequestP3,
    GoalState,
    IdentitySource,
    P3PolicyPrivateState,
    ProfileDocument,
    ResidentIdentity,
)
from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.types import RuleStateV0_1
from living_island.memory.p3_types import canonical_bytes, canonical_sha256


def request(p=None, ordinal=0):
    p = p if p is not None else perception()
    source = IdentitySource(
        actor_id=p.actor_id,
        display_name="A",
        profile=ProfileDocument(
            profile_schema_version="0.1", profile_id="curious", values=["curiosity"]
        ),
        initial_direction="Explore the island",
    )
    identity = ResidentIdentity(
        identity_schema_version="0.1",
        actor_id=p.actor_id,
        display_name=source.display_name,
        profile_id=source.profile.profile_id,
        values=source.profile.values,
        initial_direction=source.initial_direction,
        source_sha256=canonical_sha256(source),
    )
    return DecisionRequestP3(
        request_schema_version="0.2",
        actor_id=p.actor_id,
        tick=p.tick,
        decision_ordinal=ordinal,
        triggers=[] if (p.tick, ordinal) == (0, 0) else ["PLAN_FINISHED"],
        context=DecisionContextP3(
            context_schema_version="0.2",
            perception=p,
            identity=identity,
            goals=GoalState(goal_schema_version="0.1", current=None, next_goal_sequence=0),
            recalled_experience=[],
            owned_intents=[],
        ),
    )


def private(mode="llm", last=None, **updates):
    return P3PolicyPrivateState(
        private_schema_version="0.1",
        mode=mode,
        fallback_state=RuleStateV0_1.model_validate({**empty_state(), **updates}),
        last_fallback_ordinal=last,
    )


def learned(mode="fallback"):
    return private(
        mode=mode,
        last=3,
        commitment={"goal": "water", "target": {"x": 4, "y": 4}, "set_at_tick": 1},
        issued_intents=[ref(3, 0, "fill_canteen", ent_t("bottle"))],
        failed_targets=failed(
            [
                ("gather", tile_t(1, 1), "RESOURCE_TAKEN", 10),
                ("move_to", tile_t(3, 3), "NO_PATH", 11),
            ]
        ),
        cue_impressions=[
            {
                "cue_id": "moss",
                "position": {"x": 3, "y": 3},
                "detail_level": "distant",
                "direction": None,
            }
        ],
        canteen_capacity=7,
    )


def capture_rule_inputs(monkeypatch):
    captured = []
    original = RuleBasedPolicy

    class CapturingPolicy(original):
        def decide(self, req):
            captured.append((req.model_copy(deep=True), self.export_state()))
            return super().decide(req)

    monkeypatch.setattr(fallback, "RuleBasedPolicy", CapturingPolicy)
    return captured


def test_exact_projection_keeps_raw_perception_without_shared_cognition():
    original = request(perception(tick=12), ordinal=7)
    projected = project_request(original)
    assert projected.actor_id == original.actor_id
    assert projected.tick == 12 and projected.decision_ordinal == 7
    assert projected.triggers == ["PLAN_FINISHED"]
    assert projected.context.perception == original.context.perception
    assert projected.context.personality_profile.model_dump() == {
        "profile_id": "curious",
        "values": [],
    }
    assert [g.model_dump() for g in projected.context.current_goals] == [
        {"goal_id": "initial", "text": "Explore the island", "priority": 0}
    ]
    assert projected.context.recalled_episodes == [] and projected.context.beliefs == []
    assert projected.context.current_plan_summary is None
    projected.context.perception.explored_static_tiles.clear()
    assert original.context.perception.explored_static_tiles


@pytest.mark.parametrize("initial_mode", ["llm", "fallback"])
def test_initial_and_adjacent_decisions_match_frozen_policy(initial_mode):
    cfg = config()
    adapter = FrozenRuleFallbackAdapter(cfg)
    state = private(mode=initial_mode)
    direct = RuleBasedPolicy(cfg)
    for tick, ordinal in [(0, 0), (1, 1), (2, 2)]:
        req = request(perception(tick=tick, stamina="critical"), ordinal)
        before = canonical_bytes(state)
        plan, successor = adapter.decide(req, state)
        direct_result = direct.decide(project_request(req))
        direct.finish_decision(True)
        assert plan == direct_result.plan
        assert successor.fallback_state.model_dump(mode="json") == direct.export_state()
        assert successor.mode == "fallback" and successor.last_fallback_ordinal == ordinal
        assert plan.plan_id == f"a:p{ordinal:06d}"
        assert canonical_bytes(state) == before
        state = successor


def test_continuous_fallback_passes_full_state_and_learns_current_feedback(monkeypatch):
    captured = capture_rule_inputs(monkeypatch)
    prior = learned()
    req = request(
        perception(
            tick=10, stamina="critical", canteen=("bottle", 2), feedback=success("a:p000003:i0")
        ),
        ordinal=4,
    )
    _, successor = FrozenRuleFallbackAdapter(config()).decide(req, prior)
    assert len(captured) == 1
    assert captured[0][1] == prior.fallback_state.model_dump(mode="json")
    assert successor.fallback_state.canteen_capacity == 2
    assert [e.retry_after_tick for e in successor.fallback_state.failed_targets] == [11]
    assert successor.last_fallback_ordinal == 4


def test_return_freezes_all_rule_state_and_is_independent(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("return must not execute the rule")

    monkeypatch.setattr(fallback, "RuleBasedPolicy", forbidden)
    prior = learned()
    before = canonical_bytes(prior)
    returned = return_to_llm(prior)
    assert returned.mode == "llm" and returned.fallback_state == prior.fallback_state
    assert returned.last_fallback_ordinal == 3
    returned.fallback_state.failed_targets.clear()
    assert canonical_bytes(prior) == before


def test_reentry_clears_stale_refs_preserves_unexpired_backoff_and_knowledge(monkeypatch):
    captured = capture_rule_inputs(monkeypatch)
    prior = return_to_llm(learned())
    before = canonical_bytes(prior)
    req = request(
        perception(
            tick=10, stamina="critical", canteen=("bottle", 2), feedback=success("a:p000003:i0")
        ),
        ordinal=9,
    )
    plan, successor = FrozenRuleFallbackAdapter(config()).decide(req, prior)
    staged = captured[0][1]
    assert staged["commitment"] is None and staged["issued_intents"] == []
    assert [e["retry_after_tick"] for e in staged["failed_targets"]] == [11]
    assert staged["cue_impressions"] == prior.fallback_state.model_dump()["cue_impressions"]
    assert staged["canteen_capacity"] == 7 and successor.fallback_state.canteen_capacity == 7
    assert successor.fallback_state.failed_targets[0].retry_after_tick == 11
    assert plan.plan_id == "a:p000009" and successor.last_fallback_ordinal == 9
    assert canonical_bytes(prior) == before


def test_long_llm_interval_removes_expired_cells_only(monkeypatch):
    captured = capture_rule_inputs(monkeypatch)
    prior = return_to_llm(learned())
    req = request(perception(tick=100, stamina="critical"), ordinal=51)
    plan, successor = FrozenRuleFallbackAdapter(config()).decide(req, prior)
    staged = captured[0][1]
    assert staged["commitment"] is None and staged["issued_intents"] == []
    assert staged["failed_targets"] == []
    assert staged["cue_impressions"] == prior.fallback_state.model_dump()["cue_impressions"]
    assert staged["canteen_capacity"] == 7 and successor.fallback_state.canteen_capacity == 7
    assert plan.plan_id == "a:p000051" and successor.last_fallback_ordinal == 51


def test_discarded_staging_does_not_advance_adapter_or_alias_private_state():
    adapter = FrozenRuleFallbackAdapter(config())
    prior = private()
    req = request(perception(stamina="critical"))
    first, second = adapter.decide(req, prior), adapter.decide(req, prior)
    assert first == second
    first[1].fallback_state.issued_intents.clear()
    assert second[1].fallback_state.issued_intents
    assert prior.fallback_state.issued_intents == []


@pytest.mark.parametrize("ordinal", [0, 3])
def test_rejects_uncommitted_or_future_last_ordinal(ordinal):
    with pytest.raises(ValueError, match="ordinal"):
        FrozenRuleFallbackAdapter(config()).decide(request(perception(tick=10), ordinal), learned())


def test_rejects_foreign_saved_intents_before_reentry_refresh():
    data = learned(mode="llm").model_dump(mode="json")
    data["fallback_state"]["issued_intents"][0]["intent_id"] = "other:p000003:i0"
    with pytest.raises(ValueError, match="actor"):
        FrozenRuleFallbackAdapter(config()).decide(
            request(perception(tick=10), 9), P3PolicyPrivateState.model_validate(data)
        )


def test_rejects_reference_ordinal_inconsistent_with_lifecycle():
    data = learned().model_dump(mode="json")
    data["last_fallback_ordinal"] = 2
    with pytest.raises(ValueError, match="last fallback"):
        FrozenRuleFallbackAdapter(config()).decide(
            request(perception(tick=10), 9), P3PolicyPrivateState.model_validate(data)
        )


def test_rejects_noninitial_state_before_any_rule_execution():
    with pytest.raises(ValueError, match="initial"):
        FrozenRuleFallbackAdapter(config()).decide(request(), private(canteen_capacity=4))


def test_revalidates_forged_request_before_rule_execution():
    with pytest.raises(ValueError):
        FrozenRuleFallbackAdapter(config()).decide(
            request().model_copy(update={"actor_id": "other"}), private()
        )


@pytest.mark.parametrize(
    "rule",
    [
        params(canteen_use="restricted"),
        params(cue_use="ignored"),
        params(carry=3),
        params(retry=35),
    ],
)
def test_rejects_nonbase_rule_configuration(rule):
    with pytest.raises(ValueError, match="frozen base"):
        FrozenRuleFallbackAdapter(config(rule=rule))


def test_malformed_rule_output_discards_staging_and_preserves_prior(monkeypatch):
    finishes = []
    original = RuleBasedPolicy

    class MalformedPolicy(original):
        def decide(self, req):
            outcome = super().decide(req)
            return SimpleNamespace(plan=outcome.plan.model_copy(update={"plan_id": "bad"}))

        def finish_decision(self, accepted):
            finishes.append(accepted)
            return super().finish_decision(accepted)

    monkeypatch.setattr(fallback, "RuleBasedPolicy", MalformedPolicy)
    prior = private()
    before = canonical_bytes(prior)
    with pytest.raises(InvalidFallbackPlan):
        FrozenRuleFallbackAdapter(config()).decide(request(), prior)
    assert finishes == [False] and canonical_bytes(prior) == before


def test_unexpected_rule_exception_propagates_without_fallback_loop(monkeypatch):
    calls = []

    def broken(self, req):
        calls.append(req)
        raise RuntimeError("programming defect")

    monkeypatch.setattr(RuleBasedPolicy, "decide", broken)
    prior = private()
    before = canonical_bytes(prior)
    with pytest.raises(RuntimeError, match="programming defect"):
        FrozenRuleFallbackAdapter(config()).decide(request(), prior)
    assert len(calls) == 1 and canonical_bytes(prior) == before


def test_multiple_return_reentry_cycles_preserve_local_deadlines(monkeypatch):
    captured = capture_rule_inputs(monkeypatch)
    prior = private(
        mode="llm",
        last=3,
        failed_targets=failed(
            [
                ("gather", tile_t(1, 1), "OBSERVED_EMPTY", 12),
                ("request", res_t("other"), "REQUESTED", 15),
            ]
        ),
        canteen_capacity=7,
    )
    adapter = FrozenRuleFallbackAdapter(config())
    for tick, ordinal, deadlines in [(10, 9, [12, 15]), (12, 15, [15]), (15, 21, [])]:
        req = request(perception(tick=tick, stamina="critical"), ordinal)
        plan, successor = adapter.decide(req, prior)
        assert [
            entry["retry_after_tick"] for entry in captured[-1][1]["failed_targets"]
        ] == deadlines
        assert [
            entry.retry_after_tick for entry in successor.fallback_state.failed_targets
        ] == deadlines
        assert plan.plan_id == f"a:p{ordinal:06d}"
        assert successor.last_fallback_ordinal == ordinal
        prior = return_to_llm(successor)
        assert prior.fallback_state.canteen_capacity == 7


def test_return_revalidates_forged_private_mode():
    with pytest.raises(ValueError):
        return_to_llm(private().model_copy(update={"mode": "invalid"}))
