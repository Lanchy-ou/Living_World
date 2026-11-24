"""The five mapped starter tests, using short excerpts for the long evidence vectors."""

from functools import partial
from pathlib import Path


def _exercise(vector, directory: Path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.scenarios.runtime import Boundary

    scenario = vector.scenario
    world = scenario.world
    journal = PacketJournal(directory / vector.name, world.run_id)
    session = scenario.session(world, journal, None)
    stats = {}
    for _ in range(vector.horizon):
        tick = world.tick
        result = session.advance()
        assert result is not None
        record = session.runner.manifest.boundaries.pop().for_replay()
        stats = scenario.observe(
            stats,
            Boundary(
                tick,
                record,
                result,
                partial(journal.read, tick),
                lambda: _encode_snapshot(world),
            ),
        )
    assert stats
    return stats


def _encode_snapshot(world):
    from living_island.world.v2.engine.snapshot import encode_snapshot

    return encode_snapshot(world)


def test_ct08_world_rules(tmp_path: Path):
    from living_island.sim.v2.scenarios.dynamics import physical

    for vector in (
        physical.regrowth(),
        physical.lighting(succeeds=True),
        physical.lighting(succeeds=False),
        physical.baking(5),
        physical.spilling(blocked=False),
        physical.fruit(short=True),
        physical.fruit(crumble=True),
        physical.wear(),
    ):
        _exercise(vector, tmp_path)


def test_ct09_fatigue_faint_and_sleep(tmp_path: Path):
    from living_island.sim.v2.scenarios.dynamics import physiology

    for vector in (
        physiology.fatigue_day(short=True),
        physiology.fainting(short=True),
        physiology.night(short=True),
    ):
        _exercise(vector, tmp_path)


def test_ct10_starter_urgent_and_critical(tmp_path: Path):
    from living_island.sim.v2.scenarios.dynamics.physiology import early_wake

    for need in ("satiety", "hydration"):
        for critical in (False, True):
            _exercise(early_wake(need, critical=critical), tmp_path)


def test_ct11_starter_asleep_and_awake_rates(tmp_path: Path):
    from living_island.sim.v2.scenarios.dynamics.physiology import rate_control

    _exercise(rate_control(), tmp_path)


def test_ct19_due_tick_blocked_spill_and_split_resume(tmp_path: Path, monkeypatch):
    from living_island.sim.v2 import cli
    from living_island.sim.v2.scenarios.dynamics import physical
    from living_island.sim.v2.scenarios.dynamics.__main__ import case_plan
    from living_island.sim.v2.scenarios.runtime import replay_case, run_or_resume

    _exercise(physical.baking(6), tmp_path)
    _exercise(physical.baking(7), tmp_path)
    _exercise(physical.spilling(blocked=True), tmp_path)

    # The shared recorder covers repository provenance separately. The test uses local fixtures
    # even while its own executable source is being edited.
    monkeypatch.setattr(cli, "bind_evidence", lambda directory, through: None)

    def setup():
        return physical.fruit(split=True).scenario

    vector = physical.fruit(split=True)
    plan = case_plan(vector, "pytest-ct19-split")
    direct, interrupted = tmp_path / "direct", tmp_path / "interrupted"
    first = run_or_resume(direct, plan, setup)
    paused = run_or_resume(interrupted, plan, setup, pause_after=lambda tick: tick == 1)
    assert paused.evidence is None and paused.tick == 1
    resumed = run_or_resume(interrupted, plan, setup)
    assert first.evidence is not None and resumed.evidence is not None
    assert resumed.timing.attempts[-1].resumed_tick == 1
    assert first.evidence.observer == resumed.evidence.observer
    assert first.evidence.prefix_sha256 == resumed.evidence.prefix_sha256
    assert first.evidence.final_snapshot_sha256 == resumed.evidence.final_snapshot_sha256
    pack = vector.scenario.world.pack.source
    assert list(replay_case(direct, pack)) == list(replay_case(interrupted, pack))
