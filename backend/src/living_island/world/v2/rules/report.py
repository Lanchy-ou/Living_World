"""Deterministic coverage, overlap and two-phase reachability proofs."""

from itertools import permutations
from operator import eq, ge, gt, le, lt, ne
from typing import Any

from .catalog import Catalog
from .rule import covered_roles, specificity
from .schema import Pair, Table, ValidationReport

OPERATORS = {"==": eq, "!=": ne, ">": gt, ">=": ge, "<": lt, "<=": le}


def signature(catalog: Catalog, rule: Table) -> Table:
    roles = covered_roles(catalog, rule)
    target = rule.get("target")
    mode = rule.get("on_interrupt")
    outputs = rule["outputs"] + (mode.get("partial", []) if isinstance(mode, dict) else [])
    homogeneous = {
        output[field]
        for output in outputs
        for field in ("material_from", "archetype_from")
        if field in output
    }
    # Include the full variant domain. Distinct instances can have the same
    # archetype/material pair yet disagree on a true property.
    return {
        "target": (target.get("terrain"), roles.get("target", ())) if target else None,
        "subject": roles.get("subject"),
        **{
            key: [
                (slot["qty"], roles[f"slot:{slot['slot']}"], slot["slot"] in homogeneous)
                for slot in rule[key]
            ]
            for key in ("instruments", "inputs")
        },
    }


def compatible(left: Table, right: Table, *, subset: bool) -> bool:
    def domain(a: tuple[Any, ...], b: tuple[Any, ...]) -> bool:
        return all(v in b for v in a) if subset else any(v in b for v in a)

    def slots(a: tuple[Any, ...], b: tuple[Any, ...]) -> bool:
        qty, variants, homogeneous = a
        other_qty, other_variants, other_homogeneous = b
        if qty != other_qty or not domain(variants, other_variants):
            return False
        if subset and qty > 1 and other_homogeneous and not homogeneous:
            # A by-kind choice can combine materials of the same archetype.
            pairs = {v.pair for v in variants}
            return len(pairs) == len({arch for arch, _ in pairs})
        return True

    a, b = left["target"], right["target"]
    if (a is None) != (b is None):
        return False
    if a is not None and b is not None:
        if a[0] != b[0] or (a[0] is None and not domain(a[1], b[1])):
            return False
    if left["subject"] is not None and not domain(left["subject"], right["subject"]):
        return False

    for group in ("instruments", "inputs"):
        x, y = left[group], right[group]
        if len(x) != len(y):
            return False
        if not any(
            all(slots(a, b) for a, b in zip(x, perm, strict=True)) for perm in permutations(y)
        ):
            return False
    return True


def implies(known: Table, required: Table, catalog: Catalog, pack: Table) -> bool:
    """Certify a check only when all values holding for the premise imply it."""
    kind = required["kind"]
    if known["kind"] != kind:
        return False
    lhs = {key: val for key, val in known.items() if key != "id"}
    rhs = {key: val for key, val in required.items() if key != "id"}
    # Slot names are local to a rule and may bind different entities.
    if kind == "state" and known["of"].startswith("slot:"):
        return False
    if lhs == rhs:
        return True
    if kind in ("terrain_near", "entity_near"):
        a, b = known["distance"], required["distance"]
        if a["min"] < b["min"] or a["max"] > b["max"]:
            return False
        if kind == "terrain_near":
            return bool(known["terrain"] == required["terrain"])
        domain = catalog.match(known["where"])
        return bool(domain) and all(v in catalog.match(required["where"]) for v in domain)
    if kind not in ("need", "free_slots", "state"):
        return False
    if any(lhs.get(key) != rhs.get(key) for key in lhs.keys() - {"op", "value"}):
        return False
    bounds = pack["needs"][known["need"]] if kind == "need" else {}
    x = known["value"]
    y = required["value"]
    if isinstance(x, str):
        x = bounds[x]
    if isinstance(y, str):
        y = bounds[y]
    assert isinstance(x, int) and isinstance(y, int)
    # Comparisons are constant between their boundary values. Check one
    # representative on each side and each boundary, including domain edges.
    probes = {x - 1, x, x + 1, y - 1, y, y + 1}
    if kind == "need":
        probes |= {bounds["min"], bounds["max"]}
    accepted = [
        value
        for value in probes
        if bounds.get("min", 0) <= value <= bounds.get("max", max(probes))
        and OPERATORS[known["op"]](value, x)
    ]
    return bool(accepted) and all(OPERATORS[required["op"]](v, y) for v in accepted)


def build_report(catalog: Catalog, pack: Table, rules: dict[str, Table]) -> ValidationReport:
    coverage = {}
    signatures = {}
    for key, rule in rules.items():
        roles = covered_roles(catalog, rule)
        coverage[key] = {
            role.removeprefix("slot:"): tuple(
                sorted(
                    {variant.pair for variant in variants},
                    key=lambda pair: (pair[0], pair[1] or ""),
                )
            )
            for role, variants in sorted(roles.items())
            if role != "subject"
        }
        if "target" in rule and "terrain" in rule["target"]:
            empty: tuple[Pair, ...] = ()
            coverage[key]["target"] = empty
        signatures[key] = signature(catalog, rule)

    overlaps = []
    unreachable = set()
    for key, rule in rules.items():
        trigger: str = rule["trigger"]
        rank = (-specificity(rule), key)
        for other_key, other in rules.items():
            if other_key == key or other["trigger"] != trigger:
                continue
            other_rank = (-specificity(other), other_key)
            if (
                key < other_key
                and rank[0] == other_rank[0]
                and compatible(signatures[key], signatures[other_key], subset=False)
            ):
                overlaps.append((key, other_key))
            if not trigger.startswith("verb:"):
                continue
            verb = catalog.vocabulary.verbs[trigger.partition(":")[2]]
            # Only terrain around a stationary sleeper has a specified
            # completion invariant here. Entity proximity can change mid-work.
            if verb.get("awareness_during") != "asleep":
                continue
            if not compatible(signatures[key], signatures[other_key], subset=True):
                continue
            for index, condition in enumerate(rule["conditions"]):
                if condition["kind"] != "terrain_near" and not (
                    condition["kind"] == "terrain_at" and condition["of"] == "actor"
                ):
                    continue
                preceding = rule["conditions"][:index]
                if all(
                    any(implies(check, needed, catalog, pack) for check in preceding)
                    for needed in other["conditions"]
                ):
                    unreachable.add((key, condition["id"]))
    return ValidationReport(coverage, tuple(sorted(overlaps)), tuple(sorted(unreachable)))
