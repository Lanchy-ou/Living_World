"""The unique canteen: one location, servings within capacity, fill, spend and transfers.

World Rules §2 and §3. Pure functions over ``UniqueCanteenState``; each returns a new value
(see ``rulefacts``). Whether an action may start (ownership, adjacency, recipient room) is
P1-04's check; these functions only protect the canteen's own invariants and raise
``ValueError`` when asked to break them.
"""

from __future__ import annotations

from dataclasses import dataclass

from living_island.world.content import EffectiveConfig
from living_island.world.facts import CanteenFilledPayload
from living_island.world.protocol import Coord
from living_island.world.rulefacts import PendingFact
from living_island.world.state import UniqueCanteenState, WorldState


def check_canteen(config: EffectiveConfig, state: WorldState) -> None:
    """Raise unless the canteen is in exactly one place with consistent ownership.

    One place: a living holder's inventory, or one ground tile (the model also enforces
    exactly-one). Servings are within ``0..canteen.capacity_servings``. The ID is the
    configured unique item ID. A holder must be a living resident whose inventory has room for
    the canteen's slot.
    """
    canteen = state.unique_canteen
    if canteen.id != config.canteen.unique_item_id:
        raise ValueError("the canteen ID must be the configured unique item ID")
    if not 0 <= canteen.servings <= config.canteen.capacity_servings:
        raise ValueError("canteen servings must be within 0..capacity_servings")
    if (canteen.holder_id is None) == (canteen.ground_position is None):
        raise ValueError("the canteen must be in exactly one place")
    if canteen.holder_id is not None:
        holder = next((r for r in state.residents if r.id == canteen.holder_id), None)
        if holder is None or not holder.alive:
            raise ValueError("the canteen holder must be a living resident")
        if holder.fruit_count + 1 > config.inventory.slot_capacity:
            raise ValueError("the holder's inventory cannot exceed slot_capacity")


@dataclass(frozen=True)
class CanteenFill:
    canteen: UniqueCanteenState
    fact: PendingFact  # ``canteen_filled``


def fill_canteen(config: EffectiveConfig, canteen: UniqueCanteenState) -> CanteenFill:
    """Fill a held canteen to ``capacity_servings`` (refilling a full one is a caller error)."""
    if canteen.holder_id is None:
        raise ValueError("only a held canteen can be filled")
    capacity = config.canteen.capacity_servings
    if canteen.servings >= capacity:
        raise ValueError("the canteen is already full")
    new = canteen.model_copy(deep=True)
    new.servings = capacity
    fact = PendingFact(
        type="canteen_filled",
        actor_id=canteen.holder_id,
        target_id=canteen.id,
        payload=CanteenFilledPayload(
            canteen_id=canteen.id, servings_before=canteen.servings, servings_after=capacity
        ),
    )
    return CanteenFill(new, fact)


def spend_serving(canteen: UniqueCanteenState) -> UniqueCanteenState:
    """One serving drunk from a held canteen."""
    if canteen.holder_id is None:
        raise ValueError("only a held canteen can be drunk from")
    if canteen.servings < 1:
        raise ValueError("the canteen is empty")
    new = canteen.model_copy(deep=True)
    new.servings = canteen.servings - 1
    return new


def give_canteen(canteen: UniqueCanteenState, from_id: str, to_id: str) -> UniqueCanteenState:
    """Move the held canteen to another resident, servings unchanged."""
    if canteen.holder_id != from_id:
        raise ValueError(f"{from_id} does not hold the canteen")
    if from_id == to_id:
        raise ValueError("cannot give the canteen to oneself")
    return UniqueCanteenState(
        id=canteen.id, holder_id=to_id, ground_position=None, servings=canteen.servings
    )


def drop_canteen(canteen: UniqueCanteenState, position: Coord) -> UniqueCanteenState:
    """Move the held canteen to a ground tile, servings unchanged."""
    if canteen.holder_id is None:
        raise ValueError("the canteen is already on the ground")
    return UniqueCanteenState(
        id=canteen.id,
        holder_id=None,
        ground_position=Coord(x=position.x, y=position.y),
        servings=canteen.servings,
    )


def pick_up_canteen(canteen: UniqueCanteenState, resident_id: str) -> UniqueCanteenState:
    """Move the ground canteen into a resident's inventory, servings unchanged."""
    if canteen.ground_position is None:
        raise ValueError("the canteen is not on the ground")
    return UniqueCanteenState(
        id=canteen.id, holder_id=resident_id, ground_position=None, servings=canteen.servings
    )
