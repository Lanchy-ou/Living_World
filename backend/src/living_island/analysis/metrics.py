"""Per-resident and per-run metrics (P2 experiments §3). Pure functions over ``RunData``.

Every record is a frozen dataclass (JSON-ready through ``dataclasses.asdict``). A missing event
gives ``None``, never 0; counts of nothing are 0. Rates are exact fractions plus a 6-decimal
string, never floats.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from .canon import canonical_bytes_of_data
from .data import RunData, payload_of

WATER_ACCESS_ORDER = ("drank", "found_not_drunk", "not_found")
SIGNATURE_LAST_TICK = 144  # §3.2 behavioral variation: records with tick <= 144


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------


def decimal6(value: Fraction) -> str:
    """Round half away from zero to 6 decimals, with integer arithmetic only."""
    sign = "-" if value < 0 else ""
    scaled = (abs(value.numerator) * 2_000_000 + value.denominator) // (2 * value.denominator)
    return f"{sign}{scaled // 1_000_000}.{scaled % 1_000_000:06d}"


def number(value: Fraction) -> int | dict[str, str]:
    """An integer stays an integer; any other fraction is exact plus a 6-decimal string."""
    if value.denominator == 1:
        return value.numerator
    return {"exact": f"{value.numerator}/{value.denominator}", "decimal": decimal6(value)}


@dataclass(frozen=True)
class Rate:
    """A count over exposure ticks: exact fraction plus 6 decimals; null when exposure is 0."""

    count: int
    exposure_ticks: int
    decimal: str | None


def rate(count: int, exposure_ticks: int) -> Rate:
    if exposure_ticks == 0:
        return Rate(count, 0, None)
    return Rate(count, exposure_ticks, decimal6(Fraction(count, exposure_ticks)))


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotFull:
    """``INVENTORY_FULL`` incidents attributed to a resident, by canteen held at tick - 1."""

    holding_canteen: int
    not_holding_canteen: int


@dataclass(frozen=True)
class ResidentMetrics:
    resident_id: str
    first_spring_discovery_tick: int | None
    first_drink_tick: int | None
    first_spring_drink_tick: int | None
    alive_at_T: bool
    death_tick: int | None
    death_cause: str | None
    holder_at_death: bool | None
    ticks_alive: int
    exposure_ticks: int
    ticks_deprived: int
    ticks_deprived_water: int
    ticks_deprived_food: int
    water_only_visits: int
    dedicated_water_trips: int
    gathers_completed: int
    given_count: dict[str, int]
    given_qty: dict[str, int]
    received_count: dict[str, int]
    received_qty: dict[str, int]
    pickups_count: dict[str, int]
    pickups_qty: dict[str, int]
    canteen_drinks: int
    spring_drinks: int
    canteen_fills: int
    hydration_cap_waste: int
    movement_ticks: int
    slot_full_incidents: SlotFull
    water_access: str
    # Route evidence (§3.2): associations only.
    completions: dict[str, int]
    spring_adjacent_frames: int
    gathers_per_tree: dict[str, int]


@dataclass(frozen=True)
class C1Instance:
    failure_event_id: str
    match_event_id: str
    actor_id: str
    decision_ordinal: int  # of the decision whose plan holds the failed intent


@dataclass(frozen=True)
class A1Instance:
    failure_event_id: str
    actor_id: str
    failure_decision_ordinal: int
    next_decision_ordinal: int | None  # D; None for an unresolved failure


@dataclass(frozen=True)
class A2Instance:
    actor_id: str
    decision_ordinal: int
    tree_id: str
    depletion_event_id: str | None


@dataclass(frozen=True)
class RunMetrics:
    run_id: str
    final_tick: int
    residents: tuple[ResidentMetrics, ...]
    c1: tuple[C1Instance, ...]
    a1: tuple[A1Instance, ...]
    repeats: tuple[A1Instance, ...]
    unresolved: tuple[A1Instance, ...]
    a2: tuple[A2Instance, ...]
    transfer_then_drink: int
    signature: dict[str, Any] = field(default_factory=dict)

    def resident(self, resident_id: str) -> ResidentMetrics:
        return next(r for r in self.residents if r.resident_id == resident_id)


# ---------------------------------------------------------------------------
# Visits (§3.1)
# ---------------------------------------------------------------------------


def visits(data: RunData, resident_id: str) -> list[tuple[int, int]]:
    """Maximal runs of consecutive frames in which the resident is alive and spring-adjacent."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for tick in range(data.final_tick + 1):
        frame = data.frame_of(tick, resident_id)
        inside = frame.alive and data.spring_adjacent(frame.position.x, frame.position.y)
        if inside and start is None:
            start = tick
        elif not inside and start is not None:
            runs.append((start, tick - 1))
            start = None
    if start is not None:
        runs.append((start, data.final_tick))
    return runs


def completions_of(data: RunData, resident_id: str) -> list[tuple[int, str]]:
    """``(tick, action_type)`` of every ``action_succeeded`` by the resident."""
    return [
        (event.tick, payload_of(event).action_type)
        for event in data.of_type("action_succeeded")
        if event.actor_id == resident_id
    ]


def count_water_visits(
    data: RunData, resident_id: str, completions: list[tuple[int, str]]
) -> tuple[int, int]:
    """``(water_only_visits, dedicated_water_trips)``."""
    water_only = dedicated = 0
    previous_end = -1
    for first, last in visits(data, resident_id):
        inside = [kind for tick, kind in completions if first <= tick <= last]
        has_water = any(kind in ("drink", "fill_canteen") for kind in inside)
        others = any(kind not in ("drink", "fill_canteen", "move_to") for kind in inside)
        if has_water and not others:
            water_only += 1
            leg = [kind for tick, kind in completions if previous_end + 1 <= tick <= first - 1]
            if not any(kind in ("gather", "give", "pick_up") for kind in leg):
                dedicated += 1
        previous_end = last
    return water_only, dedicated


# ---------------------------------------------------------------------------
# Per resident
# ---------------------------------------------------------------------------


def water_access_of(discovery: int | None, spring_drink_ticks: list[int], end: int) -> str:
    if discovery is None:
        return "not_found"
    if any(discovery <= tick <= end for tick in spring_drink_ticks):
        return "drank"
    return "found_not_drunk"


def _sum_by_item(events: list[Any]) -> tuple[dict[str, int], dict[str, int]]:
    count: Counter[str] = Counter()
    qty: Counter[str] = Counter()
    for event in events:
        payload = payload_of(event)
        item = payload.item_type
        count[item] += 1
        qty[item] += payload.quantity
    return dict(sorted(count.items())), dict(sorted(qty.items()))


def resident_metrics(data: RunData, resident_id: str) -> ResidentMetrics:
    end = data.end(resident_id)
    final = data.final_tick
    minimum = data.limits.min_value
    gain = data.limits.hydration_gain_per_serving

    def mine(event_type: str, *, field_name: str = "actor_id") -> list[Any]:
        found = []
        for event in data.of_type(event_type):
            who = (
                event.actor_id
                if field_name == "actor_id"
                else getattr(payload_of(event), field_name)
            )
            if who == resident_id and event.tick <= end:
                found.append(event)
        return found

    discoveries = [
        event.tick
        for event in mine("exploration_updated", field_name="resident_id")
        if data.spring_indices & set(payload_of(event).newly_seen_tile_indices)
    ]
    drinks = mine("water_drank")
    spring_drink_ticks = [e.tick for e in drinks if payload_of(e).source == "spring"]
    discovery = min(discoveries) if discoveries else None
    death = data.death_event(resident_id)

    alive_ticks = deprived = deprived_water = deprived_food = exposure = 0
    for tick in range(1, final + 1):
        before, after = data.frame_of(tick - 1, resident_id), data.frame_of(tick, resident_id)
        if after.alive:
            alive_ticks += 1
        if before.alive:
            exposure += 1
            water = after.hydration == minimum
            food = after.satiety == minimum
            deprived += water or food
            deprived_water += water
            deprived_food += food

    completions = completions_of(data, resident_id)
    water_only, dedicated = count_water_visits(data, resident_id, completions)

    given_count, given_qty = _sum_by_item(mine("item_given", field_name="from_id"))
    received_count, received_qty = _sum_by_item(mine("item_given", field_name="to_id"))
    pickups_count, pickups_qty = _sum_by_item(mine("item_picked_up", field_name="resident_id"))

    held = not_held = 0
    for event in data.of_type("action_failed"):
        payload = payload_of(event)
        if payload.failure_code != "INVENTORY_FULL":
            continue
        # The actor for gather/pick_up (own room); the recipient for give, never the giver.
        owner = event.target_id if payload.action_type == "give" else event.actor_id
        if owner != resident_id or event.tick > end:
            continue
        if data.frame_of(event.tick - 1, resident_id).canteen_servings is not None:
            held += 1
        else:
            not_held += 1

    holder_at_death = (
        None
        if death is None
        else data.frame_of(death.tick - 1, resident_id).canteen_servings is not None
    )
    gathers = mine("fruit_gathered")
    per_tree = Counter(payload_of(e).tree_id for e in gathers)
    movement_ticks = len({e.tick for e in mine("resident_moved")})
    spring_frames = sum(
        1
        for tick in range(final + 1)
        if data.alive(tick, resident_id)
        and data.spring_adjacent(
            data.frame_of(tick, resident_id).position.x,
            data.frame_of(tick, resident_id).position.y,
        )
    )
    return ResidentMetrics(
        resident_id=resident_id,
        first_spring_discovery_tick=discovery,
        first_drink_tick=min((e.tick for e in drinks), default=None),
        first_spring_drink_tick=min(spring_drink_ticks, default=None),
        alive_at_T=data.alive(final, resident_id),
        death_tick=None if death is None else death.tick,
        death_cause=None if death is None else payload_of(death).cause,
        holder_at_death=holder_at_death,
        ticks_alive=alive_ticks,
        exposure_ticks=exposure,
        ticks_deprived=deprived,
        ticks_deprived_water=deprived_water,
        ticks_deprived_food=deprived_food,
        water_only_visits=water_only,
        dedicated_water_trips=dedicated,
        gathers_completed=len(gathers),
        given_count=given_count,
        given_qty=given_qty,
        received_count=received_count,
        received_qty=received_qty,
        pickups_count=pickups_count,
        pickups_qty=pickups_qty,
        canteen_drinks=sum(payload_of(e).source == "canteen" for e in drinks),
        spring_drinks=len(spring_drink_ticks),
        canteen_fills=len(mine("canteen_filled")),
        hydration_cap_waste=sum(
            payload_of(e).hydration_before + gain - payload_of(e).hydration_after for e in drinks
        ),
        movement_ticks=movement_ticks,
        slot_full_incidents=SlotFull(held, not_held),
        water_access=water_access_of(discovery, spring_drink_ticks, end),
        completions=dict(sorted(Counter(kind for _, kind in completions).items())),
        spring_adjacent_frames=spring_frames,
        gathers_per_tree=dict(sorted(per_tree.items())),
    )


def rates_of(metrics: ResidentMetrics) -> dict[str, Rate]:
    """Per-resident rates of the counted metrics over ``exposure_ticks`` (§3.0, §5)."""
    exposure = metrics.exposure_ticks
    counts: dict[str, int] = {
        "ticks_deprived": metrics.ticks_deprived,
        "ticks_deprived_water": metrics.ticks_deprived_water,
        "ticks_deprived_food": metrics.ticks_deprived_food,
        "water_only_visits": metrics.water_only_visits,
        "dedicated_water_trips": metrics.dedicated_water_trips,
        "gathers_completed": metrics.gathers_completed,
        "movement_ticks": metrics.movement_ticks,
        "given_count": sum(metrics.given_count.values()),
        "received_count": sum(metrics.received_count.values()),
        "canteen_drinks": metrics.canteen_drinks,
        "spring_drinks": metrics.spring_drinks,
        "canteen_fills": metrics.canteen_fills,
        "slot_full_incidents": (
            metrics.slot_full_incidents.holding_canteen
            + metrics.slot_full_incidents.not_holding_canteen
        ),
    }
    return {name: rate(count, exposure) for name, count in counts.items()}


# ---------------------------------------------------------------------------
# Per run: C1, A1, A2 (§3.2)
# ---------------------------------------------------------------------------


def _target(intent: Any) -> Any:
    """The intent's target (untyped: the union members differ per action type)."""
    return intent.target


def contention(data: RunData) -> list[C1Instance]:
    """C1: a ``RESOURCE_TAKEN``/``ITEM_TAKEN`` failure matched to an earlier same-tick success."""
    found: list[C1Instance] = []
    for failure in data.of_type("action_failed"):
        payload = payload_of(failure)
        if failure.intent_id is None or failure.intent_id not in data.intents:
            continue
        record, intent = data.intents[failure.intent_id]
        match: Any = None
        if payload.failure_code == "RESOURCE_TAKEN" and intent.action_type == "gather":
            tree_id = intent.target.id
            candidates = [
                e for e in data.of_type("fruit_gathered") if payload_of(e).tree_id == tree_id
            ]
        elif payload.failure_code == "ITEM_TAKEN" and intent.action_type == "pick_up":
            tile, item_type = intent.target.position, intent.parameters.item_type
            candidates = [
                e
                for e in data.of_type("item_picked_up")
                if payload_of(e).position == tile and payload_of(e).item_type == item_type
            ]
        else:
            continue
        eligible = [
            e
            for e in candidates
            if e.tick == failure.tick
            and e.seq_in_tick < failure.seq_in_tick
            and e.actor_id != failure.actor_id
        ]
        if eligible:
            match = min(eligible, key=lambda e: e.seq_in_tick)
            found.append(
                C1Instance(
                    failure.event_id, match.event_id, record.actor_id, record.decision_ordinal
                )
            )
    return found


A1_CODES: dict[str, frozenset[str] | None] = {
    "move_to": frozenset({"NO_PATH", "PATH_BLOCKED", "INVALID_TARGET"}),
    "gather": frozenset({"RESOURCE_TAKEN", "OUT_OF_REACH", "INVALID_TARGET"}),
    "pick_up": frozenset({"ITEM_TAKEN", "OUT_OF_REACH", "INVALID_TARGET"}),
    "give": None,  # any code except the excluded ones
    "talk": None,
}
A1_EXCLUDED = frozenset({"DEAD", "EXHAUSTED", "NO_ITEM"})


def _a1_candidate(action_type: str, code: str) -> bool:
    if action_type not in A1_CODES:
        return False
    allowed = A1_CODES[action_type]
    if allowed is None:
        return code not in A1_EXCLUDED
    return code in allowed


def adaptation_after_failure(
    data: RunData,
) -> tuple[list[A1Instance], list[A1Instance], list[A1Instance]]:
    """A1 (adapted), repeats and unresolved failures, each citing event IDs and ordinals."""
    a1: list[A1Instance] = []
    repeats: list[A1Instance] = []
    unresolved: list[A1Instance] = []
    for failure in data.of_type("action_failed"):
        payload = payload_of(failure)
        if failure.intent_id is None or failure.intent_id not in data.intents:
            continue
        record, intent = data.intents[failure.intent_id]
        if intent.target is None or not _a1_candidate(payload.action_type, payload.failure_code):
            continue
        actor = failure.actor_id
        following = next(
            (r for r in data.records_by_actor.get(actor or "", []) if r.tick >= failure.tick),
            None,
        )
        if following is None:
            unresolved.append(
                A1Instance(failure.event_id, actor or "", record.decision_ordinal, None)
            )
            continue
        same = any(
            other.action_type == intent.action_type and other.target == intent.target
            for other in following.plan.intents
        )
        instance = A1Instance(
            failure.event_id, actor or "", record.decision_ordinal, following.decision_ordinal
        )
        (repeats if same else a1).append(instance)
    return a1, repeats, unresolved


def adaptation_after_depletion(data: RunData, a1: list[A1Instance]) -> list[A2Instance]:
    """A2: a decision after a gather whose tree is empty and which does not target it again."""
    a1_decisions = {(i.actor_id, i.next_decision_ordinal) for i in a1}
    found: list[A2Instance] = []
    gathered = data.of_type("fruit_gathered")
    for actor, records in data.records_by_actor.items():
        by_ordinal = {r.decision_ordinal: r for r in records}
        for record in records:
            ordinal = record.decision_ordinal
            if ordinal < 1 or ordinal - 1 not in by_ordinal:
                continue
            if (actor, ordinal) in a1_decisions:
                continue
            previous = by_ordinal[ordinal - 1]
            targeted = {
                _target(i).id
                for i in record.plan.intents
                if i.target is not None and i.target.kind == "entity"
            }
            for intent in previous.plan.intents:
                if intent.action_type != "gather" or intent.target is None:
                    continue
                tree_id = _target(intent).id
                stock = next(
                    (t.stock for t in data.frames[record.tick].fruit_trees if t.id == tree_id),
                    None,
                )
                if stock != 0 or tree_id in targeted:
                    continue
                cited = [
                    e
                    for e in gathered
                    if payload_of(e).tree_id == tree_id
                    and payload_of(e).stock_after == 0
                    and e.tick <= record.tick
                ]
                depletion = max(cited, key=lambda e: (e.tick, e.seq_in_tick), default=None)
                found.append(
                    A2Instance(
                        actor, ordinal, tree_id, None if depletion is None else depletion.event_id
                    )
                )
                break  # a record is counted once
    return found


def transfer_then_drink(data: RunData) -> int:
    """Canteen gifts followed by a canteen drink of the recipient within one game day (§5)."""
    window = data.limits.day_ticks
    gifts = [e for e in data.of_type("item_given") if payload_of(e).item_type == "canteen"]
    drinks = [e for e in data.of_type("water_drank") if payload_of(e).source == "canteen"]
    counted = 0
    for gift in gifts:
        recipient = payload_of(gift).to_id
        for drink in drinks:
            if drink.actor_id != recipient:
                continue
            if not gift.tick < drink.tick <= min(gift.tick + window, data.end(recipient)):
                continue
            passed_on = any(
                other.tick > gift.tick
                and other.tick < drink.tick
                and payload_of(other).from_id == recipient
                for other in gifts
            )
            if not passed_on:
                counted += 1
                break
    return counted


def behavior_signature(data: RunData, residents: tuple[ResidentMetrics, ...]) -> dict[str, Any]:
    """The canonical diagnostic signature of one run (§3.2)."""
    by_id = {r.resident_id: r for r in residents}
    order = sorted(
        by_id,
        key=lambda rid: (
            by_id[rid].first_spring_discovery_tick is None,
            by_id[rid].first_spring_discovery_tick or 0,
            rid,
        ),
    )
    exploration: dict[str, list[tuple[int, list[int]]]] = {rid: [] for rid in data.residents}
    for event in data.of_type("exploration_updated"):
        payload = payload_of(event)
        exploration[payload.resident_id].append((event.tick, list(payload.newly_seen_tile_indices)))
    frontiers: dict[str, list[list[int]]] = {}
    for rid in data.residents:
        entries: list[list[int]] = []
        for record in data.records_by_actor.get(rid, []):
            if record.tick > SIGNATURE_LAST_TICK:
                continue
            seen = {
                index
                for tick, indices in exploration[rid]
                if tick <= record.tick
                for index in indices
            }
            for intent in record.plan.intents:
                if intent.action_type != "move_to":
                    continue
                target = _target(intent).position
                if data.tile_index(target.x, target.y) not in seen:
                    entries.append([target.x, target.y])
        frontiers[rid] = entries
    return {
        "discovery_order": order,
        "discovery_ticks": {rid: by_id[rid].first_spring_discovery_tick for rid in data.residents},
        "early_frontiers": frontiers,
        "survival": {rid: by_id[rid].alive_at_T for rid in data.residents},
    }


def signature_json(signature: dict[str, Any]) -> str:
    return canonical_bytes_of_data(signature).decode("utf-8")


def compute_run(data: RunData) -> RunMetrics:
    residents = tuple(resident_metrics(data, rid) for rid in data.residents)
    a1, repeats, unresolved = adaptation_after_failure(data)
    return RunMetrics(
        run_id=data.run_id,
        final_tick=data.final_tick,
        residents=residents,
        c1=tuple(contention(data)),
        a1=tuple(a1),
        repeats=tuple(repeats),
        unresolved=tuple(unresolved),
        a2=tuple(adaptation_after_depletion(data, a1)),
        transfer_then_drink=transfer_then_drink(data),
        signature=behavior_signature(data, residents),
    )


# ---------------------------------------------------------------------------
# Timing summaries (§3.1)
# ---------------------------------------------------------------------------


def summarize(values: list[int]) -> dict[str, Any]:
    """``n``, mean, median, min and max; the statistics are null when ``n = 0``."""
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    ordered = sorted(values)
    middle = len(ordered) // 2
    median = (
        Fraction(ordered[middle])
        if len(ordered) % 2
        else Fraction(ordered[middle - 1] + ordered[middle], 2)
    )
    return {
        "n": len(ordered),
        "mean": number(Fraction(sum(ordered), len(ordered))),
        "median": number(median),
        "min": ordered[0],
        "max": ordered[-1],
    }


def timing_summaries(residents: list[ResidentMetrics]) -> dict[str, Any]:
    """Discovery time, and discovery-to-first-spring-drink over ``drank`` residents only."""
    discovered = [
        r.first_spring_discovery_tick
        for r in residents
        if r.first_spring_discovery_tick is not None
    ]
    to_drink = [
        r.first_spring_drink_tick - r.first_spring_discovery_tick
        for r in residents
        if r.water_access == "drank"
        and r.first_spring_drink_tick is not None
        and r.first_spring_discovery_tick is not None
    ]
    split: Counter[str] = Counter()
    for r in residents:
        if r.water_access != "drank":
            split[f"{r.water_access}/{'alive' if r.alive_at_T else 'dead'}"] += 1
    return {
        "discovery": summarize(discovered),
        "not_found": sum(r.water_access == "not_found" for r in residents),
        "discovery_to_first_spring_drink": summarize(to_drink),
        "not_drank_by_survival": dict(sorted(split.items())),
    }
