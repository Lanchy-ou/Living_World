"""Project verified v2 observations to P2 metrics and evaluation §3.6 intervals."""

from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from living_island.analysis.compare import RunSummary, death_categories, summarize_run
from living_island.analysis.data import RunData
from living_island.analysis.metrics import RunMetrics, compute_run, rate
from living_island.contract.replay import DisplayFrame
from living_island.events import WorldEvent
from living_island.sim.equivalence.projection import Frame
from living_island.sim.v2.compat.bridge import visible_result
from living_island.world import protocol as legacy
from living_island.world.v2 import protocol as v2

from ..receipts import Evidence
from .observations import Interval, Opening, Start


class _Endpoint(BaseModel):
    id: str


def _frame(frame: Frame, opening: Opening) -> DisplayFrame:
    # Only the P2 physical view is projected. Action occupancy comes from the WAP journal.
    return DisplayFrame.model_validate(
        {
            "tick": frame.tick,
            "residents": [
                {**r.model_dump(exclude={"canteen_id"}), "active_action": None}
                for r in frame.residents
            ],
            "fruit_trees": [
                {**t.model_dump(), "position": opening.tree_positions[t.id].model_dump()}
                for t in frame.trees
            ],
            "ground_fruit": [g.model_dump() for g in frame.ground_fruit],
            "ground_canteen": (
                {
                    "position": frame.canteen.ground_position.model_dump(),
                    "servings": frame.canteen.servings,
                }
                if frame.canteen.ground_position
                else None
            ),
            "corpses": [c.model_dump(exclude={"death_tick"}) for c in frame.corpses],
            "event_range": {"first_index": 0, "count": 0},
        }
    )


def _event(
    event: v2.WorldEvent, kind: str, payload: object, binding: Start | None = None
) -> WorldEvent:
    values = event.model_dump()
    values.update(schema_version="0.1", type=kind, payload=payload)
    if binding:
        values["intent_id"] = binding.intent.intent_id
        if isinstance(binding.intent.target, legacy.ResidentTarget):
            values["target_id"] = binding.intent.target.id
    return WorldEvent.model_validate(values)


def _events(
    row: Interval, prior: Frame, opening: Opening, issued: dict[str, Start]
) -> Iterator[WorldEvent]:
    outcomes = {action.intent_id: action for action in row.outcomes}
    for event in row.events:
        p = event.payload
        if event.type in {"exploration_updated", "resident_moved", "resident_died"}:
            yield _event(event, event.type, p)
        if event.intent_id is None:
            continue
        start = issued[event.intent_id]
        if (
            event.type == "store_count_changed"
            and p["archetype_id"] == "fruit"
            and start.verb == "gather"
        ):
            yield _event(
                event,
                "fruit_gathered",
                {
                    "tree_id": p["entity_id"],
                    "quantity": 1,
                    "stock_before": p["before"],
                    "stock_after": p["after"],
                },
                start,
            )
        if event.type == "item_transferred" and p["via"] in ("give", "pick_up"):
            item = p["archetype_id"]
            transfer = {
                "item_type": item,
                "quantity": p["quantity"],
                "canteen_id": p["item_id"] if item == "canteen" else None,
            }
            if p["via"] == "give":
                yield _event(
                    event,
                    "item_given",
                    {
                        **transfer,
                        "from_id": event.actor_id,
                        "to_id": _Endpoint.model_validate(p["to"]).id,
                    },
                    start,
                )
            else:
                x, y = map(int, _Endpoint.model_validate(p["from"]).id.split(","))
                yield _event(
                    event,
                    "item_picked_up",
                    {
                        **transfer,
                        "resident_id": event.actor_id,
                        "position": {"x": x, "y": y},
                    },
                    start,
                )
        if event.type not in {"act_settled", "action_failed", "action_succeeded"}:
            continue
        outcome = outcomes[event.intent_id]
        actor = outcome.actor_id
        translated = visible_result(
            start.intent,
            outcome.tick_started,
            outcome.tick_finished,
            outcome.visible_feedback,
            row.speech.get(actor),
        )
        if translated is None:
            continue
        action = start.intent.action_type
        if translated.status == "failure":
            yield _event(
                event,
                "action_failed",
                {"action_type": action, "failure_code": translated.failure_code},
                start,
            )
            continue
        yield _event(event, "action_succeeded", {"action_type": action, "result_code": "OK"}, start)
        if action == "drink" and isinstance(start.intent.parameters, legacy.DrinkParameters):
            hydration = next(
                d for d in outcome.state_delta if d.path == f"/residents/{actor}/needs/hydration"
            )
            yield _event(
                event,
                "water_drank",
                {
                    "source": start.intent.parameters.source,
                    "servings": 1,
                    "hydration_before": hydration.before,
                    "hydration_after": hydration.after,
                    "canteen_servings_after": next(
                        r.canteen_servings for r in row.frame.residents if r.id == actor
                    ),
                },
                start,
            )
        elif action == "fill_canteen":
            yield _event(
                event,
                "canteen_filled",
                {
                    "canteen_id": opening.canteen,
                    "servings_before": prior.canteen.servings,
                    "servings_after": row.frame.canteen.servings,
                },
                start,
            )


def action_class(start: Start) -> str:
    match start.verb:
        case "rest" | "sleep" | "eat" | "drink" | "fill":
            return "survival"
        case "gather":
            return "survival" if start.item == "fruit_tree" else "crafting"
        case "pick_up" | "drop":
            return "survival" if start.item in {"fruit", "canteen", "clay_pot"} else "crafting"
        case "combine" | "strike" | "cut" | "light" | "build" | "contribute":
            return "crafting"
        case "move_to" | "inspect":
            return "exploring"
        case "give":
            return "social"
        case "wait":
            return "social" if start.utterance else "idle"
    raise ValueError(f"unmapped time-use verb {start.verb}")


def _travel(move: Start, following: Start, springs: set[tuple[int, int]]) -> bool:
    if action_class(following) != "survival" or move.target != following.position:
        return False
    pos = following.position
    params = following.intent.parameters
    if following.verb == "fill" or (
        isinstance(params, legacy.DrinkParameters) and params.source == "spring"
    ):
        return any(abs(x - pos.x) + abs(y - pos.y) == 1 for x, y in springs)
    if following.verb in {"gather", "pick_up", "drop"}:
        target = following.target
        if target is None:
            return False
        distance = abs(pos.x - target.x) + abs(pos.y - target.y)
        return distance == 1 if following.verb == "gather" else distance <= 1
    return True


def time_use(opening: Opening, rows: list[Interval]) -> dict[str, list[dict[str, Any]]]:
    springs = {
        (x, y) for y, line in enumerate(opening.map_rows) for x, c in enumerate(line) if c == "S"
    }
    classes = {}
    following: dict[str, Start | None] = {}
    for row in reversed(rows):
        for actor, start in row.starts.items():
            kind = action_class(start)
            after = following.get(actor)
            if start.verb == "move_to" and after and _travel(start, after, springs):
                kind = "survival"
            classes[start.intent_id] = kind
            following[actor] = start if row.awareness[actor] == "awake" else None
    day_ticks = opening.limits.day_ticks
    days = {
        r.id: [Counter[str]() for _ in range(0, len(rows), day_ticks)]
        for r in opening.frame.residents
    }
    for index, row in enumerate(rows):
        paid: dict[str, set[str]] = defaultdict(set)
        for event in row.events:
            if event.actor_id is None or event.intent_id is None:
                continue
            if event.type in {
                "action_started",
                "action_progressed",
                "act_settled",
                "action_succeeded",
                "action_failed",
            } or (event.type == "action_stopped" and event.payload["by"] == "world"):
                paid[event.actor_id].add(event.intent_id)
        day = index // day_ticks
        opening_frame = opening.frame if index == 0 else rows[index - 1].frame
        for resident in opening_frame.residents:
            if resident.alive:
                days[resident.id][day]["living"] += 1
        for actor, awareness in row.awareness.items():
            counts = days[actor][day]
            if awareness == "awake":
                counts["awake"] += 1
                if len(paid[actor]) != 1:
                    raise ValueError(f"tick {index}, {actor}: expected one paid awake attempt")
                (intent_id,) = paid[actor]
                counts[classes[intent_id]] += 1
            else:
                counts[awareness] += 1
        for event in row.events:
            if event.type == "resident_fainted" and event.actor_id is not None:
                days[event.actor_id][day]["faints"] += 1
    return {
        actor: [_day(index + 1, counts) for index, counts in enumerate(entries)]
        for actor, entries in days.items()
    }


def _day(day: int, counts: Counter[str]) -> dict[str, Any]:
    classes = {key: counts[key] for key in ("survival", "crafting", "exploring", "social", "idle")}
    awake = counts["awake"]
    if (
        sum(classes.values()) != awake
        or awake + counts["asleep"] + counts["unconscious"] != counts["living"]
    ):
        raise ValueError("living interval counts do not reconcile")
    spare = awake - classes["survival"]
    return {
        "day": day,
        **classes,
        "living": counts["living"],
        "awake": awake,
        "asleep": counts["asleep"],
        "unconscious": counts["unconscious"],
        "faints": counts["faints"],
        "fallback": 0,
        "non_survival": spare,
        "non_survival_fraction": asdict(rate(spare, awake)),
        "survival_fraction": asdict(rate(classes["survival"], awake)),
    }


@dataclass
class Measurement:
    metrics: RunMetrics
    summary: RunSummary
    days: dict[str, list[dict[str, Any]]]


def measure(directory: Path, evidence: Evidence, seed: int) -> Measurement:
    def read(key: str) -> bytes:
        path = directory / "observations" / f"{key}.json"
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != evidence.observer[key]:
            raise ValueError(f"{path}: observation digest differs")
        return raw

    opening = Opening.model_validate_json(read("opening"))
    rows = [Interval.model_validate_json(read(str(i))) for i in range(evidence.final_tick)]
    frames = [_frame(opening.frame, opening)]
    events = [
        _event(e, e.type, e.payload) for e in opening.events if e.type == "exploration_updated"
    ]
    records = []
    prior = opening.frame
    issued: dict[str, Start] = {}
    for row in rows:
        frames.append(_frame(row.frame, opening))
        issued.update((s.intent_id, s) for s in row.starts.values())
        events.extend(_events(row, prior, opening, issued))
        records.extend(row.decisions)
        prior = row.frame
    data = RunData(evidence.run_id, frames, events, records, opening.map_rows, opening.limits)
    run = compute_run(data)
    summary = summarize_run(directory.name, seed, True, run, death_categories(data, run))
    return Measurement(run, summary, time_use(opening, rows))
