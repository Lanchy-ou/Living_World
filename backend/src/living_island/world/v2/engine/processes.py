"""Contributions and the phase 4b snapshot of open processes."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ..protocol import StateDelta
from .effects import Create, Ledger, Operands, Refused, extend_delta
from .items import tile_of
from .kernel import distance
from .state import ActiveAction, Contribute, Entity, Inside, OnTile, Part
from .world_rules import RuleSchedule, apply, eligible, run

if TYPE_CHECKING:
    from ..rules import Rule
    from .settle import AppliedBranch
    from .tick import TickContext


def in_reach(ctx: TickContext, actor_id: str, subject: Entity) -> bool:
    return distance(ctx.state.residents[actor_id].position, tile_of(ctx.state, subject.place)) <= 1


def contribute(
    ctx: TickContext, action: ActiveAction, command: Contribute, schedule: RuleSchedule
) -> None:
    """Count one unit if a completion rule can use the current contents."""
    subject = ctx.state.entities.get(command.process_id)
    actor_id = action.intent.actor_id
    if subject is None or not in_reach(ctx, actor_id, subject):
        return
    if not any(
        eligible(ctx, subject, rule) is not None
        for rule in schedule.processes.get(subject.archetype_id, ())
    ):
        return
    progress = subject.components["process"]
    before = progress["work_done"]
    progress["work_done"] = before + 1
    work = ctx.record_process_work(
        subject.entity_id,
        before=before,
        after=before + 1,
        required=progress["work_required"],
    )
    work.contributors.add(actor_id)
    extend_delta(
        action,
        [
            StateDelta(
                path=f"/entities/{subject.entity_id}/components/process/work_done",
                before=before,
                after=before + 1,
            )
        ],
    )
    ctx.writer.emit(
        "process_progressed",
        {"process_id": subject.entity_id, "work_done": before + 1, "contributor_id": actor_id},
        action=action,
    )


def world_rules(ctx: TickContext, schedule: RuleSchedule) -> None:
    run(ctx, schedule)


def finish_processes(ctx: TickContext, schedule: RuleSchedule) -> None:
    """Check each subject present after 4a exactly once in entity ID order."""
    state = ctx.state
    open_ids = sorted(
        key for key, entity in state.entities.items() if "process" in entity.components
    )
    for key in open_ids:
        subject = state.entities.get(key)
        if subject is None:
            continue
        progress = subject.components["process"]
        if progress["work_done"] < progress["work_required"]:
            continue
        for entry in schedule.processes.get(subject.archetype_id, ()):
            slots = eligible(ctx, subject, entry)
            if slots is None:
                continue
            contributors = [
                action
                for actor_id, action in sorted(state.active_actions.items())
                if finishes_with(action, key) and in_reach(ctx, actor_id, subject)
            ]
            if apply(ctx, subject, entry, slots, process_id=key):
                for action in contributors:
                    ctx.record_result(action)
            break


def finishes_with(action: ActiveAction, process_id: str) -> bool:
    match action.command:
        case Contribute(process_id=subject):
            return subject == process_id and action.pending_failure is None
        case _:
            return False


def keep_progress(
    ctx: TickContext,
    action: ActiveAction,
    rule: Rule,
    archetype: str,
    groups: tuple[tuple[Part, ...], ...],
) -> AppliedBranch | None:
    """Place the interrupted work and transfer its inputs as one branch."""
    from .settle import AppliedBranch

    provisional = replace(action, event_ids=[])
    operands = Operands(ctx.state, ctx.pack, {}, action)
    ledger = Ledger(ctx, provisional, rule, operands)
    place = OnTile(ctx.state.residents[action.intent.actor_id].position)
    material: str | None = ctx.pack.source.data["archetype"][archetype].get("material")
    process = operands.prototype(archetype, material, place, 1)
    process.components["process"]["work_done"] = action.elapsed_ticks
    try:
        ledger.create(Create(process, None, None))
        destination = Inside(ledger.outputs[0].entity_id)
        for group in groups[len(rule.data["instruments"]) :]:
            for part in group:
                entity = ledger.state.entities[part.entity_id]
                ledger.move(entity, entity.place, destination)
    except Refused:
        return None
    merged = ledger.publish(ctx, action, provisional)
    return None if merged is None else AppliedBranch((), merged)
