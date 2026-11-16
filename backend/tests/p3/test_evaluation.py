"""Exact VM arithmetic, missing cases and once-only allocation accounting."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
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


def test_vm01_complete_attempt_denominators_and_zero_call_llm():
    from living_island.agents.p3.cognition import initial_goal_state
    from living_island.agents.p3.types import GoalChange

    initial = initial_goal_state()
    shards = []
    for ordinal, (policy, status) in enumerate(
        [
            ("llm-v0", "ok"),
            ("llm-v0", "ok"),
            ("rule-based-v0", "error"),
            ("sim-fallback-wait", "error"),
        ]
    ):
        call_id = f"call-{ordinal}"
        record = SimpleNamespace(
            policy_id="llm-v0",
            effective_policy_id=policy,
            status=status,
            call_ids=[call_id],
            detail_code=None,
            actor_id="ella",
            tick=ordinal,
            run_id="r",
            decision_id=f"r:d:ella:{ordinal:06d}",
            decision_ordinal=ordinal,
            accepted_delta=SimpleNamespace(
                goal_change=GoalChange(operation="continue", expected_goal_id=None, proposal=None)
            ),
            plan=SimpleNamespace(intents=[]),
        )
        manifest = SimpleNamespace(experiences=[], static_tiles=[], evicted_record_count=0)
        call = SimpleNamespace(
            call_id=call_id,
            debit=debit(call_id, unknown=ordinal == 0),
            result=SimpleNamespace(latency_ms=10),
            validation_error="PARSE_ERROR" if ordinal == 2 else None,
        )
        shards.append(
            SimpleNamespace(
                record=record,
                calls=[call],
                context=SimpleNamespace(
                    request=SimpleNamespace(context=SimpleNamespace(goals=initial)),
                    assembly=SimpleNamespace(manifest=manifest),
                ),
            )
        )
    samples = [SimpleNamespace(tick=4, actor_id="ella", goals=initial)]
    report = evaluate_cognition(shards, samples, llm_actor_ids=["ella"], expected_tick=4)
    metric = report["metrics"]
    assert metric["rejection_share"] == fraction(1, 4)
    assert metric["usage"]["unknown_usage_share"] == fraction(1, 4)
    assert metric["v05"] == "FAIL"
    shards[-1].record.call_ids = []
    shards[-1].calls = []
    revised = evaluate_cognition(shards, samples, llm_actor_ids=["ella"])["metrics"]
    assert revised["llm_accepted_share"] == fraction(2, 4)
    assert revised["rejection_share"] == fraction(1, 3)


# Synthetic canonical owner snapshots exercise issuance arithmetic only. They do
# not stand in for historical M9 registrations, receipts or source-verified runs.
def synthetic_snapshot(registration, case_id, caps, charged, *, unknown=False):
    from living_island.agents.p3.types import CaseAllocationP3

    key = canonical_sha256({"registration_sha256": registration, "case_id": case_id})
    entries = []
    count, inputs, outputs, money = charged
    for ordinal in range(count):
        used = (inputs, outputs, money) if ordinal == count - 1 else (0, 0, 0)
        call_id = f"synthetic-{ordinal}"
        debit = CallDebit(
            call_id=call_id,
            input_reserved=used[0],
            output_reserved=used[1],
            money_reserved=used[2],
            input_reported=None if unknown else used[0],
            output_reported=None if unknown else used[1],
            input_charged=used[0],
            output_charged=used[1],
            money_charged=used[2],
            usage_unknown=unknown,
        )
        entries.append(
            AllocationEntry.model_validate(
                {
                    "reservation": {
                        "allocation_key": key,
                        "reservation_ordinal": ordinal,
                        "call_id": call_id,
                        "input_reserved": used[0],
                        "output_reserved": used[1],
                        "money_reserved": used[2],
                    },
                    "provider_request_sha256": "b" * 64,
                    "wire_body_sha256": "c" * 64,
                    "state": "settled",
                    "debit": debit.model_dump(mode="json"),
                    "terminal_call_sha256": "d" * 64,
                }
            )
        )
    return CaseAllocationP3.model_validate(
        {
            "allocation_schema_version": "0.1",
            "allocation_key": key,
            "registration_sha256": registration,
            "case_id": case_id,
            "caps": caps.model_dump(mode="json"),
            "generation": 2,
            "status": "complete",
            "head": {
                "checkpoint_sha256": "e" * 64,
                "checkpoint_tick": 24,
                "input_manifest_sha256": "f" * 64,
                "run_directory": f"Z:/inert-synthetic/{case_id}",
                "reservation_cursor": count,
            },
            "prepared_head": None,
            "pending_recovery_sha256": None,
            "entries": [e.model_dump(mode="json") for e in entries],
        }
    )


def synthetic_owner_archive(tmp_path):
    import json

    from scripts.p3_experiments import ArchiveReader

    from living_island.memory.p3_types import canonical_bytes
    from living_island.persistence.p3_allocation import (
        _ORIGINAL_SMOKE_CASE,
        _ORIGINAL_SMOKE_CHARGED,
        _ORIGINAL_SMOKE_REGISTRATION,
        _PRIOR_REPLACEMENT_CHARGED,
        _PRIOR_REPLACEMENT_REGISTRATION,
        REPLACEMENT_SMOKE_CAPS,
        REPLACEMENT_SMOKE_CASE,
        U4_SMOKE_CAPS,
        U4_SMOKE_CASE,
        _Binding,
        _Pilot,
        _pilot_slots,
    )

    archive = tmp_path / "owner-archive"
    archive.mkdir()
    slots = _pilot_slots()
    snapshots = []
    for index, slot in enumerate(slots):
        registration = _ORIGINAL_SMOKE_REGISTRATION if index == 0 else str(index) * 64
        case_id = _ORIGINAL_SMOKE_CASE if index == 0 else f"synthetic-{index}.s{slot.seed}"
        charge = tuple(_ORIGINAL_SMOKE_CHARGED.values()) if index == 0 else (0, 0, 0, 0)
        snapshot = synthetic_snapshot(registration, case_id, slot.caps, charge)
        snapshots.append(snapshot)
        slots[index] = slot.model_copy(
            update={
                "binding": _Binding(
                    registration_sha256=registration,
                    case_id=case_id,
                    allocation_key=snapshot.allocation_key,
                    caps=slot.caps,
                    state="issued",
                )
            }
        )
    previous = synthetic_snapshot(
        _PRIOR_REPLACEMENT_REGISTRATION,
        REPLACEMENT_SMOKE_CASE,
        REPLACEMENT_SMOKE_CAPS,
        _PRIOR_REPLACEMENT_CHARGED,
    )
    final = synthetic_snapshot(
        "a" * 64, U4_SMOKE_CASE, U4_SMOKE_CAPS, (34, 1000, 100, 1000), unknown=True
    )
    snapshots.extend((previous, final))
    pilot = _Pilot(
        approval_version="0.1",
        approval_path="Z:/inert-owner/pilot.json",
        authority_root="Z:/inert-owner/authority",
        ceiling_micro_cny=150000000,
        slots=slots,
    )
    (archive / "pilot.json").write_bytes(canonical_bytes(pilot))
    (archive / "unit-only.json").write_bytes(b"{}")
    for index, snapshot in enumerate(snapshots):
        (archive / f"allocation-{index}.json").write_bytes(canonical_bytes(snapshot))
    for label, predecessor, replacement in (
        ("cr007", snapshots[0], previous),
        ("cr008", previous, final),
    ):
        record = {
            "replacement_version": "0.1",
            "authority_root": pilot.authority_root,
            "original_allocation_key": predecessor.allocation_key,
            "original_allocation_sha256": canonical_sha256(predecessor),
            "binding": {
                "registration_sha256": replacement.registration_sha256,
                "case_id": replacement.case_id,
                "allocation_key": replacement.allocation_key,
                "caps": replacement.caps.model_dump(mode="json"),
                "state": "issued",
            },
        }
        for name in (label, label + "-guard"):
            (archive / f"{name}.json").write_bytes(canonical_bytes(record))
    manifest = {
        "evidence_manifest_version": "0.1",
        "artifacts": [],
        "registrations": [
            {"registration": "unit-only.json", "repository_path": "unit-only.json", "cases": []}
        ],
        "pilot": "pilot.json",
        "cr007": {"record": "cr007.json", "guard": "cr007-guard.json"},
        "cr008": {"record": "cr008.json", "guard": "cr008-guard.json"},
        "allocations": [f"allocation-{i}.json" for i in range(len(snapshots))],
    }
    path = archive / "manifest.json"
    owner_manifest(path, manifest)
    # Sanity-check our closed fixture container; this is not a live registration.
    ArchiveReader(path, canonical_sha256(json.loads(path.read_bytes())))
    return path, manifest, snapshots


def owner_manifest(path, manifest):
    from hashlib import sha256

    from living_island.memory.p3_types import canonical_bytes

    manifest["artifacts"] = [
        {"path": p.name, "sha256": sha256(p.read_bytes()).hexdigest()}
        for p in sorted(path.parent.iterdir())
        if p.is_file() and p != path
    ]
    path.write_bytes(canonical_bytes(manifest))
    return sha256(path.read_bytes()).hexdigest()


def owner_arithmetic(issuance, snapshots):
    from living_island.analysis.p3 import SLOTS, ExpectedAllocation

    keys = {
        key: (purpose, seed)
        for (slot, keys) in issuance.slots
        for key in keys
        for purpose, seed, _ in SLOTS
        if slot == f"{purpose}:{seed}"
    }
    evidence = [
        AllocationEvidence(
            s.registration_sha256,
            s.case_id,
            *keys[s.allocation_key],
            s.caps,
            tuple(s.entries),
            "e" * 64 if s.status == "complete" else None,
        )
        for s in snapshots
    ]
    expected = [
        ExpectedAllocation(e.registration_sha256, e.case_id, e.purpose, e.seed, e.caps)
        for e in evidence
    ]
    return allocation_accounting(evidence, expected=expected, issuance=issuance)


def test_synthetic_owner_archive_six_slots_cr_links_attempt50_and_dedup(tmp_path):
    from scripts.p3_experiments import ArchiveReader, archive_issuance

    path, manifest, snapshots = synthetic_owner_archive(tmp_path)
    issuance, loaded = archive_issuance(ArchiveReader(path, owner_manifest(path, manifest)))
    assert issuance is not None
    report = owner_arithmetic(issuance, [*snapshots, *snapshots])
    assert report["technical"] == report["arithmetic_status"] == "PASS"
    assert report["issuance_proof"] == "VERIFIED_ARCHIVE"
    assert len(report["allocations"]) == 8 and len(report["slots"]) == 6
    assert report["cost_ceiling_micro_cny"] == 909760 + 61104 + 1000
    assert all(row["issuance_status"] == "ISSUED" for row in report["slots"])
    assert report["actual_supplier_bill_micro_cny"] is None
    final = synthetic_snapshot(
        snapshots[-1].registration_sha256,
        snapshots[-1].case_id,
        snapshots[-1].caps,
        (35, 1000, 100, 1000),
    )
    assert owner_arithmetic(issuance, [*snapshots[:-1], final])["technical"] == "FAIL"
    assert len(loaded) == 8


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "initializing",
        "wrong-slot",
        "duplicate-binding",
        "guard",
        "predecessor-hash",
        "predecessor-key",
        "caps",
        "missing-predecessor",
        "incomplete-predecessor",
        "predecessor-tick",
        "missing-cr007",
        "wrong-original-registration",
        "wrong-prior-charges",
    ],
)
def test_owner_archive_frozen_issuance_refusals(tmp_path, mutation):
    import json

    from scripts.p3_experiments import ArchiveReader, archive_issuance

    from living_island.memory.p3_types import canonical_bytes

    path, manifest, _ = synthetic_owner_archive(tmp_path)

    def read(name):
        return json.loads((path.parent / name).read_bytes())

    def write(name, value):
        (path.parent / name).write_bytes(canonical_bytes(value))

    if mutation in (
        "version",
        "initializing",
        "wrong-slot",
        "duplicate-binding",
        "wrong-original-registration",
    ):
        pilot = read("pilot.json")
        if mutation == "version":
            pilot["approval_version"] = "9.9"
        elif mutation == "initializing":
            pilot["slots"][0]["binding"]["state"] = "initializing"
        elif mutation == "wrong-slot":
            pilot["slots"][0]["seed"] = 1
        elif mutation == "duplicate-binding":
            pilot["slots"][1]["binding"] = pilot["slots"][0]["binding"]
        else:
            pilot["slots"][0]["binding"]["registration_sha256"] = "f" * 64
        write("pilot.json", pilot)
    elif mutation == "guard":
        guard = read("cr007-guard.json")
        guard["binding"]["state"] = "initializing"
        write("cr007-guard.json", guard)
    elif mutation in ("predecessor-hash", "predecessor-key", "caps"):
        record = read("cr007.json")
        if mutation == "predecessor-hash":
            record["original_allocation_sha256"] = "0" * 64
        elif mutation == "predecessor-key":
            record["original_allocation_key"] = "0" * 64
        else:
            record["binding"]["caps"]["output_tokens"] += 1
        write("cr007.json", record)
        write("cr007-guard.json", record)
    elif mutation == "missing-predecessor":
        manifest["allocations"].remove("allocation-0.json")
    elif mutation == "missing-cr007":
        manifest["cr007"] = None
    else:
        name = "allocation-6.json" if mutation == "wrong-prior-charges" else "allocation-0.json"
        snapshot = read(name)
        if mutation == "incomplete-predecessor":
            snapshot["status"] = "running"
        elif mutation == "predecessor-tick":
            snapshot["head"]["checkpoint_tick"] = 23
        else:
            snapshot["entries"][-1]["debit"]["money_charged"] += 1
        write(name, snapshot)
        label = "cr008" if mutation == "wrong-prior-charges" else "cr007"
        record = read(label + ".json")
        record["original_allocation_sha256"] = canonical_sha256(snapshot)
        write(label + ".json", record)
        write(label + "-guard.json", record)
    digest = owner_manifest(path, manifest)
    with pytest.raises(ValueError):
        archive_issuance(ArchiveReader(path, digest))


def test_copied_prefix_snapshots_dedup_but_conflicting_rows_refuse(tmp_path):
    from scripts.p3_experiments import ArchiveReader, archive_issuance

    from living_island.memory.p3_types import canonical_bytes

    path, manifest, snapshots = synthetic_owner_archive(tmp_path)
    first = snapshots[0]
    prefix = first.model_copy(
        update={
            "status": "running",
            "entries": first.entries[:7],
            "head": first.head.model_copy(update={"reservation_cursor": 7}),
        }
    )
    (path.parent / "prefix.json").write_bytes(canonical_bytes(prefix))
    manifest["allocations"].append("prefix.json")
    issuance, loaded = archive_issuance(ArchiveReader(path, owner_manifest(path, manifest)))
    assert issuance is not None
    assert (
        owner_arithmetic(issuance, [s for copies in loaded.values() for s in copies])[
            "cost_ceiling_micro_cny"
        ]
        == 971864
    )
    bad = prefix.model_copy(deep=True)
    bad.entries[0] = bad.entries[0].model_copy(update={"terminal_call_sha256": "f" * 64})
    (path.parent / "prefix.json").write_bytes(canonical_bytes(bad))
    with pytest.raises(ValueError, match="conflicting copied"):
        archive_issuance(ArchiveReader(path, owner_manifest(path, manifest)))


def test_snapshot_only_archive_cannot_pass_case_verification(tmp_path):
    from scripts.p3_experiments import evaluate_archive

    path, manifest, _ = synthetic_owner_archive(tmp_path)
    # The explicit unit-only registration is deliberately not a valid real trial.
    with pytest.raises(ValueError):
        evaluate_archive(
            path,
            trusted_owner_digest=owner_manifest(path, manifest),
            repository=Path(__file__).resolve().parents[3],
            output=None,
        )
