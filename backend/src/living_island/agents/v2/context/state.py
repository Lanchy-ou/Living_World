"""Render the state replaced at each turn from the latest resident-safe inputs."""

from dataclasses import dataclass
from typing import Literal

from living_island.agents.v2.calls.guard import Part, Ref
from living_island.memory.v2.projections import ProjectedRevision
from living_island.world.v2 import protocol as wap

from .dialogue import DialogueSession
from .prefix import memory_ref

type TurnReason = Literal["start", "woke", "action_ended", "notification"]
type NotificationClass = Literal["body", "direct_speech", "nearby_speech", "discovery", "progress"]

_REASONS: dict[TurnReason, str] = {
    "start": "your first turn",
    "woke": "you woke",
    "action_ended": "your action ended",
    "notification": "you noticed something",
}
_FATIGUE: dict[wap.NeedBand, str] = {
    "critical": "mentally exhausted",
    "low": "very mentally tired",
    "moderate": "mentally tired",
    "good": "mentally rested",
    "strong": "fully mentally rested",
}
_TERRAIN: dict[wap.Terrain, str] = {
    "sea": "~",
    "beach": ".",
    "grass": ",",
    "woods": "T",
    "rock": "^",
    "spring": "S",
    "cave": "C",
    "fruit_tree": "F",
    "damp_moss": "M",
}


def need_words(need: wap.NeedView) -> str:
    if need.need_id == "mental_fatigue":
        return _FATIGUE[need.band]
    return f"{need.band} {need.need_id.replace('_', ' ')}"


def look_words(view: wap.InspectView) -> str:
    details = [word for word in (view.archetype_id, view.material_id) if word is not None]
    details.extend(f"{d.property_id} {d.value}" for d in view.descriptors)
    return f"{view.entity_id} ({', '.join(details)})" if details else view.entity_id


def _coord(position: wap.Coord) -> str:
    return f"({position.x},{position.y})"


def _entity(view: wap.EntityView) -> str:
    words = f"{view.kind} {look_words(view)} at {_coord(view.position)}"
    if view.quantity is not None:
        words += f", quantity {view.quantity}"
    if view.observable_signs:
        words += f", looks {', '.join(view.observable_signs)}"
    return words


def _sight(view: wap.Perception) -> str:
    lines = [_entity(entity) for entity in view.visible_entities]
    lines.extend(
        f"Passing sight at step {sighting.seen_at_step}: {_entity(sighting)}"
        for sighting in view.transient_sightings
    )
    for cue in view.environmental_cues:
        direction = f" {cue.direction}" if cue.direction is not None else ""
        lines.append(
            f"{cue.cue_id} at {_coord(cue.position)} ({cue.detail_level}{direction}): "
            f"{cue.physical_description}"
        )
    return "In sight: " + ("\n".join(lines) if lines else "nothing")


def _explored_map(view: wap.Perception) -> str:
    tiles = {
        (tile.position.x, tile.position.y): tile.terrain for tile in view.explored_static_tiles
    }
    own = (view.own_position.x, view.own_position.y)
    symbols = {point: _TERRAIN[terrain] for point, terrain in tiles.items()}
    symbols[own] = "@"
    columns = range(min(x for x, _ in symbols), max(x for x, _ in symbols) + 1)
    rows = range(min(y for _, y in symbols), max(y for _, y in symbols) + 1)
    grid = ["".join(symbols.get((x, y), "?") for x in columns) for y in rows]
    legend = [f"{_TERRAIN[t]} = {t.replace('_', ' ')}" for t in sorted(set(tiles.values()))]
    springs = [f"({x},{y})" for (x, y), terrain in sorted(tiles.items()) if terrain == "spring"]
    lines = [
        f"Explored map from ({columns.start},{rows.start}):",
        *grid,
        ", ".join(["@ you", "? unknown", *legend]),
        "Column x coordinates, left to right: " + " ".join(map(str, columns)),
        "Row y coordinates, top to bottom: " + " ".join(map(str, rows)),
    ]
    if springs:
        lines.append("Explored spring tiles: " + ", ".join(springs))
    return "\n".join(lines)


@dataclass(frozen=True)
class CurrentState:
    parts: tuple[Part, ...]
    pressure_at: int


def render_current_state(
    packet: wap.BoundaryDelivery,
    *,
    reasons: tuple[TurnReason, ...],
    time_of_day: str,
    mute: tuple[NotificationClass, ...] = (),
    intention: ProjectedRevision | None = None,
    dialogue: tuple[DialogueSession, ...] = (),
) -> CurrentState:
    """The coordinator supplies scheduled reasons, local clock words and action mute state."""
    view = packet.perception

    def part(name: str, words: str, version: str = "state/0.1") -> Part:
        ref = Ref(kind="current_state", id=f"{packet.delivery_id}/{name}", version=version)
        return Part("current_state", ref, words)

    body = [need_words(need) for need in view.needs if need.need_id != "mental_fatigue"]
    body.extend(need_words(need) for need in view.needs if need.need_id == "mental_fatigue")
    parts = [
        part("reasons", "Turn reasons: " + (", ".join(_REASONS[r] for r in reasons) or "none")),
        part("body", "You feel " + (", ".join(body) or "no body cues") + "."),
    ]
    pressure_at = len(parts)
    parts.append(
        part(
            "position",
            f"You are at {_coord(view.own_position)} at {time_of_day}, {view.awareness}.",
        )
    )
    items = [f"{look_words(item)}, quantity {item.quantity}" for item in view.inventory]
    parts.append(part("inventory", "Carrying: " + ("\n".join(items) or "nothing")))
    running = view.running_action
    if running is None:
        action = "No action is running. Choose an action."
    else:
        action = f"Running {running.verb or running.action}"
        if running.progress is not None:
            action += f", {running.progress}"
        muted = ", ".join(sorted(mute)) or "none"
        action += f". Continue or replace this action. Muted notifications: {muted}."
    parts.append(part("running", action))
    parts.extend(
        part(f"dialogue/{session.counterpart_id}", session.words()) for session in dialogue
    )
    if intention is None:
        parts.append(part("intention", "Current intention: none"))
    else:
        parts.append(
            Part(
                "current_state",
                memory_ref(intention.ref),
                f"Current intention {intention.ref.id}: {intention.record.text}",
            )
        )
    parts.extend((part("sight", _sight(view)), part("map", _explored_map(view), "state-map/0.2")))
    return CurrentState(tuple(parts), pressure_at)
