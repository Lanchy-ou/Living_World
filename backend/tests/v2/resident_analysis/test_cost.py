import gzip
import json
from fractions import Fraction
from pathlib import Path
from shutil import copytree

import pytest

from living_island.analysis.v2.cost import context_cost
from living_island.analysis.v2.export import export
from living_island.analysis.v2.shards import InspectionArchive
from living_island.contract import inspection_v2 as ia


def billing(calls, mode="paid"):
    prepared, dispatches, terminals, undispatched = [], [], [], []
    first = next(c.prepared for c in calls if c.prepared)
    pin = first.settings.model_dump(include={"provider", "model", "model_version"})
    for c in calls:
        if c.prepared:
            prepared.append(c.prepared.model_dump(mode="json"))
        else:
            undispatched.append(dict(**pin, call_id=c.call.call_id, kind=c.call_kind))
        for a in c.attempts:
            dispatches.append(a.dispatch.model_dump(mode="json"))
            if a.terminal:
                terminals.append(a.terminal.model_dump(mode="json"))
    tariff = dict(
        **pin,
        effective_on="2000-01-01",
        through="2000-01-01",
        source="fixture tariff",
        model_evidence="fixture model",
        cache_hit_per_million="0.5",
        cache_miss_per_million="2",
        output_per_million="3",
        peak_cache_miss_per_million="2",
        peak_output_per_million="3",
    )
    return dict(
        opening=dict(settled_cny="0", source="fixture"),
        tariffs=[tariff],
        runs={
            "island": dict(
                mode=mode,
                date="2000-01-01",
                stage="resident_run",
                prepared=prepared,
                dispatches=dispatches,
                terminals=terminals,
                undispatched=undispatched,
            )
        },
    )


@pytest.fixture
def priced(short):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.calls.provider import Usage

    view = short.read(short.index.decisions[0].shard)
    template = view.calls[0]
    calls = {}
    charges = []
    for kind in (
        "decision",
        "recall",
        "decision_after_recall",
        "morning",
        "consolidation_selection",
        "consolidation_change_set",
    ):
        c = template.call.model_copy(
            update={
                "call_id": kind,
                "turn_id": view.record.turn_id
                if kind in ("decision", "recall", "decision_after_recall")
                else None,
            }
        )
        prep = template.prepared
        candidates = tuple(
            k.model_copy(update={"manifest": k.manifest.model_copy(update={"call_kind": kind})})
            for k in prep.candidates
        )
        prep = prep.model_copy(update={"call": c, "candidates": candidates})
        stages = []
        for n in range(0 if kind == "consolidation_selection" else 2 if kind == "decision" else 1):
            seed = template.attempts[0]
            dispatch = seed.dispatch.model_copy(
                update={"call": c, "n": n, "sent": candidates[prep.admitted_candidate]}
            )
            usage = Usage(input=10, cache_hit=3, cache_miss=7, output=4)
            terminal = seed.terminal.model_copy(
                update={
                    "call_id": kind,
                    "n": n,
                    "dispatch_cursor": Journal.cursor(kind, f"{n}.dispatch"),
                    "error_class": "timeout" if kind == "decision" and not n else None,
                    "tokens": usage,
                }
            )
            if kind == "consolidation_change_set":
                terminal = None
            stages.append(seed.model_copy(update={"dispatch": dispatch, "terminal": terminal}))
            charges.append(
                ia.Charge(
                    call_id=kind,
                    n=n,
                    **(usage.model_dump() if terminal else Usage().model_dump()),
                    latency_ms=terminal.latency_ms if terminal else None,
                    missing_usage_reason=None if terminal else "terminal unavailable",
                )
            )
        calls[kind] = template.model_copy(
            update={
                "call": c,
                "call_kind": kind,
                "attempts": stages,
                "prepared": prep,
                "full_manifest": candidates[0].manifest,
                "outcome": "abandoned"
                if not stages
                else "failed"
                if not stages[-1].terminal
                else "adopted",
            }
        )
    return calls, charges, [view.record]


def test_section_costs_ledger_retry_missing_usage_and_fake(priced, tmp_path):
    calls, charges, decisions = priced
    evidence = billing(calls.values())
    (tmp_path / "sanitized-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    result = context_cost(tmp_path, "island", calls, charges, decisions, 10)
    assert {r.call_kind for r in result.contexts} == set(calls)
    first, second = [r for r in result.contexts if r.call_id == "decision"]
    assert (first.n, first.attempt_outcome, second.n, second.attempt_outcome) == (
        0,
        "timeout",
        1,
        "returned",
    )
    assert first.input_pico_cny == 15_500_000 and first.output_pico_cny == 12_000_000
    assert first.paid_pico_cny == 27_500_000 and first.unassignable_pico_cny == 0
    assert sum(s.estimated_input_pico_cny for s in first.sections) == first.input_pico_cny
    assert sum(Fraction(s.share) for s in first.sections) == 1
    assert first.sent_tokens == sum(s.tokens for s in first.sections)
    assert {"schema", "wire framing and tokenization"} <= {s.section for s in first.sections}
    absent = next(r for r in result.contexts if r.call_id == "consolidation_selection")
    missing = next(r for r in result.contexts if r.call_id == "consolidation_change_set")
    assert absent.n is absent.sent_tokens is None and absent.paid_pico_cny == 0
    assert missing.paid_pico_cny is None and missing.cost_reason
    assert result.days[0].paid_pico_cny is None and result.days[0].attempts == 6
    evidence["runs"]["island"]["mode"] = "fake"
    (tmp_path / "sanitized-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    fake = context_cost(tmp_path, "island", calls, charges, decisions, 10)
    assert fake.ledger_mode == "fake" and fake.days[0].paid_pico_cny == 0
    assert all(r.paid_pico_cny == 0 for r in fake.contexts)
    assert fake.attempts == charges


@pytest.mark.parametrize("mismatch", ["run", "count", "usage"])
def test_ledger_must_identify_the_recorded_attempt(priced, tmp_path, mismatch):
    calls, charges, decisions = priced
    evidence = billing(calls.values())
    run = evidence["runs"]["island"]
    if mismatch == "run":
        evidence["runs"] = {"other": run}
    elif mismatch == "count":
        run["dispatches"].pop()
    else:
        run["terminals"][0]["tokens"]["output"] = 200
    (tmp_path / "sanitized-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="spend ledger"):
        context_cost(tmp_path, "island", calls, charges, decisions, 10)


def test_export_repeats_resident_shards_and_matches_browser_fixture(capture, short, tmp_path):
    original, manifest, replay = capture
    run = copytree(original, tmp_path / "run")
    calls = [short.read(c.shard) for c in short.index.calls]
    evidence = billing(calls, mode="fake")
    evidence["runs"] = {short.index.run_id: evidence["runs"]["island"]}
    (run / "sanitized-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    first, second = [tmp_path / name for name in ("first", "second")]
    index = export(run, manifest, replay, first)
    assert export(run, manifest, replay, second) == index
    archive = InspectionArchive.open(first)
    metrics = archive.read(index.metrics).resident_analysis
    cost = archive.read(index.cost)
    assert metrics.uses and cost.contexts
    assert cost.ledger_mode == "fake" and cost.days[0].paid_pico_cny == 0
    fixture = json.loads(
        gzip.decompress(Path(__file__).with_name("short-inspection.json.gz").read_bytes())
    )
    expected = json.loads(fixture["files"]["index.json"])
    for family in ("metrics", "cost"):
        assert expected[family]["sha256"] == getattr(index, family).sha256
    assert all(s.self_found_skills == s.prior_day_uses == 0 for s in metrics.residents)
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
