"""Record direct action effects independently of unrelated per-tick rule changes."""

from living_island.world.protocol import (
    ActionIntent,
    DeltaValue,
    EntityTarget,
    ResidentTarget,
    StateDelta,
    TileTarget,
)
from living_island.world.state import ResidentPhysicalState, WorldState


def effect_values(
    state: WorldState,
    actor: ResidentPhysicalState,
    intent: ActionIntent,
) -> dict[str, DeltaValue]:
    """Values potentially changed by a successful settlement, read before and after it."""
    kind = intent.action_type
    target = intent.target
    prefix = f"residents/{actor.id}"
    values: dict[str, DeltaValue] = {
        f"{prefix}/fruit_count": actor.fruit_count,
        f"{prefix}/satiety": actor.satiety,
        f"{prefix}/hydration": actor.hydration,
    }
    if kind == "gather":
        assert isinstance(target, EntityTarget)
        tree = next(tree for tree in state.fruit_nodes if tree.id == target.id)
        values[f"fruit_nodes/{tree.id}/stock"] = tree.stock
    if kind == "eat":
        values["lifetime_fruit_consumed"] = state.lifetime_fruit_consumed
    if kind == "give":
        assert isinstance(target, ResidentTarget)
        recipient = next(resident for resident in state.residents if resident.id == target.id)
        values[f"residents/{recipient.id}/fruit_count"] = recipient.fruit_count
    if kind == "pick_up":
        assert isinstance(target, TileTarget)
        position = target.position
        values[f"ground_fruit/{position.x},{position.y}/quantity"] = next(
            (pile.quantity for pile in state.ground_fruit if pile.position == position),
            0,
        )
    if kind in ("drink", "fill_canteen", "give", "pick_up"):
        canteen = state.unique_canteen
        values.update(
            {
                "unique_canteen/holder_id": canteen.holder_id,
                "unique_canteen/ground_position": canteen.ground_position,
                "unique_canteen/servings": canteen.servings,
            }
        )
    if kind == "talk":
        assert isinstance(target, ResidentTarget)
        pair = sorted([actor.id, target.id])
        session = next((s for s in state.dialogue_sessions if s.pair_ids == pair), None)
        path = "dialogue_sessions/" + ",".join(pair)
        values.update(
            {
                f"{path}/turn_count": session.turn_count if session else None,
                f"{path}/last_utterance_tick": session.last_utterance_tick if session else None,
                f"{path}/cooldown_until_tick": session.cooldown_until_tick if session else None,
            }
        )
    return values


def changes(before: dict[str, DeltaValue], after: dict[str, DeltaValue]) -> list[StateDelta]:
    return [
        StateDelta(path=path, before=value, after=after[path])
        for path, value in sorted(before.items())
        if value != after[path]
    ]
