"""Build the same local signatures for live matching and recorded back-tests."""

from dataclasses import dataclass
from typing import Literal, cast

from ..protocol import Coord, EntityTarget, Terrain, TileTarget
from ..rules.catalog import Variant, matches
from ..rules.schema import Table
from .items import observed_count, slots_used, tile_of, true_values
from .kernel import distance
from .state import ActiveAction, Entity, Held, Part, PropertyValues, WorldState
from .validate import EnginePack

CONDITION_RADIUS = 2
STATE_FIELDS = {
    "store": ("store.count", "store.free"),
    "container": ("container.used", "container.free"),
    "durability": ("durability.wear", "durability.left"),
    "fuel": ("fuel.ticks_left",),
    "process": ("process.work_done",),
}


@dataclass(frozen=True)
class Property:
    property_id: str
    value: int | bool


@dataclass(frozen=True)
class StateField:
    field: str
    value: int


@dataclass(frozen=True)
class Signature:
    local_key: int
    ref_kind: Literal["tile", "entity", "resident"]
    archetype_id: str | None
    material_id: str | None
    terrain: Terrain | None
    components: tuple[str, ...]
    properties: tuple[Property, ...]
    state: tuple[StateField, ...]
    held: bool
    distance: int

    def matches(self, predicate: Table) -> bool:
        # Corpses and residents have no rule archetype, but may have a tile.
        if self.archetype_id is None:
            return False
        return matches(
            predicate,
            Variant(
                (self.archetype_id, self.material_id),
                {entry.property_id: entry.value for entry in self.properties},
                dict.fromkeys(self.components),
            ),
        )


@dataclass(frozen=True)
class SignaturePart:
    signature: Signature
    quantity: int


@dataclass(frozen=True)
class Input:
    quantity: int
    parts: tuple[SignaturePart, ...]


@dataclass(frozen=True)
class NeedValue:
    need_id: str
    value: int


@dataclass(frozen=True)
class NearbyTerrain:
    terrain: Terrain
    distances: tuple[int, ...]


@dataclass(frozen=True)
class NearbyEntity:
    signature: Signature
    distance: int


@dataclass(frozen=True)
class ConditionContext:
    awareness: str
    needs: tuple[NeedValue, ...]
    free_slots: int
    position: Coord
    terrain_here: Terrain
    time_phase: Literal["day", "night"]
    nearby_terrain: tuple[NearbyTerrain, ...]
    nearby_entities: tuple[NearbyEntity, ...]


@dataclass(frozen=True)
class AttemptDescriptor:
    verb: str
    tick: int
    target: Signature | None
    instruments: tuple[Signature, ...]
    inputs: tuple[Input, ...]
    context: ConditionContext


def entity_signature(
    state: WorldState,
    pack: EnginePack,
    entity: Entity,
    actor_id: str,
    position: Coord,
    tick: int,
    local_key: int,
) -> Signature:
    point = tile_of(state, entity.place)
    values: PropertyValues = (
        pack.defaults if entity.archetype_id is None else true_values(pack, entity)
    )
    state_values = {"quantity": entity.quantity, "age": tick - entity.created_tick}
    for component, names in STATE_FIELDS.items():
        if component in entity.components:
            for name in names:
                state_values[name] = observed_count(state, entity, name)
    if "container" in entity.components:
        for archetype in pack.archetypes:
            field = f"container.count:{archetype}"
            state_values[field] = observed_count(state, entity, field)
    return Signature(
        local_key,
        "entity",
        entity.archetype_id,
        entity.material_id,
        state.static_map.terrain(point),
        tuple(sorted(entity.components)),
        tuple(Property(key, val) for key, val in sorted(values.items())),
        tuple(StateField(key, val) for key, val in sorted(state_values.items())),
        entity.place == Held(actor_id),
        distance(position, point),
    )


def nearby_context(
    state: WorldState,
    pack: EnginePack,
    actor_id: str,
    tick: int,
) -> tuple[tuple[str, NearbyEntity], ...]:
    point = state.residents[actor_id].position
    entries = sorted(
        (steps, entity_id)
        for entity_id, entity in state.entities.items()
        if (steps := distance(point, tile_of(state, entity.place))) <= CONDITION_RADIUS
    )
    return tuple(
        (
            entity_id,
            NearbyEntity(
                entity_signature(
                    state, pack, state.entities[entity_id], actor_id, point, tick, index
                ),
                steps,
            ),
        )
        for index, (steps, entity_id) in enumerate(entries)
    )


def describe(
    state: WorldState,
    pack: EnginePack,
    action: ActiveAction,
    groups: tuple[tuple[Part, ...], ...],
    tick: int,
) -> tuple[AttemptDescriptor, tuple[str, ...]]:
    """Return objective local data and a parallel live witness ID index."""
    intent = action.intent
    actor_id = intent.actor_id
    point = state.residents[actor_id].position
    smap = state.static_map
    keys: dict[tuple[str, str | Coord], int] = {}

    def key(kind: str, identity: str | Coord) -> int:
        return keys.setdefault((kind, identity), len(keys))

    def entity_view(entity_id: str) -> Signature:
        return entity_signature(
            state, pack, state.entities[entity_id], actor_id, point, tick, key("entity", entity_id)
        )

    target: Signature | None
    match intent.target:
        case None:
            target = None
        case EntityTarget(id=entity_id):
            target = entity_view(entity_id)
        case TileTarget(position=position):
            target = Signature(
                key("tile", position),
                "tile",
                None,
                None,
                smap.terrain(position),
                (),
                (),
                (),
                False,
                distance(point, position),
            )
        case resident:
            position = state.residents[resident.id].position
            target = Signature(
                key("resident", resident.id),
                "resident",
                None,
                None,
                smap.terrain(position),
                (),
                (),
                (),
                False,
                distance(point, position),
            )

    instrument_count = len(intent.instruments)
    instruments = tuple(entity_view(parts[0].entity_id) for parts in groups[:instrument_count])
    inputs = tuple(
        Input(
            sum(part.quantity for part in parts),
            tuple(
                SignaturePart(entity_view(part.entity_id), part.quantity)
                for part in sorted(parts, key=lambda part: part.entity_id)
            ),
        )
        for parts in groups[instrument_count:]
    )
    terrain_distances: dict[Terrain, set[int]] = {}
    for y in range(
        max(0, point.y - CONDITION_RADIUS), min(len(smap.rows), point.y + CONDITION_RADIUS + 1)
    ):
        for x in range(
            max(0, point.x - CONDITION_RADIUS), min(smap.width, point.x + CONDITION_RADIUS + 1)
        ):
            steps = abs(point.x - x) + abs(point.y - y)
            if steps <= CONDITION_RADIUS:
                terrain_distances.setdefault(smap.rows[y][x], set()).add(steps)

    nearby = sorted(
        (steps, entity_id)
        for entity_id, entity in state.entities.items()
        if (steps := distance(point, tile_of(state, entity.place))) <= CONDITION_RADIUS
    )
    clock = state.clock
    minute = clock.minute_at(tick)
    context = ConditionContext(
        state.awareness[actor_id].kind,
        tuple(NeedValue(k, v) for k, v in sorted(state.needs[actor_id].items())),
        pack.inventory_slots - slots_used(state, Held(actor_id)),
        point,
        smap.terrain(point),
        "day" if clock.day_start_minute <= minute < clock.day_end_minute else "night",
        tuple(NearbyTerrain(k, tuple(sorted(v))) for k, v in sorted(terrain_distances.items())),
        tuple(NearbyEntity(entity_view(entity_id), steps) for steps, entity_id in nearby),
    )
    return (
        AttemptDescriptor(cast(str, intent.verb), tick, target, instruments, inputs, context),
        tuple(entity_id for _, entity_id in nearby),
    )
