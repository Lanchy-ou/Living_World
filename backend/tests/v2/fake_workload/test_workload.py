"""EV-13 uses bounded prefixes and terminal branches in ordinary CI."""

import json

import pytest

from living_island.analysis.v2.export import fingerprint
from living_island.analysis.v2.shards import InspectionArchive
from living_island.memory.v2.profiles import SelectedProfile
from v2.fake_workload.evidence import capture, disconnected, terminal_cases
from v2.fake_workload.island import ROOT
from v2.resident_replay.test_resident_reconstruction import replace_fact
from v2.working_context.conftest import packet as packet


def test_ev13_bounded_workload(tmp_path, packet):
    exercise_periods(tmp_path / "periods", packet)
    for case, models in (("week", {"ella", "iris", "mia", "noah", "ryan"}), ("ella", {"ella"})):
        directory = tmp_path / case
        directory.mkdir()
        report = capture(directory, case, 10)
        print(f"{case} ten-tick capture, replay and export: {report['wall_seconds']:.2f}s")
        assert set(report["actors"]) == models
        assert report["network_dispatches"] == 0
        pins = json.loads((directory / "run-manifest.json").read_bytes())["inputs"]
        for actor, pin in pins["profiles"].items():
            path = ROOT / f"content/characters/v2/{pin['profile_id']}.json"
            assert (
                SelectedProfile.load(path, expected_sha256=pin["sha256"]).document.values
                == pin["values"]
            )
            assert (pin["controller"] == "fake") == (actor in models)
        for actor in models:
            row = report["actors"][actor]
            assert row["replayed_ticks"] == 10 and row["shards"] > 0
            assert row["index_sha256"] == fingerprint(directory / row["export"] / "index.json")
            assert all(
                row["terminal_counts"][kind] == 1
                for kind in ("timeout", "rate_limit", "server_error", "invalid_output")
            )
            assert row["days"][1]["retries"] == 4
            assert {"decision", "recall", "decision_after_recall"} <= set(
                row["single_copy_samples"]
            )
        if case == "week":
            noah = report["actors"]["noah"]
            assert noah["fallback_turns"] and noah["model_handbacks"]
            archive = InspectionArchive.open(directory / noah["export"])
            decisions = sorted(
                (c for c in archive.index.calls if c.call_kind == "decision"), key=lambda c: c.tick
            )
            attempts = [a for c in decisions for a in archive.read(c.shard).attempts]
            seventh = attempts[6]
            assert seventh.dispatch.call.turn_id == noah["fallback_turns"][0]
            assert (seventh.terminal.status, seventh.terminal.error_class) == (
                400,
                "provider_error",
            )
            assert noah["terminal_counts"]["provider_error"] == 1
            assert report["terminal_counts"]["provider_error"] == 1
    with disconnected():
        terminals = terminal_cases(tmp_path / "terminals")
    assert terminals["no_dispatch"]["attempts"] == 0
    assert set(terminals["death"]) == {"authorized", "prepared", "dispatched"}


def exercise_periods(directory, packet):
    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.agents.v2.context.prefix import FrozenPrefix
    from v2.consolidation.conftest import sleeping
    from v2.fake_workload.island import Island

    directory.mkdir()
    island = Island(directory, "ella", 75)
    island.advance()
    record = island.recordings["ella"]
    period = record.session.resident.period
    fake = island.fakes["ella"]
    for start, expected in ((1, "failed"), (38, "committed")):
        if period.context is None:
            period.open(FrozenPrefix(period.period_id, (), (), (), None))
        first, intents = sleeping(packet, tick=start + 1, start=start)
        period.deliver(first, intents=intents)
        flow = period.workflow
        while flow.state.stage != "ready":
            fake.delay(flow.advance(fake, fake.clock))
        closed = period.deliver(FilteredDelivery(packet(tick=start + 36))).record
        assert closed.outcome == expected
        if expected == "failed":
            (selection,) = flow.state.calls
            assert selection.authorized.kind == "consolidation_selection"
            (attempt,) = selection.attempts
            assert (attempt.terminal.status, attempt.terminal.error_class) == (
                400,
                "provider_error",
            )
            assert closed.pending_after == ("p:ella:1",)
        else:
            assert not closed.pending_after
            assert [(p.period_id, p.state) for p in closed.pending] == [("p:ella:1", "included")]
            assert {v.op_id: v.result for v in closed.verdicts} == {
                "missing": "dropped",
                "observation": "committed",
            }


def test_tampered_request_part(tmp_path):
    from living_island.sim.v2.harness.replay import History
    from v2.fake_workload.island import Island

    island = Island(tmp_path, "ella", 1)
    island.advance()
    record = island.recordings["ella"]
    history = History(record.audit, record.audit.cursor())
    key = record.session.records[0].prepared_cursors[0]
    verbs = tuple(v.shape for v in island.world.pack.verbs.values())
    prepared = history.request(key, verbs)
    entry = prepared.record.candidates[0].manifest.entries[0]
    replace_fact(record.audit.path, entry.sha256, b"tampered")
    with pytest.raises(ValueError, match="audit hash differs"):
        history.request(key, verbs)
