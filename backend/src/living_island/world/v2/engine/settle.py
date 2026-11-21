"""Act lifecycle hooks for the world tick."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal, cast

from pydantic_core import to_jsonable_python

from ..protocol import (
    DescriptorValue,
    EntityTarget,
    ItemRole,
    ItemUse,
    Settlement,
    StateDelta,
    TileTarget,
)
from ..rules import Rule
from ..rules.schema import Table
from . import kernel, physiology
from .chance import chance_roll
from .conditions import first_failure, nearby_match, unmatched_phenomena
from .descriptors import (
    AttemptDescriptor,
    SignaturePart,
    describe,
    entity_signature,
    nearby_context,
)
from .effects import Ledger, Operands, Refused, branch_delta, clamp_need, extend_delta, release
from .events import json_object
from .items import inspect_view, split, still_held, tile_of
from .match import Assignment, inherited_slots, match_attempt, parts_match, slot_signatures
from .state import (
    Act,
    ActiveAction,
    Binding,
    Entity,
    Held,
    OnTile,
    Part,
    PendingSettlement,
    PhaseItem,
    PhaseLocation,
)

if TYPE_CHECKING:
    from .tick import TickContext


@dataclass(frozen=True)
class Unmatched(PendingSettlement):
    descriptor: AttemptDescriptor


@dataclass(frozen=True)
class AppliedBranch:
    outputs: tuple[Part, ...]
    merged: dict[str, str]


def outcome(
    rule: Rule | None,
    kind: Literal["applied", "chance_failed", "unmet", "unmatched"],
    at: Literal["start", "completion"],
    failed: str | None = None,
) -> PendingSettlement:
    phenomena: tuple[str, ...] = ()
    if rule is not None:
        table = rule.data["phenomena"]
        if kind == "unmet":
            values = table["unmet_by_check"].get(failed, table["unmet"])
        else:
            values = table["success" if kind == "applied" else "chance_failed"]
        phenomena = tuple(sorted(set(values)))
    return PendingSettlement(
        Settlement(
            rule_id=None if rule is None else rule.id, kind=kind, at=at, failed_check=failed
        ),
        phenomena,
    )


def look(ctx: TickContext, entity: Entity, quantity: int, role: ItemRole) -> PhaseItem:
    view = inspect_view(ctx.state, ctx.pack, entity, inspect=False)
    return PhaseItem(
        ItemUse(
            entity_id=view.entity_id,
            archetype_id=view.archetype_id,
            material_id=view.material_id,
            descriptors=view.descriptors,
            quantity=quantity,
            role=role,
        ),
        entity.place,
    )


def capture_start(
    ctx: TickContext, action: ActiveAction, groups: tuple[tuple[Part, ...], ...]
) -> None:
    actor = ctx.state.residents[action.intent.actor_id]
    kernel.start_look(ctx.state, ctx.pack, actor, action)
    phase = cast(PhaseLocation, action.start_location)
    items = []
    target = action.intent.target
    if isinstance(target, EntityTarget) and phase.target_view is not None:
        items.append(look(ctx, ctx.state.entities[target.id], 1, "target"))
    instrument_count = len(action.intent.instruments)
    for index, group in enumerate(groups):
        for part in group:
            items.append(
                look(
                    ctx,
                    ctx.state.entities[part.entity_id],
                    part.quantity,
                    "instrument" if index < instrument_count else "input",
                )
            )
    action.start_items = tuple(item.look for item in items)
    action.start_location = replace(phase, items=tuple(items))


def ordered_groups(
    action: ActiveAction,
    groups: tuple[tuple[Part, ...], ...],
    assignment: Assignment,
) -> tuple[tuple[Part, ...], ...]:
    offset = len(action.intent.instruments)
    return tuple(groups[i] for i in assignment.instruments) + tuple(
        groups[offset + i] for i in assignment.inputs
    )


def start_act(ctx: TickContext, action: ActiveAction, groups: tuple[tuple[Part, ...], ...]) -> None:
    """Choose one eligible rule and fix the work time and physical bindings."""
    command = cast(Act, action.command)
    attempt, _ = describe(ctx.state, ctx.pack, action, groups, ctx.tick)
    capture_start(ctx, action, groups)
    action.due_tick = action.tick_started + ctx.pack.timing.attempts[command.verb]
    for rule in sorted(
        (
            rule
            for rule in ctx.pack.source.rules.values()
            if rule.data["trigger"] == f"verb:{command.verb}"
        ),
        key=lambda rule: (-rule.specificity, rule.id),
    ):
        assignment = match_attempt(rule, attempt)
        if assignment is None:
            continue
        failed = first_failure(
            rule, attempt, slot_signatures(attempt, rule, assignment), ctx.pack.needs
        )
        if failed is not None:
            if action.pending_settlement is None:
                action.pending_settlement = outcome(rule, "unmet", "start", failed)
            continue

        action.rule_id = rule.id
        action.pending_settlement = None
        time = rule.data["work_ticks"]
        duration = command.params[time["param"]] if isinstance(time, dict) else time
        action.due_tick = action.tick_started + duration
        action.resolved_choices = ordered_groups(action, groups, assignment)
        break

    if action.rule_id is None and action.pending_settlement is None:
        settlement = outcome(None, "unmatched", "start").settlement
        phenomena = unmatched_phenomena(ctx.pack.source.data["unmatched"][command.verb], attempt)
        action.pending_settlement = Unmatched(settlement, phenomena, attempt)

    bindings = []
    for group in cast(tuple[tuple[Part, ...], ...], action.resolved_choices):
        for part in group:
            original = ctx.state.entities[part.entity_id]
            physical = (
                original
                if original.quantity == part.quantity
                else split(
                    ctx.state,
                    original,
                    part.quantity,
                    "reservation",
                    ctx.writer,
                    action,
                )
            )
            bindings.append(Binding(original.entity_id, physical.entity_id, part.quantity))
    action.bindings = tuple(bindings)


def record_act_started(ctx: TickContext, action: ActiveAction) -> None:
    """Emit the objective slot bindings and enter sleep only on a chosen rule."""
    state = ctx.state
    groups = cast(tuple[tuple[Part, ...], ...], action.resolved_choices)
    if action.start_location is None:
        # The generic check may fail on held-target ownership or reach after resolving the inputs.
        capture_start(ctx, action, groups)

    def part_payload(part: Part, physical_id: str) -> dict[str, str | int | None]:
        entity = state.entities[physical_id]
        return {
            "entity_id": part.entity_id,
            "physical_id": physical_id,
            "quantity": part.quantity,
            "archetype_id": entity.archetype_id,
            "material_id": entity.material_id,
        }

    rule = None if action.rule_id is None else ctx.pack.source.rules[action.rule_id]
    physical = {binding.original_id: binding.physical_id for binding in action.bindings}
    target = action.intent.target
    target_payload = None
    slots = []
    if target is not None:
        key = None
        position = None
        if isinstance(target, TileTarget):
            position = target.position
        else:
            key = target.id
            if isinstance(target, EntityTarget):
                entity = state.entities[key]
                position = tile_of(state, entity.place)
                slots.append(
                    {
                        "slot": "target" if rule is not None else None,
                        "role": "target",
                        "parts": [part_payload(Part(key, 1), key)],
                    }
                )
            else:
                position = state.residents[key].position
        target_payload = {"kind": target.kind, "id": key, "position": position}

    data = None if rule is None else rule.data
    for index, group in enumerate(groups):
        instrument = index < len(action.intent.instruments)
        name = (
            None
            if data is None
            else (
                data["instruments"][index]["slot"]
                if instrument
                else data["inputs"][index - len(action.intent.instruments)]["slot"]
            )
        )
        slots.append(
            {
                "slot": name,
                "role": "instrument" if instrument else "input",
                "parts": [
                    part_payload(part, physical.get(part.entity_id, part.entity_id))
                    for part in group
                ],
            }
        )
    ctx.writer.emit(
        "act_items",
        json_object(
            to_jsonable_python(
                {"rule_id": action.rule_id, "target": target_payload, "slots": slots}
            )
        ),
        action=action,
    )
    verb = ctx.pack.source.vocabulary.verbs[cast(Act, action.command).verb]
    if rule is not None and verb.get("awareness_during") == "asleep":
        physiology.start_sleep(ctx, action, cast(int, action.due_tick) - action.tick_started)


def physical_groups(action: ActiveAction) -> tuple[tuple[Part, ...], ...]:
    bindings = {binding.original_id: binding for binding in action.bindings}
    return tuple(
        tuple(Part(bindings[part.entity_id].physical_id, part.quantity) for part in group)
        for group in cast(tuple[tuple[Part, ...], ...], action.resolved_choices)
    )


def record_witnesses(
    ctx: TickContext,
    action: ActiveAction,
    rule: Rule,
    timing: Literal["per_tick", "completion"],
) -> None:
    entity_conditions = [row for row in rule.data["conditions"] if row["kind"] == "entity_near"]
    if not entity_conditions:
        return
    nearby = nearby_context(ctx.state, ctx.pack, action.intent.actor_id, ctx.tick)
    for condition in entity_conditions:
        index = nearby_match(condition, tuple(entry for _, entry in nearby))
        ctx.writer.emit(
            "condition_witness",
            {
                "intent_id": action.intent.intent_id,
                "condition_id": condition["id"],
                "entity_id": None if index is None else nearby[index][0],
                "tick": ctx.tick,
                "timing": timing,
            },
            action=action,
        )


def progress_act(ctx: TickContext, action: ActiveAction) -> tuple[dict[str, int], str]:
    """Advance rule effects and return opening need values and their rule ID."""
    rule = ctx.pack.source.rules[cast(str, action.rule_id)]
    actor_id = action.intent.actor_id
    if rule.data["exhaustion_stops"] and kernel.exhausted(ctx.state, ctx.pack, actor_id):
        action.pending_stop = "EXHAUSTED"
        return {}, rule.id
    opening: dict[str, int] = {}
    effects = [
        effect
        for effect in rule.data["effects"]
        if effect["op"] == "need" and effect["timing"] == "per_tick"
    ]
    for effect in effects:
        name = effect["need"]
        delta = effect["delta"]
        if delta > 0 and ctx.state.needs[actor_id][name] < ctx.pack.needs[name].maximum:
            record_witnesses(ctx, action, rule, "per_tick")
        before, after = clamp_need(ctx.state, ctx.pack, actor_id, name, delta)
        if before != after:
            opening.setdefault(name, before)
            extend_delta(
                action,
                [
                    StateDelta(
                        path=f"/residents/{actor_id}/needs/{name}", before=before, after=after
                    )
                ],
            )
    return opening, rule.id


def progress_word(action: ActiveAction) -> DescriptorValue | None:
    if (
        action.due_tick is None
        or action.pending_failure is not None
        or action.pending_settlement is not None
    ):
        return None
    required = action.due_tick - action.tick_started
    if required == 1:
        return None
    work = 3 * action.elapsed_ticks
    return "started" if work < required else "halfway" if work < 2 * required else "nearly_done"


def completion_failure(
    ctx: TickContext,
    action: ActiveAction,
    rule: Rule,
    groups: tuple[tuple[Part, ...], ...],
) -> str | None:
    state = ctx.state
    actor_id = action.intent.actor_id
    actor = state.residents[actor_id]
    verb = ctx.pack.verbs[cast(Act, action.command).verb]
    target = action.intent.target
    if isinstance(target, EntityTarget):
        entity = state.entities.get(target.id)
        if entity is None:
            return "target"
        current = entity_signature(state, ctx.pack, entity, actor_id, actor.position, ctx.tick, 0)
        if (
            (verb.must_be_held and not current.held)
            or (not current.held and not verb.min_reach <= current.distance <= verb.max_reach)
            or not current.matches(rule.data["target"]["where"])
        ):
            return "target"
    # A tile and its terrain are immutable and a resident target cannot match a rule predicate.
    uniform = inherited_slots(rule)
    ordered = (*rule.data["instruments"], *rule.data["inputs"])
    for slot, group in zip(ordered, groups, strict=True):
        if not still_held(state, actor_id, group):
            return cast(str, slot["slot"])
        parts = tuple(
            SignaturePart(
                entity_signature(
                    state,
                    ctx.pack,
                    state.entities[part.entity_id],
                    actor_id,
                    actor.position,
                    ctx.tick,
                    index,
                ),
                part.quantity,
            )
            for index, part in enumerate(group)
        )
        if not parts_match(slot, parts, uniform):
            return cast(str, slot["slot"])
    if not rule.data["conditions"]:
        return None
    attempt, _ = describe(state, ctx.pack, action, groups, ctx.tick)
    split_at = len(rule.data["instruments"])
    assignment = Assignment(tuple(range(split_at)), tuple(range(len(rule.data["inputs"]))))
    return first_failure(rule, attempt, slot_signatures(attempt, rule, assignment), ctx.pack.needs)


def apply_branch(
    ctx: TickContext,
    action: ActiveAction,
    rule: Rule,
    groups: tuple[tuple[Part, ...], ...],
    *,
    consume: bool,
    mode: Literal["applied", "chance_failed", "partial"],
    partial: list[Table] | None = None,
) -> AppliedBranch | None:
    data = rule.data
    names = [slot["slot"] for slot in (*data["instruments"], *data["inputs"])]
    slots = dict(zip(names, groups, strict=True))
    operands = Operands(ctx.state, ctx.pack, action, slots)
    ledger = Ledger(ctx, action, rule, operands)
    effects = (
        data["effects"]
        if mode == "applied"
        else data["chance_failed_effects"]
        if mode == "chance_failed"
        else []
    )
    output_rows = data["outputs"] if mode == "applied" else partial or []
    try:
        operations = [
            operands.effect(row)
            for row in effects
            if row["op"] != "need" or row["timing"] == "completion"
        ]
        outputs = [operands.output(row) for row in output_rows]
        if mode == "applied":
            # Keep witness publication provisional along with every effect event.
            provisional = replace(ctx, state=ledger.state, writer=ledger.writer)
            record_witnesses(provisional, ledger.action, rule, "completion")
        if consume:
            for slot in data["inputs"]:
                name = slot["slot"]
                ledger.returns[name] = list(slots[name])
                for part in slots[name]:
                    ledger.consume(part)
        for operation in (*operations, *outputs):
            ledger.apply(operation)
    except Refused:
        return None
    merged = ledger.publish(ctx, action)
    return None if merged is None else AppliedBranch(tuple(ledger.outputs), merged)


def release_with_delta(ctx: TickContext, action: ActiveAction) -> AppliedBranch:
    merged = {}
    if action.bindings:
        before = replace(ctx.state, entities=deepcopy(ctx.state.entities))
        merged = release(ctx.state, ctx.writer, action)
        extend_delta(action, branch_delta(before, ctx.state, action.intent.actor_id))
    return AppliedBranch((), merged)


def phase_location(ctx: TickContext, action: ActiveAction, branch: AppliedBranch) -> PhaseLocation:
    state = ctx.state
    actor_id = action.intent.actor_id
    position = state.residents[actor_id].position
    target = action.intent.target
    point = None
    if isinstance(target, TileTarget):
        point = target.position
    elif isinstance(target, EntityTarget):
        entity = state.entities.get(target.id)
        if entity is not None:
            point = tile_of(state, entity.place)
    elif target is not None:
        point = state.residents[target.id].position

    items = []
    bound = {binding.original_id: binding for binding in action.bindings}
    for item in action.start_items:
        binding = bound.get(item.entity_id)
        physical = (
            item.entity_id if binding is None or item.role == "target" else binding.physical_id
        )
        entity = state.entities.get(branch.merged.get(physical, physical))
        if entity is not None:
            items.append(PhaseItem(item, entity.place))
    for part in branch.outputs:
        entity = state.entities.get(branch.merged.get(part.entity_id, part.entity_id))
        if entity is not None and entity.place in (Held(actor_id), OnTile(position)):
            items.append(look(ctx, entity, part.quantity, "output"))
    return PhaseLocation(
        position, point, tuple(items), action.start_target if point is not None else None
    )


def complete_act(ctx: TickContext, action: ActiveAction) -> None:
    """Recheck the selected rule once, then admit only its selected branch."""
    pending = action.pending_settlement
    if pending is not None:
        action.settle_location = phase_location(ctx, action, release_with_delta(ctx, action))
        action.bindings = ()
        ctx.record_result(action)
        if isinstance(pending, Unmatched):
            event = ctx.writer.emit(
                "attempt_unmatched",
                json_object(
                    to_jsonable_python(
                        {"verb": action.intent.verb, "descriptor": pending.descriptor}
                    )
                ),
                action=action,
            )
            ctx.results[-1].event_ids.append(event.event_id)
        return

    rule = ctx.pack.source.rules[cast(str, action.rule_id)]
    groups = physical_groups(action)
    failed = completion_failure(ctx, action, rule, groups)
    if failed is None:
        chance = rule.data["success_per_mille"]
        missed = (
            chance < 1000
            and chance_roll(ctx.state.seed, ctx.tick, rule.id, action.intent.intent_id) >= chance
        )
        kind: Literal["applied", "chance_failed"] = "chance_failed" if missed else "applied"
        branch = apply_branch(
            ctx,
            action,
            rule,
            groups,
            consume=not missed or rule.data["on_chance_failed"] == "consume_inputs",
            mode=kind,
        )
        if branch is not None:
            action.pending_settlement = outcome(rule, kind, "completion")
            action.settle_location = phase_location(ctx, action, branch)
            action.bindings = ()
            ctx.record_result(action)
            return
        failed = "world_limit"

    action.pending_settlement = outcome(rule, "unmet", "completion", failed)
    action.settle_location = phase_location(ctx, action, release_with_delta(ctx, action))
    action.bindings = ()
    ctx.record_result(action)


def interrupt(ctx: TickContext, action: ActiveAction) -> None:
    """Apply admitted partial outputs, then release any remaining reservations."""
    branch = None
    if action.rule_id is not None:
        rule = ctx.pack.source.rules[action.rule_id]
        mode = rule.data["on_interrupt"]
        if isinstance(mode, dict) and "partial" in mode:
            groups = physical_groups(action)
            actor = ctx.state.residents[action.intent.actor_id]
            if actor.alive and all(still_held(ctx.state, actor.id, group) for group in groups):
                branch = apply_branch(
                    ctx, action, rule, groups, consume=True, mode="partial", partial=mode["partial"]
                )
    if branch is None:
        branch = release_with_delta(ctx, action)
    action.stop_location = phase_location(ctx, action, AppliedBranch((), branch.merged))
    action.bindings = ()
