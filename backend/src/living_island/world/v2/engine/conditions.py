"""Conditions and unmatched comparisons over objective attempt data."""

from collections.abc import Callable, Mapping
from operator import eq, ge, gt, le, lt, ne
from typing import cast

from ..rules import Rule
from ..rules.schema import Table
from .descriptors import AttemptDescriptor, NearbyEntity, Signature
from .state import NeedSpec

COMPARE: dict[str, Callable[[int, int], bool]] = {
    "<": lt,
    "<=": le,
    "==": eq,
    "!=": ne,
    ">=": ge,
    ">": gt,
}


def within(steps: int, condition: Table) -> bool:
    bounds: dict[str, int] = condition["distance"]
    return bounds["min"] <= steps <= bounds["max"]


def nearby_match(condition: Table, nearby: tuple[NearbyEntity, ...]) -> int | None:
    def eligible(entry: NearbyEntity) -> bool:
        return within(entry.distance, condition) and entry.signature.matches(condition["where"])

    return next((i for i, entry in enumerate(nearby) if eligible(entry)), None)


def holds(
    condition: Table,
    attempt: AttemptDescriptor,
    slots: Mapping[str, tuple[Signature, ...]],
    needs: Mapping[str, NeedSpec],
) -> bool:
    context = attempt.context
    match condition["kind"]:
        case "awareness":
            return context.awareness == cast(str, condition["value"])
        case "need":
            name = condition["need"]
            stored = next(entry.value for entry in context.needs if entry.need_id == name)
            value = condition["value"]
            if value == "min":
                value = needs[name].minimum
            elif value == "max":
                value = needs[name].maximum
            return COMPARE[cast(str, condition["op"])](stored, value)
        case "free_slots":
            return COMPARE[cast(str, condition["op"])](context.free_slots, condition["value"])
        case "terrain_near":
            return any(
                entry.terrain == condition["terrain"]
                and any(within(steps, condition) for steps in entry.distances)
                for entry in context.nearby_terrain
            )
        case "entity_near":
            return nearby_match(condition, context.nearby_entities) is not None
        case "terrain_at":
            terrain = (
                context.terrain_here
                if condition["of"] == "actor"
                else cast(Signature, attempt.target).terrain
            )
            return terrain == cast(str, condition["terrain"])
        case "state":
            role = condition["of"]
            parts = (cast(Signature, attempt.target),) if role == "target" else slots[role[5:]]
            return all(
                any(
                    field.field == condition["field"]
                    and COMPARE[condition["op"]](field.value, condition["value"])
                    for field in part.state
                )
                for part in parts
            )
        case "time_phase":
            return context.time_phase == cast(str, condition["value"])
    raise AssertionError("non-verb condition in a validated verb rule")


def first_failure(
    rule: Rule,
    attempt: AttemptDescriptor,
    slots: Mapping[str, tuple[Signature, ...]],
    needs: Mapping[str, NeedSpec],
) -> str | None:
    return next(
        (
            condition["id"]
            for condition in rule.data["conditions"]
            if not holds(condition, attempt, slots, needs)
        ),
        None,
    )


def comparison_value(attempt: AttemptDescriptor, operand: str) -> int | bool | None:
    role, _, property_id = operand.partition(".")
    parts: tuple[Signature, ...]
    match role:
        case "target":
            parts = () if attempt.target is None else (attempt.target,)
        case "instrument":
            parts = attempt.instruments[:1]
        case _:
            parts = tuple(part.signature for entry in attempt.inputs[:1] for part in entry.parts)
    values = [
        next((prop.value for prop in part.properties if prop.property_id == property_id), None)
        for part in parts
    ]
    return values[0] if values and len(set(values)) == 1 else None


def unmatched_phenomena(table: Table, attempt: AttemptDescriptor) -> tuple[str, ...]:
    matched = []
    for entry in table["entries"]:
        left, op, right = entry["when"]["compare"]
        lhs = comparison_value(attempt, left) if isinstance(left, str) else left
        rhs = comparison_value(attempt, right) if isinstance(right, str) else right
        if lhs is not None and rhs is not None and COMPARE[op](lhs, rhs):
            matched.append(entry["phenomena"])
    return (
        tuple(sorted({value for row in matched for value in row}))
        if matched
        else tuple(table["default"])
    )
