"""Exercise the fixed resident CLI and its dispatch stop with synthetic transports."""

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from living_island.agents.llm import provider as p3
from living_island.agents.v2.calls.contracts import digest, json_bytes
from living_island.agents.v2.calls.fake import FakeClock
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.decision.caller import Caller
from living_island.analysis.v2.shards import InspectionArchive
from living_island.sim.v2.harness import live_resident as live
from living_island.sim.v2.harness.checkpoint import Recording


def test_fake_cli_records_resumes_replays_and_exports(tmp_path, monkeypatch, capsys):
    run = tmp_path / "resident"
    inspection = tmp_path / "inspection"

    def unreachable(*args):
        pytest.fail("offline command initialized HTTPS")

    monkeypatch.setattr(p3, "HTTPSByteTransport", unreachable)

    def execute(command, *extra):
        monkeypatch.setattr(sys, "argv", ["live_resident", command, "--out", str(run), *extra])
        return live.main()

    assert execute("run", "--through", "2") == 0
    assert json.loads(capsys.readouterr().out) == {"status": "paused", "tick": 2}

    # Simulate an interruption after a committed boundary and before the next
    # checkpoint file. Resume must rebuild that boundary without dispatch.
    save = Recording.save

    def interrupted(record, path):
        if path.name == "3.json":
            raise OSError("interrupted before checkpoint publication")
        return save(record, path)

    monkeypatch.setattr(Recording, "save", interrupted)
    with pytest.raises(SystemExit, match="1"):
        execute("run", "--resume", "--through", "3")
    monkeypatch.setattr(Recording, "save", save)
    assert execute("run", "--resume", "--through", "4") == 0
    assert json.loads(capsys.readouterr().out) == {"status": "paused", "tick": 4}

    assert execute("replay") == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["tick"] == 4 and replay["provider_calls"] == 0
    assert execute("export", "--destination", str(inspection)) == 0
    archive = InspectionArchive.open(inspection)
    assert archive.index.final_tick == 4
    assert archive.index.decisions
    assert all(row.resident_id == "ella" for row in archive.index.decisions)
    assert archive.read(archive.index.decisions[0].shard).record.origin == "model"
    assert archive.read(archive.index.cost).ledger_mode == "fake"
    assert not (run / "release.json").exists()


def test_resume_keeps_an_interrupted_dispatch_without_resending(tmp_path):
    (tmp_path / "checkpoints").mkdir()
    capture = live.Capture.open(tmp_path, live.Case.load())
    hits = []

    class InterruptedTransport:
        def exchange(self, body, timeout_ms):
            hits.append(body)
            raise RuntimeError("interrupted after claim")

    caller = Caller(InterruptedTransport(), FakeClock(), lambda _: None)
    with pytest.raises(RuntimeError, match="interrupted after claim"):
        capture.run(caller, through=2, resume=False, authority=None)
    result = capture.run(caller, through=2, resume=True, authority=None)
    assert result.reason == "interrupted_boundary" and result.tick == 0
    assert live.verify(capture).tail_attempts == len(hits) == 1


@pytest.mark.parametrize("commit_first", [False, True])
def test_budget_stop_preserves_final_checkpoint_and_reconciles_the_sent_attempt(
    tmp_path, monkeypatch, commit_first
):
    bounds = (15_000, 15_000) if commit_first else (30_000,)
    reserve = 188_000_000_000 if commit_first else 124_000_000_000
    monkeypatch.setattr(live, "REHEARSAL", {(0, "decision"): bounds})
    monkeypatch.setattr(live, "RESERVED", reserve)
    case = live.Case.load()
    preflight = case.preflight("fixture")
    day = "2026-11-25"
    from v2.live_resident_evidence.test_predispatch_evidence import evidence

    ledger_bytes = json_bytes(evidence(day, opening="0.05343482"))
    release = json_bytes(
        {
            "approval": "synthetic test release",
            "wire_evidence": "synthetic dated wire pin",
            "dispatch_on": day,
            "max_cny": "0.188" if commit_first else "0.124",
            "preflight_sha256": digest(preflight),
            "ledger_sha256": digest(ledger_bytes),
        }
    )
    authority = live.Authority.load(release, ledger_bytes, preflight)
    (tmp_path / "checkpoints").mkdir()
    (tmp_path / "release.json").write_bytes(release)
    (tmp_path / "ledger-base.json").write_bytes(ledger_bytes)
    capture = live.Capture.open(tmp_path, case)
    clock = FakeClock(datetime(2026, 11, 25, tzinfo=UTC))
    hits = []

    class RetryTransport(live.OfflineTransport):
        def exchange(self, body, timeout_ms):
            hits.append(body)
            response = super().exchange(body, timeout_ms)
            if commit_first and len(hits) == 1:
                payload = json.loads(response.body)
                payload["usage"] = {
                    "input_tokens": 100,
                    "output_tokens": 8_000,
                    "prompt_cache_hit_tokens": 0,
                }
                return replace(response, body=json_bytes(payload))
            return replace(response, status=503)

    result = capture.run(
        Caller(RetryTransport(), clock, lambda _: None),
        through=4,
        resume=False,
        authority=authority,
    )
    assert result.status == "incomplete" and result.reason == "budget_stop"
    assert result.tick == int(commit_first)
    assert result.refusal.reason == "rehearsal_reserve"
    refused = result.refusal.dispatch
    assert refused.n == 1 and len(hits) == 1 + int(commit_first)
    with pytest.raises(KeyError):
        capture.audit.read(Journal.cursor(refused.call.call_id, "1.dispatch"))
    assert len(capture.boundaries()) == int(commit_first)
    assert not (capture.packets.directory / f"{result.tick + 1}.json").exists()

    verified = live.verify(capture)
    assert verified.tail_attempts == 1
    ledger = live.publish_ledger(verified)
    assert ledger.settled_pico == 53_434_820_000 + int(commit_first) * 32_100_000_000
    account = live.Account.model_validate_json(
        capture.audit.read(Journal.cursor(refused.call.call_id, "0.spend"))
    )
    assert account.settled_pico_cny is None
    assert ledger.reserve_pico == account.held_pico_cny > 0
    destination = tmp_path / "inspection"
    if commit_first:
        assert live.export_verified(verified, destination).final_tick == 1
    else:
        with pytest.raises(ValueError, match="no committed resident delivery"):
            live.export_verified(verified, destination)
        assert not destination.exists()
    with pytest.raises(ValueError, match="already sealed"):
        capture.run(
            Caller(RetryTransport(), clock, lambda _: None),
            through=4,
            resume=True,
            authority=authority,
        )
    assert len(hits) == 1 + int(commit_first)
