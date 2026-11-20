"""Phase 5 metabolism, awareness transitions and need reporting inputs."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict, cast

from ..protocol import NeedBand
from .events import coord_payload, json_object
from .items import entities_at, equal_stacks, merge, transfer_endpoint
from .state import Awareness, Entity, Held, Lineage, OnTile
from .stops import resolve_stops

if TYPE_CHECKING:
    from .state import ActiveAction, AwarenessKind, NeedSpec, Resident
    from .tick import TickContext
    from .validate import EnginePack

BANDS: tuple[NeedBand, ...] = ("critical", "low", "moderate", "good", "strong")


@dataclass(frozen=True)
class Crossing:
    need_id: str
    threshold_id: str
    wakes: bool


class NeedChange(TypedDict):
    need_id: str
    before: int
    after: int


@dataclass(frozen=True)
class ProgressNeeds:
    """Opening values and rule IDs for phase 2 need effects, supplied by the tick driver."""

    before: Mapping[str, int]
    rule_ids: tuple[str, ...]


def condition_value(pack: EnginePack, need_id: str, value: int) -> int:
    spec = pack.needs[need_id]
    if pack.source.vocabulary.needs[need_id]["polarity"] == "higher_is_worse":
        return spec.maximum - value
    return value - spec.minimum


def need_band(pack: EnginePack, need_id: str, value: int) -> NeedBand:
    return BANDS[
        bisect_right(pack.needs[need_id].band_cutoffs, condition_value(pack, need_id, value))
    ]


def need_crossings(
    pack: EnginePack,
    before: Mapping[str, int],
    after: Mapping[str, int],
) -> tuple[Crossing, ...]:
    """Compare consecutive boundaries. Initial perception has no preceding tick."""
    crossings: list[Crossing] = []
    for need_id, value in sorted(before.items()):
        prior = condition_value(pack, need_id, value)
        current = condition_value(pack, need_id, after[need_id])
        crossings.extend(
            Crossing(need_id, threshold.id, threshold.wakes)
            for threshold in sorted(pack.needs[need_id].thresholds, key=lambda entry: entry.id)
            if current <= threshold.at < prior
        )
    return tuple(crossings)


def start_sleep(ctx: TickContext, action: ActiveAction, duration: int) -> None:
    """Mark a successfully started sleep in phase 2, before any completion resolves."""
    actor_id = action.intent.actor_id
    ctx.state.awareness[actor_id] = Awareness("asleep")
    ctx.writer.emit(
        "resident_fell_asleep", {"resident_id": actor_id, "duration_ticks": duration}, action=action
    )


def hearing_awake(ctx: TickContext, actor_id: str) -> bool:
    """Read awareness during phase 2, even after a phase 5 or 6 transition."""
    for event in reversed(ctx.writer.events):
        if event.actor_id != actor_id:
            continue
        if event.type == "resident_fainted":
            return True
        if event.type in {"resident_fell_asleep", "resident_woke"}:
            return False
    return ctx.state.awareness[actor_id].kind == "awake"


def sight_enabled(pack: EnginePack, awareness: AwarenessKind) -> bool:
    """Use boundary awareness, so a resident who just woke can see again."""
    return awareness == "awake" or (awareness == "asleep" and pack.sight_while_asleep)


def _adjust(needs: dict[str, int], specs: Mapping[str, NeedSpec], key: str, delta: int) -> None:
    spec = specs[key]
    needs[key] = min(spec.maximum, max(spec.minimum, needs[key] + delta))


def _metabolism(ctx: TickContext, actor_id: str, awake: bool, rates: Mapping[str, int]) -> None:
    needs, specs = ctx.state.needs[actor_id], ctx.pack.needs
    mode = "awake" if awake else "asleep"
    for key in ("satiety", "hydration"):
        if key in needs:
            _adjust(needs, specs, key, -rates.get(f"{key}_{mode}_decay_per_tick", 0))
    if "stamina" in needs:
        if awake:
            _adjust(needs, specs, "stamina", -rates.get("stamina_awake_decay_per_tick", 0))
        if ctx.activity[actor_id].tiles_traversed:
            _adjust(needs, specs, "stamina", -rates.get("stamina_move_extra_cost_per_tick", 0))
    if "health" in needs:
        food_and_water = tuple(key for key in ("satiety", "hydration") if key in needs)
        if any(needs[key] == specs[key].minimum for key in food_and_water):
            _adjust(needs, specs, "health", -rates.get("health_loss_per_tick_if_deprived", 0))
        elif not awake and all(
            needs[key] > rates.get(f"health_recovery_min_{key}", specs[key].minimum)
            for key in food_and_water
        ):
            _adjust(needs, specs, "health", rates.get("health_recovery_sleep_per_tick", 0))


def _fatigue(ctx: TickContext, actor_id: str, awake: bool, rates: Mapping[str, int]) -> bool:
    key = "mental_fatigue"
    needs, specs = ctx.state.needs[actor_id], ctx.pack.needs
    if key not in needs:
        return False
    if awake:
        inputs = ctx.state.fatigue_inputs[actor_id]
        delta = (
            rates["awake_per_tick"]
            + rates["per_utterance_heard"] * inputs.utterances_heard
            + rates["per_first_sighting"] * inputs.first_sightings
        )
    else:
        delta = -rates["recovery_per_tick_asleep"]
    _adjust(needs, specs, key, delta)
    return awake and needs[key] == specs[key].maximum


def _die(ctx: TickContext, actor: Resident) -> None:
    actor.alive = False
    state, writer = ctx.state, ctx.writer
    tile = OnTile(actor.position)
    position = coord_payload(actor.position)
    death = writer.emit(
        "resident_died",
        {"resident_id": actor.id, "position": position, "cause": "DEPRIVATION"},
        actor_id=actor.id,
    )
    corpse_id = f"corpse@{actor.id}"
    state.entities[corpse_id] = Entity(
        corpse_id,
        None,
        None,
        1,
        ctx.tick,
        None,
        tile,
        {},
        {},
        {},
        (),
        False,
        (Lineage(corpse_id, ctx.tick, 1, state.event_log_cursor),),
        corpse_resident_id=actor.id,
        death_tick=ctx.tick,
    )
    writer.emit(
        "corpse_created",
        {"corpse_id": corpse_id, "resident_id": actor.id, "position": position},
        actor_id=actor.id,
        target_id=corpse_id,
        caused_by=(death.event_id,),
    )
    held = Held(actor.id)
    for item in entities_at(state, held):
        writer.emit(
            "item_transferred",
            {
                "item_id": item.entity_id,
                "archetype_id": item.archetype_id,
                "quantity": item.quantity,
                "from": transfer_endpoint(held),
                "to": transfer_endpoint(tile),
                "via": "drop",
                "owner_before": item.owner_id,
                "owner_after": item.owner_id,
            },
            actor_id=actor.id,
            target_id=item.entity_id,
            caused_by=(death.event_id,),
        )
        survivor = next(
            (entity for entity in entities_at(state, tile) if equal_stacks(entity, item)), None
        )
        item.place = tile
        if survivor is not None:
            merge(state, item, survivor, writer)


def apply_physiology(ctx: TickContext, progress: Mapping[str, ProgressNeeds] | None = None) -> None:
    """Apply phase 5 physiology, death and drops in resident order."""
    rates = cast("Mapping[str, int]", ctx.pack.source.data["physiology"])
    for actor_id, actor in sorted(ctx.state.residents.items()):
        if not actor.alive:
            continue
        needs = ctx.state.needs[actor_id]
        during_progress = None if progress is None else progress.get(actor_id)
        before = dict(needs)
        causes = ["physiology"]
        if during_progress is not None:
            before.update(during_progress.before)
            causes.extend(during_progress.rule_ids)
        awake = ctx.state.awareness[actor_id].kind == "awake"
        _metabolism(ctx, actor_id, awake, rates)
        fainted = _fatigue(ctx, actor_id, awake, rates)
        changes = [
            {"need_id": key, "before": before[key], "after": value}
            for key, value in sorted(needs.items())
            if value != before[key]
        ]
        if changes:
            ctx.writer.emit(
                "needs_changed",
                json_object(
                    {"resident_id": actor_id, "changes": changes, "causes": sorted(causes)}
                ),
                actor_id=actor_id,
            )
        if fainted:
            ctx.state.awareness[actor_id] = Awareness(
                "unconscious", ctx.tick + rates["faint_ticks"]
            )
            ctx.writer.emit("resident_fainted", {"resident_id": actor_id}, actor_id=actor_id)
        if "health" in needs and needs["health"] == ctx.pack.needs["health"].minimum:
            _die(ctx, actor)


def boundary_crossings(
    ctx: TickContext, progress: Mapping[str, ProgressNeeds] | None = None
) -> dict[str, tuple[Crossing, ...]]:
    """Read opening values from the objective changes, before phase 6 effects."""
    opening = {} if progress is None else {key: dict(need.before) for key, need in progress.items()}
    for event in ctx.writer.events:
        if event.type != "needs_changed":
            continue
        resident_id = cast(str, event.payload["resident_id"])
        before = opening.setdefault(resident_id, {})
        for change in cast("list[NeedChange]", event.payload["changes"]):
            before.setdefault(change["need_id"], change["before"])
    return {
        actor_id: need_crossings(ctx.pack, before, ctx.state.needs[actor_id])
        for actor_id, before in opening.items()
    }


def hard_stops_and_waking(
    ctx: TickContext, progress: Mapping[str, ProgressNeeds] | None = None
) -> None:
    """Run phase 6 hard stops and wake transitions before perception."""
    waking = {
        actor_id
        for actor_id, crossings in boundary_crossings(ctx, progress).items()
        if any(crossing.wakes for crossing in crossings)
    }
    fainted = {event.actor_id for event in ctx.writer.events if event.type == "resident_fainted"}
    for actor_id, actor in sorted(ctx.state.residents.items()):
        action = ctx.state.active_actions.get(actor_id)
        awareness = ctx.state.awareness[actor_id]
        early = False
        if action is not None:
            early = resolve_stops(ctx, actor, action, actor_id in fainted, actor_id in waking)
        if actor.alive and (
            (awareness.kind == "asleep" and actor_id not in ctx.state.active_actions)
            or awareness.unconscious_until == ctx.tick
        ):
            ctx.state.awareness[actor_id] = Awareness("awake")
            ctx.writer.emit(
                "resident_woke", {"resident_id": actor_id, "early": early}, actor_id=actor_id
            )
