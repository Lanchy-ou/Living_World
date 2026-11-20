"""Kernel start checks, movement and completion effects."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from heapq import heappop, heappush

from ..protocol import (
    Coord,
    EntityTarget,
    FailureCode,
    InspectView,
    ItemUse,
    StateDelta,
    SubjectStartTarget,
    TileStartTarget,
    TileTarget,
)
from .events import EventWriter, coord_payload, json_object
from .items import (
    accepts,
    entities_at,
    inspect_view,
    resolve_choices,
    slots_for,
    slots_used,
    still_held,
    take_parts,
    tile_of,
    transfer,
)
from .state import (
    Act,
    ActiveAction,
    Contribute,
    Drop,
    Entity,
    Give,
    Held,
    Inspect,
    Move,
    OnTile,
    Part,
    PhaseItem,
    PhaseLocation,
    PickupEntity,
    PickupTile,
    Resident,
    Route,
    StaticMap,
    Wait,
    WorldState,
)
from .validate import EnginePack

NEIGHBORS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def distance(first: Coord, second: Coord) -> int:
    return abs(first.x - second.x) + abs(first.y - second.y)


def neighbors(point: Coord) -> Iterable[Coord]:
    return (Coord.model_construct(x=point.x + dx, y=point.y + dy) for dx, dy in NEIGHBORS)


def path(
    smap: StaticMap,
    explored: set[int],
    start: Coord,
    target: Coord,
) -> Route | FailureCode:
    if not smap.contains(target):
        return "INVALID_TARGET"
    known = smap.index(target) in explored
    if known and smap.cost(target) is None:
        return "PATH_BLOCKED"
    if not known and not any(
        smap.contains(point) and smap.index(point) in explored and smap.cost(point) is not None
        for point in neighbors(target)
    ):
        return "INVALID_TARGET"

    costs = {start: 0}
    previous: dict[Coord, Coord] = {}
    heap = [(0, start.y, start.x)]
    while heap:
        total, y, x = heappop(heap)
        point = Coord.model_construct(x=x, y=y)
        if total != costs[point]:
            continue
        if point == target:
            steps = []
            while point != start:
                steps.append(point)
                point = previous[point]
            return Route(tuple(reversed(steps)))
        for step in neighbors(point):
            if not smap.contains(step):
                continue
            entry: int | None
            if not known and step == target:
                entry = smap.step_costs["grass"]
            elif smap.index(step) in explored:
                entry = smap.cost(step)
            else:
                continue
            if entry is None:
                continue
            new_cost = total + entry
            if step not in costs or new_cost < costs[step]:
                costs[step] = new_cost
                previous[step] = point
                heappush(heap, (new_cost, step.y, step.x))
    return "NO_PATH"


def exposed(state: WorldState, actor_id: str, target_id: str) -> bool:
    # The holder's own inventory authorizes item references even before a packet is built.
    if target_id == actor_id or target_id in state.exposure_receipts_by_resident[actor_id].entities:
        return True
    return any(entity.entity_id == target_id for entity in entities_at(state, Held(actor_id)))


def exhausted(state: WorldState, pack: EnginePack, actor_id: str) -> bool:
    stamina = pack.needs.get("stamina")
    return stamina is not None and state.needs[actor_id]["stamina"] <= stamina.minimum


def start_movement(
    state: WorldState,
    pack: EnginePack,
    actor: Resident,
    command: Move,
) -> Route | FailureCode:
    if exhausted(state, pack, actor.id):
        return "EXHAUSTED"
    route = path(
        state.static_map, state.explored_tiles_by_resident[actor.id], actor.position, command.target
    )
    if isinstance(route, Route) and route.steps and state.static_map.cost(route.steps[0]) is None:
        return "PATH_BLOCKED"
    return route


def progress_movement(
    state: WorldState,
    actor: Resident,
    route: Route,
    action: ActiveAction,
    writer: EventWriter,
    observe: Callable[[Coord, int], None],
) -> tuple[int, bool]:
    budget = state.static_map.walk_budget
    steps = 0
    before = actor.position
    for step in route.steps[route.cursor :]:
        cost = state.static_map.cost(step)
        if cost is None:
            action.pending_stop = "PATH_BLOCKED"
            break
        if cost > budget:
            break
        old = actor.position
        actor.position = step
        budget -= cost
        route.cursor += 1
        steps += 1
        writer.emit(
            "resident_moved",
            {
                "from": coord_payload(old),
                "to": coord_payload(step),
                "step_cost_units": cost,
            },
            action=action,
        )
        observe(step, steps)
    if steps:
        origin = action.state_delta[0].before if action.state_delta else before
        action.state_delta = [
            StateDelta(path=f"/residents/{actor.id}/position", before=origin, after=actor.position)
        ]
    return steps, action.pending_stop is not None or route.cursor == len(route.steps)


def inventory_room(
    state: WorldState,
    pack: EnginePack,
    actor_id: str,
    parts: tuple[Part, ...],
) -> bool:
    return slots_used(state, Held(actor_id)) + slots_for(state, parts) <= pack.inventory_slots


def transfer_parts(
    state: WorldState,
    action: ActiveAction,
    command: Give | Drop,
    at_start: bool,
) -> tuple[Part, ...] | None:
    actor_id = action.intent.actor_id
    if at_start:
        resolved = resolve_choices(state, actor_id, ((command.item, command.quantity),))
        return None if resolved is None else resolved[0]
    return action.parts if still_held(state, actor_id, action.parts) else None


def check_transfer(
    state: WorldState,
    pack: EnginePack,
    actor: Resident,
    action: ActiveAction,
    command: Give | Drop,
    *,
    at_start: bool,
) -> tuple[Part, ...] | FailureCode:
    if isinstance(command, Give):
        if command.recipient_id == actor.id or not exposed(state, actor.id, command.recipient_id):
            return "INVALID_TARGET"
        recipient = state.residents.get(command.recipient_id)
        if recipient is None or not recipient.alive:
            return "INVALID_TARGET"
        if distance(actor.position, recipient.position) != 1:
            return "OUT_OF_REACH"
        parts = transfer_parts(state, action, command, at_start)
        if parts is None:
            return "NO_ITEM"
        return parts if inventory_room(state, pack, recipient.id, parts) else "INVENTORY_FULL"

    destination = command.destination
    if isinstance(destination, OnTile):
        parts = transfer_parts(state, action, command, at_start)
        if parts is None:
            return "NO_ITEM"
        if at_start:
            if distance(actor.position, destination.position) > 1:
                return "OUT_OF_REACH"
            if not state.static_map.contains(destination.position) or (
                state.static_map.cost(destination.position) is None
            ):
                return "INVALID_TARGET"
        return parts

    if not exposed(state, actor.id, destination.container_id):
        return "INVALID_TARGET"
    target = state.entities.get(destination.container_id)
    if target is None or "container" not in target.components:
        return "INVALID_TARGET"
    parts = transfer_parts(state, action, command, at_start)
    if parts is None:
        return "NO_ITEM"
    if any(not accepts(pack, target, state.entities[part.entity_id]) for part in parts):
        return "INVALID_TARGET"
    if distance(actor.position, tile_of(state, target.place)) > 1:
        return "OUT_OF_REACH"
    if (
        slots_used(state, destination) + slots_for(state, parts)
        > (target.components["container"]["capacity"])
    ):
        return "CONTAINER_FULL"
    return parts


def check_pickup(
    state: WorldState,
    pack: EnginePack,
    actor: Resident,
    command: PickupEntity | PickupTile,
) -> tuple[Part, ...] | FailureCode:
    if isinstance(command, PickupEntity):
        if not exposed(state, actor.id, command.entity_id):
            return "INVALID_TARGET"
        entity = state.entities.get(command.entity_id)
        if entity is None or isinstance(entity.place, Held) or "portable" not in entity.components:
            return "INVALID_TARGET"
        if distance(actor.position, tile_of(state, entity.place)) > 1:
            return "OUT_OF_REACH"
        parts = take_parts((entity,), command.quantity)
    else:
        if (command.archetype_id, command.tile) not in state.exposure_receipts_by_resident[
            actor.id
        ].item_tiles:
            return "INVALID_TARGET"
        if distance(actor.position, command.tile) > 1:
            return "OUT_OF_REACH"
        parts = take_parts(
            (
                entity
                for entity in entities_at(state, OnTile(command.tile))
                if entity.archetype_id == command.archetype_id and "portable" in entity.components
            ),
            command.quantity,
        )
    if parts is None:
        return "ITEM_TAKEN"
    return parts if inventory_room(state, pack, actor.id, parts) else "INVENTORY_FULL"


def check_subject(
    state: WorldState,
    actor: Resident,
    command: Inspect | Contribute,
) -> Entity | FailureCode:
    entity_id = command.entity_id if isinstance(command, Inspect) else command.process_id
    if not exposed(state, actor.id, entity_id):
        return "INVALID_TARGET"
    entity = state.entities.get(entity_id)
    if entity is None:
        return "INVALID_TARGET"
    if isinstance(command, Contribute) and "process" not in entity.components:
        return "NOT_A_PROCESS"
    if distance(actor.position, tile_of(state, entity.place)) > 1:
        return "OUT_OF_REACH"
    return entity


def generic_act(
    state: WorldState,
    pack: EnginePack,
    actor: Resident,
    action: ActiveAction,
    command: Act,
) -> tuple[tuple[Part, ...], ...] | FailureCode:
    target = action.intent.target
    choices = [(item, 1) for item in action.intent.instruments]
    choices.extend((entry.item, entry.quantity) for entry in action.intent.inputs)
    refs = [item.id for item, _ in choices if item.kind == "item"]
    if target is not None and target.kind != "tile":
        refs.append(target.id)
    if any(not exposed(state, actor.id, key) for key in refs):
        return "INVALID_TARGET"

    verb = pack.verbs[command.verb]
    position = actor.position
    held = False
    match target:
        case TileTarget(position=tile):
            if not state.static_map.contains(tile):
                return "INVALID_TARGET"
            position = tile
        case EntityTarget(id=entity_id):
            entity = state.entities.get(entity_id)
            if entity is None or (
                verb.target_class is not None and verb.target_class not in entity.components
            ):
                return "INVALID_TARGET"
            held = entity.place == Held(actor.id)
            position = tile_of(state, entity.place)
        case _:
            if target is not None:
                resident = state.residents.get(target.id)
                if resident is None or not resident.alive:
                    return "INVALID_TARGET"
                position = resident.position
    groups = resolve_choices(state, actor.id, choices)
    action.resolved_choices = groups
    if groups is None or (verb.must_be_held and not held):
        return "NO_ITEM"
    if (
        target is not None
        and not held
        and not (verb.min_reach <= distance(actor.position, position) <= verb.max_reach)
    ):
        return "OUT_OF_REACH"
    return groups


def start_look(state: WorldState, pack: EnginePack, actor: Resident, action: ActiveAction) -> None:
    items = []
    visible = state.visible_entities_by_resident[actor.id]
    for part in action.parts:
        entity = state.entities[part.entity_id]
        if entity.entity_id not in visible and entity.place != Held(actor.id):
            continue
        look = inspect_view(state, pack, entity, inspect=False)
        items.append(
            PhaseItem(
                ItemUse(
                    entity_id=look.entity_id,
                    archetype_id=look.archetype_id,
                    material_id=look.material_id,
                    descriptors=look.descriptors,
                    quantity=part.quantity,
                    role="item",
                ),
                entity.place,
            )
        )
    action.start_items = tuple(item.look for item in items)
    target = action.intent.target
    where = None
    match target:
        case TileTarget(position=tile):
            where = tile
            if (
                state.static_map.contains(tile)
                and state.static_map.index(tile) in (state.explored_tiles_by_resident[actor.id])
            ):
                action.start_target = TileStartTarget(
                    kind="tile", position=tile, terrain=state.static_map.terrain(tile)
                )
        case EntityTarget(id=entity_id):
            subject = state.entities.get(entity_id)
            if subject is not None and (entity_id in visible or subject.place == Held(actor.id)):
                look = inspect_view(state, pack, subject, inspect=False)
                where = tile_of(state, subject.place)
                action.start_target = SubjectStartTarget(
                    kind="entity",
                    id=entity_id,
                    archetype_id=look.archetype_id,
                    material_id=look.material_id,
                    descriptors=look.descriptors,
                )
        case _:
            if target is not None and target.id in visible:
                where = state.residents[target.id].position
                action.start_target = SubjectStartTarget(
                    kind="resident",
                    id=target.id,
                    archetype_id=None,
                    material_id=None,
                    descriptors=[],
                )
    action.start_location = PhaseLocation(actor.position, where, tuple(items), action.start_target)


@dataclass(frozen=True)
class KernelResult:
    failure: FailureCode | None = None
    inspected: InspectView | None = None


def complete_kernel(
    state: WorldState,
    pack: EnginePack,
    actor: Resident,
    action: ActiveAction,
    writer: EventWriter,
) -> KernelResult:
    command = action.command
    match command:
        case Give() | Drop():
            parts = check_transfer(state, pack, actor, action, command, at_start=False)
            if isinstance(parts, str):
                return KernelResult(parts)
            if isinstance(command, Give):
                transfer(state, parts, Held(command.recipient_id), "give", writer, action)
                action.received_items = action.start_items
            else:
                transfer(state, parts, command.destination, "drop", writer, action)
        case PickupEntity() | PickupTile():
            parts = check_pickup(state, pack, actor, command)
            if isinstance(parts, str):
                return KernelResult(parts)
            transfer(state, parts, Held(actor.id), "pick_up", writer, action)
        case Inspect():
            target = check_subject(state, actor, command)
            if isinstance(target, str):
                return KernelResult(target)
            view = inspect_view(state, pack, target, inspect=True)
            writer.emit(
                "entity_inspected",
                json_object(
                    {
                        "entity_id": view.entity_id,
                        "descriptors": [row.model_dump(mode="json") for row in view.descriptors],
                    }
                ),
                action=action,
                target_id=target.entity_id,
            )
            return KernelResult(inspected=view)
        case Move() | Wait():
            pass
    return KernelResult()
