"""Dijkstra pathfinding over a resident's explored static tiles (World Rules §5.3).

A pure function: it reads the static map and an explored set and returns a result; it never
changes state, reveals terrain or moves anyone. Action legality (``INVALID_TARGET``),
stamina and budget packing belong to P1-04.
"""

from __future__ import annotations

import heapq
from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from living_island.world.protocol import Coord
from living_island.world.space import StaticMap

PathStatus = Literal["ok", "PATH_BLOCKED", "NO_PATH"]

# Expansion order is normative: N, E, S, W.
NEIGHBOR_STEPS: tuple[tuple[int, int], ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))


@dataclass(frozen=True)
class PathResult:
    """Outcome of one search.

    ``route`` lists the tiles to enter in order (start excluded). For ``PATH_BLOCKED`` on a
    permitted unexplored frontier target it holds the approach tiles up to, but excluding,
    the impassable target; for any other blocked or unreachable result it is empty.
    ``cost`` is the sum of the route's search costs.
    """

    status: PathStatus
    route: tuple[Coord, ...]
    cost: int


def _is_frontier(
    smap: StaticMap, explored: Collection[int], x: int, y: int, start_index: int
) -> bool:
    """An unexplored tile orthogonally adjacent to an explored passable tile (or the start)."""
    for dx, dy in NEIGHBOR_STEPS:
        nx, ny = x + dx, y + dy
        if not smap.in_bounds(nx, ny):
            continue
        idx = smap.index(nx, ny)
        if (idx in explored or idx == start_index) and smap.step_cost(nx, ny) is not None:
            return True
    return False


def find_path(
    smap: StaticMap, explored: Collection[int], start: Coord, target: Coord
) -> PathResult:
    """Shortest route from ``start`` to ``target`` through explored passable tiles.

    One adjacent unexplored frontier ``target`` may be the final tile; the search costs it as
    grass (``step_cost_grass``) without consulting its terrain. If the target is impassable
    the result is ``PATH_BLOCKED``; if no route exists, ``NO_PATH``. A target that is neither
    explored nor an adjacent frontier is outside the search space and yields ``NO_PATH``.
    """
    if not (smap.in_bounds(start.x, start.y) and smap.in_bounds(target.x, target.y)):
        raise ValueError("start and target must lie inside the map")
    start_index = smap.index(start.x, start.y)
    target_index = smap.index(target.x, target.y)
    target_explored = target_index in explored
    target_cost = smap.step_cost(target.x, target.y)

    if target_explored and target_cost is None:
        return PathResult("PATH_BLOCKED", (), 0)
    if start_index == target_index:
        return PathResult("ok", (), 0)
    frontier_target = not target_explored and _is_frontier(
        smap, explored, target.x, target.y, start_index
    )
    if not target_explored and not frontier_target:
        return PathResult("NO_PATH", (), 0)

    def entry_cost(x: int, y: int, idx: int) -> int | None:
        """Search cost of entering a tile, or ``None`` when outside the search space."""
        if idx == target_index and frontier_target:
            return smap.grass_cost  # tentative: terrain stays hidden
        if idx in explored:
            return smap.step_cost(x, y)
        return None

    dist: dict[int, int] = {start_index: 0}
    pred: dict[int, int] = {}
    finalized: set[int] = set()
    heap: list[tuple[int, int, int]] = [(0, start.y, start.x)]
    while heap:
        cost, y, x = heapq.heappop(heap)
        idx = smap.index(x, y)
        if idx in finalized:
            continue
        finalized.add(idx)
        if idx == target_index:
            break
        for dx, dy in NEIGHBOR_STEPS:
            nx, ny = x + dx, y + dy
            if not smap.in_bounds(nx, ny):
                continue
            nidx = smap.index(nx, ny)
            if nidx in finalized:
                continue
            step = entry_cost(nx, ny, nidx)
            if step is None:
                continue
            new_cost = cost + step
            if nidx not in dist or new_cost < dist[nidx]:  # strictly lower only
                dist[nidx] = new_cost
                pred[nidx] = idx
                heapq.heappush(heap, (new_cost, ny, nx))

    if target_index not in finalized:
        return PathResult("NO_PATH", (), 0)

    route_indices: list[int] = []
    cur = target_index
    while cur != start_index:
        route_indices.append(cur)
        cur = pred[cur]
    route_indices.reverse()

    if frontier_target and target_cost is None:
        # Authoritative check on reaching the frontier tile: impassable, so never entered.
        # dist[target] = dist[last approach tile] + grass_cost.
        approach = route_indices[:-1]
        return PathResult(
            "PATH_BLOCKED",
            tuple(smap.coord(i) for i in approach),
            dist[target_index] - smap.grass_cost,
        )
    return PathResult(
        "ok",
        tuple(smap.coord(i) for i in route_indices),
        dist[target_index],
    )
