"""Within-case recovery on the registered compatibility smoke fixture."""

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass, replace
from functools import partial
from hashlib import sha256
from pathlib import Path

import pytest


def _files(directory, pattern):
    return {path.name: path.read_bytes() for path in sorted(directory.glob(pattern))}


def _saved_world(directory, progress, scenario):
    from living_island.persistence.v2.checkpoint import load_checkpoint
    from living_island.persistence.v2.journal import PacketJournal

    journal = PacketJournal(directory / "packets", scenario.world.run_id)
    return load_checkpoint(directory / progress.checkpoint, scenario.world.pack.source, journal)


@pytest.mark.parametrize(("mode", "split_tick"), [("script", 1), ("policy", 3)])
def test_resume_inside_action_then_recover_final_boundary(tmp_path, mode, split_tick):
    from scenario_smoke import plan, setup

    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.scenarios.runtime import replay_case, run_or_resume
    from living_island.world.v2.engine.snapshot import encode_snapshot

    direct, split = tmp_path / "direct", tmp_path / "split"
    factory = partial(setup, mode)
    case = plan(mode)
    complete = run_or_resume(direct, case, factory)
    interior = run_or_resume(split, case, factory, pause_after=lambda tick: tick == split_tick)
    assert interior.tick == split_tick and interior.evidence is None
    scenario = factory()
    pack = scenario.world.pack.source
    reopened = _saved_world(split, interior, scenario)
    packets = reopened.world.pending_packets()
    assert packets and all(packet.observed_tick == split_tick for packet in packets)
    running_actor = "ella" if mode == "script" else "ryan"
    packet = next(packet for packet in packets if packet.actor_id == running_actor)
    assert packet.perception.running_action is not None
    assert not (split / f"packets/{split_tick}.json").exists()
    assert PacketJournal(direct / "packets", scenario.world.run_id).read(split_tick) == packets
    cursor = reopened.sim_checkpoint
    assert cursor["observer"]["ticks"] == split_tick
    if mode == "script":
        assert all(position == 1 for position in cursor["controller"]["position"].values())
    else:
        assert cursor["controller"][running_actor]["cursor"] == split_tick - 1

    reference = list(replay_case(direct, pack))
    assert encode_snapshot(reopened.world) == reference[split_tick - 1].snapshot
    final_boundary = run_or_resume(split, case, factory, pause_after=lambda t: t == case.horizon)
    assert final_boundary.tick == case.horizon and final_boundary.evidence is None
    assert final_boundary.timing.attempts[-1].resumed_tick == split_tick
    assert final_boundary.timing.attempts[-1].last_checkpoint_tick == case.horizon
    assert not (split / "evidence.json").exists()
    assert (split / "inputs.json").read_bytes() == (direct / "inputs.json").read_bytes()
    assert _files(split, "packets/*.json") == _files(direct, "packets/*.json")
    assert _files(split, "turns/*.json") == _files(direct, "turns/*.json")

    def next_choice(directory):
        return next(
            (tick, turn)
            for tick in range(split_tick, case.horizon)
            for turn in json.loads((directory / f"turns/{tick}.json").read_bytes())["submissions"]
            if turn["actor_id"] == running_actor
        )

    tick, turn = next_choice(split)
    assert (tick, turn) == next_choice(direct)
    if mode == "policy":
        assert (tick, turn["turn_id"]) == (4, "ryan:t000003")
    else:
        assert tick == 1 and turn["action"]["kind"] == "continue"
    assert list(replay_case(split, pack)) == reference

    recovered = run_or_resume(split, case, factory)
    assert recovered.timing.attempts[-1].resumed_tick == case.horizon
    assert recovered.evidence is not None and complete.evidence is not None
    assert recovered.evidence.provider_calls == 0
    assert recovered.evidence.final_tick == case.horizon
    assert recovered.evidence.prefix_sha256 == complete.evidence.prefix_sha256
    assert recovered.evidence.observer == complete.evidence.observer
    assert recovered.evidence.observer["ticks"] == case.horizon
    assert recovered.evidence.final_snapshot_sha256 == sha256(reference[-1].snapshot).hexdigest()
    final_world = _saved_world(split, recovered, scenario)
    assert encode_snapshot(final_world.world) == reference[-1].snapshot
    assert final_world.sim_checkpoint == _saved_world(direct, complete, scenario).sim_checkpoint

    evidence_bytes = (split / "evidence.json").read_bytes()
    points = _files(split, "checkpoints/*.json")
    retry = run_or_resume(split, case, factory)
    assert retry.evidence == recovered.evidence
    assert retry.timing.active_ns == recovered.timing.active_ns
    assert (split / "evidence.json").read_bytes() == evidence_bytes
    assert _files(split, "checkpoints/*.json") == points


@pytest.mark.parametrize(
    ("altered", "message"),
    [("input", "inputs.json"), ("packet", "committed witness prefix"), ("checkpoint", "digest")],
)
def test_refusal_preserves_boundary_and_failed_attempt(tmp_path, altered, message):
    from scenario_smoke import plan, setup

    from living_island.sim.v2.scenarios.runtime import run_or_resume
    from living_island.world.v2.rules.schema import canonical_json_bytes

    factory = partial(setup, "script")
    case = plan("script").model_copy(update={"checkpoint_every": 1})
    stopped = run_or_resume(tmp_path, case, factory, pause_after=lambda tick: tick == 2)
    requested = case
    if altered == "input":
        requested = case.model_copy(update={"controller": "changed-script"})
    else:
        path = tmp_path / ("packets/0.json" if altered == "packet" else stopped.checkpoint)
        original = path.read_bytes()
        if altered == "packet":
            # Still a canonical packet, outside EN-07's latest checkpoint window.
            batch = json.loads(original)
            batch["packets"][0]["perception"]["own_position"]["x"] ^= 1
            path.write_bytes(canonical_json_bytes(batch))
        else:
            path.write_bytes(original + b" ")

    witnesses = {
        kind: _files(tmp_path, f"{kind}/*.json") for kind in ("packets", "turns", "checkpoints")
    }
    with pytest.raises(ValueError, match=message):
        run_or_resume(tmp_path, requested, factory)
    for kind, expected in witnesses.items():
        assert _files(tmp_path, f"{kind}/*.json") == expected
    assert not (tmp_path / "evidence.json").exists()
    if altered != "input":
        path.write_bytes(original)
    result = run_or_resume(tmp_path, case, factory)
    assert [attempt.status for attempt in result.timing.attempts[:2]] == ["paused", "failed"]
    assert message in result.timing.attempts[1].failure
    assert result.timing.attempts[-1].resumed_tick == 2
    assert result.evidence.observer["ticks"] == case.horizon


@dataclass
class _ManualClock:
    active: int = 0
    wall: int = 1000

    def monotonic_ns(self):
        return self.active

    def wall_ns(self):
        return self.wall

    def spend(self, ns):
        self.active += ns
        self.wall += ns


def test_attempt_limit_and_cumulative_active_budget(tmp_path, monkeypatch):
    from scenario_smoke import plan, setup

    from living_island.sim.v2.scenarios import runtime

    clock = _ManualClock()
    case = plan("script").model_copy(update={"horizon": 3, "budget_ns": 27})

    def measured_setup():
        clock.spend(3)
        scenario = setup("script")

        def observe(state, boundary):
            clock.spend(5)
            return scenario.observe(state, boundary)

        return replace(scenario, observe=observe)

    publish = runtime.store_once

    def measured_write(path, data):
        publish(path, data)
        if path.name == "evidence.json":
            clock.spend(7)

    monkeypatch.setattr(runtime, "store_once", measured_write)
    partial_run = runtime.run_or_resume(
        tmp_path, case, measured_setup, attempt_limit_ns=8, clock=clock
    )
    assert partial_run.tick == 1 and partial_run.evidence is None
    assert partial_run.timing.active_ns == 8 and partial_run.timing.verdict == "partial"
    assert partial_run.timing.attempts[0].attempt_limit_ns == 8
    clock.wall += 90
    complete = runtime.run_or_resume(tmp_path, case, measured_setup, clock=clock)
    assert complete.timing.active_ns == 28  # Two setups, three ticks and durable evidence.
    assert complete.timing.downtime_ns == 90
    assert complete.timing.unclassified_gap_ns == 0
    assert complete.timing.verdict == "exceeded"
    assert complete.timing.ticks_per_second == 3_000_000_000 / 28


def _abandon_case(directory):
    from scenario_smoke import plan, setup

    from living_island.sim.v2.scenarios.runtime import run_or_resume

    clock = _ManualClock()
    case = plan("script").model_copy(update={"checkpoint_every": 1, "budget_ns": 100})

    def after_tick(tick):
        clock.spend(5)
        if tick == 2:
            # Kill the writer after its previous checkpoint, before the next publication.
            os._exit(37)
        return False

    run_or_resume(
        Path(directory), case, partial(setup, "script"), pause_after=after_tick, clock=clock
    )


def test_unclean_process_exit_keeps_elapsed_bound_indeterminate(tmp_path):
    from scenario_smoke import plan, setup

    from living_island.sim.v2.scenarios.runtime import run_or_resume

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from test_runtime import _abandon_case; import sys; _abandon_case(sys.argv[1])",
            str(tmp_path),
        ],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 37, child.stderr
    case = plan("script").model_copy(update={"checkpoint_every": 1, "budget_ns": 100})
    resumed = run_or_resume(tmp_path, case, partial(setup, "script"), clock=_ManualClock(wall=1200))
    first, second = resumed.timing.attempts
    assert first.status == "interrupted" and first.active_ns == 5
    assert second.resumed_tick == 1
    assert resumed.evidence.observer["ticks"] == case.horizon
    assert resumed.timing.active_ns == 5
    assert resumed.timing.downtime_ns == 0
    assert resumed.timing.unclassified_gap_ns == 195
    assert resumed.timing.verdict == "indeterminate"
    assert resumed.timing.ticks_per_second is None


def test_script_stop_records_failure_before_any_boundary_commit(tmp_path):
    from scenario_smoke import plan, setup

    from living_island.sim.v2.manifest import TerminalStop
    from living_island.sim.v2.scenarios.runtime import run_or_resume, scripted

    class StopScript:
        def deliver(self, packet):
            return False

        def choose(self, request):
            return TerminalStop("fixture stopped", {"turn": request.turn_id})

        def checkpoint(self):
            return {}

    def stop_setup():
        return replace(setup("script"), session=scripted(lambda saved: StopScript()))

    with pytest.raises(ValueError, match="fixture stopped"):
        run_or_resume(tmp_path, plan("script"), stop_setup)
    with closing(sqlite3.connect(tmp_path / "progress.sqlite")) as db:
        status, error = db.execute("SELECT status, failure FROM attempts").fetchone()
        assert status == "failed" and "fixture stopped" in error
        assert db.execute("SELECT tick FROM checkpoints").fetchall() == [(0,)]
    assert not (tmp_path / "evidence.json").exists()
    assert not _files(tmp_path, "turns/*.json")
