"""Physical sight, exposure receipts and completed-boundary delivery packets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..protocol import (
    ActionFeedback,
    BoundaryDelivery,
    Coord,
    DescriptorValue,
    EntityView,
    EnvironmentalCue,
    ItemView,
    NeedView,
    Perception,
    RunningAction,
    TileView,
    TransientSighting,
    VisibleSign,
    WorldReport,
    boundary_delivery_id,
)
from . import observe, physiology, reports, settle
from .items import entities_at, inspect_view, progress_descriptor
from .kernel import distance
from .state import (
    Contribute,
    DeferredFeedback,
    Exposure,
    Held,
    OnTile,
    Resident,
    StaticMap,
    WorldState,
)

if TYPE_CHECKING:
    from .tick import TickContext


@dataclass
class Sight:
    tiles: set[int]
    entities: list[EntityView]
    item_tiles: set[tuple[str, Coord]]
    cues: dict[str, EnvironmentalCue]


def has_line_of_sight(smap: StaticMap, position: Coord, target_x: int, target_y: int) -> bool:
    """Use the frozen integer Bresenham rule, testing intervening tiles only."""
    x, y = position.x, position.y
    dx, dy = abs(target_x - x), -abs(target_y - y)
    step_x = (target_x > x) - (target_x < x)
    step_y = (target_y > y) - (target_y < y)
    error = dx + dy
    while (x, y) != (target_x, target_y):
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x += step_x
        if doubled <= dx:
            error += dx
            y += step_y
        if (x, y) != (target_x, target_y) and smap.rows[y][x] in smap.opaque_terrains:
            return False
    return True


def visible_tiles(state: WorldState, position: Coord, tick: int) -> set[int]:
    smap, clock = state.static_map, state.clock
    minute = clock.minute_at(tick)
    radius = (
        state.senses.day_radius
        if clock.day_start_minute <= minute < clock.day_end_minute
        else state.senses.night_radius
    )
    visible = set()
    for y in range(max(0, position.y - radius), min(len(smap.rows), position.y + radius + 1)):
        span = radius - abs(y - position.y)
        for x in range(max(0, position.x - span), min(smap.width, position.x + span + 1)):
            if has_line_of_sight(smap, position, x, y):
                visible.add(y * smap.width + x)
    return visible


def signs(state: WorldState, actor_id: str) -> list[VisibleSign]:
    needs, senses = state.needs[actor_id], state.senses
    thresholds: tuple[tuple[str, int, VisibleSign], ...] = (
        ("health", senses.visible_weakness_below, "weak"),
        ("hydration", senses.visible_dehydration_below, "dehydrated"),
        ("stamina", senses.visible_fatigue_below, "fatigued"),
    )
    return [sign for key, cutoff, sign in thresholds if key in needs and needs[key] < cutoff]


def sample_sight(ctx: TickContext, actor: str, position: Coord) -> Sight:
    state, pack = ctx.state, ctx.pack
    smap = state.static_map
    tiles = visible_tiles(state, position, ctx.tick)
    sight = Sight(tiles, [], set(), {})
    for resident in state.residents.values():
        if resident.id != actor and resident.alive and smap.index(resident.position) in tiles:
            sight.entities.append(
                EntityView(
                    entity_id=resident.id,
                    kind="resident",
                    position=resident.position,
                    archetype_id=None,
                    material_id=None,
                    descriptors=[],
                    quantity=None,
                    observable_signs=signs(state, resident.id),
                )
            )
    for entity in state.entities.values():
        place = observe.sight_place(state, entity.place)
        # A resident's own held items are delivered in inventory.
        if not isinstance(place, OnTile) or smap.index(place.position) not in tiles:
            continue
        look = inspect_view(state, pack, entity, inspect=False)
        kind = (
            "corpse" if entity.archetype_id is None else pack.archetypes[entity.archetype_id].kind
        )
        sight.entities.append(
            EntityView(
                entity_id=look.entity_id,
                kind=kind,
                position=place.position,
                archetype_id=look.archetype_id,
                material_id=look.material_id,
                descriptors=look.descriptors,
                quantity=entity.quantity if kind == "item" else None,
                observable_signs=[],
            )
        )
        if (
            isinstance(entity.place, OnTile)
            and "portable" in entity.components
            and entity.archetype_id is not None
        ):
            sight.item_tiles.add((entity.archetype_id, place.position))
    for cue in state.cues:
        if smap.index(cue.position) in tiles:
            near = distance(position, cue.position) <= state.senses.cue_detail_radius
            sight.cues[cue.id] = EnvironmentalCue(
                cue_id=cue.id,
                position=cue.position,
                detail_level="near" if near else "distant",
                physical_description=cue.near_description if near else cue.visible_description,
                direction=cue.direction if near else None,
            )
    return sight


def retain_cues(current: dict[str, EnvironmentalCue], new: dict[str, EnvironmentalCue]) -> None:
    for key, cue in new.items():
        if key not in current or cue.detail_level == "near":
            current[key] = cue


def observe_step(ctx: TickContext, actor_id: str, position: Coord, step: int) -> None:
    sight = sample_sight(ctx, actor_id, position)
    ctx.step_tiles.setdefault(actor_id, set()).update(sight.tiles)
    ctx.step_item_tiles.setdefault(actor_id, set()).update(sight.item_tiles)
    retain_cues(ctx.step_cues.setdefault(actor_id, {}), sight.cues)
    transient = ctx.transient_sightings.setdefault(actor_id, {})
    for view in sight.entities:
        transient[view.entity_id] = TransientSighting(
            entity_id=view.entity_id,
            kind=view.kind,
            position=view.position,
            archetype_id=view.archetype_id,
            material_id=view.material_id,
            quantity=view.quantity,
            observable_signs=view.observable_signs,
            descriptors=view.descriptors,
            seen_at_step=step,
        )
    cue_sightings = ctx.step_cue_sightings.setdefault(actor_id, {})
    for cue in sight.cues.values():
        cue_sightings[cue.cue_id] = TransientSighting(
            entity_id=cue.cue_id,
            kind="feature",
            position=cue.position,
            archetype_id=None,
            material_id=None,
            quantity=None,
            observable_signs=[],
            descriptors=[],
            seen_at_step=step,
        )


def inventory_view(ctx: TickContext, actor_id: str) -> list[ItemView]:
    state = ctx.state
    return [
        ItemView.model_validate(
            {
                "entity_id": entity.entity_id,
                "archetype_id": entity.archetype_id,
                "material_id": entity.material_id,
                "quantity": entity.quantity,
                "descriptors": inspect_view(state, ctx.pack, entity, inspect=False).descriptors,
            }
        )
        for entity in entities_at(state, Held(actor_id))
    ]


def expose(
    state: WorldState,
    actor: Resident,
    inventory: list[ItemView],
    sight: Sight,
    transient: list[TransientSighting],
) -> set[str]:
    receipts = state.exposure_receipts_by_resident[actor.id]
    first_seen = set()
    exposures = [
        Exposure(view.entity_id, view.position, view.archetype_id)
        for view in (*transient, *sight.entities)
    ]
    exposures.extend(
        Exposure(item.entity_id, actor.position, item.archetype_id) for item in inventory
    )
    for exposure in exposures:
        if exposure.entity_id not in receipts.entities:
            first_seen.add(exposure.entity_id)
        receipts.entities[exposure.entity_id] = exposure
    receipts.item_tiles.update(sight.item_tiles)
    for key, cue in sight.cues.items():
        prior = receipts.cue_detail_seen.get(key)
        if prior is None or (prior == "distant" and cue.detail_level == "near"):
            first_seen.add(key)
            receipts.cue_detail_seen[key] = cue.detail_level
    return first_seen


def tile_views(state: WorldState, indices: set[int]) -> list[TileView]:
    smap = state.static_map
    return [
        TileView(position=Coord(x=x, y=y), terrain=smap.rows[y][x])
        for index in sorted(indices)
        for y, x in (divmod(index, smap.width),)
    ]


def running_action(state: WorldState, actor: str) -> RunningAction | None:
    action = state.active_actions.get(actor)
    if action is None:
        return None
    intent = action.intent
    progress: DescriptorValue | None = settle.progress_word(action)
    if isinstance(action.command, Contribute) and action.pending_failure is None:
        process = state.entities[action.command.process_id].components["process"]
        progress = progress_descriptor(process["work_done"], process["work_required"])
    return RunningAction(
        intent_id=intent.intent_id,
        action=intent.action,
        verb=intent.verb,
        tick_started=action.tick_started,
        progress=progress,
        start_target=action.start_target,
        items=list(action.start_items),
    )


def build_perception(
    ctx: TickContext, actor: Resident, feedback: list[ActionFeedback]
) -> tuple[Perception, set[str]]:
    state, actor_id = ctx.state, actor.id
    awareness = state.awareness[actor_id].kind
    inventory = inventory_view(ctx, actor_id)
    explored = state.explored_tiles_by_resident[actor_id]
    sight = Sight(set(), [], set(), {})
    transient = []
    transient_cues = []
    visible: set[str] = set()
    if physiology.sight_enabled(ctx.pack, awareness):
        sight = sample_sight(ctx, actor_id, actor.position)
        visible = {view.entity_id for view in sight.entities}
        transient_cues = [
            view
            for key, view in ctx.step_cue_sightings.get(actor_id, {}).items()
            if key not in sight.cues
        ]
        step_cues = ctx.step_cues.get(actor_id, {})
        retain_cues(step_cues, sight.cues)
        sight.cues = step_cues
        transient = [
            view
            for key, view in ctx.transient_sightings.get(actor_id, {}).items()
            if key not in visible
        ]
        explored.update(sight.tiles)
        explored.update(ctx.step_tiles.get(actor_id, ()))
        sight.item_tiles.update(ctx.step_item_tiles.get(actor_id, ()))
    state.visible_entities_by_resident[actor_id] = visible
    state.visible_tiles_by_resident[actor_id] = sight.tiles
    first_seen = expose(state, actor, inventory, sight, transient)
    awake = awareness == "awake"
    return Perception(
        schema_version=state.schema_version,
        actor_id=actor_id,
        tick=ctx.tick,
        awareness=awareness,
        needs=[
            NeedView(need_id=key, band=physiology.need_band(ctx.pack, key, value))
            for key, value in state.needs[actor_id].items()
        ],
        own_position=actor.position,
        inventory=inventory,
        running_action=running_action(state, actor_id),
        visible_tiles=tile_views(state, sight.tiles),
        explored_static_tiles=tile_views(state, explored),
        visible_entities=sight.entities,
        transient_sightings=[*transient, *transient_cues],
        environmental_cues=list(sight.cues.values()),
        heard_utterances=ctx.heard.get(actor_id, []) if awake else [],
        observed_actions=observe.observations(
            ctx, actor_id, sight.tiles, visible, {item.entity_id for item in inventory}
        )
        if awake
        else [],
        action_feedback=feedback,
        last_utterance_feedback=ctx.utterances.get(actor_id),
    ), first_seen


def build_deliveries(ctx: TickContext) -> None:
    """Commit receipts and queue one packet per living resident."""
    state = ctx.state
    feedback_by_actor: dict[str, list[ActionFeedback]] = {}
    reports_by_actor: dict[str, list[WorldReport]] = {}
    for action in sorted(ctx.results, key=lambda result: (result.tick_finished, result.intent_id)):
        if action.stop is not None and action.stop.by == "actor":
            continue
        feedback_by_actor.setdefault(action.actor_id, []).append(action.visible_feedback)
        reports_by_actor.setdefault(action.actor_id, []).append(
            reports.report("action_ended", action.intent_id)
        )
    for actor_id, actor in sorted(state.residents.items()):
        deferred = state.deferred_feedback[actor_id]
        state.deferred_feedback[actor_id] = DeferredFeedback()
        if not actor.alive:
            state.visible_entities_by_resident[actor_id].clear()
            state.visible_tiles_by_resident[actor_id].clear()
            continue
        view, first_seen = build_perception(
            ctx, actor, deferred.feedback + feedback_by_actor.get(actor_id, [])
        )
        state.pending_deliveries[actor_id] = BoundaryDelivery(
            delivery_id=boundary_delivery_id(state.run_id, ctx.tick, actor_id),
            actor_id=actor_id,
            observed_tick=ctx.tick,
            perception=view,
            reports=reports.build_reports(
                ctx, view, first_seen, deferred.reports + reports_by_actor.get(actor_id, [])
            ),
        )
        for watched in view.observed_actions:
            ctx.writer.emit(
                "action_observed",
                {
                    "observer_id": actor_id,
                    "actor_id": watched.actor_id,
                    "observed_intent_id": watched.intent_id,
                    "phase": watched.phase,
                },
                actor_id=actor_id,
                target_id=watched.actor_id,
                intent_id=watched.intent_id,
            )
