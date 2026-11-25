"""D1 admission, timing and recovery on the production setup with a short horizon."""

import json
import sqlite3
from contextlib import closing

import pytest


@pytest.fixture
def accepted(tmp_path, monkeypatch):
    from living_island.sim.v2.scenarios import long_run as d1

    monkeypatch.setattr(d1, "HORIZON", 4)
    monkeypatch.setattr(d1.cli, "bind_evidence", lambda *args: None)
    monkeypatch.setattr(d1, "_source_pins", lambda *args: {"source_commit": "fixture"})
    round_ = {
        "stage": "acceptance",
        "seeds": d1.registered("acceptance"),
        "d1_seed": d1.D1_SEED,
        "horizon": 1008,
        "budget_ns": d1.BUDGET_NS,
        "checkpoint_every": 24,
        "policy": d1.POLICY,
        "calibration_sha256": "1" * 64,
        "implementation": "2" * 64,
        "starter_tree": "3" * 40,
        "measurement": "4" * 40,
        "host": "fixture-host",
        "processor": "fixture-cpu",
        "platform": "fixture-os",
        "worker_processes": 2,
    }
    balance = tmp_path / "acceptance"
    key = f"{d1.D1_SEED}/{d1.ARM}"
    directory = balance / key
    plan = d1._Round.model_validate(round_).plan()
    progress = d1.run_or_resume(directory, plan, lambda: d1.scenario(directory, d1.D1_SEED, d1.ARM))
    selected = {
        "inputs": json.loads((directory / "inputs.json").read_bytes()),
        "case_receipt": "cases/1.json",
        "evidence": "evidence.json",
        "timing_db": "progress.sqlite",
        "receipt_sha256": d1.file_digest(directory / "cases/1.json"),
        "evidence_sha256": d1.file_digest(directory / "evidence.json"),
        "timing": progress.timing.model_dump(mode="json"),
    }
    report = {
        "stage": "acceptance",
        "technical": "PASS",
        "verdict": "PASS",
        "pins": round_,
        "reviewed_head": "5" * 40,
        "measurement_tree": "6" * 40,
        "d1_case": key,
        "cases": {
            key: selected,
            f"{d1.D1_SEED}/compat-v1": {**selected, "case_receipt": "cases/0.json"},
        },
    }
    (balance / "round.json").write_bytes(d1.cli.report_bytes(round_))
    (balance / "report.json").write_bytes(d1.cli.report_bytes(report))
    return d1, balance, directory, report, selected, progress


def test_d1_reuses_selected_case_deterministically(accepted, tmp_path, monkeypatch):
    d1, balance, directory, _, _, progress = accepted
    monkeypatch.setattr(d1, "run_or_resume", lambda *args: pytest.fail("unexpected simulation"))
    out = tmp_path / "review"
    before = d1.file_digest(directory / "progress.sqlite")
    assert d1.publish(balance, out, verify_only=True) == ("PASS", out / "receipt.json")
    raw = (out / "receipt.json").read_bytes()
    result = json.loads(raw)
    assert result["reused_acceptance_case"]
    assert result["last_committed_tick"] == 4
    assert result["execution"]["host"] == "fixture-host"
    assert result["resident_ids"] == ["ella", "mia", "ryan"]
    assert result["provider_calls"] == 0
    assert result["timing"] == progress.timing.model_dump(mode="json")
    assert d1.publish(balance, out) == ("PASS", out / "receipt.json")
    assert raw == (out / "receipt.json").read_bytes()
    assert len(list((out / "verification").glob("*.json"))) == 2
    assert before == d1.file_digest(directory / "progress.sqlite")


def test_d1_budget_and_completion_edges(accepted, tmp_path, monkeypatch):
    d1, balance, directory, report, selected, progress = accepted
    plan = d1.Inputs.model_validate_json((directory / "inputs.json").read_bytes()).plan
    assert progress.evidence is not None
    monkeypatch.setattr(d1, "run_or_resume", lambda *args: pytest.fail("unexpected simulation"))

    for elapsed, expected in ((d1.BUDGET_NS, "PASS"), (d1.BUDGET_NS + 1, "BUDGET_MISS")):
        with closing(sqlite3.connect(directory / "progress.sqlite")) as db, db:
            db.execute("UPDATE attempts SET active_ns = ?", (elapsed,))
            measured = d1.read_timing(db, plan, 4, True)
        selected["timing"] = measured.model_dump(mode="json")
        (balance / "report.json").write_bytes(d1.cli.report_bytes(report))
        assert d1.publish(balance, tmp_path / expected)[0] == expected

    week = plan.model_copy(update={"horizon": 1008})
    short = progress.evidence.model_copy(update={"final_tick": 1007})
    assert d1.verdict(week, 1007, short, progress.timing) == "INDETERMINATE"
    assert d1.verdict(week, 1007, None, progress.timing) == "PARTIAL"


def test_d1_rejects_changed_registration_and_inputs(accepted, tmp_path):
    d1, balance, _, report, selected, _ = accepted
    old_case = report["d1_case"]
    report["d1_case"] = f"{d1.D1_SEED}/compat-v1"
    (balance / "report.json").write_bytes(d1.cli.report_bytes(report))
    with pytest.raises(ValueError, match="predeclared"):
        d1.publish(balance, tmp_path / "review")
    report["d1_case"] = old_case
    selected["inputs"]["map_sha256"] = "0" * 64
    (balance / "report.json").write_bytes(d1.cli.report_bytes(report))
    with pytest.raises(ValueError, match="case inputs differ"):
        d1.publish(balance, tmp_path / "review")


def test_d1_refuses_unverifiable_timing_and_retains_interruption(accepted, tmp_path, monkeypatch):
    d1, balance, directory, report, selected, _ = accepted
    monkeypatch.setattr(d1, "run_or_resume", lambda *args: pytest.fail("unexpected simulation"))
    plan = d1.Inputs.model_validate_json((directory / "inputs.json").read_bytes()).plan
    with closing(sqlite3.connect(directory / "progress.sqlite")) as db, db:
        db.execute("UPDATE attempts SET status = 'interrupted'")
        measured = d1.read_timing(db, plan, 4, True)
    out = tmp_path / "review"
    with pytest.raises(ValueError, match="timing claimed"):
        d1.publish(balance, out)
    selected["timing"] = measured.model_dump(mode="json")
    (balance / "report.json").write_bytes(d1.cli.report_bytes(report))
    assert d1.publish(balance, out) == ("INDETERMINATE", out / "receipt.json")
    assert (
        json.loads((out / "receipt.json").read_bytes())["timing"]["attempts"][0]["status"]
        == "interrupted"
    )


def test_d1_absent_timing_records_and_resumes_once(accepted, tmp_path, monkeypatch):
    d1, balance, directory, report, selected, progress = accepted
    (directory / "progress.sqlite").rename(tmp_path / "retained.sqlite")
    selected["timing"] = None
    (balance / "report.json").write_bytes(d1.cli.report_bytes(report))
    out = tmp_path / "review"
    with pytest.raises(ValueError, match="never captured"):
        d1.publish(balance, out, verify_only=True)
    assert not out.exists()

    run = d1.run_or_resume
    allowances = []

    def pause_first(directory, plan, setup, *, attempt_limit_ns):
        allowances.append(attempt_limit_ns)
        return run(
            directory,
            plan,
            setup,
            attempt_limit_ns=attempt_limit_ns,
            pause_after=lambda tick: len(allowances) == 1 and tick == 2,
        )

    monkeypatch.setattr(d1, "run_or_resume", pause_first)
    result, partial = d1.publish(balance, out)
    assert result == "PARTIAL"
    stopped = json.loads(partial.read_bytes())
    assert stopped["last_committed_tick"] == 2
    assert allowances == [d1.BUDGET_NS]
    assert d1.publish(balance, out) == ("PASS", out / "receipt.json")
    assert allowances[1] == d1.BUDGET_NS - stopped["timing"]["active_ns"]
    receipt = json.loads((out / "receipt.json").read_bytes())
    assert not receipt["reused_acceptance_case"]
    assert receipt["timing"]["attempts"][1]["resumed_tick"] == 2
    assert receipt["timing"]["downtime_ns"] > 0
    saved = d1.Evidence.model_validate_json((out / "case/evidence.json").read_bytes())
    assert saved.prefix_sha256 == progress.evidence.prefix_sha256
    assert saved.final_snapshot_sha256 == progress.evidence.final_snapshot_sha256
