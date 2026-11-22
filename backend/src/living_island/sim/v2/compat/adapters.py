"""Translate frozen v1 policy intents and the resident-visible v2 packet."""

from collections import defaultdict
from typing import cast

from pydantic import JsonValue

from living_island.world import protocol as v1
from living_island.world.v2 import protocol as v2


def adapt_intent(intent: v1.ActionIntent, sleep_ticks: int) -> v2.ModelTurn:
    action: v2.Action
    verb: str | None = None
    target: v2.Target | None = None
    params: dict[str, JsonValue] = {}
    inputs: list[v2.ActionInput] = []
    instruments: list[v2.ItemChoice] = []
    speech: v2.Utterance | None = None
    match intent.action_type:
        case "move_to" | "pick_up":
            action = intent.action_type
            tile = cast(v1.TileTarget, intent.target).position
            target = v2.TileTarget(kind="tile", position=v2.Coord(x=tile.x, y=tile.y))
            if action == "pick_up":
                transfer = cast(v1.ItemTransferParameters, intent.parameters)
                params = {"archetype_id": transfer.item_type, "quantity": transfer.quantity}
        case "give":
            action = "give"
            recipient = cast(v1.ResidentTarget, intent.target).id
            target = v2.ResidentTarget(kind="resident", id=recipient)
            transfer = cast(v1.ItemTransferParameters, intent.parameters)
            params = {
                "item": {"kind": "held", "archetype_id": transfer.item_type},
                "quantity": transfer.quantity,
            }
        case "talk":
            action = "wait"
            speech = _utterance(intent)
        case "wait":
            action = "wait"
        case _:
            action = "act"
            verb = intent.action_type
            match intent.action_type:
                case "gather" | "fill_canteen":
                    verb = "gather" if intent.action_type == "gather" else "fill"
                    target = v2.EntityTarget(
                        kind="entity", id=cast(v1.EntityTarget, intent.target).id
                    )
                case "eat":
                    inputs = [
                        v2.ActionInput(
                            item=v2.HeldItem(kind="held", archetype_id="fruit"), quantity=1
                        )
                    ]
                case "drink":
                    if cast(v1.DrinkParameters, intent.parameters).source == "canteen":
                        instruments = [v2.HeldItem(kind="held", archetype_id="canteen")]
                case "sleep":
                    params = {"duration_ticks": sleep_ticks}
    shape = v2.IntentShape(
        action=action,
        verb=verb,
        target=target,
        params=params,
        inputs=inputs,
        instruments=instruments,
        reason=intent.reason,
    )
    return v2.ModelTurn(action=v2.ModelIntentAction(kind="intent", intent=shape), utterance=speech)


def _utterance(intent: v1.ActionIntent) -> v2.Utterance:
    params = cast(v1.TalkParameters, intent.parameters)
    recipient = cast(v1.ResidentTarget, intent.target).id
    terms = None
    act: v2.SpeechAct
    if params.speech_act == "request":
        act = "propose"
        request = cast(v1.ItemRequest, params.request)
        terms = v2.Terms(
            promisor_id=recipient,
            promisee_id=intent.actor_id,
            due_tick=None,
            what=v2.GiveItemTerm(
                kind="give_item",
                item=v2.KindItemSpec(archetype_id=request.item_type, quantity=request.quantity),
            ),
        )
    else:
        act = params.speech_act
    return v2.Utterance(
        addressee_id=recipient,
        speech_act=act,
        text=params.text,
        terms=terms,
        in_reply_to=params.in_reply_to,
    )


def legacy_speech(
    speaker: str,
    speech: v2.Utterance,
) -> tuple[v1.SpeechAct, str | None, int | None]:
    terms = speech.terms
    if speech.speech_act != "propose":
        return speech.speech_act, None, None
    if (
        terms is not None
        and terms.due_tick is None
        and terms.promisor_id == speech.addressee_id
        and terms.promisee_id == speaker
        and terms.what.kind == "give_item"
        and isinstance(terms.what.item, v2.KindItemSpec)
        and terms.what.item.archetype_id in ("fruit", "canteen")
    ):
        return "request", terms.what.item.archetype_id, terms.what.item.quantity
    # A native agreement outside the v1 request shape can still be heard.
    return "statement", None, None


def _heard(utterance: v2.HeardUtterance) -> v1.HeardUtterance:
    act, item, quantity = legacy_speech(utterance.speaker_id, utterance)
    return v1.HeardUtterance(
        speaker_id=utterance.speaker_id,
        utterance_id=utterance.utterance_id,
        addressee_id=utterance.addressee_id or "",
        speech_act=act,
        text=utterance.text,
        request_item_type=item,
        request_quantity=quantity,
        in_reply_to=utterance.in_reply_to,
        heard_at_tick=utterance.heard_at_tick,
    )


def _coord(position: v2.Coord) -> v1.Coord:
    return v1.Coord(x=position.x, y=position.y)


def _tiles(tiles: list[v2.TileView]) -> list[v1.TileView]:
    return [v1.TileView(position=_coord(tile.position), terrain=tile.terrain) for tile in tiles]


def _entity(view: v2.EntityView) -> v1.VisibleEntity | None:
    entity_type: v1.EntityType
    band: v1.FruitBand | None = None
    if view.kind in ("resident", "corpse"):
        entity_type = view.kind
    elif view.archetype_id == "fruit_tree":
        entity_type = "fruit_tree"
        band = cast(
            v1.FruitBand, next(d.value for d in view.descriptors if d.property_id == "fruit_amount")
        )
    elif view.archetype_id == "canteen":
        entity_type = "canteen"
    else:
        return None
    return v1.VisibleEntity(
        entity_id=view.entity_id,
        entity_type=entity_type,
        position=_coord(view.position),
        observable_signs=list(view.observable_signs),
        fruit_band=band,
        quantity=None,
    )


def _ground(
    views: list[v2.EntityView] | list[v2.TransientSighting],
) -> dict[str, v1.VisibleEntity]:
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for item in views:
        if item.archetype_id == "fruit":
            counts[item.position.x, item.position.y] += cast(int, item.quantity)
    return {
        f"ground_fruit@{x},{y}": v1.VisibleEntity(
            entity_id=f"ground_fruit@{x},{y}",
            entity_type="ground_fruit",
            position=v1.Coord(x=x, y=y),
            observable_signs=[],
            fruit_band=None,
            quantity=count,
        )
        for (x, y), count in counts.items()
    }


def project_perception(view: v2.Perception) -> v1.Perception:
    """Build the physical part of the private legacy policy input."""
    cue_ids = {cue.cue_id for cue in view.environmental_cues}
    tiles = _tiles(view.visible_tiles)
    tile_positions = {(tile.position.x, tile.position.y) for tile in tiles}
    visible = _ground(view.visible_entities)
    for sight in view.visible_entities:
        if (entity := _entity(sight)) is not None:
            visible[entity.entity_id] = entity
    transient = _ground(view.transient_sightings)
    steps: dict[str, int] = {}
    cue_steps: dict[str, int] = {}
    for sight in view.transient_sightings:
        if sight.archetype_id == "fruit":
            key = f"ground_fruit@{sight.position.x},{sight.position.y}"
            steps[key] = max(steps.get(key, 0), sight.seen_at_step)
        elif (entity := _entity(sight)) is not None:
            transient[entity.entity_id] = entity
            steps[entity.entity_id] = sight.seen_at_step
        elif sight.kind == "feature" and sight.archetype_id is None and sight.entity_id in cue_ids:
            cue_steps[sight.entity_id] = sight.seen_at_step

    # v1 has one sighting ID space. Keep real entities there and cues in the cue view.
    for cue in view.environmental_cues:
        if cue.cue_id in visible or cue.cue_id in transient:
            continue
        entry = v1.VisibleEntity(
            entity_id=cue.cue_id,
            entity_type="cue",
            position=_coord(cue.position),
            observable_signs=[],
            fruit_band=None,
            quantity=None,
        )
        if (cue.position.x, cue.position.y) in tile_positions:
            visible[cue.cue_id] = entry
        elif (step := cue_steps.get(cue.cue_id)) is not None:
            transient[cue.cue_id] = entry
            steps[cue.cue_id] = step

    needs = {item.need_id: item.band for item in view.needs}
    canteen = next((item for item in view.inventory if item.archetype_id == "canteen"), None)
    servings = {"empty": 0, "one serving": 1, "two servings": 2}
    return v1.Perception(
        schema_version="0.1",
        actor_id=view.actor_id,
        tick=view.tick,
        own_position=_coord(view.own_position),
        own_condition=v1.OwnCondition(
            satiety=needs["satiety"],
            hydration=needs["hydration"],
            stamina=needs["stamina"],
            health=needs["health"],
        ),
        own_inventory=v1.OwnInventory(
            fruit_count=sum(
                item.quantity for item in view.inventory if item.archetype_id == "fruit"
            ),
            canteen_id=canteen.entity_id if canteen is not None else None,
            canteen_servings=(
                servings[
                    next(d.value for d in canteen.descriptors if d.property_id == "water_amount")
                ]
                if canteen is not None
                else None
            ),
        ),
        visible_tiles=tiles,
        visible_entities=[visible[key] for key in sorted(visible)],
        transient_sightings=[
            v1.TransientSighting(**transient[key].model_dump(), seen_at_step=steps[key])
            for key in sorted(transient.keys() - visible.keys())
        ],
        explored_static_tiles=_tiles(view.explored_static_tiles),
        environmental_cues=[
            v1.EnvironmentalCue(
                cue_id=cue.cue_id,
                position=_coord(cue.position),
                detail_level=cue.detail_level,
                physical_description=cue.physical_description,
                direction=cue.direction,
            )
            for cue in view.environmental_cues
        ],
        heard_utterances=[_heard(heard) for heard in view.heard_utterances],
        last_action_feedback=None,
    )
