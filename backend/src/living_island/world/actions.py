"""Preconditions and atomic effects for timed physical actions."""

from typing import assert_never

from living_island.world.canteen import fill_canteen, give_canteen, pick_up_canteen, spend_serving
from living_island.world.content import EffectiveConfig
from living_island.world.facts import (
    FruitConsumedPayload,
    FruitGatheredPayload,
    ItemGivenPayload,
    ItemPickedUpPayload,
    WaterDrankPayload,
)
from living_island.world.perception import ground_fruit_id
from living_island.world.physiology import hydration_after_drinking, satiety_after_eating
from living_island.world.protocol import (
    ActionIntent,
    Coord,
    DrinkParameters,
    EntityTarget,
    FailureCode,
    ItemTransferParameters,
    ResidentTarget,
    TileTarget,
)
from living_island.world.receipts import receipt_authorizes_entity, receipt_authorizes_pickup
from living_island.world.resources import record_consumption, remove_ground_fruit
from living_island.world.rulefacts import PendingFact
from living_island.world.state import ResidentPhysicalState, WorldState


def distance(a: Coord, b: Coord) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def _room(config: EffectiveConfig, state: WorldState, actor: ResidentPhysicalState) -> int:
    return (
        config.inventory.slot_capacity
        - actor.fruit_count
        - int(state.unique_canteen.holder_id == actor.id)
    )


def validate(
    config: EffectiveConfig, state: WorldState, actor: ResidentPhysicalState, intent: ActionIntent
) -> FailureCode | None:
    if not actor.alive:
        return "DEAD"
    kind = intent.action_type
    target = intent.target
    params = intent.parameters
    receipt = next(
        group for group in state.exposure_receipts_by_resident if group.resident_id == actor.id
    )
    if isinstance(target, EntityTarget | ResidentTarget):
        if not receipt_authorizes_entity(receipt, target.id):
            return "INVALID_TARGET"
    if kind == "pick_up":
        assert isinstance(target, TileTarget) and isinstance(params, ItemTransferParameters)
        if not receipt_authorizes_pickup(receipt, params.item_type, target.position):
            return "INVALID_TARGET"

    if kind == "gather":
        assert isinstance(target, EntityTarget)
        if actor.stamina <= config.needs.min_value:
            return "EXHAUSTED"
        tree = next((tree for tree in state.fruit_nodes if tree.id == target.id), None)
        if tree is None:
            return "INVALID_TARGET"
        if distance(actor.position, tree.position) != 1:
            return "OUT_OF_REACH"
        if _room(config, state, actor) < 1:
            return "INVENTORY_FULL"
        if tree.stock == 0:
            return "RESOURCE_TAKEN"
    elif kind == "eat":
        if actor.fruit_count == 0:
            return "NO_ITEM"
        if actor.satiety >= config.needs.max_value:
            return "NO_NEED"
    elif kind == "drink":
        assert isinstance(params, DrinkParameters)
        if actor.hydration >= config.needs.max_value:
            return "NO_NEED"
        if params.source == "spring":
            if distance(actor.position, state.spring) != 1:
                return "OUT_OF_REACH"
        else:
            if state.unique_canteen.holder_id != actor.id:
                return "NO_ITEM"
            if not state.unique_canteen.servings:
                return "NO_WATER"
    elif kind == "fill_canteen":
        assert isinstance(target, EntityTarget)
        if target.id != state.unique_canteen.id:
            return "INVALID_TARGET"
        if state.unique_canteen.holder_id != actor.id:
            return "NO_ITEM"
        if distance(actor.position, state.spring) != 1:
            return "OUT_OF_REACH"
        if state.unique_canteen.servings >= config.canteen.capacity_servings:
            return "ALREADY_FULL"
    elif kind == "give":
        assert isinstance(target, ResidentTarget) and isinstance(params, ItemTransferParameters)
        recipient = next((r for r in state.residents if r.id == target.id), None)
        if recipient is None or not recipient.alive or recipient.id == actor.id:
            return "INVALID_TARGET"
        if distance(actor.position, recipient.position) != 1:
            return "OUT_OF_REACH"
        owned = (
            actor.fruit_count
            if params.item_type == "fruit"
            else int(state.unique_canteen.holder_id == actor.id)
        )
        if owned < params.quantity:
            return "NO_ITEM"
        if _room(config, state, recipient) < params.quantity:
            return "INVENTORY_FULL"
    elif kind == "pick_up":
        assert isinstance(target, TileTarget) and isinstance(params, ItemTransferParameters)
        if distance(actor.position, target.position) > 1:
            return "OUT_OF_REACH"
        if params.item_type == "fruit":
            available = next(
                (pile.quantity for pile in state.ground_fruit if pile.position == target.position),
                0,
            )
        else:
            available = int(state.unique_canteen.ground_position == target.position)
        if available < params.quantity:
            return "ITEM_TAKEN"
        if _room(config, state, actor) < params.quantity:
            return "INVENTORY_FULL"
    else:
        match kind:
            case "move_to" | "rest" | "sleep" | "talk" | "wait":
                # The engine handles movement and dialogue checks. Rest, sleep and wait
                # require only the shared checks above.
                pass
            case _:
                assert_never(kind)
    return None


def settle(
    config: EffectiveConfig, state: WorldState, actor: ResidentPhysicalState, intent: ActionIntent
) -> PendingFact | None:
    """Apply the effect after rechecking preconditions in the same settlement operation."""
    kind = intent.action_type
    target = intent.target
    params = intent.parameters
    if kind == "gather":
        assert isinstance(target, EntityTarget)
        tree = next(tree for tree in state.fruit_nodes if tree.id == target.id)
        before = tree.stock
        tree.stock -= 1
        actor.fruit_count += 1
        return PendingFact(
            "fruit_gathered",
            actor.id,
            tree.id,
            FruitGatheredPayload(
                tree_id=tree.id,
                quantity=1,
                stock_before=before,
                stock_after=tree.stock,
            ),
        )
    if kind == "eat":
        before = actor.satiety
        actor.fruit_count -= 1
        actor.satiety = satiety_after_eating(config, before)
        state.lifetime_fruit_consumed = record_consumption(state.lifetime_fruit_consumed, 1)
        return PendingFact(
            "fruit_consumed",
            actor.id,
            None,
            FruitConsumedPayload(
                quantity=1,
                satiety_before=before,
                satiety_after=actor.satiety,
            ),
        )
    if kind == "drink":
        assert isinstance(params, DrinkParameters)
        before = actor.hydration
        actor.hydration = hydration_after_drinking(config, before)
        canteen = None
        if params.source == "canteen":
            canteen = state.unique_canteen = spend_serving(state.unique_canteen)
        return PendingFact(
            "water_drank",
            actor.id,
            canteen.id if canteen else None,
            WaterDrankPayload(
                source=params.source,
                servings=1,
                hydration_before=before,
                hydration_after=actor.hydration,
                canteen_servings_after=canteen.servings if canteen else None,
            ),
        )
    if kind == "fill_canteen":
        filled = fill_canteen(config, state.unique_canteen)
        state.unique_canteen = filled.canteen
        return filled.fact
    if kind == "give":
        assert isinstance(target, ResidentTarget) and isinstance(params, ItemTransferParameters)
        recipient = next(r for r in state.residents if r.id == target.id)
        canteen_id = None
        if params.item_type == "fruit":
            actor.fruit_count -= params.quantity
            recipient.fruit_count += params.quantity
        else:
            state.unique_canteen = give_canteen(state.unique_canteen, actor.id, recipient.id)
            canteen_id = state.unique_canteen.id
        return PendingFact(
            "item_given",
            actor.id,
            recipient.id,
            ItemGivenPayload(
                from_id=actor.id,
                to_id=recipient.id,
                item_type=params.item_type,
                quantity=params.quantity,
                canteen_id=canteen_id,
            ),
        )
    if kind == "pick_up":
        assert isinstance(target, TileTarget) and isinstance(params, ItemTransferParameters)
        canteen_id = None
        if params.item_type == "fruit":
            state.ground_fruit = remove_ground_fruit(
                state.ground_fruit, target.position, params.quantity
            )
            actor.fruit_count += params.quantity
        else:
            state.unique_canteen = pick_up_canteen(state.unique_canteen, actor.id)
            canteen_id = state.unique_canteen.id
        return PendingFact(
            "item_picked_up",
            actor.id,
            canteen_id or ground_fruit_id(target.position),
            ItemPickedUpPayload(
                resident_id=actor.id,
                position=target.position,
                item_type=params.item_type,
                quantity=params.quantity,
                canteen_id=canteen_id,
            ),
        )
    match kind:
        case "move_to" | "rest" | "sleep" | "talk" | "wait":
            # Movement and recovery apply during progress. The engine settles dialogue.
            # Wait has no direct effect.
            return None
        case _:
            assert_never(kind)
