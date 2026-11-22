"""Project captured action phases through each watcher's delivery-time sight."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..protocol import (
    Coord,
    Intent,
    ItemUse,
    ObservationPhase,
    ObservedAction,
    StartTarget,
    Target,
    TileTarget,
)
from .state import ActiveAction, Give, Held, Inside, OnTile, PhaseItem, Place, WorldState

if TYPE_CHECKING:
    from .tick import TickContext


@dataclass(frozen=True)
class Phase:
    intent: Intent
    kind: ObservationPhase
    tick: int
    items: tuple[PhaseItem, ...]
    start_target: StartTarget | None
    phenomena: tuple[str, ...] = ()
    recipient_id: str | None = None
    received_items: tuple[ItemUse, ...] = ()


def capture_start(ctx: TickContext, action: ActiveAction) -> None:
    location = action.start_location
    ctx.phases.append(
        Phase(
            action.intent,
            "start",
            action.tick_started,
            () if location is None else location.items,
            action.start_target,
        )
    )


def surviving_items(
    state: WorldState, action: ActiveAction, moved: Mapping[str, str]
) -> tuple[PhaseItem, ...]:
    return tuple(
        phase_item(state, look, entity.place)
        for look in action.start_items
        if (entity := state.entities.get(moved.get(look.entity_id, look.entity_id))) is not None
    )


def capture_end(
    ctx: TickContext,
    action: ActiveAction,
    kind: ObservationPhase,
    tick: int,
    moved: Mapping[str, str],
    phenomena: list[str],
) -> None:
    location = action.stop_location if kind == "stop" else action.settle_location
    items = surviving_items(ctx.state, action, moved) if location is None else location.items
    visible = ctx.pack.source.vocabulary.phenomena
    command = action.command
    ctx.phases.append(
        Phase(
            action.intent,
            kind,
            tick,
            items,
            action.start_target,
            tuple(word for word in phenomena if visible[word]["watcher_visible"]),
            command.recipient_id if isinstance(command, Give) and kind == "settle" else None,
            action.received_items,
        )
    )


def sight_place(state: WorldState, place: Place) -> OnTile | Held | None:
    # Process workspaces expose their contents, as recorded in OQ-P3.5-EN-05.
    match place:
        case OnTile() | Held():
            return place
        case Inside(container_id):
            container = state.entities[container_id]
            return (
                sight_place(state, container.place) if "process" in container.components else None
            )
        case _:
            return None


def phase_item(state: WorldState, look: ItemUse, place: Place) -> PhaseItem:
    return PhaseItem(look, place, sight_place(state, place))


def place_visible(
    state: WorldState, place: OnTile | Held | None, watcher: str, tiles: set[int]
) -> bool:
    match place:
        case OnTile(position):
            return state.static_map.index(position) in tiles
        case Held(holder_id):
            return holder_id == watcher
        case None:
            return False


def project_target(
    state: WorldState,
    target: Target | None,
    watcher: str,
    tiles: set[int],
    entities: set[str],
    held: set[str],
) -> Target | None:
    if isinstance(target, TileTarget):
        point: Coord = target.position
        return (
            target
            if state.static_map.contains(point) and state.static_map.index(point) in tiles
            else None
        )
    if target is not None and (target.id == watcher or target.id in entities or target.id in held):
        return target
    return None


def observations(
    ctx: TickContext, watcher: str, tiles: set[int], entities: set[str], inventory: set[str]
) -> list[ObservedAction]:
    state = ctx.state
    observed = []
    for phase in ctx.phases:
        intent = phase.intent
        actor = intent.actor_id
        if actor == watcher or state.static_map.index(state.residents[actor].position) not in tiles:
            continue
        actor_hands = Held(actor)
        visible_items = [
            item.look
            for item in phase.items
            if item.place == actor_hands or place_visible(state, item.sight_place, watcher, tiles)
        ]
        held = inventory | {
            item.look.entity_id for item in phase.items if item.place == actor_hands
        }
        target = project_target(state, intent.target, watcher, tiles, entities, held)
        observed.append(
            ObservedAction(
                actor_id=actor,
                intent_id=intent.intent_id,
                tick=phase.tick,
                phase=phase.kind,
                action=intent.action,
                verb=intent.verb,
                target=target,
                start_target=phase.start_target if target is not None else None,
                received_items=list(phase.received_items) if phase.recipient_id == watcher else [],
                visible_items=visible_items,
                phenomena=list(phase.phenomena),
            )
        )
    return observed
