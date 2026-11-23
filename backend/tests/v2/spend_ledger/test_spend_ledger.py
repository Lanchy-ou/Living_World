"""Reconcile bounded DL-01 journal evidence without provider access."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from living_island.analysis.v2_spend import project, read_evidence, render_markdown

EVIDENCE_DATE = "2026-11-23"
PICO_PER_CNY = 10**12
PICO_PER_MICRO = 10**6


@pytest.fixture
def journal_evidence():
    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.fake import FakeClock, FakeTransport, ScriptedReply
    from living_island.agents.v2.calls.guard import Assembly, Call, prepare
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.calls.provider import attempt
    from living_island.agents.v2.calls.wire import WINDOW

    clock = FakeClock(datetime(2026, 11, 23, tzinfo=UTC))

    def reply(text, usage=None, status=200):
        body = json.dumps(
            {
                "model": "deepseek-flash",
                "status": "completed",
                "usage": usage,
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": text}],
                    }
                ],
            }
        ).encode()
        return ScriptedReply(TransportResponse(status, body, True), 2)

    def usage(input_tokens, output_tokens, cached_tokens):
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_tokens_details": {"cached_tokens": cached_tokens},
        }

    morning = '{"ids":[]}'
    transport = FakeTransport(
        clock,
        [
            reply(morning, usage(100, 10, 40)),
            reply(morning, status=503),
            reply(morning, usage(80, 9, 20)),
            reply('{"read":[]}', usage(50, 8, 10)),
            reply(morning, usage(36, 7, None)),
        ],
    )
    stored = {}
    audit = Journal(stored.setdefault, stored.__setitem__)

    def call(call_id, kind="morning"):
        records = Call(call_id=call_id, resident_id="ella", tick=9, period_id="p1")
        assembly = Assembly((), (), frozenset(), 0 if kind == "morning" else None)
        return prepare(records, Contract(kind), assembly, audit)

    def dispatch(prepared, n=0):
        return attempt(
            prepared,
            n=n,
            has_running_action=False,
            journal=audit,
            transport=transport,
            clock=clock,
        )

    successful = call("successful")
    dispatch(successful)
    retried = call("retried")
    dispatch(retried)
    dispatch(retried, n=1)
    abandoned = call("abandoned", "consolidation_selection")
    returned_late = dispatch(abandoned)
    split_missing = call("split-missing")
    dispatch(split_missing)

    # The no-dispatch projection takes an already measured floor. Synthesize its count
    # to avoid building a nearly million-token request just to exercise accounting.
    prepared = successful.record
    floor_hash = sha256(b"synthetic oversized floor").hexdigest()
    candidate = prepared.candidates[0]
    floor = candidate.model_copy(
        update={
            "manifest": candidate.manifest.model_copy(update={"tokens_total": WINDOW + 1}),
            "wire_sha256": floor_hash,
        }
    )
    audit.fact(
        "unfit",
        "prepared",
        prepared.model_copy(
            update={
                "call": prepared.call.model_copy(update={"call_id": "unfit"}),
                "candidates": (floor,),
                "admitted_candidate": None,
                "reason": "stopped_unfit",
            }
        ),
    )
    late = json.loads(stored.pop(returned_late.terminal_cursor))

    def facts(kind):
        return [json.loads(value) for key, value in stored.items() if key.endswith(f".{kind}.json")]

    paid = {
        "stage": "provider_check",
        "mode": "paid",
        "date": EVIDENCE_DATE,
        "prepared": facts("prepared"),
        "dispatches": facts("dispatch"),
        "terminals": facts("terminal"),
        "abandoned": ["abandoned"],
        "charges": [],
    }
    fake = deepcopy(paid)
    fake.update(mode="fake", stage="resident_run")
    settings = successful.record.settings
    evidence = {
        "opening": {"settled_cny": "1.25", "source": "synthetic opening evidence"},
        "tariffs": [
            {
                "provider": settings.provider,
                "model": settings.model,
                "model_version": settings.model_version,
                "effective_on": EVIDENCE_DATE,
                "through": EVIDENCE_DATE,
                "source": "synthetic CNY tariff",
                "model_evidence": "synthetic version verification",
                "cache_hit_per_million": "0.5",
                "cache_miss_per_million": "2.5",
                "output_per_million": "8.75",
                "peak_cache_miss_per_million": "2.5",
                "peak_output_per_million": "8.75",
            }
        ],
        "runs": {"paid-vector": paid, "fake-vector": fake},
    }
    return evidence, late


def read(evidence):
    return read_evidence(json.dumps(evidence).encode())


def forecast(evidence):
    (tariff,) = evidence["tariffs"]
    pin = {field: tariff[field] for field in ("provider", "model", "model_version")}
    return {
        **pin,
        "stage": "resident_run",
        "date": EVIDENCE_DATE,
        "rows": [
            {
                "day": day,
                "kind": "morning",
                "n": 0,
                "count": 1,
                "input_bound": 155,
                "output_bound": 8_000,
                "central_cny": "0.0002575",
            }
            for day in (1, 2)
        ],
    }


def test_reconciles_retry_restore_late_usage_and_no_dispatch(journal_evidence):
    evidence, late = journal_evidence
    partial = project(read(evidence))
    paid = next(run for run in partial.runs if run.run_id == "paid-vector")
    calls = {call.call_id: call for call in paid.calls}
    (first,) = calls["successful"].attempts
    failed, retried = calls["retried"].attempts
    (interrupted,) = calls["abandoned"].attempts
    (split_missing,) = calls["split-missing"].attempts

    # The numbers are micro-CNY at the synthetic rates, converted to pico-CNY.
    # Successful: 40 x 0.5 + 60 x 2.5 + 10 x 8.75 = 257.5.
    # Retry: 20 x 0.5 + 60 x 2.5 + 9 x 8.75 = 238.75.
    assert first.settled_pico == 257_500_000
    assert retried.settled_pico == 238_750_000
    assert first.reserve_pico == retried.reserve_pico == 0
    assert first.request_sha256 == failed.request_sha256 == retried.request_sha256
    assert (failed.n, retried.n) == (0, 1)
    assert failed.tokens.input is None
    assert failed.tokens.output is None
    assert interrupted.tokens.input is None
    assert split_missing.tokens.input == 36
    assert split_missing.tokens.output == 7
    assert split_missing.tokens.cache_hit is None
    assert split_missing.tokens.cache_miss is None
    assert calls["unfit"].outcome == "stopped_unfit"
    assert calls["unfit"].attempts == ()
    assert calls["abandoned"].outcome == "abandoned"

    dispatches = evidence["runs"]["paid-vector"]["dispatches"]
    holds = {
        row["call"]["call_id"]: (row["sent"]["manifest"]["tokens_total"] * 2_500_000)
        + (row["settings"]["max_output_tokens"] * 8_750_000)
        for row in dispatches
    }
    assert failed.reserve_pico == holds["retried"]
    assert interrupted.reserve_pico == holds["abandoned"]
    assert split_missing.reserve_pico == holds["split-missing"]
    assert partial.reserve_pico == sum(holds[k] for k in ("retried", "abandoned", "split-missing"))
    assert partial.settled_pico == 1_250_000_000_000 + 496_250_000

    restored = deepcopy(evidence)
    run = restored["runs"]["paid-vector"]
    for records in ("prepared", "dispatches", "terminals"):
        run[records] += list(reversed(run[records]))
    run["terminals"] += [late, late]
    final = project(read(restored))
    paid = next(run for run in final.runs if run.run_id == "paid-vector")
    late_call = next(call for call in paid.calls if call.call_id == "abandoned")
    (late_attempt,) = late_call.attempts

    # Late usage settles once at 10 x 0.5 + 40 x 2.5 + 8 x 8.75 = 175 micro-CNY.
    assert late_call.outcome == "abandoned"
    assert late_attempt.settled_pico == 175 * PICO_PER_MICRO
    assert late_attempt.reserve_pico == 0
    assert final.settled_pico == partial.settled_pico + 175 * PICO_PER_MICRO
    assert final.reserve_pico == partial.reserve_pico - holds["abandoned"]
    assert final.remaining_pico == 20 * PICO_PER_CNY - final.settled_pico - final.reserve_pico

    document = render_markdown(final)
    assert all(value in document for value in ("paid-vector", "fake-vector", first.request_sha256))
    for records in ("prepared", "dispatches", "terminals"):
        run[records].reverse()
    assert render_markdown(project(read(restored))) == document

    opening = {**evidence["opening"], "settled_cny": "19.7"}
    plan = forecast(evidence)
    before_settlement = project(read({**evidence, "opening": opening, "plan": plan}))
    after_settlement = project(read({**restored, "opening": opening, "plan": plan}))
    for ledger, days, fits in ((before_settlement, 1, False), (after_settlement, 2, True)):
        assert ledger.sizing is not None
        assert ledger.sizing.reserve_pico == 2 * (155 * 2_500_000 + 8_000 * 8_750_000)
        assert ledger.sizing.affordable_days == days
        assert ledger.sizing.fits == fits

    run["charges"] = [
        {
            "call_id": "retried",
            "n": 0,
            "provider_cny": "0.00031",
            "invoice_cny": "0.00032",
            "source": "synthetic invoice evidence",
        }
    ]
    invoiced = project(read(restored))
    assert invoiced.settled_pico == final.settled_pico + 320 * PICO_PER_MICRO
    assert invoiced.reserve_pico == final.reserve_pico - holds["retried"]
    invoice_line = next(
        line
        for line in render_markdown(invoiced).splitlines()
        if "synthetic invoice evidence" in line
    )
    assert "| 0.00031 | 0.00032 | 0.00001 |" in invoice_line


def test_rejects_terminal_without_its_dispatch(journal_evidence):
    evidence, _ = journal_evidence
    run = evidence["runs"]["paid-vector"]
    run["dispatches"] = [row for row in run["dispatches"] if row["call"]["call_id"] != "successful"]
    with pytest.raises(ValueError, match="no durable dispatch"):
        read(evidence)


def test_rejects_conflicting_dispatch_snapshots(journal_evidence):
    evidence, _ = journal_evidence
    dispatches = evidence["runs"]["paid-vector"]["dispatches"]
    dispatches.append({**dispatches[0], "started_at": "2026-11-23T00:00:01Z"})
    with pytest.raises(ValueError, match="conflicting dispatch"):
        read(evidence)


def test_rejects_nonexact_or_negative_money(journal_evidence):
    evidence, _ = journal_evidence
    for value in (0.1, True, "NaN", "-0.01"):
        evidence["opening"]["settled_cny"] = value
        with pytest.raises(ValueError):
            read(evidence)


def test_rejects_opening_amount_without_evidence(journal_evidence):
    evidence, _ = journal_evidence
    evidence["opening"]["source"] = None
    with pytest.raises(ValueError, match="opening balance requires evidence"):
        read(evidence)


def test_rejects_inconsistent_tariff_schedule(journal_evidence):
    evidence, _ = journal_evidence
    (tariff,) = evidence["tariffs"]
    for changes, message in (
        ({"through": "2026-11-22"}, "tariff dates"),
        ({"peak_cache_miss_per_million": "2.4"}, "peak rates"),
        ({"peak_output_per_million": "8.74"}, "peak rates"),
    ):
        with pytest.raises(ValueError, match=message):
            read({**evidence, "tariffs": [{**tariff, **changes}]})
    overlapping = {**tariff, "effective_on": "2026-11-22"}
    with pytest.raises(ValueError, match="overlapping tariff dates"):
        read({**evidence, "tariffs": [tariff, overlapping]})


def test_rejects_terminal_for_different_dispatch(journal_evidence):
    evidence, _ = journal_evidence
    terminals = evidence["runs"]["paid-vector"]["terminals"]
    first = terminals[0]
    for field, mismatch in (
        ("request_sha256", "0" * 64),
        ("dispatch_cursor", terminals[1]["dispatch_cursor"]),
    ):
        terminals[0] = {**first, field: mismatch}
        with pytest.raises(ValueError, match="terminal belongs to a different dispatch"):
            read(evidence)


def test_rejects_conflicting_logical_call_facts(journal_evidence):
    evidence, _ = journal_evidence
    (tariff,) = evidence["tariffs"]
    run = evidence["runs"]["paid-vector"]
    pin = {field: tariff[field] for field in ("provider", "model", "model_version")}
    undispatched = {**pin, "call_id": "successful", "kind": "morning"}
    run["undispatched"] = [undispatched]
    with pytest.raises(ValueError, match="duplicates a prepared call"):
        read(evidence)
    run["prepared"] = [fact for fact in run["prepared"] if fact["call"]["call_id"] != "successful"]
    with pytest.raises(ValueError, match="dispatch conflicts with its logical call"):
        read(evidence)
    run["undispatched"] = []
    run["abandoned"].append("no-record")
    with pytest.raises(ValueError, match="abandoned call has no metadata"):
        read(evidence)


def test_rejects_ambiguous_json_keys():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        read_evidence(b'{"opening":null,"runs":{},"runs":{}}')


def test_unknown_opening_blocks_paid_admission(journal_evidence):
    evidence, _ = journal_evidence
    evidence["plan"] = forecast(evidence)
    evidence["opening"] = {"settled_cny": None, "source": None}
    ledger = project(read(evidence))
    assert ledger.remaining_pico is None
    assert ledger.sizing is not None
    assert ledger.sizing.reserve_pico is not None
    assert ledger.sizing.affordable_days is None
    assert ledger.sizing.fits is False


def test_missing_dated_tariff_leaves_unbounded_attempts(journal_evidence):
    evidence, _ = journal_evidence
    evidence["plan"] = forecast(evidence)
    (tariff,) = evidence["tariffs"]
    evidence["tariffs"] = [{**tariff, "effective_on": "2026-11-22", "through": "2026-11-22"}]
    ledger = project(read(evidence))
    assert ledger.unbounded_attempts == 5
    assert ledger.remaining_pico is None
    assert ledger.sizing is not None
    assert ledger.sizing.reserve_pico is None
    assert ledger.sizing.fits is False


def test_incomplete_usage_beyond_pinned_bounds_blocks_paid_admission(journal_evidence):
    evidence, _ = journal_evidence
    evidence["plan"] = forecast(evidence)
    run = evidence["runs"]["paid-vector"]
    terminal = next(row for row in run["terminals"] if row["call_id"] == "split-missing")
    tokens = terminal["tokens"]
    for name, overrun in (("input", 156), ("output", 8_001)):
        terminal["tokens"] = {**tokens, name: overrun}
        ledger = project(read(evidence))
        assert ledger.unbounded_attempts == 1
        assert ledger.remaining_pico is None
        assert ledger.sizing is not None
        assert ledger.sizing.fits is False


def test_rejects_charge_without_attributed_amount(journal_evidence):
    evidence, _ = journal_evidence
    evidence["runs"]["paid-vector"]["charges"] = [
        {"call_id": "successful", "n": 0, "source": "invoice without amount"}
    ]
    with pytest.raises(ValueError, match="charge evidence requires an attributed amount"):
        read(evidence)


def test_rejects_nonconsecutive_or_wrong_stage_forecast_days(journal_evidence):
    evidence, _ = journal_evidence
    plan = forecast(evidence)
    with pytest.raises(ValueError, match="game days belong to the resident run"):
        read({**evidence, "plan": {**plan, "stage": "provider_check"}})
    plan["rows"][1]["day"] = 3
    with pytest.raises(ValueError, match="forecast game days must be consecutive"):
        read({**evidence, "plan": plan})
