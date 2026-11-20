"""Exact matching shared by live attempts and recorded descriptors."""

from dataclasses import dataclass
from itertools import permutations

from ..rules import Rule
from ..rules.schema import Table
from .descriptors import AttemptDescriptor, Signature, SignaturePart


@dataclass(frozen=True)
class Assignment:
    instruments: tuple[int, ...]
    inputs: tuple[int, ...]


def inherited_slots(rule: Rule) -> set[str]:
    interrupt = rule.data["on_interrupt"]
    partial = interrupt.get("partial", []) if isinstance(interrupt, dict) else []
    return {
        output[key]
        for output in (*rule.data["outputs"], *partial)
        for key in ("archetype_from", "material_from")
        if key in output
    }


def target_matches(slot: Table | None, target: Signature | None) -> bool:
    if slot is None or target is None:
        return slot is None and target is None
    if "terrain" in slot:
        return target.ref_kind == "tile" and target.terrain == slot["terrain"]
    return target.matches(slot["where"])


def slot_matches(slot: Table, parts: tuple[SignaturePart, ...], uniform: set[str]) -> bool:
    return sum(part.quantity for part in parts) == slot["qty"] and parts_match(slot, parts, uniform)


def parts_match(slot: Table, parts: tuple[SignaturePart, ...], uniform: set[str]) -> bool:
    return all(part.signature.matches(slot["where"]) for part in parts) and (
        slot["slot"] not in uniform
        or len({(part.signature.archetype_id, part.signature.material_id) for part in parts}) == 1
    )


def assign(
    slots: list[Table], entries: tuple[tuple[SignaturePart, ...], ...], uniform: set[str]
) -> tuple[int, ...] | None:
    if len(slots) != len(entries):
        return None
    return next(
        (
            order
            for order in permutations(range(len(entries)))
            if all(
                slot_matches(slot, entries[index], uniform)
                for slot, index in zip(slots, order, strict=True)
            )
        ),
        None,
    )


def match_attempt(rule: Rule, attempt: AttemptDescriptor) -> Assignment | None:
    if rule.data["trigger"] != f"verb:{attempt.verb}":
        return None
    target = attempt.target
    if not target_matches(rule.data.get("target"), target):
        return None
    instruments = tuple((SignaturePart(signature, 1),) for signature in attempt.instruments)
    inputs = tuple(entry.parts for entry in attempt.inputs)
    if target is not None and any(
        part.signature.local_key == target.local_key
        for group in (*instruments, *inputs)
        for part in group
    ):
        return None
    uniform = inherited_slots(rule)
    instrument_order = assign(rule.data["instruments"], instruments, uniform)
    input_order = assign(rule.data["inputs"], inputs, uniform)
    if instrument_order is None or input_order is None:
        return None
    return Assignment(instrument_order, input_order)


def slot_signatures(
    attempt: AttemptDescriptor, rule: Rule, assignment: Assignment
) -> dict[str, tuple[Signature, ...]]:
    return {
        **{
            slot["slot"]: (attempt.instruments[index],)
            for slot, index in zip(rule.data["instruments"], assignment.instruments, strict=True)
        },
        **{
            slot["slot"]: tuple(part.signature for part in attempt.inputs[index].parts)
            for slot, index in zip(rule.data["inputs"], assignment.inputs, strict=True)
        },
    }


def specificity(rule: Rule) -> int:
    data = rule.data
    target = data.get("target", {})
    return (
        len(target.get("where", target))
        + sum(len(slot["where"]) for slot in (*data["instruments"], *data["inputs"]))
        + len(data["conditions"])
    )
