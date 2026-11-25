"""Exercise the EV-06 evidence joins with a bounded fake resident recording."""

import json
from dataclasses import replace
from hashlib import sha256

import pytest

from v2.inspection_export.short_capture import seal_capture
from v2.resident_replay.replay_fixture import start, verify

MODEL = {
    "provider": "deepseek-responses",
    "model": "deepseek-flash",
    "model_version": "DeepSeek-V4.1-Flash-1017",
}


def evidence(day, *, opening):
    return {
        "opening": {"settled_cny": opening, "source": "EV-06 test opening"},
        "tariffs": [
            {
                **MODEL,
                "effective_on": day,
                "through": day,
                "source": "EV-06 test tariff",
                "model_evidence": "EV-06 test model pin",
                "cache_hit_per_million": "0.02",
                "cache_miss_per_million": "1",
                "output_per_million": "4",
                "peak_cache_miss_per_million": "2",
                "peak_output_per_million": "8",
            }
        ],
        "runs": {},
    }


def test_rehearsed_whole_day_prefix_fits_phase_headroom():
    from living_island.analysis.v2_spend import project, read_evidence, render_markdown

    day = "2026-11-25"
    bundle = evidence(day, opening="0.05343482")
    # Each compact test row preserves the total input bound and attempt count
    # of that day. The retained sizing bundle accounts by kind and ordinal.
    rehearsal = [(47, 534_641), (33, 364_236), (29, 353_542)]
    rows = []
    for game_day, (attempts, counted_input) in enumerate(rehearsal, start=1):
        width, remainder = divmod(counted_input, attempts)
        for n, (count, bound) in enumerate(((attempts - remainder, width), (remainder, width + 1))):
            rows.append(
                dict(
                    day=game_day,
                    kind="decision",
                    n=n,
                    count=count,
                    input_bound=bound,
                    output_bound=8000,
                    central_cny=None,
                )
            )
    bundle["plan"] = {**MODEL, "stage": "resident_run", "date": day, "rows": rows}

    ledger = project(read_evidence(json.dumps(bundle).encode()))
    sizing = ledger.sizing
    assert ledger.remaining_pico == 19_946_565_180_000
    assert sizing.fits and sizing.affordable_days == 3
    assert [(row.attempts, row.reserve_pico) for row in sizing.days] == [
        (47, 4_077_282_000_000),
        (33, 2_840_472_000_000),
        (29, 2_563_084_000_000),
    ]
    assert sizing.reserve_pico == 9_480_838_000_000
    report = render_markdown(ledger)
    assert "Affordable whole resident days from the proposed prefix — 3" in report
    assert "Proposed unit hold (CNY) — 9.480838" in report

    # Exactly two days fit. The third would exceed the available phase balance.
    bundle["opening"]["settled_cny"] = "13.082246"
    short = project(read_evidence(json.dumps(bundle).encode())).sizing
    assert short.affordable_days == 2 and not short.fits


def test_partial_day_report_reconciles_replayed_attempts_and_rejects_usage_drift(
    tmp_path, monkeypatch
):
    from living_island.analysis.v2.export import export
    from living_island.analysis.v2.shards import InspectionArchive
    from living_island.analysis.v2_spend import project, read_evidence

    source = tmp_path / "run"
    record, kwargs, fake = start(source)
    exchange = fake.exchange

    def metered_exchange(body, timeout_ms):
        response = exchange(body, timeout_ms)
        envelope = json.loads(response.body)
        envelope["usage"] = {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens": 10,
        }
        return replace(response, body=json.dumps(envelope).encode())

    monkeypatch.setattr(fake, "exchange", metered_exchange)
    assert record.advance() is not None
    assert record.session.world.tick == 1

    def fail_on_exchange(*_):
        pytest.fail("offline replay invoked the fake capture transport")

    monkeypatch.setattr(fake, "exchange", fail_on_exchange)
    (replayed,) = verify(source, record, kwargs, boundaries=1)
    assert replayed.decision == record.session.records[0]
    assert replayed.boundary.store_hash == record.session.resident.period.store.snapshot.store_hash

    facts = record.audit.keys(0, record.audit.cursor())
    run = {
        field: [json.loads(record.audit.read(key)) for key in facts if key.endswith(suffix)]
        for field, suffix in (
            ("prepared", ".prepared.json"),
            ("dispatches", ".dispatch.json"),
            ("terminals", ".terminal.json"),
        )
    }
    day = run["dispatches"][0]["started_at"][:10]
    # Simulate invoice attribution on fake bytes. No provider or account is involved.
    extra = run["terminals"][0]
    run.update(
        stage="resident_run",
        mode="paid",
        date=day,
        charges=[
            dict(
                call_id=extra["call_id"], n=extra["n"], source="test invoice", invoice_cny="0.00011"
            )
        ],
    )
    bundle = evidence(day, opening="0")
    bundle["runs"][record.session.world.run_id] = run
    raw = json.dumps(bundle).encode()
    ledger_path = source / "sanitized-evidence.json"
    ledger_path.write_bytes(raw)
    ledger = project(read_evidence(raw))

    capture = seal_capture(tmp_path, source, record, kwargs, "on")
    destination = tmp_path / "inspection"
    index = export(*capture, destination)
    archive = InspectionArchive.open(destination)
    (selected,) = index.decisions
    decision = archive.read(selected.shard)
    assert decision.record.turn_id == replayed.decision.turn_id
    assert decision.record.origin == "model"
    cost = archive.read(index.cost)
    assert cost.ledger_sha256 == sha256(raw).hexdigest()
    (partial,) = cost.days
    assert (partial.day, partial.calls, partial.attempts, partial.fallback_turns) == (1, 3, 3, 0)
    assert (partial.input_pico_cny, partial.output_pico_cny) == (182_400_000, 120_000_000)
    assert partial.unassignable_pico_cny == 9_200_000
    assert partial.paid_pico_cny == ledger.settled_pico == 311_600_000
    for attempt in cost.contexts:
        assert sum(section.tokens for section in attempt.sections) == attempt.sent_tokens
        assert sum(section.estimated_input_pico_cny for section in attempt.sections) == (
            attempt.input_pico_cny
        )

    extra["tokens"]["output"] += 1
    ledger_path.write_bytes(json.dumps(bundle).encode())
    with pytest.raises(ValueError, match="dispatch identity, date, model or usage differs"):
        export(*capture, tmp_path / "mismatched")
