"""Project a committed world boundary to the public replay frame."""

from living_island.contract.replay import (
    ActiveActionDisplay,
    CorpseFrame,
    DisplayFrame,
    EventRange,
    FruitTreeFrame,
    GroundCanteenFrame,
    GroundFruitFrame,
    ResidentFrame,
)
from living_island.world.state import WorldState


def project_frame(snapshot: WorldState, event_count: int) -> DisplayFrame:
    """Use the snapshot's canonical entity order and the just-committed event count."""
    actions = {
        action.intent.actor_id: ActiveActionDisplay(
            intent_id=action.intent.intent_id,
            action_type=action.intent.action_type,
            tick_started=action.tick_started,
            remaining_ticks=action.remaining_ticks,
        )
        for action in snapshot.active_actions
    }
    canteen = snapshot.unique_canteen
    return DisplayFrame(
        tick=snapshot.tick,
        residents=[
            ResidentFrame(
                id=resident.id,
                position=resident.position,
                alive=resident.alive,
                satiety=resident.satiety,
                hydration=resident.hydration,
                stamina=resident.stamina,
                health=resident.health,
                fruit_count=resident.fruit_count,
                canteen_servings=canteen.servings if resident.id == canteen.holder_id else None,
                active_action=actions.get(resident.id),
            )
            for resident in snapshot.residents
        ],
        fruit_trees=[
            FruitTreeFrame(id=tree.id, position=tree.position, stock=tree.stock)
            for tree in snapshot.fruit_nodes
        ],
        ground_fruit=[
            GroundFruitFrame(position=pile.position, quantity=pile.quantity)
            for pile in snapshot.ground_fruit
        ],
        ground_canteen=(
            GroundCanteenFrame(position=canteen.ground_position, servings=canteen.servings)
            if canteen.ground_position is not None
            else None
        ),
        corpses=[
            CorpseFrame(id=corpse.id, resident_id=corpse.resident_id, position=corpse.position)
            for corpse in snapshot.corpses
        ],
        event_range=EventRange(
            first_index=snapshot.event_log_cursor - event_count, count=event_count
        ),
    )
