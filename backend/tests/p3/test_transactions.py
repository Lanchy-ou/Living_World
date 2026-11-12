"""P3 resident transaction vectors, injected failures, and offline replay sentinels."""

from __future__ import annotations

import base64
import copy
import json

import pytest
from test_cognition import WAIT, config, goal_change, perception, proposal, request

from living_island.agents.p3.cognition import validate_proposal
from living_island.agents.p3.runtime import (
    ProviderOverrun,
    ReplayDiverged,
    create_p3_runtime,
    debit_for_result,
)
from living_island.agents.p3.types import (
    CallReservation,
    P3PolicyConfig,
    PricingPin,
    ProviderResult,
    WireRequest,
)
from living_island.memory.p3_types import canonical_bytes, canonical_sha256
from living_island.world.protocol import (
    ActionFeedback,
    BoundaryPerceptionDelivery,
    format_delivery_id,
)


def delivery(tick=0, *, run="runtime-test", feedback=None, speech=None):
    return BoundaryPerceptionDelivery(
        delivery_id=format_delivery_id(run, tick, "ella"),
        actor_id="ella",
        observed_tick=tick,
        perception=perception(tick=tick, feedback=feedback, speech=speech),
        decision_triggers=[] if tick == 0 else ["PLAN_FINISHED"],
    )


def response(text=None, *, outcome="response", token_input=80, token_output=10):
    if text is None and outcome == "response":
        text = proposal(goal_change(), WAIT).model_dump_json()
    body = None if text is None else text.encode("utf-8")
    return ProviderResult(
        provider_result_version="0.1",
        outcome=outcome,
        raw_response=text,
        raw_body_base64=None if body is None else base64.b64encode(body).decode(),
        observed_body_bytes=0 if body is None else len(body),
        response_complete=body is not None,
        response_text=text,
        provider_request_id=None,
        token_input=token_input,
        token_output=token_output,
        latency_ms=1,
        provider_error_code=None,
    )


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value


class Sentinel:
    def __getattribute__(self, name):
        raise AssertionError(f"external replay access: {name}")


class FakeProvider:
    def __init__(self, outputs=None, *, timeline=None, clock=None, elapsed=None, count=100):
        self.outputs = list(outputs or [response()])
        self.timeline = timeline if timeline is not None else []
        self.clock = clock
        self.elapsed = list(elapsed or [0] * len(self.outputs))
        self.count = count
        self.calls = []
        self.prepares = 0
        self.counters = 0

    def prepare(self, request):
        self.prepares += 1
        self.timeline.append("prepare")
        return WireRequest(
            wire_schema_version="0.1",
            method="POST",
            origin="https://api.deepseek.com",
            path="/responses",
            content_type="application/json",
            body_base64=base64.b64encode(canonical_bytes(request)).decode(),
        )

    def count_input_tokens(self, request, wire):
        self.counters += 1
        self.timeline.append("count")
        return self.count

    def complete(self, request, wire, timeout_ms):
        self.timeline.append("complete")
        self.calls.append((request, wire, timeout_ms))
        index = len(self.calls) - 1
        if self.clock is not None:
            self.clock.value += self.elapsed[index]
        output = self.outputs[index]
        if isinstance(output, Exception):
            raise output
        return output


class FakeBudget:
    def __init__(self, pricing, *, timeline=None, deny_after=None):
        self.pricing = pricing
        self.timeline = timeline if timeline is not None else []
        self.deny_after = deny_after
        self.reservations = []

    def admit(
        self, call_id, input_tokens, output_tokens, provider_request_sha256, wire_body_sha256
    ):
        self.timeline.append("admit")
        if self.deny_after is not None and len(self.reservations) >= self.deny_after:
            return None
        price = self.pricing
        money = (input_tokens * price.input_micro_cny_per_million_tokens + 999999) // 1000000 + (
            output_tokens * price.output_micro_cny_per_million_tokens + 999999
        ) // 1000000
        reservation = CallReservation(
            allocation_key="a" * 64,
            reservation_ordinal=len(self.reservations),
            call_id=call_id,
            input_reserved=input_tokens,
            output_reserved=output_tokens,
            money_reserved=money,
        )
        self.reservations.append(reservation)
        return reservation

    def commit(self, decision_id, debits):
        raise AssertionError("only the coordinator commits budget")


class Journal:
    def __init__(self, *, timeline=None, fail=None):
        self.timeline = timeline if timeline is not None else []
        self.contexts, self.dispatches, self.calls = [], [], []
        self.fail = fail

    def stage_context(self, record):
        self.timeline.append("context")
        if self.fail == "context":
            raise OSError("injected context flush failure")
        self.contexts.append(record)

    def before_call(self, context, record):
        self.timeline.append("dispatch")
        if self.fail == "dispatch":
            raise OSError("injected dispatch flush failure")
        assert context == self.contexts[-1]
        self.dispatches.append(record)

    def after_call(self, record):
        self.timeline.append("terminal")
        if self.fail == "terminal":
            raise OSError("injected terminal flush failure")
        self.calls.append(record)


class FakeFallback:
    def __init__(self, cfg, *, malformed=False, error=None):
        self.config = cfg
        self.malformed = malformed
        self.error = error
        self.calls = []

    def decide(self, req, state):
        self.calls.append((req, state))
        if self.error is not None:
            raise self.error
        current = req.context.goals.current
        change = goal_change(expected=None if current is None else current.goal_id)
        plan, _ = validate_proposal(proposal(change, WAIT), req, self.config)
        # Mutate nested copies to prove the runtime did not lend committed private state.
        state.fallback_state.cue_impressions.clear()
        private = state.model_copy(
            update={"mode": "fallback", "last_fallback_ordinal": req.decision_ordinal}
        )
        if self.malformed:
            plan = plan.model_copy(update={"created_at_tick": req.tick + 1})
        return plan, private


def setup(
    *,
    outputs=None,
    policy="llm-v0",
    live=True,
    malformed=False,
    clock=None,
    elapsed=None,
    count=100,
    deny_after=None,
    fail=None,
    fallback_error=None,
    restored=None,
    own_records=None,
    own_contexts=None,
    external_sentinel=False,
    run="runtime-test",
    cfg=None,
):
    identity = request().context.identity
    cfg = cfg or config(request())
    if cfg.policy_id != policy:
        cfg = P3PolicyConfig.model_validate({**cfg.model_dump(mode="json"), "policy_id": policy})
    timeline = []
    provider = FakeProvider(outputs, timeline=timeline, clock=clock, elapsed=elapsed, count=count)
    budget = FakeBudget(cfg.pricing, timeline=timeline, deny_after=deny_after)
    journal = Journal(timeline=timeline, fail=fail)
    fallback = FakeFallback(cfg, malformed=malformed, error=fallback_error)
    runtime = create_p3_runtime(
        "ella",
        cfg,
        identity,
        restored,
        live_enabled=live,
        provider=Sentinel() if external_sentinel else provider,
        budget=Sentinel() if external_sentinel else budget,
        attempts=Sentinel() if external_sentinel else journal,
        fallback=Sentinel() if external_sentinel else fallback,
        own_records=own_records,
        own_contexts=own_contexts,
        run_id=run,
        purpose="fake",
        clock_ms=clock or Clock(),
    )
    return runtime, provider, budget, journal, fallback, timeline


def decide(runtime, tick=0, *, feedback=None):
    packet = delivery(tick, feedback=feedback)
    runtime.ingest(packet)
    return runtime.decide(runtime.make_request(tick, packet.decision_triggers))


def test_bd01_stages_whole_transaction_then_publishes_once():
    runtime, provider, budget, journal, fallback, timeline = setup()
    runtime.ingest(delivery())
    before = runtime.export_state()
    req = runtime.make_request(0, [])
    with pytest.raises(ValueError, match="awaiting"):
        runtime.export_state()
    record = runtime.decide(req)
    assert record.status == "ok" and record.effective_policy_id == "llm-v0"
    assert record.state_before_sha256 == canonical_sha256(before)
    assert record.plan.plan_id == "ella:p000000"
    assert record.plan.intents[0].intent_id == "ella:p000000:i0"
    assert timeline == ["prepare", "count", "context", "admit", "dispatch", "complete", "terminal"]
    assert len(provider.calls) == len(budget.reservations) == len(journal.calls) == 1
    assert fallback.calls == []
    with pytest.raises(ValueError):
        runtime.commit_decision(record.model_copy(update={"state_after_sha256": "0" * 64}))
    with pytest.raises(ValueError):
        runtime.decide(req)
    runtime.commit_decision(record)
    after = runtime.export_state()
    assert after.next_decision_ordinal == 1 and canonical_sha256(after) == record.state_after_sha256
    assert [r.kind for r in after.cognitive_state.experience.records] == [
        "own_state",
        "accepted_decision",
    ]
    assert after.cognitive_state.goals.current is None
    with pytest.raises(ValueError):
        runtime.commit_decision(record)
    with pytest.raises(ValueError):
        runtime.make_request(0, [])


def test_bd02_invalid_delta_then_success_uses_same_request_and_one_capture():
    bad = proposal(goal_change(expected="ella:g999999"), WAIT)
    good = proposal(goal_change("revise"), WAIT)
    runtime, provider, _, journal, fallback, _ = setup(
        outputs=[response(bad.model_dump_json()), response(good.model_dump_json())]
    )
    record = decide(runtime)
    assert [r.validation_error for r in journal.calls] == ["INVALID_DELTA", None]
    assert provider.calls[0][:2] == provider.calls[1][:2]
    assert provider.prepares == provider.counters == 1
    assert len(record.budget_debits) == 2 and fallback.calls == []
    runtime.commit_decision(record)
    state = runtime.export_state()
    assert state.cognitive_state.goals.current.goal_id == "ella:g000000"
    assert sum(r.kind == "accepted_decision" for r in state.cognitive_state.experience.records) == 1
    assert journal.contexts[0].request.context.goals.current is None


def test_bd03_both_parse_failures_fallback_once_and_no_model_capture():
    runtime, _, _, journal, fallback, _ = setup(outputs=[response("bad"), response("[]")])
    record = decide(runtime)
    assert (record.error_kind, record.detail_code) == ("PARSE_ERROR", "INVALID_JSON")
    assert len(record.call_ids) == 2 and record.llm_call_id == record.call_ids[1]
    assert record.accepted_delta.goal_change.operation == "continue"
    assert len(fallback.calls) == 1
    runtime.commit_decision(record)
    assert runtime.export_state().policy_private.last_fallback_ordinal == 0
    assert all(c.parsed_proposal is None for c in journal.calls)


@pytest.mark.parametrize(
    "counts, expected",
    [
        ((80, 10), (80, 10, 105, False)),
        ((80, None), (100, 20, 165, True)),
        ((None, 10), (100, 20, 165, True)),
    ],
)
def test_bd05_bd06_exact_money_and_unknown_usage(counts, expected):
    pricing = PricingPin(
        currency="CNY",
        date="2026-11-12",
        source_url="fixture",
        input_micro_cny_per_million_tokens=750000,
        output_micro_cny_per_million_tokens=4500000,
    )
    reservation = CallReservation(
        allocation_key="a" * 64,
        reservation_ordinal=0,
        call_id="c0",
        input_reserved=100,
        output_reserved=20,
        money_reserved=165,
    )
    debit = debit_for_result(
        reservation, response(token_input=counts[0], token_output=counts[1]), pricing
    )
    assert (
        debit.input_charged,
        debit.output_charged,
        debit.money_charged,
        debit.usage_unknown,
    ) == expected
    assert (debit.input_reported, debit.output_reported) == counts


def test_bd07_admission_denied_is_zero_dispatch_with_context():
    runtime, provider, _, journal, fallback, _ = setup(deny_after=0)
    record = decide(runtime)
    assert (record.error_kind, record.detail_code) == ("BUDGET", "ADMISSION_DENIED")
    assert len(journal.contexts) == len(fallback.calls) == 1
    assert record.call_ids == record.budget_debits == provider.calls == journal.dispatches == []


def test_bd12_replay_success_and_fallback_never_access_any_external_port():
    runtime, _, _, journal, _, _ = setup(outputs=[response(), response("bad"), response("bad")])
    records = []
    for tick in range(2):
        record = decide(runtime, tick)
        records.append(record)
        runtime.commit_decision(record)
    for _ in range(2):
        replay, *_ = setup(
            own_records=records, own_contexts=journal.contexts, external_sentinel=True
        )
        for tick, source in enumerate(records):
            observed = decide(replay, tick)
            assert canonical_bytes(observed) == canonical_bytes(source)
            replay.commit_decision(observed)
        assert canonical_bytes(replay.export_state()) == canonical_bytes(runtime.export_state())


def test_bd15_rule_primary_no_provider_and_ordinary_success():
    runtime, provider, budget, journal, fallback, timeline = setup(policy="rule-based-v0")
    runtime._provider = Sentinel()
    runtime._budget = Sentinel()
    record = decide(runtime)
    runtime.commit_decision(record)
    assert (record.status, record.effective_policy_id, record.substituted) == (
        "ok",
        "rule-based-v0",
        False,
    )
    assert record.error_kind is None and record.call_ids == record.budget_debits == []
    assert runtime.export_state().policy_private.last_fallback_ordinal == 0
    assert timeline == ["context"] and journal.contexts[0].provider_request is None
    assert len(fallback.calls) == 1 and provider.calls == budget.reservations == []


@pytest.mark.parametrize("elapsed, status", [(59999, "ok"), (60000, "error"), (60001, "error")])
def test_bd17_total_deadline_after_parse_retains_proposal_and_debit(elapsed, status):
    clock = Clock()
    runtime, _, _, journal, fallback, _ = setup(clock=clock, elapsed=[elapsed])
    record = decide(runtime)
    assert record.status == status
    assert journal.calls[0].parsed_proposal is not None and len(record.budget_debits) == 1
    if status == "error":
        assert (record.error_kind, record.detail_code) == ("TIMEOUT", "DECISION_TIMEOUT")
        assert (
            len(fallback.calls) == 1 and record.accepted_delta.goal_change.operation == "continue"
        )
    else:
        assert fallback.calls == []


def test_bd04_oversized_mandatory_context_never_touches_provider_or_budget():
    from rule_policy_builders import heard

    runtime, provider, budget, journal, fallback, _ = setup()
    runtime._provider = Sentinel()
    runtime._budget = Sentinel()
    speech = heard("u", "ryan", "statement", tick=0).model_copy(update={"text": "x" * 65536})
    runtime.ingest(delivery(speech=[speech]))
    record = runtime.decide(runtime.make_request(0, []))
    assert (record.error_kind, record.detail_code) == ("INVALID_CONTEXT", "MANDATORY_OVERSIZE")
    assert record.projection_sha256 is None and journal.contexts[0].provider_request is None
    assert len(journal.contexts) == len(fallback.calls) == 1
    assert record.call_ids == provider.calls == budget.reservations == []


def test_bd14_failed_delivered_goal_evidence_survives_bad_model_and_fallback():
    from test_cognition import GIVE

    first = proposal(goal_change("revise"), GIVE)
    runtime, _, _, _, _, _ = setup(
        outputs=[response(first.model_dump_json()), response("bad"), response("bad")]
    )
    record = decide(runtime)
    runtime.commit_decision(record)
    feedback = ActionFeedback(
        intent_id=record.plan.intents[0].intent_id,
        status="failure",
        failure_code="OUT_OF_REACH",
        interruption_reason=None,
        visible_effects=[],
    )
    second = decide(runtime, 1, feedback=feedback)
    runtime.commit_decision(second)
    cognitive = runtime.export_state().cognitive_state
    assert cognitive.goals.current.status == "attempted"
    assert cognitive.goals.current.evidence.feedback == feedback
    memories = [r for r in cognitive.experience.records if r.kind == "action_feedback"]
    assert (
        len(memories) == 1
        and memories[0].payload.data.owned_intent.intent == record.plan.intents[0]
    )
    assert cognitive.experience.intent_refs[0].intent == second.plan.intents[0]


@pytest.mark.parametrize(
    "text, kind, detail",
    [
        ("{", "PARSE_ERROR", "INVALID_JSON"),
        ("[]", "PARSE_ERROR", "INVALID_JSON"),
        (
            '{"proposal_schema_version":"0.1","proposal_schema_version":"0.1","actions":[],"cognitive_delta":{}}',
            "PARSE_ERROR",
            "INVALID_JSON",
        ),
        (
            '{"proposal_schema_version":"9","actions":[],"cognitive_delta":{}}',
            "PARSE_ERROR",
            "INVALID_JSON",
        ),
        (
            '{"proposal_schema_version":"0.1","actions":[],"cognitive_delta":{}}',
            "INVALID_PLAN",
            "INVALID_ACTION",
        ),
        (
            '{"proposal_schema_version":"0.1","actions":[{"action_type":"teleport","target":null,"parameters":{},"reason":null}],"cognitive_delta":{}}',
            "INVALID_PLAN",
            "INVALID_ACTION",
        ),
        (
            '{"proposal_schema_version":"0.1","actions":[{"action_type":"wait","target":null,"parameters":{},"reason":null}],"cognitive_delta":{}}',
            "INVALID_DELTA",
            "INVALID_COGNITION",
        ),
        (
            '{"proposal_schema_version":"0.1","actions":NaN,"cognitive_delta":{}}',
            "PARSE_ERROR",
            "INVALID_JSON",
        ),
    ],
)
def test_error_priority_and_closed_json(text, kind, detail):
    runtime, _, _, journal, fallback, _ = setup(outputs=[response(text), response(text)])
    record = decide(runtime)
    assert (record.error_kind, record.detail_code) == (kind, detail)
    assert all((r.validation_error, r.detail_code) == (kind, detail) for r in journal.calls)
    assert len(fallback.calls) == 1


@pytest.mark.parametrize(
    "outcome, expected",
    [
        ("timeout", ("TIMEOUT", "ATTEMPT_TIMEOUT")),
        ("provider_error", ("PROVIDER_ERROR", "PROVIDER_REJECTED")),
        ("output_limit", ("PARSE_ERROR", "OUTPUT_LIMIT")),
    ],
)
def test_adapter_classification_precedes_json(outcome, expected):
    result = response("invalid", outcome=outcome)
    runtime, _, _, _, _, _ = setup(outputs=[result, result])
    record = decide(runtime)
    assert (record.error_kind, record.detail_code) == expected


def test_invalid_utf8_keeps_raw_bytes_and_classifies_parse_error():
    result = response().model_copy(
        update={
            "raw_response": None,
            "raw_body_base64": "/w==",
            "observed_body_bytes": 1,
            "response_text": None,
        }
    )
    runtime, _, _, journal, _, _ = setup(outputs=[result, result])
    record = decide(runtime)
    assert (record.error_kind, record.detail_code) == ("PARSE_ERROR", "INVALID_JSON")
    assert journal.calls[0].result.raw_body_base64 == "/w=="


@pytest.mark.parametrize("count", [32769, 100000])
def test_input_token_limit_zero_calls_and_null_dispatchable_request(count):
    runtime, provider, budget, journal, fallback, _ = setup(count=count)
    record = decide(runtime)
    assert (record.error_kind, record.detail_code) == ("INVALID_CONTEXT", "INPUT_LIMIT")
    assert record.call_ids == provider.calls == budget.reservations == []
    assert journal.contexts[0].provider_request is None and len(fallback.calls) == 1


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_invalid_counter_is_fatal_without_fallback(count):
    runtime, provider, _, journal, fallback, _ = setup(count=count)
    with pytest.raises(ValueError, match="counter"):
        decide(runtime)
    assert provider.calls == journal.calls == fallback.calls == []
    with pytest.raises(ValueError, match="failed"):
        runtime.export_state()


def test_provider_overrun_retains_terminal_then_halts_without_retry_or_fallback():
    runtime, provider, _, journal, fallback, _ = setup(outputs=[response(token_input=101)])
    with pytest.raises(ProviderOverrun):
        decide(runtime)
    assert len(provider.calls) == len(journal.calls) == 1 and fallback.calls == []
    assert journal.calls[0].debit.input_charged == 101
    assert journal.calls[0].debit.output_charged == 2048
    with pytest.raises(ValueError, match="failed"):
        runtime.export_state()


@pytest.mark.parametrize(
    "fail, expected_reservations, expected_calls",
    [
        ("context", 0, 0),
        ("dispatch", 1, 0),
        ("terminal", 1, 1),
    ],
)
def test_persistent_phase_failure_keeps_reservation_and_prevents_commit(
    fail, expected_reservations, expected_calls
):
    runtime, provider, budget, _, fallback, _ = setup(fail=fail)
    with pytest.raises(OSError):
        decide(runtime)
    assert len(budget.reservations) == expected_reservations
    assert len(provider.calls) == expected_calls and fallback.calls == []
    with pytest.raises(ValueError, match="failed"):
        runtime.export_state()
    with pytest.raises(ValueError):
        runtime.ingest(delivery(1))


def test_unexpected_provider_exception_propagates_without_fallback():
    runtime, _, budget, journal, fallback, _ = setup(outputs=[RuntimeError("provider bug")])
    with pytest.raises(RuntimeError, match="provider bug"):
        decide(runtime)
    assert len(budget.reservations) == len(journal.dispatches) == 1
    assert journal.calls == fallback.calls == []


def test_fallback_exception_propagates_even_value_error():
    runtime, *_ = setup(deny_after=0, fallback_error=ValueError("fallback bug"))
    with pytest.raises(ValueError, match="fallback bug"):
        decide(runtime)


@pytest.mark.parametrize("policy", ["llm-v0", "rule-based-v0"])
def test_malformed_fallback_preserves_entire_prior_private(policy):
    runtime, _, _, _, fallback, _ = setup(policy=policy, deny_after=0, malformed=True)
    before = runtime.export_state().policy_private
    record = decide(runtime)
    assert (
        record.effective_policy_id == "sim-fallback-wait"
        and record.fallback_error == "INVALID_PLAN"
    )
    assert record.policy_private_after == before and len(fallback.calls) == 1
    assert record.plan.intents[0].action_type == "wait" and record.plan.intents[0].reason is None
    if policy == "rule-based-v0":
        assert (record.error_kind, record.detail_code) == ("INVALID_PLAN", "INVALID_ACTION")
    runtime.commit_decision(record)
    assert runtime.export_state().policy_private == before


def test_offline_every_llm_decision_is_recovery_offline_without_provider_or_budget():
    runtime, _, _, journal, fallback, _ = setup(live=False)
    runtime._provider = runtime._budget = Sentinel()
    for tick in range(3):
        record = decide(runtime, tick)
        assert (record.error_kind, record.detail_code) == ("PROVIDER_ERROR", "RECOVERY_OFFLINE")
        assert record.call_ids == record.budget_debits == []
        runtime.commit_decision(record)
    assert len(journal.contexts) == len(fallback.calls) == 3


def test_timeout_uses_remaining_decision_deadline_and_records_both_attempts():
    clock = Clock()
    runtime, provider, _, journal, _, _ = setup(
        outputs=[response(outcome="timeout", token_input=None, token_output=None), response()],
        clock=clock,
        elapsed=[30000, 30000],
    )
    record = decide(runtime)
    assert [c[2] for c in provider.calls] == [30000, 30000]
    assert record.detail_code == "DECISION_TIMEOUT" and len(journal.calls) == 2
    assert record.budget_debits[0].usage_unknown


def test_preparation_deadline_prevents_admission_or_shortens_next_timeout():
    for elapsed, expected_calls in [(59000, 1), (60000, 0)]:
        clock = Clock()
        runtime, provider, budget, journal, _, _ = setup(clock=clock)
        runtime.ingest(delivery())
        req = runtime.make_request(0, [])
        clock.value = elapsed
        record = runtime.decide(req)
        assert len(provider.calls) == len(budget.reservations) == expected_calls
        assert len(journal.contexts) == 1
        if expected_calls:
            assert provider.calls[0][2] == 1000 and record.status == "ok"
        else:
            assert record.detail_code == "DECISION_TIMEOUT"


def test_ingestion_duplicate_gap_wrong_run_are_atomic_and_no_decision_is_required():
    runtime, *_ = setup()
    runtime.ingest(delivery())
    before = canonical_bytes(runtime.export_state())
    for packet in [delivery(), delivery(2), delivery(1, run="foreign")]:
        with pytest.raises(ValueError):
            runtime.ingest(packet)
        assert canonical_bytes(runtime.export_state()) == before
    runtime.ingest(delivery(1))
    assert runtime.export_state().latest_perception_tick == 1
    assert runtime.export_state().next_decision_ordinal == 0


def test_nested_request_return_and_export_are_not_runtime_owned():
    runtime, *_ = setup()
    runtime.ingest(delivery())
    exported = runtime.export_state()
    exported.cognitive_state.experience.records.clear()
    assert len(runtime.export_state().cognitive_state.experience.records) == 1
    req = runtime.make_request(0, [])
    req.context.recalled_experience.clear()
    with pytest.raises(ValueError, match="prepared"):
        runtime.decide(req)


def test_abort_cannot_refund_or_reuse_an_attempt():
    runtime, provider, budget, journal, _, _ = setup()
    record = decide(runtime)
    runtime.abort_pending()
    assert len(provider.calls) == len(budget.reservations) == len(journal.calls) == 1
    with pytest.raises(ValueError):
        runtime.commit_decision(record)
    with pytest.raises(ValueError, match="failed"):
        runtime.ingest(delivery(1))


def test_restored_runtime_is_cold_and_continuation_matches_uninterrupted_state():
    runtime, *_ = setup(outputs=[response(), response()])
    record = decide(runtime)
    runtime.commit_decision(record)
    saved = runtime.export_state()
    restored, *_ = setup(restored=saved)
    with pytest.raises(ValueError, match="fresh"):
        restored.make_request(1, ["PLAN_FINISHED"])
    for target in [runtime, restored]:
        target.commit_decision(decide(target, 1))
    assert canonical_bytes(restored.export_state()) == canonical_bytes(runtime.export_state())
    with pytest.raises(ValueError, match="trusted run"):
        setup(restored=saved, run=None)
    with pytest.raises(ValueError, match="another run"):
        setup(restored=saved, run="foreign")


@pytest.mark.parametrize(
    "field",
    [
        "request_sha256",
        "context_sha256",
        "projection_sha256",
        "state_before_sha256",
        "state_after_sha256",
    ],
)
def test_replay_tampered_semantic_hash_is_fatal_without_external_access(field):
    runtime, _, _, journal, _, _ = setup()
    record = decide(runtime)
    runtime.commit_decision(record)
    changed = record.model_copy(update={field: "0" * 64})
    replay, *_ = setup(own_records=[changed], own_contexts=journal.contexts, external_sentinel=True)
    with pytest.raises(ReplayDiverged):
        decide(replay)
    with pytest.raises(ValueError, match="failed"):
        replay.export_state()


def test_empty_replay_requires_context_slice_and_never_falls_back():
    with pytest.raises(ValueError, match="complete own context"):
        setup(own_records=[])
    replay, *_ = setup(own_records=[], own_contexts=[], external_sentinel=True)
    with pytest.raises(ReplayDiverged, match="exhausted"):
        decide(replay)


def test_replay_compares_provider_request_bytes_not_just_projection():
    runtime, _, _, journal, _, _ = setup()
    record = decide(runtime)
    context = journal.contexts[0]
    altered_request = context.provider_request.model_copy(update={"model_id": "different-model"})
    altered_context = context.model_copy(update={"provider_request": altered_request})
    replay, *_ = setup(own_records=[record], own_contexts=[altered_context], external_sentinel=True)
    with pytest.raises(ReplayDiverged, match="provider request"):
        decide(replay)


def test_unknown_nested_restored_version_is_refused_before_dispatch():
    runtime, *_ = setup()
    saved = runtime.export_state()
    bad = copy.deepcopy(saved.model_dump(mode="json"))
    bad["cognitive_state"]["experience"]["experience_schema_version"] = "9"
    with pytest.raises(ValueError):
        type(saved).model_validate(bad)


def test_unicode_action_invalidity_precedes_cognitive_invalidity():
    body = json.loads(response().response_text)
    body["actions"][0]["reason"] = "\ud800"
    body["cognitive_delta"] = {}
    bad = response(json.dumps(body))
    runtime, *_ = setup(outputs=[bad, bad])
    assert decide(runtime).error_kind == "INVALID_PLAN"
