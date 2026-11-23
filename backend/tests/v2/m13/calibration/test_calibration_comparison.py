"""CT-20 trace comparison and coverage refusal at the campaign input boundary."""

from pathlib import Path

import pytest


@pytest.fixture
def sample():
    from living_island.sim.equivalence.projection import read_projection
    from living_island.sim.v2.scenarios.calibration.comparison import (
        ActorTrace,
        PhysicalFrame,
        PolicyBoundary,
        TraceBoundary,
        Trajectory,
    )

    path = (
        Path(__file__).resolve().parents[3]
        / "fixtures/v1_projection/scripted/wap23-give-same-tile.json.gz"
    )
    oracle = read_projection(path)
    frames = [
        PhysicalFrame.model_validate(
            frame.model_dump(exclude={"utterances", "decisions", "outcomes"})
        )
        for frame in oracle.frames
    ]
    actors = [resident.id for resident in frames[0].residents]
    rows = [
        TraceBoundary(
            seed=oracle.source.seed,
            tick=opening.tick,
            actors={actor: ActorTrace(ordinal=2, decision=None) for actor in actors},
            submissions=[],
            trajectory=Trajectory(
                opening=opening if opening.tick == frames[0].tick else None,
                closing=closing,
                actions=[],
                utterances={},
                spoken=[],
                final_boundary=(
                    PolicyBoundary(
                        tick=closing.tick,
                        actors={actor: ActorTrace(ordinal=2, decision=None) for actor in actors},
                        submissions=[],
                    )
                    if closing.tick == frames[-1].tick
                    else None
                ),
            ),
        )
        for opening, closing in zip(frames, frames[1:], strict=False)
    ]
    return oracle, actors, rows


def test_first_different_actor_tick_ordinal_and_field(sample):
    from living_island.sim.v2.scenarios.calibration.comparison import compare_traces

    oracle, actors, rows = sample
    changed = rows[1].model_copy(deep=True)
    changed.actors["ella"] = changed.actors["ella"].model_copy(
        update={"deferred": ("URGENT_NEED",)}
    )
    result = compare_traces(
        oracle.source.seed, 0, len(rows), actors, rows, [rows[0], changed, *rows[2:]]
    )
    assert result.status == "different"
    assert result.compared_boundaries == 1
    assert result.difference.model_dump() == {
        "seed": oracle.source.seed,
        "tick": 1,
        "actor": "ella",
        "ordinal": 2,
        "field": "actors.ella.deferred.length",
        "expected": 0,
        "actual": 1,
    }
    final = rows[-1].model_copy(deep=True)
    final.trajectory.final_boundary.actors["ella"] = changed.actors["ella"]
    result = compare_traces(oracle.source.seed, 0, len(rows), actors, rows, [*rows[:-1], final])
    assert (result.difference.tick, result.difference.actor, result.difference.ordinal) == (
        final.trajectory.closing.tick,
        "ella",
        2,
    )
    assert result.difference.field == "trajectory.final_boundary.actors.ella.deferred.length"


def test_archive_exposes_identical_wrong_opening_in_both_modes(sample):
    from living_island.sim.v2.scenarios.calibration.comparison import compare_traces

    oracle, actors, rows = sample
    opening_tree = rows[0].trajectory.opening.trees[0]
    opening_tree.stock += 1
    result = compare_traces(oracle.source.seed, 0, len(rows), actors, rows, rows, oracle=oracle)
    assert result.status == "different"
    assert result.difference.tick == 0
    assert result.difference.field == "archive.trees[0].stock"
    assert result.difference.expected + 1 == result.difference.actual == opening_tree.stock


def test_missing_mode_boundary_is_incomplete(sample):
    from living_island.sim.v2.scenarios.calibration.comparison import compare_traces

    oracle, actors, rows = sample
    result = compare_traces(oracle.source.seed, 0, len(rows), actors, rows, rows[:-1])
    assert result.status == "incomplete"
    assert result.difference.tick == len(rows) - 1
    assert result.difference.field == "coverage.boundary"
    assert result.difference.actual == ["bridge"]


def test_wrong_tick_seed_or_roster_in_one_or_both_modes_is_incomplete(sample):
    from living_island.sim.v2.scenarios.calibration.comparison import compare_traces

    oracle, actors, rows = sample
    for change, field in (
        ({"tick": 1}, "tick"),
        ({"seed": oracle.source.seed + 1}, "seed"),
        ({"actors": {"ella": rows[0].actors["ella"]}}, "actors.length"),
    ):
        changed = [rows[0].model_copy(update=change), *rows[1:]]
        result = compare_traces(oracle.source.seed, 0, len(rows), actors, changed, changed)
        assert result.status == "incomplete"
        assert result.difference.field == f"coverage.bridge.{field}"
    missing_opening = rows[0].model_copy(deep=True)
    missing_opening.trajectory.opening = None
    result = compare_traces(
        oracle.source.seed, 0, len(rows), actors, [missing_opening, *rows[1:]], rows, oracle=oracle
    )
    assert result.status == "incomplete"
    assert result.difference.field == "coverage.bridge.opening"


def test_extra_mode_boundary_is_incomplete(sample):
    from living_island.sim.v2.scenarios.calibration.comparison import compare_traces

    oracle, actors, rows = sample
    result = compare_traces(oracle.source.seed, 0, len(rows) - 1, actors, rows[:-1], rows)
    assert result.status == "incomplete"
    assert result.difference.field == "coverage.visible.tick"
    assert result.difference.actual == rows[-1].tick


def test_archive_interval_must_cover_the_requested_ticks(sample):
    from living_island.sim.v2.scenarios.calibration.comparison import compare_traces

    oracle, actors, rows = sample
    result = compare_traces(oracle.source.seed, 0, len(rows) + 1, actors, rows, rows, oracle=oracle)
    assert result.status == "incomplete"
    assert result.difference.field == "coverage.archive.interval[1]"
    assert result.difference.actual == len(rows)


def test_en08_digest_must_match_the_independently_rebuilt_frames(sample):
    from living_island.sim.v2.scenarios.calibration.comparison import compare_traces

    oracle, actors, rows = sample
    physical = [rows[0].trajectory.opening, *(row.trajectory.closing for row in rows)]
    oracle = oracle.model_copy(update={"frames": physical})
    matching = compare_traces(oracle.source.seed, 0, len(rows), actors, rows, rows, oracle=oracle)
    assert matching.status == "equal"
    result = compare_traces(
        oracle.source.seed,
        0,
        len(rows),
        actors,
        rows,
        rows,
        oracle=oracle,
        en08_sha256="0" * 64,
    )
    assert result.status == "different"
    assert result.difference.field == "en08.v2_projection_sha256"
    assert result.difference.actual == matching.projection_sha256 == result.projection_sha256
