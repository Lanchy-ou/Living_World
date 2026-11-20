"""Entity capacity checks shared by initialization and branch preflight."""

from collections import Counter
from collections.abc import Iterable

from ..protocol import Coord
from .state import Limits, OnTile, WorldState


def entity_units(state: WorldState) -> int:
    return sum(entity.quantity for entity in state.entities.values())


def tile_loads(state: WorldState) -> Counter[Coord]:
    return Counter(
        entity.place.position
        for entity in state.entities.values()
        if isinstance(entity.place, OnTile)
    )


def within_placement_limits(
    state: WorldState, limits: Limits, receiving_tiles: Iterable[Coord]
) -> bool:
    """Check a final scratch ledger after merges, with one corpse slot per living resident."""
    if entity_units(state) + sum(resident.alive for resident in state.residents.values()) > (
        limits.max_entity_units_world
    ):
        return False
    loads = tile_loads(state)
    return all(loads[tile] <= limits.max_entities_per_tile for tile in receiving_tiles)


def validate_initial_limits(state: WorldState, limits: Limits) -> None:
    if not within_placement_limits(state, limits, tile_loads(state)):
        raise ValueError("initial placements exceed entity limits")
