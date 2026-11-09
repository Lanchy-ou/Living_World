"""Dijkstra pathfinding: normative vectors, frontier rule and pure failures (WR §5.3)."""

from __future__ import annotations

from typing import Any

import pytest
from world_builders import default_content, static_map

from living_island.world.pathfinding import PathResult, find_path
from living_island.world.protocol import Coord
from living_island.world.space import StaticMap


def c(x: int, y: int) -> Coord:
    return Coord(x=x, y=y)


def everything(smap: StaticMap) -> set[int]:
    return set(range(smap.width * smap.height))


def directions(start: Coord, result: PathResult) -> str:
    out = []
    cx, cy = start.x, start.y
    for step in result.route:
        out.append(
            {(0, -1): "N", (1, 0): "E", (0, 1): "S", (-1, 0): "W"}[(step.x - cx, step.y - cy)]
        )
        cx, cy = step.x, step.y
    return "".join(out)


# --------------------------------------------------------------- normative vectors


def test_vector_a_open_3x3_grass_goes_east_then_south() -> None:
    smap = static_map([",,,", ",,,", ",,,"])
    result = find_path(smap, everything(smap), c(0, 0), c(1, 1))
    assert result.status == "ok"
    assert directions(c(0, 0), result) == "ES"
    assert result.cost == 2


def test_vector_b_default_map_cave_to_spring_adjacent_costs_36() -> None:
    content = default_content()
    smap = StaticMap.from_content(content)
    result = find_path(smap, everything(smap), c(13, 32), c(37, 30))
    assert result.status == "ok"
    assert result.cost == 36
    # The cost is the sum of the actual entry costs of the route.
    total = 0
    for step in result.route:
        cost = smap.step_cost(step.x, step.y)
        assert cost is not None
        total += cost
    assert total == 36
    assert result.route[-1] == c(37, 30)


# --------------------------------------------------------------- Dijkstra rules


def test_costs_not_hops_decide_the_route() -> None:
    # Direct row is woods (cost 2 each); the detour over beach costs 1 per tile.
    smap = static_map([",WWW,", "....."])
    result = find_path(smap, everything(smap), c(0, 0), c(4, 0))
    assert result.cost == 6 and directions(c(0, 0), result) == "SEEEEN"


def test_equal_cost_keeps_first_predecessor_and_is_deterministic() -> None:
    smap = static_map([",,,", ",,,", ",,,"])
    explored = everything(smap)
    first = find_path(smap, explored, c(0, 0), c(2, 2))
    again = find_path(smap, explored, c(0, 0), c(2, 2))
    assert first == again
    assert first.cost == 4


def test_start_equals_target_is_an_empty_route() -> None:
    smap = static_map([",,,"])
    result = find_path(smap, everything(smap), c(1, 0), c(1, 0))
    assert result == PathResult("ok", (), 0)


def test_only_explored_tiles_are_used() -> None:
    # The straight row is unexplored; only the lower row is known, so the route must use it.
    smap = static_map([",,,,", ",,,,"])
    explored = {smap.index(0, 0), smap.index(0, 1), smap.index(1, 1), smap.index(2, 1)}
    explored |= {smap.index(3, 1), smap.index(3, 0)}
    result = find_path(smap, explored, c(0, 0), c(3, 0))
    assert result.status == "ok"
    assert directions(c(0, 0), result) == "SEEEN"


def test_search_does_not_mutate_its_inputs() -> None:
    smap = static_map([",,,", ",,,"])
    explored = everything(smap)
    snapshot = set(explored)
    find_path(smap, explored, c(0, 0), c(2, 1))
    assert explored == snapshot


# --------------------------------------------------------------- frontier rule


def test_adjacent_unexplored_frontier_target_is_costed_as_grass() -> None:
    # The target is really woods (cost 2) but the search charges grass (cost 1).
    smap = static_map([",,W"])
    explored = {smap.index(0, 0), smap.index(1, 0)}
    result = find_path(smap, explored, c(0, 0), c(2, 0))
    assert result.status == "ok"
    assert result.cost == 2  # 1 (explored grass) + 1 (tentative grass), not 1 + 2
    assert result.route[-1] == c(2, 0)


def test_unexplored_target_not_adjacent_to_explored_is_out_of_the_search_space() -> None:
    smap = static_map([",,,,"])
    explored = {smap.index(0, 0), smap.index(1, 0)}
    result = find_path(smap, explored, c(0, 0), c(3, 0))
    assert result == PathResult("NO_PATH", (), 0)


def test_only_one_unexplored_tile_may_be_entered() -> None:
    smap = static_map([",,,,"])
    explored = {smap.index(0, 0)}
    assert find_path(smap, explored, c(0, 0), c(1, 0)).status == "ok"
    assert find_path(smap, explored, c(0, 0), c(2, 0)).status == "NO_PATH"


def test_frontier_must_touch_an_explored_passable_tile() -> None:
    # (1,0) is explored but impassable rock: it does not make (2,0) a frontier.
    smap = static_map([",^,"])
    explored = {smap.index(0, 0), smap.index(1, 0)}
    assert find_path(smap, explored, c(0, 0), c(2, 0)).status == "NO_PATH"


# --------------------------------------------------------------- failures are pure results


@pytest.mark.parametrize("symbol", [",", ".", "W", "F", "M", "C", "^", "~", "S"])
def test_unseen_frontier_target_routes_identically_whatever_its_terrain(symbol: str) -> None:
    """G2-01: WR §5.3 charges an unexplored frontier tile as grass and defers passability
    and the actual cost to step execution (P1-04); the search never peeks at its terrain."""
    smap = static_map([",," + symbol])
    explored = {smap.index(0, 0), smap.index(1, 0)}
    result = find_path(smap, explored, c(0, 0), c(2, 0))
    assert result == PathResult("ok", (c(1, 0), c(2, 0)), 2)


def test_start_is_not_implicitly_explored() -> None:
    """G2-01: a frontier tile must touch an already explored passable tile."""
    smap = static_map([",,,"])
    assert find_path(smap, set(), c(0, 0), c(1, 0)) == PathResult("NO_PATH", (), 0)
    explored = {smap.index(0, 0)}
    assert find_path(smap, explored, c(0, 0), c(1, 0)).status == "ok"


def test_explored_impassable_target_is_path_blocked() -> None:
    smap = static_map([",,~"])
    result = find_path(smap, everything(smap), c(0, 0), c(2, 0))
    assert result == PathResult("PATH_BLOCKED", (), 0)


def test_unreachable_explored_target_is_no_path() -> None:
    smap = static_map([",^,"])
    result = find_path(smap, everything(smap), c(0, 0), c(2, 0))
    assert result == PathResult("NO_PATH", (), 0)


def test_failures_change_no_state_even_for_unseen_terrain() -> None:
    smap = static_map([",,^"])
    explored = {smap.index(0, 0), smap.index(1, 0)}
    before = set(explored)
    find_path(smap, explored, c(0, 0), c(2, 0))
    assert explored == before  # the rock was not "revealed" into the footprint


def test_woods_and_fruit_tree_costs_are_applied() -> None:
    cfg: Any = default_content().config
    smap = static_map([",W,", ",F,"])
    explored = everything(smap)
    through_w = find_path(smap, explored, c(0, 0), c(1, 0))
    assert through_w.cost == cfg.map.step_cost_woods
    through_f = find_path(smap, explored, c(0, 1), c(1, 1))
    assert through_f.cost == cfg.map.step_cost_fruit_tree
