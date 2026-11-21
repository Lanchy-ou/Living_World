"""Schedules, contents binding, and atomic applications for world rules."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..protocol import Coord
from ..rules import Rule
from ..rules.catalog import Variant, matches
from ..rules.schema import Table
from .conditions import COMPARE, within
from .descriptors import entity_signature
from .effects import EffectOperands, Ledger, Refused
from .items import entities_at, tile_of, true_values
from .kernel import distance
from .state import Entity, Inside, InStore, OnTile, Part, Place

if TYPE_CHECKING:
    from .tick import TickContext


@dataclass(frozen=True)
class ScheduledRule:
    rule: Rule
    period: int | None
    conditions: tuple[Table, ...]
    slots: tuple[Table, ...]
    homogeneous: frozenset[str]

    @classmethod
    def from_rule(
        cls, rule: Rule, period: int | None, conditions: tuple[Table, ...]
    ) -> ScheduledRule:
        homogeneous = frozenset(
            output[key]
            for output in rule.data["outputs"]
            for key in ("archetype_from", "material_from")
            if key in output
        )
        return cls(rule, period, conditions, tuple(rule.data["inputs"]), homogeneous)


@dataclass(frozen=True)
class RuleSchedule:
    ordinary: tuple[ScheduledRule, ...] = ()
    processes: dict[str | None, tuple[ScheduledRule, ...]] = field(default_factory=dict)

    def with_rules(self, rules: Iterable[Rule]) -> RuleSchedule:
        ordinary = list(self.ordinary)
        processes = {archetype: list(entries) for archetype, entries in self.processes.items()}
        for rule in rules:
            trigger: str = rule.data["trigger"]
            kind, _, operand = trigger.partition(":")
            if kind == "verb":
                continue
            conditions: tuple[Table, ...] = tuple(rule.data["conditions"])
            if kind == "every":
                ordinary.append(ScheduledRule.from_rule(rule, int(operand), conditions))
                continue
            named = next(condition for condition in conditions if condition["id"] == operand)
            if named["kind"] == "work_complete":
                archetype: str = rule.data["subject"]["archetype"]
                predicates = tuple(c for c in conditions if c["kind"] != "work_complete")
                processes.setdefault(archetype, []).append(
                    ScheduledRule.from_rule(rule, None, predicates)
                )
            else:
                ordinary.append(ScheduledRule.from_rule(rule, None, conditions))
        return RuleSchedule(
            tuple(sorted(ordinary, key=lambda entry: entry.rule.id)),
            {
                archetype: tuple(
                    sorted(entries, key=lambda entry: (-entry.rule.specificity, entry.rule.id))
                )
                for archetype, entries in processes.items()
            },
        )


def entity_matches(ctx: TickContext, entity: Entity, predicate: Table) -> bool:
    archetype = entity.archetype_id
    return archetype is not None and matches(
        predicate,
        Variant(
            (archetype, entity.material_id),
            dict(true_values(ctx.pack, entity)),
            dict(entity.components),
        ),
    )


class ContentsSearch:
    """Search decreasing vectors, pruning prefixes that cannot cover remaining slots."""

    def __init__(self, ctx: TickContext, subject: Entity, entry: ScheduledRule) -> None:
        self.items = entities_at(ctx.state, Inside(subject.entity_id))
        self.remaining = [item.quantity for item in self.items]
        self.demands = tuple(slot["qty"] for slot in entry.slots)
        self.names = tuple(slot["slot"] for slot in entry.slots)
        self.homogeneous = entry.homogeneous
        self.masks = tuple(
            sum(
                1 << index
                for index, slot in enumerate(entry.slots)
                if entity_matches(ctx, item, slot["where"])
            )
            for item in self.items
        )
        self.visited_prefixes = 0

    def feasible(
        self, slot: int, left: int, start: int, family: tuple[str | None, str | None] | None
    ) -> bool:
        """Reject shortages across any subset of the remaining slots.

        Future homogeneous slots can only narrow these unions. Their family
        constraints are applied when allocating those slots.
        """
        demands = (left, *self.demands[slot + 1 :])
        unions = [0] * (1 << len(demands))
        for index, (count, mask) in enumerate(zip(self.remaining, self.masks, strict=True)):
            mask >>= slot
            if index < start or (family is not None and family != self.family(index)):
                mask &= ~1
            unions[mask] += count
        for subset in range(1, len(unions)):
            demand = sum(amount for i, amount in enumerate(demands) if subset & (1 << i))
            if demand > sum(count for mask, count in enumerate(unions) if subset & mask):
                return False
        return True

    def family(self, index: int) -> tuple[str | None, str | None]:
        item = self.items[index]
        return item.archetype_id, item.material_id

    def allocations(self, slot: int) -> Iterator[tuple[Part, ...]]:
        available = [
            i for i, mask in enumerate(self.masks) if mask & (1 << slot) and self.remaining[i]
        ]
        uniform = self.names[slot] in self.homogeneous
        left = self.demands[slot]
        parts: list[Part] = []
        # Explicit stack keeps dense containers independent of Python's recursion limit.
        frames: list[tuple[int, Iterator[int], tuple[str | None, str | None] | None]] = []
        cursor = 0
        family = None
        while True:
            if left == 0:
                yield tuple(parts)
            elif cursor < len(available) and self.feasible(slot, left, available[cursor], family):
                i = available[cursor]
                limit = min(left, self.remaining[i])
                if family is not None and self.family(i) != family:
                    limit = 0
                frames.append((cursor, iter(range(limit, -1, -1)), family))

            while frames:
                prefix, choices, prior_family = frames[-1]
                i = available[prefix]
                if parts and parts[-1].entity_id == self.items[i].entity_id:
                    previous = parts.pop().quantity
                    self.remaining[i] += previous
                    left += previous
                amount = next(choices, None)
                if amount is None:
                    frames.pop()
                    continue
                self.visited_prefixes += 1
                family = self.family(i) if uniform and amount else prior_family
                if amount:
                    self.remaining[i] -= amount
                    left -= amount
                    parts.append(Part(self.items[i].entity_id, amount))
                cursor = prefix + 1
                if left == 0 and not self.feasible(slot, 0, len(self.items), family):
                    continue
                break
            else:
                return

    def first(self, slot: int = 0) -> tuple[tuple[Part, ...], ...] | None:
        if slot == len(self.demands):
            return ()
        for parts in self.allocations(slot):
            tail = self.first(slot + 1)
            if tail is not None:
                return (parts, *tail)
        return None


def condition_holds(
    ctx: TickContext,
    subject: Entity,
    point: Coord,
    condition: Table,
    slots: dict[str, tuple[Part, ...]],
) -> bool:
    state = ctx.state
    match condition["kind"]:
        case "state":
            role: str = condition["of"]
            entities = (
                (subject,)
                if role == "subject"
                else tuple(state.entities[part.entity_id] for part in slots[role[5:]])
            )
            return all(
                any(
                    field.field == condition["field"]
                    and COMPARE[condition["op"]](field.value, condition["value"])
                    for field in entity_signature(
                        state, ctx.pack, entity, "", point, ctx.tick, 0
                    ).state
                )
                for entity in entities
            )
        case "terrain_at":
            terrain: str = condition["terrain"]
            return state.static_map.terrain(point) == terrain
        case "time_phase":
            clock = state.clock
            day = clock.day_start_minute <= clock.minute_at(ctx.tick) < clock.day_end_minute
            phase: str = condition["value"]
            return ("day" if day else "night") == phase
        case "entity_near":
            return any(
                within(distance(point, tile_of(state, entity.place)), condition)
                and entity_matches(ctx, entity, condition["where"])
                for entity in state.entities.values()
            )
        case "terrain_near":
            radius: int = condition["distance"]["max"]
            smap = state.static_map
            return any(
                within(abs(x - point.x) + abs(y - point.y), condition)
                and smap.rows[y][x] == condition["terrain"]
                for y in range(max(0, point.y - radius), min(len(smap.rows), point.y + radius + 1))
                for x in range(max(0, point.x - radius), min(smap.width, point.x + radius + 1))
            )
    raise AssertionError("non-world condition in a validated world rule")


def eligible(
    ctx: TickContext, subject: Entity, entry: ScheduledRule
) -> dict[str, tuple[Part, ...]] | None:
    if not entity_matches(ctx, subject, entry.rule.data["subject"]):
        return None
    if entry.slots:
        binding = ContentsSearch(ctx, subject, entry).first()
        if binding is None:
            return None
        slots: dict[str, tuple[Part, ...]] = {
            row["slot"]: parts for row, parts in zip(entry.slots, binding, strict=True)
        }
    else:
        slots = {}
    if entry.conditions:
        point = tile_of(ctx.state, subject.place)
        if not all(condition_holds(ctx, subject, point, c, slots) for c in entry.conditions):
            return None
    return slots


@dataclass(frozen=True)
class WorldOperands(EffectOperands):
    subject: Entity

    def owner(self) -> None:
        return None

    def entity(self, role: str) -> Entity:
        if role == "subject":
            return self.subject
        return self.state.entities[self.slots[role[5:]][0].entity_id]

    def place(self, raw: str) -> Place:
        match raw:
            case "subject.tile":
                return OnTile(tile_of(self.state, self.subject.place))
            case "subject.place":
                return self.subject.place
            case "subject.contents":
                return Inside(self.subject.entity_id)
            case "subject.store":
                return InStore(self.subject.entity_id)
        raise AssertionError("non-world destination in a validated world rule")


def apply(
    ctx: TickContext,
    subject: Entity,
    entry: ScheduledRule,
    slots: dict[str, tuple[Part, ...]],
    *,
    process_id: str | None = None,
) -> bool:
    rule = entry.rule
    operands = WorldOperands(ctx.state, ctx.pack, slots, subject)
    ledger = Ledger(ctx, None, rule, operands, process_id=process_id)
    operations = [operands.effect(row) for row in rule.data["effects"]]
    outputs = [operands.output(row) for row in rule.data["outputs"]]
    ledger.writer.emit(
        "world_rule_applied",
        {"rule_id": rule.id, "subject_id": subject.entity_id},
        target_id=subject.entity_id,
    )
    try:
        for name, parts in slots.items():
            ledger.consume_input(name, parts)
        for operation in (*operations, *outputs):
            ledger.apply(operation)
    except Refused:
        return False
    # Empty effects, such as a regrowth output with zero available space, emit nothing.
    return len(ledger.writer.events) > 1 and ledger.publish_world(ctx)


def run(ctx: TickContext, schedule: RuleSchedule) -> None:
    for entry in schedule.ordinary:
        subjects = sorted(
            entity.entity_id
            for entity in ctx.state.entities.values()
            if entity_matches(ctx, entity, entry.rule.data["subject"])
        )
        for subject_id in subjects:
            subject = ctx.state.entities.get(subject_id)
            if subject is None:
                continue
            if entry.period is not None:
                offsets = ctx.state.phase_offsets.get(subject_id, {})
                if ctx.tick % entry.period != offsets.get(entry.rule.id, 0):
                    continue
            slots = eligible(ctx, subject, entry)
            if slots is not None:
                apply(ctx, subject, entry, slots)
