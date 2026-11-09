"""Movement over explored static tiles and one optional frontier tile."""

from collections.abc import Callable

from living_island.world.facts import ResidentMovedPayload
from living_island.world.pathfinding import NEIGHBOR_STEPS, PathResult, find_path
from living_island.world.ports import ObservationAccumulator, observe_step
from living_island.world.protocol import Coord, FailureCode
from living_island.world.space import StaticMap
from living_island.world.state import ActiveAction, ResidentPhysicalState, WorldState


def plan_movement(
    smap: StaticMap, explored: list[int], start: Coord, target: Coord
) -> PathResult | FailureCode:
    if not smap.in_bounds(target.x, target.y):
        return "INVALID_TARGET"
    known = set(explored)
    if smap.index(target.x, target.y) not in known:
        neighbors = [(target.x + dx, target.y + dy) for dx, dy in NEIGHBOR_STEPS]
        if not any(
            smap.in_bounds(x, y) and smap.index(x, y) in known and smap.step_cost(x, y) is not None
            for x, y in neighbors
        ):
            return "INVALID_TARGET"
    return find_path(smap, known, start, target)


def move(
    smap: StaticMap,
    state: WorldState,
    resident: ResidentPhysicalState,
    action: ActiveAction,
    observations: ObservationAccumulator,
    budget: int,
    emit: Callable[[ResidentMovedPayload], None],
) -> tuple[int, FailureCode | None]:
    route = action.route
    cursor = action.route_cursor
    assert route is not None and cursor is not None
    steps = 0
    for target in route[cursor:]:
        start = resident.position
        if abs(target.x - start.x) + abs(target.y - start.y) != 1:
            return steps, "PATH_BLOCKED"
        cost = smap.step_cost(target.x, target.y) if smap.in_bounds(target.x, target.y) else None
        if cost is None:
            return steps, "PATH_BLOCKED"
        if cost > budget:
            break
        resident.position = target
        budget -= cost
        cursor += 1
        action.route_cursor = cursor
        steps += 1
        emit(
            ResidentMovedPayload.model_validate(
                {"from": start, "to": target, "step_cost_units": cost}
            )
        )
        observe_step(observations, state, resident.id, target, steps)
    return steps, None
