"""Resolve hard stops found together after physiology."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import settle
from .items import tile_of
from .kernel import distance, exhausted
from .state import Act, Contribute, Move

if TYPE_CHECKING:
    from ..protocol import HardStop
    from .state import ActiveAction, Resident
    from .tick import TickContext


def _reason(
    ctx: TickContext, actor: Resident, action: ActiveAction, fainted: bool, waking: bool
) -> HardStop | None:
    if not actor.alive:
        return "DEATH"
    if fainted:
        return "FAINTED"
    command = action.command
    rule_id = action.rule_id
    exhaustion_stops = isinstance(command, Move) or (
        isinstance(command, Act)
        and rule_id is not None
        and ctx.pack.source.rules[rule_id].data["exhaustion_stops"]
    )
    if exhaustion_stops and exhausted(ctx.state, ctx.pack, actor.id):
        return "EXHAUSTED"
    if isinstance(command, Contribute) and action.pending_failure is None:
        process = ctx.state.entities.get(command.process_id)
        if process is None or distance(actor.position, tile_of(ctx.state, process.place)) > 1:
            return "TARGET_GONE"
    if waking and ctx.state.awareness[actor.id].kind == "asleep":
        return "WOKEN"
    return None


def resolve_stops(
    ctx: TickContext, actor: Resident, action: ActiveAction, fainted: bool, waking: bool
) -> bool:
    """Stop only an unfinished action and return whether a crossing woke its actor."""
    reason = _reason(ctx, actor, action, fainted, waking)
    if reason is None:
        return False
    if isinstance(action.command, Act):
        settle.interrupt(ctx, action)
    ctx.record_result(action, world_stop=reason)
    return reason == "WOKEN"
