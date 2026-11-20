"""Item selection, physical portions, and deterministic stack transfer."""

from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import replace
from typing import Literal, cast

from ..protocol import Coord, Descriptor, InspectView, IntegerJson, ItemChoice, StateDelta
from ..rules.catalog import Variant, matches
from ..rules.schema import Table
from ..rules.vocabulary import descriptor
from .events import EventWriter, coord_payload
from .state import (
    ActiveAction,
    Entity,
    Held,
    Inside,
    InStore,
    Lineage,
    OnTile,
    Part,
    Place,
    PropertyValues,
    WorldState,
)
from .validate import EnginePack

type TransferKind = Literal["give", "pick_up", "drop"]
type SplitCause = Literal["reservation", "transfer"]


def entities_at(state: WorldState, place: Place) -> list[Entity]:
    return [
        state.entities[key] for key in sorted(state.entities) if state.entities[key].place == place
    ]


def tile_of(state: WorldState, place: Place) -> Coord:
    while True:
        match place:
            case OnTile(position):
                return position
            case Held(holder_id):
                return state.residents[holder_id].position
            case Inside(container_id) | InStore(container_id):
                place = state.entities[container_id].place


def slots_used(state: WorldState, place: Place) -> int:
    return sum(
        entity.quantity * entity.components["portable"]["slots_per_unit"]
        for entity in entities_at(state, place)
    )


def slots_for(state: WorldState, parts: Iterable[Part]) -> int:
    return sum(
        part.quantity * state.entities[part.entity_id].components["portable"]["slots_per_unit"]
        for part in parts
    )


def take_parts(entities: Iterable[Entity], quantity: int) -> tuple[Part, ...] | None:
    parts = []
    for entity in entities:
        amount = min(entity.quantity, quantity)
        parts.append(Part(entity.entity_id, amount))
        quantity -= amount
        if quantity == 0:
            return tuple(parts)
    return None


def resolve_choices(
    state: WorldState, actor_id: str, choices: Sequence[tuple[ItemChoice, int]]
) -> tuple[tuple[Part, ...], ...] | None:
    held = {entity.entity_id: entity for entity in entities_at(state, Held(actor_id))}
    resolved: dict[int, tuple[Part, ...]] = {}
    for index, (choice, quantity) in enumerate(choices):
        if choice.kind == "item":
            entity = held.pop(choice.id, None)
            if entity is None or entity.quantity < quantity:
                return None
            resolved[index] = (Part(entity.entity_id, quantity),)
    for index, (choice, quantity) in enumerate(choices):
        if choice.kind == "held":
            eligible = (
                entity for entity in held.values() if entity.archetype_id == choice.archetype_id
            )
            parts = take_parts(eligible, quantity)
            if parts is None:
                return None
            resolved[index] = parts
            for part in parts:
                del held[part.entity_id]
    return tuple(resolved[index] for index in range(len(choices)))


def still_held(state: WorldState, actor_id: str, parts: Sequence[Part]) -> bool:
    place = Held(actor_id)
    return all(
        (entity := state.entities.get(part.entity_id)) is not None
        and entity.place == place
        and entity.quantity >= part.quantity
        for part in parts
    )


def ordinary_values(pack: EnginePack, archetype_id: str, material_id: str | None) -> PropertyValues:
    archetype = pack.archetypes[archetype_id]
    material = {} if material_id is None else pack.materials[material_id].properties
    return {
        **pack.defaults,
        **material,
        **archetype.properties,
    }


def true_values(pack: EnginePack, entity: Entity) -> PropertyValues:
    archetype_id = cast(str, entity.archetype_id)
    return {**ordinary_values(pack, archetype_id, entity.material_id), **entity.properties}


def accepts(pack: EnginePack, container: Entity, item: Entity) -> bool:
    return matches(
        container.components["container"]["accepts"],
        Variant(
            (cast(str, item.archetype_id), item.material_id),
            cast(Table, true_values(pack, item)),
            cast(Table, item.components),
        ),
    )


def observed_count(state: WorldState, entity: Entity, field: str) -> int:
    components = entity.components
    place = Inside(entity.entity_id)
    match field:
        case "store.count":
            return components["store"]["count"]
        case "store.free":
            store = components["store"]
            return store["capacity"] - store["count"]
        case "container.used":
            return slots_used(state, place)
        case "container.free":
            return components["container"]["capacity"] - slots_used(state, place)
        case "durability.wear":
            return components["durability"]["wear"]
        case "durability.left":
            durability = components["durability"]
            return durability["max_wear"] - durability["wear"]
        case "fuel.ticks_left":
            return components["fuel"]["ticks_left"]
        case "process.work_done":
            return components["process"]["work_done"]
        case _:
            archetype = field.removeprefix("container.count:")
            return sum(
                item.quantity
                for item in entities_at(state, place)
                if item.archetype_id == archetype
            )


def inspect_view(
    state: WorldState, pack: EnginePack, entity: Entity, *, inspect: bool
) -> InspectView:
    descriptors = []
    if entity.archetype_id is not None:
        values = true_values(pack, entity)
        archetype = pack.archetypes[entity.archetype_id]
        if entity.material_id is not None:
            material = pack.materials[entity.material_id]
            values.update(
                {
                    key: value
                    for key, value in material.apparent.items()
                    if key not in archetype.properties and key not in entity.properties
                }
            )
        values.update(entity.apparent)
        values.update(
            {name: observed_count(state, entity, field) for name, field in archetype.observations}
        )
        for key, value in sorted(values.items()):
            prop = pack.source.vocabulary.properties[key]
            if prop["observability"] == "visible" or (
                inspect and prop["observability"] == "on_inspect"
            ):
                descriptors.append(Descriptor(property_id=key, value=descriptor(prop, value)))
    return InspectView(
        entity_id=entity.entity_id,
        archetype_id=entity.archetype_id,
        material_id=entity.material_id,
        descriptors=descriptors,
    )


def place_payload(place: Place) -> dict[str, IntegerJson]:
    match place:
        case OnTile(position):
            return {"kind": "tile", "position": coord_payload(position)}
        case Held(holder_id):
            return {"kind": "held", "holder_id": holder_id}
        case Inside(container_id):
            return {"kind": "in", "container_id": container_id}
        case InStore(entity_id):
            return {"kind": "store", "entity_id": entity_id}


def transfer_endpoint(place: Place) -> dict[str, IntegerJson]:
    match place:
        case OnTile(position):
            return {"kind": "tile", "id": f"{position.x},{position.y}"}
        case Held(holder_id):
            return {"kind": "held", "id": holder_id}
        case Inside(container_id):
            return {"kind": "in", "id": container_id}
        case InStore(entity_id):
            return {"kind": "store", "id": entity_id}


def equal_stacks(left: Entity, right: Entity) -> bool:
    return (
        left.stackable
        and right.stackable
        and (
            left.archetype_id,
            left.material_id,
            left.components,
            left.properties,
            left.apparent,
            left.tells,
        )
        == (
            right.archetype_id,
            right.material_id,
            right.components,
            right.properties,
            right.apparent,
            right.tells,
        )
    )


def split(
    state: WorldState,
    entity: Entity,
    quantity: int,
    cause: SplitCause,
    writer: EventWriter,
    action: ActiveAction | None = None,
) -> Entity:
    moving_lineage: list[Lineage] = []
    remaining_lineage: list[Lineage] = []
    remaining = quantity
    for portion in entity.lineage:
        taken = min(remaining, portion.quantity)
        if taken:
            moving_lineage.append(replace(portion, quantity=taken))
        if taken < portion.quantity:
            remaining_lineage.append(replace(portion, quantity=portion.quantity - taken))
        remaining -= taken
    moving = replace(
        deepcopy(entity),
        entity_id=state.entity_counter.allocate(state.seed),
        quantity=quantity,
        lineage=tuple(moving_lineage),
    )
    entity.quantity -= quantity
    entity.lineage = tuple(remaining_lineage)
    state.entities[moving.entity_id] = moving
    writer.emit(
        "stack_split",
        {
            "from_id": entity.entity_id,
            "new_id": moving.entity_id,
            "quantity": quantity,
            "cause": cause,
        },
        action=action,
        target_id=entity.entity_id,
    )
    return moving


def merge(
    state: WorldState,
    moving: Entity,
    survivor: Entity,
    writer: EventWriter,
    action: ActiveAction | None = None,
) -> None:
    survivor.quantity += moving.quantity
    survivor.created_tick = min(survivor.created_tick, moving.created_tick)
    survivor.lineage = tuple(
        sorted((*survivor.lineage, *moving.lineage), key=lambda portion: portion.event_order)
    )
    del state.entities[moving.entity_id]
    writer.emit(
        "stack_merged",
        {
            "from_id": moving.entity_id,
            "into_id": survivor.entity_id,
            "quantity": moving.quantity,
        },
        action=action,
        target_id=survivor.entity_id,
    )


def transfer_state(entity: Entity) -> dict[str, str | int | None]:
    endpoint = transfer_endpoint(entity.place)
    prefix = f"/entities/{entity.entity_id}"
    return {
        f"{prefix}/quantity": entity.quantity,
        f"{prefix}/place": f"{endpoint['kind']}:{endpoint['id']}",
        f"{prefix}/owner_id": entity.owner_id,
    }


def transfer(
    state: WorldState,
    parts: Sequence[Part],
    destination: Place,
    via: TransferKind,
    writer: EventWriter,
    action: ActiveAction,
) -> None:
    reserved = {
        binding.physical_id
        for running in state.active_actions.values()
        for binding in running.bindings
    }
    initial: dict[str, str | int | None] = {}
    changed: set[str] = set()
    for part in parts:
        source = state.entities[part.entity_id]
        initial.update(transfer_state(source))
        changed.add(source.entity_id)
        moving = (
            source
            if part.quantity == source.quantity
            else split(state, source, part.quantity, "transfer", writer, action)
        )
        changed.add(moving.entity_id)
        owner_before = moving.owner_id
        if via == "give" and not moving.stackable:
            moving.owner_id = cast(Held, destination).holder_id
        writer.emit(
            "item_transferred",
            {
                "item_id": moving.entity_id,
                "archetype_id": moving.archetype_id,
                "quantity": moving.quantity,
                "from": transfer_endpoint(moving.place),
                "to": transfer_endpoint(destination),
                "via": via,
                "owner_before": owner_before,
                "owner_after": moving.owner_id,
            },
            action=action,
            target_id=moving.entity_id,
        )
        survivor = next(
            (
                entity
                for entity in entities_at(state, destination)
                if entity.entity_id not in reserved and equal_stacks(entity, moving)
            ),
            None,
        )
        moving.place = destination
        if survivor is not None:
            if survivor.entity_id not in changed:
                initial.update(transfer_state(survivor))
                changed.add(survivor.entity_id)
            merge(state, moving, survivor, writer, action)
    final = {
        path: value
        for key in changed
        if key in state.entities
        for path, value in transfer_state(state.entities[key]).items()
    }
    action.state_delta.extend(
        StateDelta(path=path, before=initial.get(path), after=final.get(path))
        for path in sorted(initial.keys() | final.keys())
        if initial.get(path) != final.get(path)
    )
