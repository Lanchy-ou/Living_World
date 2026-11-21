"""Capture operands and simulate a verb branch before publishing any changes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from ..protocol import Coord, EntityTarget, StateDelta, TileTarget
from ..rules import Rule
from ..rules.schema import Table
from .events import EventWriter, json_object
from .items import (
    accepts,
    entities_at,
    equal_stacks,
    item_use,
    merge,
    place_payload,
    slots_used,
    split,
    tile_of,
    transfer_state,
)
from .limits import within_placement_limits
from .observe import phase_item
from .state import (
    ActiveAction,
    Components,
    Entity,
    Held,
    Inside,
    InStore,
    Lineage,
    OnTile,
    Part,
    PhaseItem,
    Place,
    WorldState,
)
from .validate import EnginePack

if TYPE_CHECKING:
    from .tick import TickContext


class Refused(Exception):
    """The selected physical transaction cannot be applied to this ledger."""


@dataclass(frozen=True)
class Create:
    entity: Entity
    source: str | None
    return_slot: str | None


@dataclass(frozen=True)
class Debit:
    source: str | Inside | InStore
    archetype: str
    quantity: int
    destination: Place | None


@dataclass(frozen=True)
class SetState:
    ids: tuple[str, ...]
    field: str
    value: int
    relative: bool


@dataclass(frozen=True)
class Need:
    actor_id: str
    name: str
    delta: int


type Operation = Create | Debit | SetState | Need


@dataclass(frozen=True)
class EffectOperands(ABC):
    state: WorldState
    pack: EnginePack
    slots: dict[str, tuple[Part, ...]]

    @abstractmethod
    def owner(self) -> str | None: ...

    @abstractmethod
    def entity(self, role: str) -> Entity: ...

    @abstractmethod
    def place(self, raw: str) -> Place: ...

    def quantity(self, raw: int | Table, prototype: Entity | None = None) -> int:
        if isinstance(raw, int):
            return raw
        reference = raw["of"]
        if reference.startswith("fit:"):
            place = self.place(reference[4:])
            item = cast(Entity, prototype)
            if isinstance(place, InStore):
                store = self.state.entities[place.entity_id].components["store"]
                available = (
                    store["capacity"] - store["count"]
                    if store["archetype"] == item.archetype_id
                    else 0
                )
            else:
                container = self.state.entities[cast(Inside, place).container_id]
                available = (
                    (container.components["container"]["capacity"] - slots_used(self.state, place))
                    // item.components["portable"]["slots_per_unit"]
                    if accepts(self.pack, container, item)
                    else 0
                )
        else:
            role, _, field = reference.partition(".")
            if field == "store.count":
                available = self.entity(role).components["store"]["count"]
            elif role in ("target", "subject"):
                available = self.entity(role).quantity
            else:
                available = sum(part.quantity for part in self.slots[role[5:]])
        return min(available, cast(int, raw.get("upto", available)))

    def prototype(
        self, archetype: str, material: str | None, place: Place, quantity: int
    ) -> Entity:
        row = self.pack.source.data["archetype"][archetype]
        stackable = self.pack.archetypes[archetype].stackable
        return Entity(
            "",
            archetype,
            material,
            quantity,
            0,
            None if stackable else self.owner(),
            place,
            cast(Components, deepcopy(row["components"])),
            {},
            {},
            (),
            stackable,
            (),
        )

    def output(self, row: Table) -> Create:
        arch_from = row.get("archetype_from")
        mat_from = row.get("material_from")
        inherited_arch = None if arch_from is None else self.entity(slot_ref(arch_from))
        inherited_mat = None if mat_from is None else self.entity(slot_ref(mat_from))
        archetype: str = (
            row["archetype"] if inherited_arch is None else cast(str, inherited_arch.archetype_id)
        )
        default = self.pack.source.data["archetype"][archetype].get("material")
        material = row.get(
            "material", default if inherited_mat is None else inherited_mat.material_id
        )
        prototype = self.prototype(archetype, material, self.place(row["at"]), 1)
        prototype.quantity = self.quantity(row["quantity"], prototype)
        return Create(prototype, row.get("source"), arch_from if arch_from == mat_from else None)

    def effect(self, row: Table) -> Operation:
        op = row["op"]
        if op == "set_state":
            role = row["of"]
            ids = (
                (self.entity(role).entity_id,)
                if role in ("target", "subject")
                else tuple(part.entity_id for part in self.slots[role[5:]])
            )
            return SetState(
                ids, row["field"], row["add"] if "add" in row else row["set"], "add" in row
            )
        moving = op == "move"
        ref = row["from"] if moving else row["of"]
        role, _, field = ref.partition(".")
        entity = self.entity(role)
        source: str | Inside | InStore
        if field == "store":
            source = InStore(entity.entity_id)
            archetype = entity.components["store"]["archetype"]
        elif field == "contents":
            source = Inside(entity.entity_id)
            archetype = row["archetype"]
        else:
            source = entity.entity_id
            archetype = cast(str, entity.archetype_id)
        quantity = self.quantity(row.get("quantity", entity.quantity))
        return Debit(source, archetype, quantity, self.place(row["to"]) if moving else None)


@dataclass(frozen=True)
class Operands(EffectOperands):
    action: ActiveAction

    @property
    def actor_id(self) -> str:
        return self.action.intent.actor_id

    def entity(self, role: str) -> Entity:
        if role == "target":
            key = cast(EntityTarget, self.action.intent.target).id
            entity = self.state.entities.get(key)
            if entity is None:
                # A partial branch can refer to a target that disappeared during work.
                raise Refused
            return entity
        return self.state.entities[self.slots[role[5:]][0].entity_id]

    def place(self, raw: str) -> Place:
        match raw:
            case "actor":
                return Held(self.actor_id)
            case "actor.tile":
                return OnTile(self.state.residents[self.actor_id].position)
            case "target.tile":
                target = self.action.intent.target
                if isinstance(target, TileTarget):
                    return OnTile(target.position)
                return OnTile(tile_of(self.state, self.entity("target").place))
            case "target.contents":
                return Inside(self.entity("target").entity_id)
            case _:
                return InStore(self.entity("target").entity_id)

    def owner(self) -> str:
        return self.actor_id

    def effect(self, row: Table) -> Operation:
        if row["op"] == "need":
            return Need(self.actor_id, row["need"], row["delta"])
        return super().effect(row)


def slot_ref(slot: str) -> str:
    return slot if slot == "target" else f"slot:{slot}"


def portions(parts: Iterable[Part]) -> list[dict[str, str | int]]:
    return [{"physical_id": part.entity_id, "quantity": part.quantity} for part in parts]


def clamp_need(
    state: WorldState, pack: EnginePack, actor_id: str, name: str, delta: int
) -> tuple[int, int]:
    values = state.needs[actor_id]
    before = values[name]
    bounds = pack.needs[name]
    after = min(bounds.maximum, max(bounds.minimum, before + delta))
    values[name] = after
    return before, after


def coalesce_stack(
    state: WorldState,
    entity: Entity,
    reserved: set[str],
    writer: EventWriter,
    action: ActiveAction | None,
) -> Entity:
    equal = [
        other
        for other in entities_at(state, entity.place)
        if other.entity_id != entity.entity_id
        and other.entity_id not in reserved
        and equal_stacks(entity, other)
    ]
    if not equal:
        return entity
    survivor = equal[0]
    merge(state, entity, survivor, writer, action)
    return survivor


def reserved_ids(state: WorldState) -> set[str]:
    return {
        binding.physical_id
        for action in state.active_actions.values()
        for binding in action.bindings
    }


def release(state: WorldState, writer: EventWriter, action: ActiveAction) -> dict[str, str]:
    released = {binding.physical_id for binding in action.bindings}
    reserved = reserved_ids(state) - released
    merged: dict[str, str] = {}
    for key in sorted(released):
        entity = state.entities.get(key)
        if entity is None or not entity.stackable:
            continue
        candidates = [
            other
            for other in entities_at(state, entity.place)
            if other.entity_id not in reserved and equal_stacks(entity, other)
        ]
        survivor, *remnants = candidates
        for moving in remnants:
            merged[moving.entity_id] = survivor.entity_id
            merge(state, moving, survivor, writer, action)
    return merged


class Ledger:
    def __init__(
        self,
        ctx: TickContext,
        action: ActiveAction | None,
        rule: Rule,
        operands: EffectOperands,
        *,
        process_id: str | None = None,
    ) -> None:
        state = ctx.state
        needs = state.needs.copy()
        if action is not None:
            actor_id = action.intent.actor_id
            needs[actor_id] = needs[actor_id].copy()
        self.state = replace(
            state,
            entities=deepcopy(state.entities),
            entity_counter=deepcopy(state.entity_counter),
            needs=needs,
        )
        self.writer = EventWriter(self.state, ctx.tick)
        self.action = action
        self.process_id = process_id
        self.operands = operands
        self.pack = ctx.pack
        self.rule_id = rule.id
        self.reserved = reserved_ids(state)
        self.receiving: set[Coord] = set()
        self.consumed: list[Part] = []
        self.returns: dict[str, list[Part]] = {}
        self.outputs: list[Part] = []
        self.output_looks: list[PhaseItem] = []
        self.withdrawn: dict[str, int] = {}

    def publish(
        self, ctx: TickContext, action: ActiveAction, provisional: ActiveAction
    ) -> dict[str, str] | None:
        merged = release(self.state, self.writer, provisional)
        actor_id = action.intent.actor_id
        changes = branch_delta(ctx.state, self.state, actor_id)
        if not self.publish_world(ctx):
            return None
        ctx.state.needs[actor_id] = self.state.needs[actor_id]
        action.event_ids.extend(provisional.event_ids)
        extend_delta(action, changes)
        return merged

    def publish_world(self, ctx: TickContext) -> bool:
        if not within_placement_limits(self.state, self.pack.limits, self.receiving):
            return False
        ctx.state.entities = self.state.entities
        ctx.state.entity_counter = self.state.entity_counter
        ctx.state.next_event_seq_in_tick = self.state.next_event_seq_in_tick
        ctx.state.event_log_cursor = self.state.event_log_cursor
        ctx.writer.events.extend(self.writer.events)
        return True

    def register(self, entity: Entity) -> None:
        entity.entity_id = self.state.entity_counter.allocate(self.state.seed)
        entity.created_tick = self.writer.tick
        entity.lineage = (
            Lineage(
                entity.entity_id, entity.created_tick, entity.quantity, self.state.event_log_cursor
            ),
        )
        self.state.entities[entity.entity_id] = entity

    def store_change(self, target: InStore, delta: int, source: str | None = None) -> None:
        holder = self.state.entities.get(target.entity_id)
        if holder is None:
            raise Refused
        store = holder.components["store"]
        before = store["count"]
        after = before + delta
        if not 0 <= after <= store["capacity"]:
            raise Refused
        store["count"] = after
        self.writer.emit(
            "store_count_changed",
            {
                "entity_id": target.entity_id,
                "archetype_id": store["archetype"],
                "before": before,
                "after": after,
                "rule_id": self.rule_id,
                "source": source,
            },
            action=self.action,
            target_id=target.entity_id,
        )

    def destination(self, item: Entity, place: Place) -> Place:
        if isinstance(place, Held):
            portable = item.components.get("portable")
            if portable is None or (
                slots_used(self.state, place) + item.quantity * portable["slots_per_unit"]
                > self.pack.inventory_slots
            ):
                return OnTile(self.state.residents[place.holder_id].position)
        elif isinstance(place, Inside):
            holder = self.state.entities.get(place.container_id)
            if (
                holder is None
                or not accepts(self.pack, holder, item)
                or (
                    slots_used(self.state, place)
                    + (
                        0
                        if item.entity_id in self.state.entities and item.place == place
                        else item.quantity * item.components["portable"]["slots_per_unit"]
                    )
                    > holder.components["container"]["capacity"]
                )
            ):
                raise Refused
        return place

    def place_entity(self, entity: Entity, place: OnTile | Held | Inside) -> Entity:
        if isinstance(place, OnTile):
            self.receiving.add(place.position)
        entity.place = place
        return coalesce_stack(self.state, entity, self.reserved, self.writer, self.action)

    def capture_output(self, entity: Entity, place: OnTile | Held | Inside) -> None:
        if self.action is None:
            return
        actor_id = self.action.intent.actor_id
        if place in (Held(actor_id), OnTile(self.state.residents[actor_id].position)):
            look = item_use(self.state, self.pack, entity, entity.quantity, "output")
            self.output_looks.append(phase_item(self.state, look, place))

    def move(self, entity: Entity, origin: Place, destination: Place) -> None:
        place = self.destination(entity, destination)
        if isinstance(place, InStore):
            self.store_change(place, entity.quantity)
            self.state.entities.pop(entity.entity_id, None)
            result_id = None
        else:
            materialized = not entity.entity_id
            if materialized:
                self.register(entity)
                self.capture_output(entity, place)
            result_id = self.place_entity(entity, place).entity_id
            if materialized:
                self.outputs.append(Part(result_id, entity.quantity))
        self.writer.emit(
            "matter_moved",
            json_object(
                {
                    "archetype_id": entity.archetype_id,
                    "quantity": entity.quantity,
                    "from": place_payload(origin),
                    "to": place_payload(place),
                    "entity_id": result_id,
                    "rule_id": self.rule_id,
                }
            ),
            action=self.action,
        )

    def from_store(
        self, origin: InStore, archetype: str, quantity: int, destination: Place
    ) -> None:
        row = self.pack.source.data["archetype"][archetype]
        prototype = self.operands.prototype(archetype, row.get("material"), origin, quantity)
        prototype.owner_id = None
        self.store_change(origin, -quantity)
        if isinstance(destination, InStore) or prototype.stackable:
            self.move(prototype, origin, destination)
        else:
            for _ in range(quantity):
                self.move(replace(deepcopy(prototype), quantity=1), origin, destination)

    def consume_input(self, name: str, parts: tuple[Part, ...]) -> None:
        self.returns[name] = list(parts)
        for part in parts:
            self.withdrawn[part.entity_id] = part.quantity + self.withdrawn.get(part.entity_id, 0)
            self.consume(part)

    def consume(self, part: Part) -> None:
        entity = self.state.entities.get(part.entity_id)
        if entity is None or entity.quantity < part.quantity:
            raise Refused
        if part.quantity == entity.quantity:
            position = OnTile(tile_of(self.state, entity.place))
            origin = Inside(entity.entity_id)
            for item in entities_at(self.state, origin):
                self.move(item, origin, position)
            store = entity.components.get("store")
            if store is not None and store["count"]:
                self.from_store(
                    InStore(entity.entity_id), store["archetype"], store["count"], position
                )
            del self.state.entities[part.entity_id]
        else:
            # Partial destruction keeps the source ID and removes oldest portions.
            remaining = part.quantity
            lineage = []
            for segment in entity.lineage:
                taken = min(segment.quantity, remaining)
                if taken < segment.quantity:
                    lineage.append(replace(segment, quantity=segment.quantity - taken))
                remaining -= taken
            entity.lineage = tuple(lineage)
            entity.quantity -= part.quantity
        self.consumed.append(part)
        self.writer.emit(
            "entity_consumed",
            {
                "entity_id": part.entity_id,
                "archetype_id": entity.archetype_id,
                "quantity": part.quantity,
                "rule_id": self.rule_id,
            },
            action=self.action,
            target_id=part.entity_id,
        )

    def debit(self, operation: Debit) -> None:
        source, quantity = operation.source, operation.quantity
        if isinstance(source, str):
            self.consume(Part(source, quantity))
        elif isinstance(source, InStore):
            self.from_store(
                source, operation.archetype, quantity, cast(Place, operation.destination)
            )
        else:
            available = [
                item
                for item in entities_at(self.operands.state, source)
                if item.entity_id not in self.reserved and item.archetype_id == operation.archetype
            ]
            for original in available:
                amount = min(
                    quantity, original.quantity - self.withdrawn.get(original.entity_id, 0)
                )
                if not amount:
                    continue
                entity = self.state.entities.get(original.entity_id)
                if entity is None or entity.place != source or entity.quantity < amount:
                    raise Refused
                self.withdrawn[entity.entity_id] = self.withdrawn.get(entity.entity_id, 0) + amount
                if operation.destination is None:
                    self.consume(Part(entity.entity_id, amount))
                else:
                    moving = (
                        entity
                        if amount == entity.quantity
                        else split(self.state, entity, amount, "transfer", self.writer, self.action)
                    )
                    self.move(moving, source, operation.destination)
                quantity -= amount
                if quantity == 0:
                    return
            raise Refused

    def recreate(self, slot: str, quantity: int) -> list[Part]:
        histories = self.returns[slot]
        result = []
        while quantity:
            part = histories[0]
            used = min(quantity, part.quantity)
            result.append(Part(part.entity_id, used))
            if used == part.quantity:
                histories.pop(0)
            else:
                histories[0] = Part(part.entity_id, part.quantity - used)
            quantity -= used
        return result

    def create(self, operation: Create) -> None:
        prototype = operation.entity
        if isinstance(prototype.place, InStore):
            self.store_change(prototype.place, prototype.quantity, operation.source)
            return
        units = (prototype.quantity,) if prototype.stackable else (1,) * prototype.quantity
        for quantity in units:
            entity = replace(deepcopy(prototype), quantity=quantity)
            place = cast(OnTile | Held | Inside, self.destination(entity, entity.place))
            entity.place = place
            self.register(entity)
            returned = (
                []
                if operation.return_slot is None
                else self.recreate(operation.return_slot, quantity)
            )
            self.writer.emit(
                "entity_created",
                json_object(
                    {
                        "entity_id": entity.entity_id,
                        "archetype_id": entity.archetype_id,
                        "material_id": entity.material_id,
                        "quantity": entity.quantity,
                        "place": place_payload(place),
                        "owner_id": entity.owner_id,
                        "rule_id": self.rule_id,
                        "source": operation.source,
                        "recreated_from": portions(returned),
                        "made_from": portions(self.consumed) if operation.source is None else [],
                        "process_id": self.process_id,
                    }
                ),
                action=self.action,
                target_id=entity.entity_id,
            )
            self.capture_output(entity, place)
            survivor = self.place_entity(entity, place)
            self.outputs.append(Part(survivor.entity_id, quantity))

    def set_state(self, operation: SetState) -> None:
        component, _, field = operation.field.partition(".")
        for key in operation.ids:
            entity = self.state.entities.get(key)
            if entity is None:
                raise Refused
            values = cast(dict[str, int], cast(Table, entity.components)[component])
            before = values[field]
            after = max(0, before + operation.value if operation.relative else operation.value)
            if component == "durability":
                after = min(after, values["max_wear"])
            values[field] = after
            if before != after:
                self.writer.emit(
                    "entity_state_changed",
                    {
                        "entity_id": key,
                        "field": operation.field,
                        "before": before,
                        "after": after,
                        "rule_id": self.rule_id,
                    },
                    action=self.action,
                    target_id=key,
                )

    def apply(self, operation: Operation) -> None:
        match operation:
            case Debit(quantity=0) | Create(entity=Entity(quantity=0)):
                pass
            case Debit():
                self.debit(operation)
            case Create():
                self.create(operation)
            case SetState():
                self.set_state(operation)
            case Need(actor_id=actor_id, name=name, delta=delta):
                before, after = clamp_need(self.state, self.pack, actor_id, name, delta)
                if before != after:
                    self.writer.emit(
                        "needs_changed",
                        json_object(
                            {
                                "resident_id": actor_id,
                                "changes": [{"need_id": name, "before": before, "after": after}],
                                "causes": [self.rule_id],
                            }
                        ),
                        action=self.action,
                    )


def extend_delta(action: ActiveAction, changes: Iterable[StateDelta]) -> None:
    merged = {entry.path: entry for entry in action.state_delta}
    for entry in changes:
        previous = merged.get(entry.path)
        before = entry.before if previous is None else previous.before
        if before == entry.after:
            merged.pop(entry.path, None)
        else:
            merged[entry.path] = StateDelta(path=entry.path, before=before, after=entry.after)
    action.state_delta[:] = merged.values()


def branch_delta(before: WorldState, after: WorldState, actor_id: str) -> list[StateDelta]:
    def values(state: WorldState) -> dict[str, str | int | None]:
        fields: dict[str, str | int | None] = {
            f"/residents/{actor_id}/needs/{name}": value
            for name, value in state.needs[actor_id].items()
        }
        for entity in state.entities.values():
            prefix = f"/entities/{entity.entity_id}"
            fields.update(transfer_state(entity))
            for name, component in cast(Table, entity.components).items():
                for field, value in component.items():
                    if type(value) is int:
                        fields[f"{prefix}/components/{name}/{field}"] = value
        return fields

    left, right = values(before), values(after)
    return [
        StateDelta(path=key, before=left.get(key), after=right.get(key))
        for key in sorted(left.keys() | right.keys())
        if left.get(key) != right.get(key)
    ]
