"""EX-06/09, context isolation, actual-profile seams and closed foundation DTOs."""

from __future__ import annotations

import base64
import copy

import pytest
from pydantic import ValidationError
from rule_policy_builders import cue, heard, perception, resident, tiles, tree

from living_island.agents.p3.cognition import (
    advance_goal_evidence,
    apply_goal_change,
    initial_goal_state,
)
from living_island.agents.p3.context import assemble_context
from living_island.agents.p3.types import (
    MAX_PROJECTION_BYTES,
    AllocationEntry,
    BudgetCaps,
    CallDebit,
    CaseAllocationP3,
    ContextAssembly,
    ContextProfile,
    DecisionLimits,
    DecisionRecordP3,
    GoalChange,
    GoalState,
    IdentitySource,
    ProfileDocument,
    ProviderResult,
    ResidentCognitiveState,
    ResidentIdentity,
    WireRequest,
)
from living_island.memory.experience import (
    capture_accepted_decision,
    ingest_experience,
    initial_experience,
)
from living_island.memory.p3_types import (
    RetrievalQuery,
    RetrievalResult,
    canonical_bytes,
    canonical_sha256,
)
from living_island.world.protocol import (
    ActionFeedback,
    ActionPlan,
    BoundaryPerceptionDelivery,
    Coord,
    format_delivery_id,
)


def profile(fixture=False):
    return ContextProfile(
        context_profile_schema_version="0.1",
        context_profile_id="p3-context-recent-only-fixture-v0" if fixture else "p3-context-v0",
        retrieval_profile="recent-only-fixture-v0" if fixture else "recent-relevant-v0",
        projection_profile="p3-context-v0",
    )


def delivery(p):
    return BoundaryPerceptionDelivery(
        delivery_id=format_delivery_id("run", p.tick, p.actor_id),
        actor_id=p.actor_id,
        observed_tick=p.tick,
        perception=p,
        decision_triggers=[],
    )


def cognitive(p, *, store=None, goals=None):
    source = IdentitySource(
        actor_id=p.actor_id,
        display_name="Alice",
        profile=ProfileDocument(
            profile_schema_version="0.1", profile_id="alice", values=["curiosity"]
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
    return ResidentCognitiveState(
        cognitive_schema_version="0.1",
        actor_id=p.actor_id,
        identity=identity,
        experience=store
        if store is not None
        else ingest_experience(initial_experience(p.actor_id), delivery(p), run_id="run"),
        goals=goals or GoalState(goal_schema_version="0.1", current=None, next_goal_sequence=0),
    )


def assemble(p, **kwargs):
    return assemble_context(p, cognitive(p), profile(), **kwargs)


def with_text(size, *, explored=None):
    speech = heard("u", "ryan", "statement").model_copy(update={"text": "x" * size})
    return perception(explored=explored or [], heard_utterances=[speech])


def test_repeat_assembly_is_identical_and_does_not_alias_inputs():
    p = perception(explored=tiles(20, 10), entities=[resident("ryan", (1, 1))], cues=[cue()])
    state = cognitive(p)
    before = canonical_bytes(state)
    first = assemble_context(p, state, profile())
    second = assemble_context(p, state, profile())
    assert canonical_bytes(first) == canonical_bytes(second)
    assert canonical_bytes(state) == before
    assert first.context.perception == p
    assert first.context_sha256 == canonical_sha256(first.context)
    assert first.projection_sha256 == canonical_sha256(first.provider_projection)
    first.context.identity.values.append("changed outside")
    first.context.perception.explored_static_tiles.clear()
    assert state.identity.values == ["curiosity"]
    assert len(p.explored_static_tiles) == 200
    assert second.context.identity.values == ["curiosity"]


def test_ex06_exact_mandatory_boundary_and_plus_one():
    base = assemble(with_text(0, explored=tiles(1, 1))).manifest.mandatory_bytes
    exact = assemble(with_text(MAX_PROJECTION_BYTES - base, explored=tiles(1, 1)))
    assert exact.error is None
    assert exact.manifest.mandatory_bytes == MAX_PROJECTION_BYTES
    assert exact.manifest.projection_bytes == MAX_PROJECTION_BYTES
    assert exact.provider_projection.recalled_experience == []
    assert exact.provider_projection.perception.explored_static_tiles == []
    assert {r.omission for r in exact.manifest.experiences} == {"projection_bytes"}
    assert exact.manifest.static_tiles[0].omission == "projection_bytes"
    over = assemble(with_text(MAX_PROJECTION_BYTES - base + 1, explored=tiles(1, 1)))
    assert over.error == "MANDATORY_OVERSIZE"
    assert over.provider_projection is None and over.projection_sha256 is None
    assert over.manifest.projection_bytes is None
    assert over.manifest.mandatory_bytes == 65537
    assert {r.omission for r in over.manifest.experiences} == {"mandatory_oversize"}
    assert over.manifest.static_tiles[0].omission == "mandatory_oversize"
    assert len(over.context.perception.heard_utterances[0].text) == 65537 - base


def test_optional_large_record_does_not_hide_later_small_records():
    # Speech ranks before own_state, fails as a whole, then the smaller own sample fits.
    p = with_text(40000).model_copy(update={"visible_entities": [resident("ryan", (1, 1))]})
    result = assemble(p)
    assert [r.kind for r in result.context.recalled_experience] == [
        "heard_speech",
        "entity_seen",
        "own_state",
    ]
    assert [r.kind for r in result.provider_projection.recalled_experience] == [
        "entity_seen",
        "own_state",
    ]
    assert [r.omission for r in result.manifest.experiences] == ["projection_bytes", None, None]


def test_static_selection_rank_candidate_cap_and_materialized_order():
    explored = tiles(
        20, 10, {(19, 9): "spring", (18, 9): "cave", (17, 9): "fruit_tree", (16, 9): "damp_moss"}
    )
    p = perception(pos=(0, 0), explored=explored, visible_tiles=explored[:3])
    result = assemble(p)
    assert [(t.position.x, t.position.y) for t in result.manifest.static_tiles[:4]] == [
        (19, 9),
        (18, 9),
        (17, 9),
        (16, 9),
    ]
    assert result.manifest.static_tiles[4].position == Coord(x=0, y=0)
    assert sum(t.projected for t in result.manifest.static_tiles) == 128
    assert all(t.omission == "tile_limit" for t in result.manifest.static_tiles[128:])
    projected = result.provider_projection.perception.explored_static_tiles
    assert [(t.position.y, t.position.x) for t in projected] == sorted(
        (t.position.y, t.position.x) for t in projected
    )
    assert result.context.perception.explored_static_tiles == explored
    assert result.provider_projection.perception.visible_tiles == explored[:3]


def test_complete_rank_manifest_retrieval_limit_and_eviction_count():
    store = initial_experience("a")
    for tick in range(20):
        p = perception(tick=tick, explored=[])
        store = ingest_experience(store, delivery(p), run_id="run")
    result = assemble_context(p, cognitive(p, store=store), profile())
    assert len(result.context.recalled_experience) == 16
    assert [r.experience_id for r in result.manifest.experiences] == [
        f"a:e{i:06d}" for i in range(19, -1, -1)
    ]
    assert all(r.omission == "retrieval_limit" for r in result.manifest.experiences[16:])
    assert result.manifest.evicted_record_count == 0
    trimmed = store.model_copy(update={"records": store.records[-2:]})
    result = assemble_context(p, cognitive(p, store=trimmed), profile())
    assert result.manifest.evicted_record_count == 18
    assert len(result.manifest.experiences) == 2


class StaticBinding:
    """Only an explicit result stub; P3-06 owns the alternate ranking algorithm."""

    retrieval_profile = "recent-only-fixture-v0"
    implementation_sha256 = "f" * 64

    def __init__(self, result):
        self.result = result
        self.queries = []

    def retrieve(self, state, query):
        self.queries.append(query)
        return self.result


@pytest.mark.parametrize("empty", [False, True])
def test_fixture_seam_reports_actual_identity_even_with_equal_hashes(empty):
    p = perception(explored=[])
    state = cognitive(p)
    if empty:
        state = state.model_copy(
            update={"experience": state.experience.model_copy(update={"records": []})}
        )
    binding = StaticBinding(
        RetrievalResult(
            ranked_experience_ids=[r.experience_id for r in state.experience.records],
            selected_records=state.experience.records,
        )
    )
    prod = assemble_context(p, state, profile())
    fake = assemble_context(
        p, state, profile(True), purpose="fake", selector=binding, selector_sha256="f" * 64
    )
    replay = assemble_context(
        p, state, profile(True), purpose="recorded-fake", selector=binding, selector_sha256="f" * 64
    )
    assert canonical_bytes(fake) == canonical_bytes(replay)
    assert fake.context_sha256 == prod.context_sha256
    assert fake.manifest.retrieval_profile == "recent-only-fixture-v0"
    assert fake.manifest.context_profile_id == "p3-context-recent-only-fixture-v0"
    assert fake.manifest != prod.manifest


@pytest.mark.parametrize(
    "change",
    [
        "unknown_profile",
        "wrong_strategy",
        "unknown_projection",
        "unknown_purpose",
        "live_fixture",
        "missing_selector",
        "wrong_pin",
        "wrong_selector",
    ],
)
def test_profile_binding_refuses_before_selection(change):
    p = perception(explored=[])
    state = cognitive(p)
    binding = StaticBinding(
        RetrievalResult(
            ranked_experience_ids=["a:e000000"], selected_records=state.experience.records
        )
    )
    selected = profile(True)
    purpose = "fake"
    pin = "f" * 64
    if change == "unknown_profile":
        selected = selected.model_copy(update={"context_profile_id": "guessed"})
    if change == "wrong_strategy":
        selected = selected.model_copy(update={"retrieval_profile": "recent-relevant-v0"})
    if change == "unknown_projection":
        selected = selected.model_copy(update={"projection_profile": "other"})
    if change == "unknown_purpose":
        purpose = "unknown"
    if change == "live_fixture":
        purpose = "live"
    if change == "missing_selector":
        binding = None
    if change == "wrong_pin":
        pin = "0" * 64
    if change == "wrong_selector":
        binding.retrieval_profile = "recent-relevant-v0"
    with pytest.raises(ValueError):
        assemble_context(p, state, selected, purpose=purpose, selector=binding, selector_sha256=pin)
    if binding is not None:
        assert binding.queries == []


def test_query_uses_structured_fields_and_never_speech_goal_prose_or_static_tiles():
    p = perception(
        explored=tiles(),
        entities=[resident("ryan", (4, 3))],
        sightings=[tree("fruit", (5, 3), sighting=True)],
        cues=[cue("moss", (6, 3))],
        heard_utterances=[heard("u", "secret-in-speech", "statement")],
        canteen=("canteen", 1),
    )
    state = cognitive(p)
    goals = GoalState.model_validate(
        {
            "goal_schema_version": "0.1",
            "next_goal_sequence": 1,
            "current": {
                "goal_id": "a:g000000",
                "text": "secret prose at 99,99",
                "created_at_tick": 0,
                "status": "intended",
                "evidence": None,
                "completion": {
                    "kind": "own_action_success",
                    "action_type": "move_to",
                    "target": {"kind": "tile", "position": {"x": 8, "y": 7}},
                    "parameters": {},
                },
            },
        }
    )
    state = state.model_copy(update={"goals": goals})
    binding = StaticBinding(
        RetrievalResult(
            ranked_experience_ids=[r.experience_id for r in state.experience.records],
            selected_records=state.experience.records,
        )
    )
    assemble_context(
        p, state, profile(True), purpose="fake", selector=binding, selector_sha256="f" * 64
    )
    assert binding.queries == [
        RetrievalQuery(
            query_schema_version="0.1",
            owner_id="a",
            entity_ids=["canteen", "fruit", "moss", "ryan"],
            positions=[
                Coord(x=2, y=2),
                Coord(x=4, y=3),
                Coord(x=5, y=3),
                Coord(x=6, y=3),
                Coord(x=8, y=7),
            ],
        )
    ]


@pytest.mark.parametrize(
    "change", ["owner", "tick", "hidden", "identity", "version", "duplicate_tile"]
)
def test_bad_context_sources_refused(change):
    p = perception(explored=tiles(1, 1))
    state = cognitive(p)
    if change == "owner":
        p = p.model_copy(update={"actor_id": "b"})
    if change == "tick":
        p = p.model_copy(update={"tick": 1})
    if change == "hidden":
        data = state.model_dump(mode="json")
        data["state_delta"] = {}
        with pytest.raises(ValidationError):
            ResidentCognitiveState.model_validate(data)
        return
    if change == "identity":
        state.identity.values.append("rewrite")
    if change == "version":
        state = state.model_copy(update={"cognitive_schema_version": "0.2"})
    if change == "duplicate_tile":
        p.explored_static_tiles.append(p.explored_static_tiles[0])
    with pytest.raises(ValueError):
        assemble_context(p, state, profile())


@pytest.mark.parametrize(
    "change",
    [
        "context_hash",
        "projection_hash",
        "mandatory_bytes",
        "retrieved_flag",
        "projected_record",
        "missing_tile",
        "altered_tile",
        "manifest_identity",
    ],
)
def test_assembly_tampering_is_detected(change):
    p = perception(explored=tiles(2, 2))
    data = assemble(p).model_dump(mode="json")
    if change == "context_hash":
        data["context_sha256"] = "0" * 64
    if change == "projection_hash":
        data["projection_sha256"] = "0" * 64
    if change == "mandatory_bytes":
        data["manifest"]["mandatory_bytes"] += 1
    if change == "retrieved_flag":
        data["manifest"]["experiences"][0]["retrieved"] = False
    if change == "projected_record":
        data["provider_projection"]["recalled_experience"][0]["payload"]["data"]["position"][
            "x"
        ] = 99
    if change == "missing_tile":
        data["manifest"]["static_tiles"].pop()
    if change == "altered_tile":
        data["provider_projection"]["perception"]["explored_static_tiles"][0]["terrain"] = "spring"
    if change == "manifest_identity":
        data["manifest"]["retrieval_profile"] = "recent-only-fixture-v0"
    with pytest.raises(ValueError):
        ContextAssembly.model_validate(data)


@pytest.mark.parametrize("value", [-1, False, 1.5, "150000000"])
def test_budget_money_is_strict_integer_micro_cny(value):
    with pytest.raises(ValueError):
        BudgetCaps(attempts=1, input_tokens=1, output_tokens=1, micro_cny=value)
    assert (
        BudgetCaps(attempts=0, input_tokens=0, output_tokens=0, micro_cny=150000000).micro_cny
        == 150000000
    )


def test_closed_literal_limits_do_not_coerce_bool_to_zero_or_integer_to_false():
    limits = dict(
        profile_id="p3-bounded-v0.1",
        max_attempts=2,
        attempt_timeout_ms=30000,
        decision_timeout_ms=60000,
        retry_delay_ms=0,
        max_input_tokens=32768,
        max_output_tokens=2048,
        max_request_bytes=131072,
        max_response_bytes=262144,
    )
    DecisionLimits.model_validate(limits)
    with pytest.raises(ValueError):
        DecisionLimits.model_validate({**limits, "retry_delay_ms": False})


def allocation():
    key = canonical_sha256({"registration_sha256": "1" * 64, "case_id": "case"})
    return dict(
        allocation_schema_version="0.1",
        allocation_key=key,
        registration_sha256="1" * 64,
        case_id="case",
        caps=dict(attempts=2, input_tokens=100, output_tokens=200, micro_cny=150000000),
        generation=1,
        status="running",
        head=dict(
            checkpoint_sha256="2" * 64,
            checkpoint_tick=0,
            input_manifest_sha256="3" * 64,
            run_directory="run-dir",
            reservation_cursor=0,
        ),
        prepared_head=None,
        pending_recovery_sha256=None,
        entries=[
            dict(
                reservation=dict(
                    allocation_key=key,
                    reservation_ordinal=0,
                    call_id="run:d:a:000000:a0",
                    input_reserved=10,
                    output_reserved=20,
                    money_reserved=1,
                ),
                provider_request_sha256="4" * 64,
                wire_body_sha256="5" * 64,
                state="reserved",
                debit=None,
                terminal_call_sha256=None,
            )
        ],
    )


@pytest.mark.parametrize(
    "change",
    [
        "key",
        "ordinal",
        "duplicate",
        "null_head",
        "head_cursor",
        "settled_without_debit",
        "pending_live",
    ],
)
def test_allocation_dto_preserves_one_case_identity_and_reservation_prefix(change):
    data = allocation()
    CaseAllocationP3.model_validate(data)
    if change == "key":
        data["allocation_key"] = "0" * 64
    if change == "ordinal":
        data["entries"][0]["reservation"]["reservation_ordinal"] = 1
    if change == "duplicate":
        row = copy.deepcopy(data["entries"][0])
        row["reservation"]["reservation_ordinal"] = 1
        data["entries"].append(row)
    if change == "null_head":
        data["head"] = None
    if change == "head_cursor":
        data["head"]["reservation_cursor"] = 1
    if change == "settled_without_debit":
        data["entries"][0]["state"] = "settled"
    if change == "pending_live":
        data["pending_recovery_sha256"] = "6" * 64
    with pytest.raises(ValueError):
        CaseAllocationP3.model_validate(data)


def test_unknown_usage_never_becomes_zero_and_recovery_never_refunds():
    debit = dict(
        call_id="run:d:a:000000:a0",
        input_reserved=10,
        output_reserved=20,
        money_reserved=1,
        input_reported=1,
        output_reported=None,
        input_charged=10,
        output_charged=20,
        money_charged=1,
        usage_unknown=True,
    )
    CallDebit.model_validate(debit)
    for change in ({"usage_unknown": False}, {"input_charged": 1}, {"output_charged": 0}):
        with pytest.raises(ValueError):
            CallDebit.model_validate({**debit, **change})
    row = allocation()["entries"][0]
    row.update(state="recovery", debit={**debit, "money_charged": 0})
    with pytest.raises(ValueError):
        AllocationEntry.model_validate(row)


def rule_record():
    return dict(
        record_schema_version="0.2",
        run_id="run",
        decision_id="run:d:a:000000",
        tick=0,
        actor_id="a",
        decision_ordinal=0,
        policy_id="rule-based-v0",
        effective_policy_id="rule-based-v0",
        triggers=[],
        request_sha256="1" * 64,
        status="ok",
        error_kind=None,
        detail_code=None,
        plan=dict(
            plan_id="a:p000000",
            actor_id="a",
            created_at_tick=0,
            intents=[
                dict(
                    intent_id="a:p000000:i0",
                    plan_id="a:p000000",
                    actor_id="a",
                    action_type="wait",
                    target=None,
                    parameters={},
                    reason=None,
                )
            ],
        ),
        substituted=False,
        llm_call_id=None,
        context_sha256="2" * 64,
        projection_sha256="3" * 64,
        accepted_delta=dict(
            delta_schema_version="0.1",
            goal_change=dict(operation="continue", expected_goal_id=None, proposal=None),
        ),
        call_ids=[],
        state_before_sha256="4" * 64,
        state_after_sha256="5" * 64,
        fallback_error=None,
        policy_private_after=dict(
            private_schema_version="0.1",
            mode="fallback",
            last_fallback_ordinal=0,
            fallback_state=dict(
                rule_state_version="0.1",
                commitment=None,
                issued_intents=[],
                failed_targets=[],
                cue_impressions=[],
                canteen_capacity=None,
            ),
        ),
        budget_debits=[],
    )


@pytest.mark.parametrize(
    "change",
    [
        "decision_id",
        "plan_id",
        "intent_id",
        "tick",
        "ordinal",
        "status",
        "replay_error",
        "effective_policy",
        "call_id",
        "fallback_error",
        "private_mode",
        "delta",
    ],
)
def test_decision_record_enforces_own_ids_and_primary_fallback_semantics(change):
    data = rule_record()
    DecisionRecordP3.model_validate(data)
    if change == "decision_id":
        data["decision_id"] = "foreign:d:a:000000"
    if change == "plan_id":
        data["plan"]["plan_id"] = "b:p000000"
    if change == "intent_id":
        data["plan"]["intents"][0]["intent_id"] = "a:p000000:i1"
    if change == "tick":
        data["tick"] = 1
    if change == "ordinal":
        data["decision_ordinal"] = 1
    if change == "status":
        data["status"] = "error"
    if change == "replay_error":
        data.update(status="error", error_kind="REPLAY_DIVERGED", substituted=True)
    if change == "effective_policy":
        data["effective_policy_id"] = "llm-v0"
    if change == "call_id":
        data["call_ids"] = ["run:d:a:000000:a0"]
    if change == "fallback_error":
        data["fallback_error"] = "INVALID_PLAN"
    if change == "private_mode":
        data["policy_private_after"]["mode"] = "llm"
    if change == "delta":
        data["accepted_delta"]["goal_change"] = {
            "operation": "abandon",
            "expected_goal_id": "a:g000000",
            "proposal": None,
        }
    with pytest.raises(ValueError):
        DecisionRecordP3.model_validate(data)


def test_wait_substitute_requires_error_and_continue_without_legacy_record_reuse():
    data = rule_record()
    data.update(
        status="error",
        error_kind="INVALID_PLAN",
        substituted=True,
        effective_policy_id="sim-fallback-wait",
        fallback_error="INVALID_PLAN",
    )
    record = DecisionRecordP3.model_validate(data)
    assert record.record_schema_version == "0.2"
    data["plan"]["intents"][0]["reason"] = "invented reason"
    with pytest.raises(ValueError):
        DecisionRecordP3.model_validate(data)


def provider_result(body=b"{}"):
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return dict(
        provider_result_version="0.1",
        outcome="response",
        raw_response=text,
        raw_body_base64=base64.b64encode(body).decode("ascii"),
        observed_body_bytes=len(body),
        response_complete=True,
        response_text=None,
        provider_request_id=None,
        token_input=None,
        token_output=None,
        latency_ms=None,
        provider_error_code=None,
    )


@pytest.mark.parametrize("body", [b"", b"{}", b"\xff"])
def test_provider_result_preserves_exact_bytes_without_inventing_utf8(body):
    data = provider_result(body)
    ProviderResult.model_validate(data)
    with pytest.raises(ValueError):
        ProviderResult.model_validate({**data, "raw_response": "replaced"})
    with pytest.raises(ValueError):
        ProviderResult.model_validate({**data, "observed_body_bytes": len(body) + 1})


def test_response_sentinel_is_bounded_and_never_extracts_incomplete_output():
    data = provider_result(b"x" * 262144)
    data.update(observed_body_bytes=262145, outcome="output_limit", response_complete=False)
    ProviderResult.model_validate(data)
    for change in (
        {"response_complete": True},
        {"outcome": "response"},
        {"response_text": "partial"},
        {"observed_body_bytes": 262146},
    ):
        with pytest.raises(ValueError):
            ProviderResult.model_validate({**data, **change})


@pytest.mark.parametrize("body", ["?", "eA=", "eB==", "eA==\n"])
def test_wire_request_rejects_noncanonical_base64(body):
    with pytest.raises(ValueError):
        WireRequest(
            wire_schema_version="0.1",
            method="POST",
            origin="https://api.deepseek.com",
            path="/responses",
            content_type="application/json",
            body_base64=body,
        )


@pytest.mark.parametrize("prior_mode", ["llm", "fallback"])
def test_malformed_rule_wait_can_preserve_entire_prior_private_state(prior_mode):
    data = rule_record()
    data.update(
        policy_id="llm-v0",
        status="error",
        error_kind="BUDGET",
        detail_code="ADMISSION_DENIED",
        substituted=True,
        effective_policy_id="sim-fallback-wait",
        fallback_error="INVALID_PLAN",
    )
    data["policy_private_after"].update(mode=prior_mode, last_fallback_ordinal=None)
    prior = copy.deepcopy(data["policy_private_after"])
    record = DecisionRecordP3.model_validate(data)
    assert record.policy_private_after.model_dump(mode="json") == prior


def test_ex09_completed_evidence_survives_real_byte_eviction_and_pure_reexecution():
    def sequence(restore):
        p0 = perception(explored=[])
        state = cognitive(p0)
        goal = apply_goal_change(
            initial_goal_state(),
            GoalChange.model_validate(
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
            ),
            actor_id="a",
            tick=0,
        )
        plan = ActionPlan.model_validate(rule_record()["plan"])
        store = capture_accepted_decision(
            state.experience,
            "run",
            "run:d:a:000000",
            0,
            plan,
            goal.current.goal_id,
            max_plan_actions=5,
        )
        p1 = perception(
            tick=1,
            explored=[],
            feedback=ActionFeedback(
                intent_id="a:p000000:i0",
                status="success",
                failure_code=None,
                interruption_reason=None,
                visible_effects=[],
            ),
        )
        goal = advance_goal_evidence(delivery(p1), store.intent_refs, goal, run_id="run")
        store = ingest_experience(store, delivery(p1), run_id="run")
        evidence = canonical_bytes(goal)
        assert goal.current.status == "observed_complete"
        assert any(r.kind == "action_feedback" for r in store.records)
        speech = heard("large", "ryan", "statement", tick=2).model_copy(
            update={"text": "x" * 1048577}
        )
        p2 = perception(tick=2, explored=[], heard_utterances=[speech])
        store = ingest_experience(store, delivery(p2), run_id="run")
        assert store.records == []
        assert canonical_bytes(goal) == evidence
        state = cognitive(p2, store=store, goals=goal)
        if restore:
            state = ResidentCognitiveState.model_validate_json(canonical_bytes(state))
        p3 = perception(tick=3, explored=[])
        store = ingest_experience(state.experience, delivery(p3), run_id="run")
        assembly = assemble_context(p3, cognitive(p3, store=store, goals=state.goals), profile())
        assert canonical_bytes(assembly.context.goals) == evidence
        assert [r.kind for r in assembly.context.recalled_experience] == ["own_state"]
        assert assembly.manifest.evicted_record_count == 6
        return canonical_bytes(assembly)

    assert sequence(False) == sequence(True)


def test_context_rejects_future_goal_and_foreign_or_future_complete_evidence():
    p0 = perception(explored=[])
    goal = apply_goal_change(
        initial_goal_state(),
        GoalChange.model_validate(
            {
                "operation": "revise",
                "expected_goal_id": None,
                "proposal": {
                    "text": "Wait",
                    "completion": {
                        "kind": "own_action_success",
                        "action_type": "wait",
                        "target": None,
                        "parameters": {},
                    },
                },
            }
        ),
        actor_id="a",
        tick=99,
    )
    with pytest.raises(ValueError):
        cognitive(p0, goals=goal)
    goal = goal.model_copy(
        update={"current": goal.current.model_copy(update={"created_at_tick": 0})}
    )
    store = capture_accepted_decision(
        cognitive(p0).experience,
        "run",
        "run:d:a:000000",
        0,
        ActionPlan.model_validate(rule_record()["plan"]),
        goal.current.goal_id,
        max_plan_actions=5,
    )
    p1 = perception(
        tick=1,
        explored=[],
        feedback=ActionFeedback(
            intent_id="a:p000000:i0",
            status="success",
            failure_code=None,
            interruption_reason=None,
            visible_effects=[],
        ),
    )
    completed = advance_goal_evidence(delivery(p1), store.intent_refs, goal, run_id="run")
    with pytest.raises(ValueError):
        cognitive(p0, store=store, goals=completed)
    later = ingest_experience(store, delivery(p1), run_id="run")
    foreign = completed.model_dump(mode="json")
    foreign["current"]["evidence"]["delivery_id"] = format_delivery_id("foreign", 1, "a")
    foreign["current"]["evidence"]["owned_intent"]["decision_id"] = "foreign:d:a:000000"
    with pytest.raises(ValueError):
        cognitive(p1, store=later, goals=GoalState.model_validate(foreign))
