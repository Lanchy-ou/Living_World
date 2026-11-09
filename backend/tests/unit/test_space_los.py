"""Map classification, clock/radius and Bresenham line of sight (World Rules §1, §5.1)."""

from __future__ import annotations

from typing import Any

import pytest
from world_builders import default_content, static_map

from living_island.world.space import (
    StaticMap,
    clock_minutes,
    has_line_of_sight,
    is_daylight,
    line_points,
    sight_radius,
    visible_tile_indices,
)


def coords(smap: StaticMap, indices: list[int]) -> set[tuple[int, int]]:
    return {(i % smap.width, i // smap.width) for i in indices}


def test_terrain_classification_covers_all_nine_symbols() -> None:
    smap = static_map(["~.,W^SCFM"])
    names = [smap.terrain(x, 0) for x in range(9)]
    assert names == [
        "sea",
        "beach",
        "grass",
        "woods",
        "rock",
        "spring",
        "cave",
        "fruit_tree",
        "damp_moss",
    ]


def test_fruit_tree_is_wooded_and_moss_is_grassy() -> None:
    cfg: Any = default_content().config
    smap = static_map([",F,M,W,"])
    # F: passable at the fruit-tree cost, opaque. M: passable at the moss cost, clear.
    assert smap.step_cost(1, 0) == cfg.map.step_cost_fruit_tree
    assert smap.blocks_sight(1, 0)
    assert smap.step_cost(3, 0) == cfg.map.step_cost_damp_moss
    assert not smap.blocks_sight(3, 0)
    assert smap.step_cost(5, 0) == cfg.map.step_cost_woods and smap.blocks_sight(5, 0)


def test_impassable_and_opaque_tiles() -> None:
    smap = static_map(["~^S.,CM"])
    assert [smap.step_cost(x, 0) is None for x in range(3)] == [True, True, True]
    assert [smap.step_cost(x, 0) is not None for x in range(3, 7)] == [True] * 4
    # Only rock blocks sight among these; sea and spring are clear.
    assert [smap.blocks_sight(x, 0) for x in range(7)] == [False, True, False] + [False] * 4


# ----------------------------------------------------------------- clock and radius


def test_clock_and_daylight_boundaries() -> None:
    cfg: Any = default_content().config  # start 06:00, 10-minute ticks, day [6, 20)
    assert clock_minutes(cfg, 0) == 6 * 60
    assert is_daylight(cfg, 0)
    assert is_daylight(cfg, 83)  # 19:50
    assert not is_daylight(cfg, 84)  # 20:00: the end hour itself is night
    assert not is_daylight(cfg, 143)  # 05:50
    assert is_daylight(cfg, 144)  # next day 06:00 (clock wraps)


def test_sight_radius_uses_completed_tick_clock() -> None:
    cfg: Any = default_content().config
    assert sight_radius(cfg, 0) == cfg.perception.day_radius_tiles
    assert sight_radius(cfg, 83) == cfg.perception.day_radius_tiles
    assert sight_radius(cfg, 84) == cfg.perception.night_radius_tiles


def test_night_radius_shrinks_visible_set() -> None:
    smap = static_map(["." * 21 for _ in range(21)])
    day = visible_tile_indices(smap, 10, 10, 8)
    night = visible_tile_indices(smap, 10, 10, 3)
    assert len(night) == 25  # Manhattan ball of radius r has 2r^2+2r+1 tiles
    assert len(day) == 145
    assert coords(smap, night) <= coords(smap, day)


# ----------------------------------------------------------------- line of sight


def test_radius_edge_is_visible_and_beyond_is_not() -> None:
    smap = static_map(["." * 9])
    seen = coords(smap, visible_tile_indices(smap, 0, 0, 3))
    assert seen == {(0, 0), (1, 0), (2, 0), (3, 0)}


def test_radius_is_manhattan_not_euclidean() -> None:
    smap = static_map(["." * 7 for _ in range(7)])
    seen = coords(smap, visible_tile_indices(smap, 3, 3, 2))
    assert (5, 3) in seen and (4, 4) in seen
    assert (5, 4) not in seen  # distance 3
    assert (3, 5) in seen and (1, 1) not in seen


def test_blocking_target_is_visible_but_hides_what_is_behind() -> None:
    smap = static_map([".." + "W" + "..."])
    seen = coords(smap, visible_tile_indices(smap, 0, 0, 5))
    assert (2, 0) in seen  # the blocker itself
    assert (3, 0) not in seen and (4, 0) not in seen


@pytest.mark.parametrize("blocker", ["W", "F", "^"])
def test_woods_fruit_tree_and_rock_block(blocker: str) -> None:
    smap = static_map(["." + blocker + "."])
    assert not has_line_of_sight(smap, 0, 0, 2, 0)
    assert has_line_of_sight(smap, 0, 0, 1, 0)


@pytest.mark.parametrize("clear", ["~", ".", ",", "M", "S", "C"])
def test_clear_tiles_do_not_block(clear: str) -> None:
    smap = static_map(["." + clear + "."])
    assert has_line_of_sight(smap, 0, 0, 2, 0)


@pytest.mark.parametrize("start_symbol", ["F", "W"])
def test_start_tile_never_blocks(start_symbol: str) -> None:
    smap = static_map([start_symbol + "..."])
    assert has_line_of_sight(smap, 0, 0, 3, 0)
    seen = coords(smap, visible_tile_indices(smap, 0, 0, 3))
    assert seen == {(0, 0), (1, 0), (2, 0), (3, 0)}


def test_observer_sees_its_own_tile() -> None:
    smap = static_map(["^"])
    assert visible_tile_indices(smap, 0, 0, 0) == [0]


def test_los_is_not_symmetric() -> None:
    rows = ["......", "..W...", "......", "......"]
    smap = static_map(rows)
    # Verified case: the Bresenham line from (0,0) to (4,1) crosses the woods tile,
    # while the line from (4,1) back to (0,0) does not.
    assert not has_line_of_sight(smap, 0, 0, 4, 1)
    assert has_line_of_sight(smap, 4, 1, 0, 0)


def test_candidates_stay_inside_the_map() -> None:
    smap = static_map(["...", "...", "..."])
    seen = visible_tile_indices(smap, 0, 0, 8)
    assert seen == list(range(9))


def test_visible_tiles_are_ascending_y_then_x() -> None:
    smap = static_map(["." * 9 for _ in range(9)])
    seen = visible_tile_indices(smap, 4, 4, 4)
    assert seen == sorted(seen)
    assert len(seen) == len(set(seen))


def test_pre_update_e2_is_shared_by_both_axis_updates() -> None:
    # A pure diagonal: both updates fire in the same iteration (no corner-cutting rule).
    smap = static_map(["....", ".W..", "....", "...."])
    assert has_line_of_sight(smap, 0, 0, 3, 3) is False  # passes through (1,1)
    smap2 = static_map(["W...", ".W..", "..W.", "...."])
    assert has_line_of_sight(smap2, 0, 0, 3, 3) is False  # starts on W, blocked by (1,1)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ((0, 0), (3, 3), [(1, 1), (2, 2), (3, 3)]),  # both axes update on one e2
        ((0, 0), (4, 1), [(1, 0), (2, 1), (3, 1), (4, 1)]),  # shared pre-update e2
        ((4, 1), (0, 0), [(3, 1), (2, 0), (1, 0), (0, 0)]),  # reverse line differs
        ((0, 0), (0, 3), [(0, 1), (0, 2), (0, 3)]),
        ((2, 2), (2, 2), []),
    ],
)
def test_bresenham_lines_use_the_shared_pre_update_e2(
    start: tuple[int, int], end: tuple[int, int], expected: list[tuple[int, int]]
) -> None:
    assert list(line_points(*start, *end)) == expected
