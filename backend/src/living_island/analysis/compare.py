"""Run scalars, paired comparisons, death categories, pass lines (P2 experiments §4, §5).

All functions are pure. Floats appear only in the Wilson interval (§4).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .data import RunData, payload_of
from .metrics import (
    WATER_ACCESS_ORDER,
    ResidentMetrics,
    RunMetrics,
    decimal6,
    number,
    rates_of,
    signature_json,
)

WILSON_Z = 1.959964

# Run scalar -> favorable direction (§5 table); ``None`` marks a descriptive scalar.
DIRECTION: dict[str, str | None] = {
    "deaths": "lower",
    "all_alive": "higher",
    "ticks_deprived": "lower",
    "ticks_deprived_water": "lower",
    "dedicated_water_trips": "lower",
    "water_only_visits": "lower",
    "gathers_completed": "higher",
    "discovered": "higher",
    "access_drank": "higher",
    "discovery_time_capped": "lower",
    "spring_drink_time_capped": "lower",
    "movement_ticks": None,
    "given_count": None,
    "given_qty": None,
    "received_count": None,
    "received_qty": None,
    "canteen_drinks": None,
    "canteen_fills": None,
    "transfer_then_drink": None,
    "hydration_cap_waste": None,
    "slot_full_incidents": None,
    "access_found_not_drunk": None,
    "access_not_found": None,
}
S5_SCALARS = (
    "discovered",
    "discovery_time_capped",
    "access_drank",
    "access_found_not_drunk",
    "access_not_found",
    "deaths",
    "ticks_deprived_water",
)
S4_SCALARS = tuple(DIRECTION)


# ---------------------------------------------------------------------------
# Run scalars
# ---------------------------------------------------------------------------


def run_scalars(run: RunMetrics) -> dict[str, int]:
    """Every §5 run scalar, summed over residents (or per run)."""
    residents = run.residents
    capped = run.final_tick + 1
    return {
        "deaths": sum(not r.alive_at_T for r in residents),
        "all_alive": int(all(r.alive_at_T for r in residents)),
        "ticks_deprived": sum(r.ticks_deprived for r in residents),
        "ticks_deprived_water": sum(r.ticks_deprived_water for r in residents),
        "dedicated_water_trips": sum(r.dedicated_water_trips for r in residents),
        "water_only_visits": sum(r.water_only_visits for r in residents),
        "gathers_completed": sum(r.gathers_completed for r in residents),
        "discovered": sum(r.first_spring_discovery_tick is not None for r in residents),
        "access_drank": sum(r.water_access == "drank" for r in residents),
        "discovery_time_capped": sum(
            capped if r.first_spring_discovery_tick is None else r.first_spring_discovery_tick
            for r in residents
        ),
        "spring_drink_time_capped": sum(
            capped if r.first_spring_drink_tick is None else r.first_spring_drink_tick
            for r in residents
        ),
        "movement_ticks": sum(r.movement_ticks for r in residents),
        "given_count": sum(sum(r.given_count.values()) for r in residents),
        "given_qty": sum(sum(r.given_qty.values()) for r in residents),
        "received_count": sum(sum(r.received_count.values()) for r in residents),
        "received_qty": sum(sum(r.received_qty.values()) for r in residents),
        "canteen_drinks": sum(r.canteen_drinks for r in residents),
        "canteen_fills": sum(r.canteen_fills for r in residents),
        "transfer_then_drink": run.transfer_then_drink,
        "hydration_cap_waste": sum(r.hydration_cap_waste for r in residents),
        "slot_full_incidents": sum(
            r.slot_full_incidents.holding_canteen + r.slot_full_incidents.not_holding_canteen
            for r in residents
        ),
        "access_found_not_drunk": sum(r.water_access == "found_not_drunk" for r in residents),
        "access_not_found": sum(r.water_access == "not_found" for r in residents),
    }


# ---------------------------------------------------------------------------
# S1/S2 death categories (BN §5 item 5, OQ-066)
# ---------------------------------------------------------------------------


def _deprived(data: RunData, resident_id: str, tick: int) -> bool:
    before, after = data.frame_of(tick - 1, resident_id), data.frame_of(tick, resident_id)
    minimum = data.limits.min_value
    return before.alive and (after.satiety == minimum or after.hydration == minimum)


def food_ledger(data: RunData, tick: int) -> int:
    """Σ tree stocks + Σ ground fruit + Σ resident fruit (the §8.2 sum without consumption)."""
    frame = data.frames[tick]
    return (
        sum(t.stock for t in frame.fruit_trees)
        + sum(g.quantity for g in frame.ground_fruit)
        + sum(r.fruit_count for r in frame.residents)
    )


def death_category(data: RunData, resident: ResidentMetrics) -> str | None:
    """Classify a death by its final deprived run ``R``; ``None`` if the resident lived."""
    death = resident.death_tick
    if death is None:
        return None
    rid = resident.resident_id
    discovery = resident.first_spring_discovery_tick
    if discovery is None or discovery > death:
        return "not_found"
    spring_ticks = [
        e.tick
        for e in data.of_type("water_drank")
        if e.actor_id == rid and payload_of(e).source == "spring"
    ]
    if not any(discovery <= tick <= death for tick in spring_ticks):
        return "found_not_drunk"
    run: list[int] = []
    tick = death
    while tick >= 1 and _deprived(data, rid, tick):
        run.append(tick)
        tick -= 1
    if not run:
        return "unclassified"  # a death without a deprived tick cannot occur on valid runs
    minimum = data.limits.min_value
    if any(data.frame_of(k, rid).hydration == minimum for k in run):
        return "post_access_dehydration"
    if any(food_ledger(data, k) > 0 for k in run):
        return "food_access_shortfall"
    return "food_supply_shortfall"


def death_categories(data: RunData, run: RunMetrics) -> dict[str, str]:
    found: dict[str, str] = {}
    for resident in run.residents:
        category = death_category(data, resident)
        if category is not None:
            found[resident.resident_id] = category
    return found


# ---------------------------------------------------------------------------
# Wilson interval and pass lines (§4)
# ---------------------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    """Wilson score interval ``(p + z²/2n ± z·sqrt(p(1-p)/n + z²/4n²)) / (1 + z²/n)``."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    z2 = z * z
    center = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    scale = 1 + z2 / n
    return (center - margin) / scale, (center + margin) / scale


def _percent6(value: float) -> str:
    return f"{value * 100:.4f}"


def wilson_record(successes: int, n: int) -> dict[str, Any]:
    low, high = wilson_interval(successes, n)
    return {
        "successes": successes,
        "n": n,
        "p": f"{successes / n:.6f}",
        "lower_percent": _percent6(low),
        "upper_percent": _percent6(high),
    }


@dataclass(frozen=True)
class RunSummary:
    """What a comparison needs from one case; build it with ``summarize_run``."""

    case_id: str
    seed: int
    valid: bool
    final_tick: int
    scalars: dict[str, int]
    access: dict[str, str]  # resident -> water_access
    residents: tuple[ResidentMetrics, ...]
    deaths_by_holder: dict[str, int]
    death_categories: dict[str, str]
    evidence: dict[str, list[str]]
    signature: dict[str, Any]


def summarize_run(
    case_id: str, seed: int, valid: bool, run: RunMetrics, categories: dict[str, str]
) -> RunSummary:
    holder = sum(r.holder_at_death is True for r in run.residents)
    dead = sum(r.death_tick is not None for r in run.residents)
    return RunSummary(
        case_id=case_id,
        seed=seed,
        valid=valid,
        final_tick=run.final_tick,
        scalars=run_scalars(run),
        access={r.resident_id: r.water_access for r in run.residents},
        residents=run.residents,
        deaths_by_holder={"holder_at_death": holder, "nonholder_at_death": dead - holder},
        death_categories=categories,
        evidence={
            "c1": [i.failure_event_id for i in run.c1],
            "a1": [i.failure_event_id for i in run.a1],
            "a2": [f"{i.actor_id}:{i.decision_ordinal}" for i in run.a2],
        },
        signature=run.signature,
    )


def survival_line(
    summaries: Sequence[RunSummary], *, required: int = 15, n: int = 20
) -> dict[str, Any]:
    """PD-05: the technical gate on all ``n`` cases, then ``x >= required`` all-alive seeds."""
    invalid = sorted(s.case_id for s in summaries if not s.valid)
    gate = len(summaries) == n and not invalid
    x = sum(1 for s in summaries if s.valid and s.scalars["all_alive"] == 1)
    return {
        "cases": len(summaries),
        "technical_gate": "PASS" if gate else "FAIL",
        "invalid_cases": invalid,
        "all_alive_seeds": x,
        "required": required,
        "survival": "PASS" if gate and x >= required else "FAIL",
        "wilson": wilson_record(x, n),
    }


def s1_line(summaries: Sequence[RunSummary], *, n: int = 20) -> dict[str, Any]:
    """S1 (B03): all ``n`` cases valid, each with all three residents alive at ``T``."""
    invalid = sorted(s.case_id for s in summaries if not s.valid)
    dead = sorted(s.case_id for s in summaries if s.valid and s.scalars["all_alive"] != 1)
    ok = len(summaries) == n and not invalid and not dead
    return {"cases": len(summaries), "pass": ok, "invalid_cases": invalid, "not_all_alive": dead}


def s3_evidence(summaries: Sequence[RunSummary], *, n: int = 20) -> dict[str, Any]:
    """S3 (B05): each case is valid and has at least one C1, A1 or A2, with its IDs cited."""
    rows = []
    for s in sorted(summaries, key=lambda s: s.case_id):
        cited = {name: ids for name, ids in s.evidence.items() if ids}
        rows.append({"case_id": s.case_id, "valid": s.valid, "evidence": cited})
    ok = len(summaries) == n and all(r["valid"] and r["evidence"] for r in rows)
    return {"cases": len(summaries), "pass": ok, "rows": rows}


def behavior_variation(summaries: Sequence[RunSummary]) -> dict[str, Any]:
    """Diagnostic only (OQ-067): the share of valid seeds that differ from the modal signature."""
    valid = [s for s in summaries if s.valid]
    if not valid:
        return {"valid_seeds": 0, "modal_signature": None, "differing": 0, "wilson": None}
    counts = Counter(signature_json(s.signature) for s in valid)
    top = max(counts.values())
    mode = min(sig for sig, count in counts.items() if count == top)  # ties: smallest JSON
    differing = len(valid) - counts[mode]
    return {
        "valid_seeds": len(valid),
        "modal_signature": mode,
        "differing": differing,
        "differing_fraction": f"{differing / len(valid):.6f}",
        "wilson": wilson_record(differing, len(valid)),
    }


# ---------------------------------------------------------------------------
# Paired comparisons (§5)
# ---------------------------------------------------------------------------


def _median(values: list[int]) -> Fraction:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Fraction(ordered[middle])
    return Fraction(ordered[middle - 1] + ordered[middle], 2)


def _scalar_report(name: str, diffs: list[int]) -> dict[str, Any]:
    direction = DIRECTION[name]
    record: dict[str, Any] = {
        "median": number(_median(diffs)) if diffs else None,
        "min": min(diffs) if diffs else None,
        "max": max(diffs) if diffs else None,
    }
    if direction is not None:
        # d = treatment - base. For "lower is better" a negative d favors the treatment.
        sign = 1 if direction == "lower" else -1  # sign of d that favors the base arm
        record["favoring_base"] = sum(sign * d > 0 for d in diffs)
        record["favoring_treatment"] = sum(sign * d < 0 for d in diffs)
        record["tied"] = sum(d == 0 for d in diffs)
    return record


def access_transition_table(pairs: Iterable[tuple[RunSummary, RunSummary]]) -> dict[str, Any]:
    """3x3 counts of (base category, treatment category); rows and columns in fixed order."""
    index = {name: i for i, name in enumerate(WATER_ACCESS_ORDER)}
    table = [[0] * len(index) for _ in index]
    for base, treatment in pairs:
        for resident, category in base.access.items():
            table[index[category]][index[treatment.access[resident]]] += 1
    return {
        "order": list(WATER_ACCESS_ORDER),
        "rows_are": "base",
        "columns_are": "treatment",
        "counts": table,
    }


def paired_report(
    base: Mapping[int, RunSummary],
    treatment: Mapping[int, RunSummary],
    scalars: Sequence[str] = S4_SCALARS,
    *,
    expected_seeds: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Compare run-level aggregates per seed pair: ``d = treatment - base`` (never per tick)."""
    seeds = sorted(expected_seeds if expected_seeds is not None else set(base) | set(treatment))
    missing = [
        {"seed": seed, "arm": arm}
        for seed in seeds
        for arm, cases in (("base", base), ("treatment", treatment))
        if seed not in cases
    ]
    invalid = sorted(
        s.case_id
        for cases in (base, treatment)
        for seed, s in cases.items()
        if seed in seeds and not s.valid
    )
    used = [
        seed
        for seed in seeds
        if seed in base and seed in treatment and base[seed].valid and treatment[seed].valid
    ]
    dropped = [seed for seed in seeds if seed not in used]
    pairs = [(base[seed], treatment[seed]) for seed in used]
    report: dict[str, Any] = {
        "technical": "PASS" if not missing and not invalid else "FAIL",
        "invalid_cases": invalid,
        "missing_cases": missing,
        "pairs_used": len(used),
        "dropped_seeds": dropped,
        "scalars": {
            name: _scalar_report(name, [t.scalars[name] - b.scalars[name] for b, t in pairs])
            for name in scalars
        },
        "access_transition": access_transition_table(pairs),
    }
    return report


def arm_report(summaries: Sequence[RunSummary]) -> dict[str, Any]:
    """Per arm, over its valid cases: scalar totals, per-resident rates, deaths by holder."""
    valid = [s for s in summaries if s.valid]
    totals = {name: sum(s.scalars[name] for s in valid) for name in DIRECTION}
    per_resident: dict[str, Any] = {}
    ids = sorted({r.resident_id for s in valid for r in s.residents})
    for rid in ids:
        rows = [r for s in valid for r in s.residents if r.resident_id == rid]
        exposure = sum(r.exposure_ticks for r in rows)
        counts: Counter[str] = Counter()
        for row in rows:
            for name, rate in rates_of(row).items():
                counts[name] += rate.count
        per_resident[rid] = {
            "exposure_ticks": exposure,
            "rates": {
                name: {
                    "count": counts[name],
                    "exposure_ticks": exposure,
                    "decimal": None
                    if exposure == 0
                    else decimal6(Fraction(counts[name], exposure)),
                }
                for name in sorted(counts)
            },
        }
    holder = sum(s.deaths_by_holder["holder_at_death"] for s in valid)
    nonholder = sum(s.deaths_by_holder["nonholder_at_death"] for s in valid)
    return {
        "cases": len(summaries),
        "valid_cases": len(valid),
        "totals": totals,
        "per_resident": per_resident,
        "deaths_by_holder_at_death": {"holder": holder, "nonholder": nonholder},
    }
