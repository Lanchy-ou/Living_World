import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from living_island.agents.llm.provider import MODEL_ID, TransportResponse
from living_island.agents.v2.calls.contracts import Contract, digest, json_bytes
from living_island.agents.v2.calls.fake import FakeClock, FakeTransport, ScriptedReply
from living_island.agents.v2.calls.guard import Assembly, Call, prepare
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.calls.provider import Terminal
from living_island.agents.v2.calls.wire import frame
from living_island.agents.v2.decision.caller import Caller
from living_island.persistence.v2.audit import AuditReader, AuditWriter
from living_island.sim.v2.harness import provider_check as check
from living_island.sim.v2.harness.replay import History


def reply(text):
    return json_bytes(
        {
            "model": MODEL_ID,
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5, "prompt_cache_hit_tokens": 0},
        }
    )


@pytest.fixture
def staged(tmp_path):
    writer = AuditWriter(tmp_path / "stage.sqlite")
    journal = Journal(writer.keep, writer.create)
    clock = FakeClock()
    samples = []
    for kind in ("recall", "morning"):
        prepared = prepare(
            Call(call_id=f"fixture:{kind}", resident_id="ella", tick=0, period_id="p:ella:1"),
            Contract(kind),
            Assembly((), (), frozenset(), 0 if kind == "morning" else None),
            journal,
        )
        raw = reply('{"ids":[]}')
        transport = FakeTransport(clock, [ScriptedReply(TransportResponse(200, raw, True))])
        result = Caller(transport, clock, lambda _: None).dispatch(prepared, journal, running=False)
        wire = prepared.admitted.wire
        samples.append(check.Sample(prepared, wire.body, wire.counted, False, result.terminal, raw))
    audit = AuditReader(writer.path)
    return tuple(samples), History(audit, audit.cursor())


def test_source_hash_rejects_tampering(tmp_path):
    sample = tmp_path / "receipt.json"
    sample.write_bytes(b"approved")
    assert check.pinned_bytes(sample, digest(b"approved")) == b"approved"
    sample.write_bytes(b"overwritten")
    with pytest.raises(ValueError, match="pinned SHA-256 differs"):
        check.pinned_bytes(sample, digest(b"approved"))


def test_framed_schema_is_single_and_only_in_provider_field():
    contract = Contract("recall")
    body = frame(contract.kind, contract.instructions, contract.schema, "Find food.").body
    check.check_wire(body, contract)
    for format_change, error in [
        (lambda wire: wire["text"]["format"].pop("schema"), "one object schema"),
        (lambda wire: wire["input"][0].update(content=contract.schema.decode()), "system and user"),
        (
            lambda wire: wire["input"][1].update(content=json.dumps(json.loads(contract.schema))),
            "second schema copy",
        ),
        (lambda wire: wire.update(tools=[{"type": "function", "name": "test"}]), "disabled"),
        (lambda wire: wire.update(tool_choice="auto"), "disabled"),
        (lambda wire: wire.update(previous_response_id="private"), "stateless"),
        (lambda wire: wire.update(model="other"), "provider settings"),
        (lambda wire: wire["input"][1].update(role="assistant"), "system and user"),
    ]:
        wire = json.loads(body)
        format_change(wire)
        with pytest.raises(ValueError, match=error):
            check.check_wire(json_bytes(wire), contract)


def test_fake_records_reasoning_and_reuses_exact_stateless_wires(staged, monkeypatch):
    samples, history = staged

    def forbidden(*_):
        pytest.fail("offline mode attempted to initialize live HTTPS")

    monkeypatch.setattr(check.p3, "HTTPSByteTransport", forbidden)
    check.fake_check(samples, history)
    broken = replace(samples[0], fake_body=reply('{"ids":["different"]}'))
    with pytest.raises(ValueError, match="fake parsing or reasoning evidence differs"):
        check.fake_check((broken, samples[1]), history)


def test_credential_echo_is_filtered_before_durable_adapter_records(tmp_path, staged):
    (sample, _), _ = staged
    secret = b"sk-fixture-secret"
    cases = [
        TransportResponse(400, b'{"message":"' + secret + b'"}', True),
        TransportResponse(400, b'{"message":"' + secret[:10], False),
        TransportResponse(400, b'{"message":"ordinary error"}', True),
    ]
    writer = AuditWriter(tmp_path / "redaction.sqlite")
    journal = Journal(writer.keep, writer.create)
    clock = FakeClock()
    fake = FakeTransport(clock, [ScriptedReply(case) for case in cases])
    transport = check.ProtectedTransport(fake, secret, lambda: None)
    for n, raw in enumerate(cases):
        result = check.p3.TransportResponse(400, None, False) if n < 2 else raw
        assert transport.exchange(sample.body, 30_000) == result
    assert secret.decode() not in repr(transport)
    fake.replies.append(ScriptedReply(cases[0]))
    terminal = (
        Caller(transport, clock, lambda _: None)
        .dispatch(sample.prepared, journal, running=False)
        .terminal
    )
    assert terminal.raw_output_ref is None
    assert terminal.status == 400
    assert secret not in writer.path.read_bytes()
    assert fake.dispatches == [sample.body] * 4


def test_price_admission_uses_tariff_mapping_allowance_and_concurrent_liabilities(staged):
    samples, _ = staged
    evidence = deepcopy(check.HISTORICAL_EVIDENCE)
    day = check.HISTORICAL_DATE
    ledger = check.price(samples, evidence, day)
    expected = 13 * sum(sample.input_bound * 2_000_000 + 8_000 * 8_000_000 for sample in samples)
    assert ledger.sizing.reserve_pico == expected
    assert sum(row.planned.count for row in ledger.sizing.rows) == 26
    release = check.Release(
        dispatch_on=day,
        approval="owner fixture",
        wire_evidence="dated Responses fixture",
        preflight_sha256="a" * 64,
        ledger_sha256="b" * 64,
        max_cny="20",
    )
    check.admit(ledger, release)
    with pytest.raises(ValueError, match="no covered allowance"):
        check.admit(ledger, release.model_copy(update={"max_cny": expected - 1}))

    (_, sample), history = staged
    dispatch, _ = next(history.attempts(sample.prepared))
    dispatch = dispatch.model_copy(
        update={
            "started_at": datetime(2026, 11, 14, tzinfo=UTC),
            "sent": dispatch.sent.model_copy(
                update={
                    "manifest": dispatch.sent.manifest.model_copy(update={"tokens_total": 992_000}),
                }
            ),
        }
    )
    evidence["opening"]["settled_cny"] = "18"
    evidence["runs"]["concurrent"] = {
        "stage": "resident_run",
        "mode": "paid",
        "date": day.isoformat(),
        "prepared": [sample.prepared.record.model_dump(mode="json")],
        "dispatches": [dispatch.model_dump(mode="json")],
    }
    # An interrupted attempt retains an uncached-input and full output hold.
    concurrent = check.price(samples, evidence, day)
    assert concurrent.reserve_pico == 2_048_000_000_000
    with pytest.raises(ValueError, match="no covered allowance"):
        check.admit(concurrent, release)
    evidence["tariffs"][0]["model_version"] = "different-model"
    with pytest.raises(ValueError, match="no covered allowance"):
        check.admit(check.price(samples, evidence, day), release)


def test_live_guard_refuses_stale_utc_date():
    clock = FakeClock()
    check.checked_day(clock, clock.now().date())
    with pytest.raises(ValueError, match="outside the released UTC dispatch date"):
        check.checked_day(clock, check.HISTORICAL_DATE)


def test_release_binds_the_rebuilt_sample_and_exact_reconciled_bundle(
    tmp_path, staged, monkeypatch
):
    samples, history = staged
    pin = {"implementation_sha256": "fixture"}
    release_path = tmp_path / "release.json"
    ledger_path = tmp_path / "ledger.json"
    ledger = json_bytes(check.HISTORICAL_EVIDENCE)
    ledger_path.write_bytes(ledger)
    release = {
        "dispatch_on": check.HISTORICAL_DATE.isoformat(),
        "approval": "owner fixture",
        "wire_evidence": "dated Responses fixture",
        "preflight_sha256": digest(json_bytes(pin)),
        "ledger_sha256": digest(ledger),
        "max_cny": "20",
    }
    release_path.write_bytes(json_bytes(release))
    clock = FakeClock(epoch=datetime(2026, 11, 14, tzinfo=UTC))
    monkeypatch.setattr(check, "SystemClock", lambda: clock)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="release does not match the rebuilt preflight"):
        check.live_check(samples, history, {}, release_path, ledger_path)
    with pytest.raises(ValueError, match="must be injected"):
        check.live_check(samples, history, pin, release_path, ledger_path)
    ledger_path.write_bytes(ledger + b" ")
    with pytest.raises(ValueError, match="pinned SHA-256 differs"):
        check.live_check(samples, history, pin, release_path, ledger_path)


def test_attempt_report_keeps_failures_and_usage_in_the_denominator(tmp_path, staged):
    samples, history = staged
    day = check.HISTORICAL_DATE
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    clock = FakeClock(epoch=start)
    fake = FakeTransport(
        clock,
        [
            ScriptedReply(TransportResponse(429, None, True)),
            ScriptedReply(TransportResponse(200, reply('{"wrong":[]}'), True)),
            ScriptedReply(TransportResponse(200, reply('{"ids":[]}'), True)),
            ScriptedReply(TransportResponse(200, reply('{"ids":[]}'), True)),
        ],
    )
    delays = []
    writer = AuditWriter(tmp_path / "attempts.sqlite")
    journal = Journal(writer.keep, writer.create)
    check.execute(samples, history, journal, Caller(fake, clock, delays.append), live=True)
    report = check.archive(
        tmp_path, AuditReader(writer.path), check.HISTORICAL_EVIDENCE, day, samples
    )
    assert delays == [5]
    assert fake.dispatches == [samples[0].body] * 3 + [samples[1].body]
    assert report["all_dispatches_parsed"] == [2, 4]
    assert report["all_http_accepted"] == [3, 4]
    assert report["first_pass_decisions"] == [0, 2]
    assert report["provider_gate_passed"] is False
    outcomes = report["by_kind"]["recall"]
    assert [row["outcome"] for row in outcomes] == ["HTTP_429", "INVALID_MODEL_OUTPUT", "parsed"]
    bundle = json.loads((tmp_path / "ledger-evidence.json").read_bytes())
    run = bundle["runs"][check.RUN_ID]
    assert len(run["undispatched"]) == 0
    assert Terminal.model_validate(run["terminals"][0]).tokens.input is None
    assert Terminal.model_validate(run["terminals"][1]).tokens.input == 10


def test_consolidation_uses_its_own_attempt_ceiling(tmp_path, staged):
    samples, _ = staged
    writer = AuditWriter(tmp_path / "consolidation.sqlite")
    journal = Journal(writer.keep, writer.create)
    prepared = prepare(
        Call(call_id="fixture:selection", resident_id="ella", tick=0, period_id="p:ella:1"),
        Contract("consolidation_selection"),
        Assembly((), (), frozenset()),
        journal,
    )
    wire = prepared.admitted.wire
    sample = replace(samples[0], prepared=prepared, body=wire.body, input_bound=wire.counted)
    clock = FakeClock()
    limit = ScriptedReply(TransportResponse(429, None, True))
    fake = FakeTransport(clock, [limit] * 4)
    delays = []
    terminal = check.consolidation_terminal(sample, journal, Caller(fake, clock, delays.append))
    assert terminal.n == 3
    assert terminal.error == "HTTP_429"
    assert delays == [5, 10, 20]
    assert fake.dispatches == [wire.body] * 4
    sizing = check.price((sample,), check.HISTORICAL_EVIDENCE, check.HISTORICAL_DATE).sizing
    assert len(sizing.rows) == len(fake.dispatches)


def test_changed_response_model_stops_the_rest_of_the_sample(tmp_path, staged):
    samples, history = staged
    body = json.loads(reply('{"ids":[]}'))
    body["model"] = "unreleased"
    clock = FakeClock()
    fake = FakeTransport(clock, [ScriptedReply(TransportResponse(200, json_bytes(body), True))])
    writer = AuditWriter(tmp_path / "drift.sqlite")
    journal = Journal(writer.keep, writer.create)
    with pytest.raises(ValueError, match="moved away from the released alias"):
        check.execute(samples, history, journal, Caller(fake, clock, lambda _: None), live=True)
    assert fake.dispatches == [samples[0].body]
