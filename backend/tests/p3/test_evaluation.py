"""Exact VM arithmetic, missing cases and once-only allocation accounting."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from living_island.analysis.p3 import (
    AllocationEvidence,
    _shares,
    allocation_accounting,
    evaluate_cognition,
    fraction,
    latency_summary,
    usage_summary,
)
from living_island.contract.p3_inspection import (
    AllocationEntry,
    BudgetCaps,
    CallDebit,
    canonical_sha256,
)


def debit(call="call", *, unknown=False, input_reported=10, output_reported=2):
    return CallDebit(
        call_id=call,
        input_reserved=100,
        output_reserved=20,
        money_reserved=9,
        input_reported=None if unknown else input_reported,
        output_reported=output_reported,
        input_charged=100 if unknown else input_reported,
        output_charged=20 if unknown else output_reported,
        money_charged=9,
        usage_unknown=unknown,
    )


def test_vm01_primary_denominators_and_vm05_no_llm():
    records = [
        SimpleNamespace(
            policy_id="llm-v0",
            effective_policy_id=policy,
            status=status,
            call_ids=["a"],
            detail_code=None,
        )
        for policy, status in [
            ("llm-v0", "ok"),
            ("llm-v0", "ok"),
            ("rule-based-v0", "error"),
            ("sim-fallback-wait", "error"),
        ]
    ]
    rule = SimpleNamespace(policy_id="rule-based-v0")
    result = _shares([*records, rule], applicable=True)
    assert result["llm_accepted_share"] == fraction(2, 4)
    assert result["fallback_share"] == fraction(1, 4)
    assert result["wait_share"] == fraction(1, 4)
    assert result["v05"] == "FAIL"
    assert _shares([rule], applicable=False)["v05"] == "NOT_APPLICABLE"
    assert _shares([rule], applicable=True)["v05"] == "FAIL"
    assert _shares([rule], applicable=False)["llm_accepted_share"] == fraction(0, 0)


def test_vm02_nullable_usage_and_conservative_charge():
    result = usage_summary([debit(), debit("other", unknown=True, output_reported=3)])
    assert result["input"] == {
        "reported_total": None,
        "known_subtotal": 10,
        "missing_count": 1,
        "charged_total": 110,
    }
    assert result["output"] == {
        "reported_total": 5,
        "known_subtotal": 5,
        "missing_count": 0,
        "charged_total": 22,
    }
    assert result["unknown_usage_share"] == fraction(1, 2)
    assert result["cost_ceiling_micro_cny"] == 18


def test_vm03_latency_nearest_rank_and_empty():
    assert latency_summary([10, 20, None, 40, 50]) == {
        "count": 4,
        "missing_latency_count": 1,
        "min": 10,
        "max": 50,
        "median": 30,
        "p95": 50,
    }
    assert latency_summary([None])["median"] is None
    assert latency_summary([])["p95"] is None
    assert latency_summary([1, 2])["median"]["exact"] == "3/2"


def test_missing_sources_and_early_end_never_shrink_denominator():
    result = evaluate_cognition([], [], llm_actor_ids=["ella"], expected_tick=144)
    assert result["technical"] == "FAIL"
    assert result["metrics"] is None
    assert "registered final boundary" in result["missing_sources"]
    assert (
        evaluate_cognition([], [], llm_actor_ids=[], missing_sources=["calls"])["metrics"] is None
    )


def allocation(*, purpose="fake", registration="a" * 64, seed=1292387875, caps=None, unknown=False):
    case = f"fixture.s{seed}"
    key = canonical_sha256({"registration_sha256": registration, "case_id": case})
    entry = AllocationEntry.model_validate(
        {
            "reservation": {
                "allocation_key": key,
                "reservation_ordinal": 0,
                "call_id": "call",
                "input_reserved": 100,
                "output_reserved": 20,
                "money_reserved": 9,
            },
            "provider_request_sha256": "b" * 64,
            "wire_body_sha256": "c" * 64,
            "state": "settled",
            "debit": debit(unknown=unknown).model_dump(mode="json"),
            "terminal_call_sha256": "d" * 64,
        }
    )
    return AllocationEvidence(
        registration,
        case,
        purpose,
        seed,
        caps
        or BudgetCaps(attempts=48, input_tokens=1572864, output_tokens=98304, micro_cny=5000000),
        (entry,),
        "e" * 64,
    )


def test_copied_allocation_deduplicates_and_conflicts_refuse():
    evidence = allocation(unknown=True)
    result = allocation_accounting([evidence, evidence])
    assert len(result["allocations"]) == 1
    assert result["allocations"][0]["charged"]["attempts"] == 1
    assert result["allocations"][0]["charged"]["micro_cny"] == 9
    assert result["allocations"][0]["unknown_usage_count"] == 1
    with pytest.raises(ValueError, match="competing completed"):
        allocation_accounting([evidence, replace(evidence, completed_trace_sha256="f" * 64)])
    changed = evidence.entries[0].model_copy(update={"terminal_call_sha256": "f" * 64})
    with pytest.raises(ValueError, match="conflicting copied"):
        allocation_accounting([evidence, replace(evidence, entries=(changed,))])


def test_live_authorization_missing_not_reconstructed_and_six_slots():
    evidence = allocation(purpose="smoke")
    report = allocation_accounting([evidence])
    assert report["technical"] == "FAIL"
    assert "missing immutable authorization evidence" in report["errors"]
    assert sum(s["approved_micro_cny"] for s in report["slots"]) == 150000000
    authorized = {"smoke:1292387875": [evidence.allocation_key]}
    assert (
        allocation_accounting([evidence], authorizations=authorized)["arithmetic_status"] == "PASS"
    )


def test_replacement_caps_plus_prior_debits_and_cr008_attempt50():
    original = allocation(purpose="smoke")
    replacement = allocation(
        purpose="smoke",
        registration="b" * 64,
        caps=BudgetCaps(attempts=47, input_tokens=1572854, output_tokens=98302, micro_cny=4999991),
    )
    third = allocation(
        purpose="smoke",
        registration="c" * 64,
        caps=BudgetCaps(attempts=34, input_tokens=1114112, output_tokens=69275, micro_cny=3000000),
    )
    evidence = [original, replacement, third]
    bindings = {"smoke:1292387875": [e.allocation_key for e in evidence]}
    assert allocation_accounting(evidence, authorizations=bindings)["arithmetic_status"] == "PASS"
    invalid = replace(replacement, caps=original.caps)
    assert (
        allocation_accounting([original, invalid, third], authorizations=bindings)["technical"]
        == "FAIL"
    )
    with pytest.raises(ValueError, match="copied allocation"):
        allocation_accounting(
            [original], authorizations={"smoke:1292387875": [original.allocation_key] * 2}
        )


def test_unknown_authorization_slot_and_uncompleted_predecessor_refuse():
    original = allocation(purpose="smoke")
    with pytest.raises(ValueError, match="unknown authorization slot"):
        allocation_accounting([original], authorizations={"other:0": [original.allocation_key]})
    replacement = allocation(
        purpose="smoke",
        registration="b" * 64,
        caps=BudgetCaps(attempts=47, input_tokens=1572854, output_tokens=98302, micro_cny=4999991),
    )
    report = allocation_accounting(
        [replace(original, completed_trace_sha256=None), replacement],
        authorizations={"smoke:1292387875": [original.allocation_key, replacement.allocation_key]},
    )
    assert report["arithmetic_status"] == "FAIL"
    assert any("completed predecessor" in e for e in report["errors"])
    assert report["issuance_proof"] == "MISSING"


def test_vm04_terminal_repeats_same_boundary_revision_and_retired_incomplete():
    from test_cognition import perception

    from living_island.agents.p3.cognition import (
        advance_goal_evidence,
        apply_goal_change,
        initial_goal_state,
    )
    from living_island.agents.p3.types import GoalChange
    from living_island.analysis.p3 import goal_metrics
    from living_island.memory.p3_types import OwnedIntentRef
    from living_island.world.protocol import (
        ActionFeedback,
        ActionIntent,
        BoundaryPerceptionDelivery,
    )

    first = GoalChange.model_validate(
        {
            "operation": "revise",
            "expected_goal_id": None,
            "proposal": {
                "text": "Wait once",
                "completion": {
                    "kind": "own_action_success",
                    "action_type": "wait",
                    "target": None,
                    "parameters": {},
                },
            },
        }
    )
    initial = initial_goal_state()
    created = apply_goal_change(initial, first, actor_id="ella", tick=0)
    intent = ActionIntent.model_validate(
        {
            "intent_id": "ella:p000000:i0",
            "plan_id": "ella:p000000",
            "actor_id": "ella",
            "action_type": "wait",
            "target": None,
            "parameters": {},
            "reason": None,
        }
    )
    reference = OwnedIntentRef(
        intent=intent,
        decision_id="r:d:ella:000000",
        decision_ordinal=0,
        committed_tick=0,
        goal_id="ella:g000000",
    )
    feedback = ActionFeedback(
        intent_id=intent.intent_id,
        status="success",
        failure_code=None,
        interruption_reason=None,
        visible_effects=[],
    )
    delivery = BoundaryPerceptionDelivery(
        delivery_id="r:perception:0000000001:ella",
        actor_id="ella",
        observed_tick=1,
        decision_triggers=["PLAN_FINISHED"],
        perception=perception(1, feedback=feedback.model_dump(mode="json")),
    )
    complete = advance_goal_evidence(delivery, [reference], created, run_id="r")
    second = GoalChange.model_validate(
        {
            "operation": "revise",
            "expected_goal_id": "ella:g000000",
            "proposal": {
                "text": "Unverifiable receiving goal",
                "completion": {"kind": "unverifiable"},
            },
        }
    )
    next_goal = apply_goal_change(complete, second, actor_id="ella", tick=1)
    abandon = GoalChange(operation="abandon", expected_goal_id="ella:g000001", proposal=None)
    empty = apply_goal_change(next_goal, abandon, actor_id="ella", tick=2)

    def row(ordinal, tick, goals, change, intents):
        return SimpleNamespace(
            record=SimpleNamespace(
                actor_id="ella",
                tick=tick,
                run_id="r",
                decision_id=f"r:d:ella:{ordinal:06d}",
                decision_ordinal=ordinal,
                accepted_delta=SimpleNamespace(goal_change=change),
                plan=SimpleNamespace(intents=intents),
            ),
            context=SimpleNamespace(request=SimpleNamespace(context=SimpleNamespace(goals=goals))),
        )

    decisions = [
        row(0, 0, initial, first, [intent]),
        row(1, 1, complete, second, []),
        row(2, 2, next_goal, abandon, []),
    ]
    samples = [
        SimpleNamespace(actor_id="ella", tick=0, goals=initial),
        SimpleNamespace(actor_id="ella", tick=2, goals=next_goal),
        SimpleNamespace(actor_id="ella", tick=3, goals=empty),
    ]
    result = goal_metrics(decisions, samples)
    assert result["goal_completion_share"] == fraction(1, 2)
    assert result["retired_incomplete_count"] == 1
    assert result["active_incomplete_count"] == result["evidence_violations"] == 0
    # Three terminal observations of the same ID still count once.
    terminal = [SimpleNamespace(actor_id="ella", tick=tick, goals=complete) for tick in (1, 2, 3)]
    assert goal_metrics(decisions, terminal)["completed_count"] == 1
    bad = complete.model_copy(
        update={
            "current": complete.current.model_copy(
                update={
                    "evidence": complete.current.evidence.model_copy(
                        update={"delivery_id": "foreign"}
                    )
                }
            )
        }
    )
    assert (
        goal_metrics(decisions, [SimpleNamespace(actor_id="ella", tick=3, goals=bad)])[
            "evidence_violations"
        ]
        == 1
    )


def test_vm06_registered_pairs_and_zero_pairs():
    from living_island.analysis.compare import DIRECTION
    from living_island.analysis.p3 import RULE_TREE, matched_comparison

    cases = [SimpleNamespace(case_id=f"p{s}", seed=s, ticks=144) for s in (1, 2, 3)]
    controls = [SimpleNamespace(case_id=f"c{s}", paired_case_id=f"p{s}") for s in (1, 2, 3)]
    registration = SimpleNamespace(cases=cases, controls=controls)
    arms = {}
    for seed, deaths in [(1, 0), (2, 2), (3, 1)]:
        common = {
            "technical": "PASS",
            "seed": seed,
            "ticks": 144,
            "rule_tree": RULE_TREE,
            "world_inputs": ["config", "map"],
        }
        arms[f"p{seed}"] = {**common, "scalars": {**dict.fromkeys(DIRECTION, 0), "deaths": deaths}}
        arms[f"c{seed}"] = {**common, "scalars": {**dict.fromkeys(DIRECTION, 0), "deaths": 1}}
    arms["c3"]["technical"] = "FAIL"
    report = matched_comparison(registration, arms)
    assert report["pairs_expected"] == 3 and report["pairs_used"] == 2
    assert report["technical"] == "FAIL"
    deaths = report["scalars"]["deaths"]
    assert (deaths["median"], deaths["min"], deaths["max"]) == (0, -1, 1)
    assert (deaths["favorable"], deaths["unfavorable"], deaths["tied"]) == (1, 1, 0)
    empty = matched_comparison(registration, {})
    assert empty["pairs_used"] == 0 and empty["technical"] == "FAIL"
    assert empty["scalars"]["deaths"]["median"] is None
    assert empty["scalars"]["deaths"]["favorable"] == 0
    assert "favorable" not in empty["scalars"]["movement_ticks"]
