"""Physiology: metabolism, rest/sleep recovery, costs, deprivation and eat/drink gains.

World Rules §3 and §5.4 phases 2 and 5. Pure integer functions over one resident; no RNG and
no event IDs (see ``rulefacts`` for the calling convention). The engine (P1-04) calls
``apply_rest_sleep_gain`` in phase 2 and ``apply_metabolism`` in phase 5, with settlement of
completions (including ``eat``/``drink`` via the gain helpers) in between.

Physiology uses the action that was active during the tick, even if it completed in phase 3:
describe it with ``TickActivity``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from living_island.world.content import EffectiveConfig
from living_island.world.facts import ConditionUpdatedPayload, StaminaActionCostAppliedPayload
from living_island.world.protocol import Coord
from living_island.world.rulefacts import PendingFact
from living_island.world.state import ResidentPhysicalState

ActivityKind = Literal["other", "rest", "sleep"]


@dataclass(frozen=True)
class TickActivity:
    """What the resident's active action did during this tick.

    ``kind``: ``sleep`` recovers stamina and has no awake decay; ``rest`` recovers stamina and
    still has awake decay; anything else (including no action) is ``other``.
    ``tiles_traversed``: tiles a ``move_to`` entered this tick (the extra cost applies once).
    ``gather_completed``: a ``gather`` finished this tick (its cost applies once).
    """

    kind: ActivityKind = "other"
    tiles_traversed: int = 0
    gather_completed: bool = False

    def __post_init__(self) -> None:
        if self.tiles_traversed < 0:
            raise ValueError("tiles_traversed must be nonnegative")


def _clamp(config: EffectiveConfig, value: int) -> int:
    return max(config.needs.min_value, min(config.needs.max_value, value))


def _require_alive(resident: ResidentPhysicalState) -> None:
    if not resident.alive:
        raise ValueError(f"{resident.id} is dead; physiology applies to living residents only")


def near_cave(position: Coord, cave: Coord) -> bool:
    """On the cave tile or orthogonally next to it (never diagonal)."""
    return abs(position.x - cave.x) + abs(position.y - cave.y) <= 1


# ---------------------------------------------------------------------------
# Eat and drink gains (capped); P1-04 settlement uses these
# ---------------------------------------------------------------------------


def satiety_after_eating(config: EffectiveConfig, satiety: int) -> int:
    """Satiety after one fruit: ``+satiety_gain_per_fruit``, capped at ``max_value``."""
    return _clamp(config, satiety + config.needs.satiety_gain_per_fruit)


def hydration_after_drinking(config: EffectiveConfig, hydration: int) -> int:
    """Hydration after one serving: ``+hydration_gain_per_serving``, capped at ``max_value``."""
    return _clamp(config, hydration + config.needs.hydration_gain_per_serving)


# ---------------------------------------------------------------------------
# Phase 2: rest / sleep recovery
# ---------------------------------------------------------------------------


def apply_rest_sleep_gain(
    config: EffectiveConfig,
    resident: ResidentPhysicalState,
    kind: ActivityKind,
    resident_near_cave: bool,
) -> ResidentPhysicalState:
    """Phase-2 stamina recovery with clamping; ``other`` changes nothing.

    ``rest`` gains ``stamina_rest_gain_per_tick``; ``sleep`` gains ``stamina_sleep_gain_per_tick``
    plus ``stamina_sleep_cave_bonus_per_tick`` when on or orthogonally next to the cave.
    """
    _require_alive(resident)
    n = config.needs
    gain = 0
    if kind == "rest":
        gain = n.stamina_rest_gain_per_tick
    elif kind == "sleep":
        gain = n.stamina_sleep_gain_per_tick
        if resident_near_cave:
            gain += n.stamina_sleep_cave_bonus_per_tick
    new = resident.model_copy(deep=True)
    new.stamina = _clamp(config, resident.stamina + gain)
    return new


# ---------------------------------------------------------------------------
# Phase 5: metabolism, costs, deprivation and sleep recovery of health
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetabolismResult:
    resident: ResidentPhysicalState  # new object
    cost_facts: list[PendingFact]  # ``stamina_action_cost_applied`` (move, then gather)


def apply_metabolism(
    config: EffectiveConfig, resident: ResidentPhysicalState, activity: TickActivity
) -> MetabolismResult:
    """Phase-5 physiology for one living resident, every completed tick.

    * satiety and hydration lose their per-tick decay, also during rest and sleep, clamped;
    * stamina loses awake decay unless sleeping, the movement extra once if at least one tile
      was traversed, and the gather cost once if a gather completed (the sequential clamps equal
      one clamp of the total);
    * health loses ``health_loss_per_tick_if_deprived`` once if satiety **or** hydration is at
      the minimum after metabolism; otherwise a sleeping resident gains
      ``health_recovery_sleep_per_tick`` while both satiety and hydration are above their
      recovery thresholds.
    """
    _require_alive(resident)
    n = config.needs
    new = resident.model_copy(deep=True)
    new.satiety = _clamp(config, resident.satiety - n.satiety_decay_per_tick)
    new.hydration = _clamp(config, resident.hydration - n.hydration_decay_per_tick)

    stamina = resident.stamina
    cost_facts: list[PendingFact] = []
    if activity.kind != "sleep":
        stamina -= n.stamina_awake_decay_per_tick
    if activity.tiles_traversed >= 1:
        stamina -= n.stamina_move_extra_cost_per_tick
        if n.stamina_move_extra_cost_per_tick > 0:
            cost_facts.append(_cost_fact(resident.id, n.stamina_move_extra_cost_per_tick, "move"))
    if activity.gather_completed:
        stamina -= n.stamina_gather_cost_per_completion
        if n.stamina_gather_cost_per_completion > 0:
            cost_facts.append(
                _cost_fact(resident.id, n.stamina_gather_cost_per_completion, "gather")
            )
    new.stamina = _clamp(config, stamina)

    if new.satiety == n.min_value or new.hydration == n.min_value:
        new.health = _clamp(config, resident.health - n.health_loss_per_tick_if_deprived)
    elif (
        activity.kind == "sleep"
        and new.satiety > n.health_recovery_min_satiety
        and new.hydration > n.health_recovery_min_hydration
    ):
        new.health = _clamp(config, resident.health + n.health_recovery_sleep_per_tick)
    return MetabolismResult(new, cost_facts)


def _cost_fact(resident_id: str, amount: int, reason: Literal["gather", "move"]) -> PendingFact:
    return PendingFact(
        type="stamina_action_cost_applied",
        actor_id=resident_id,
        target_id=None,
        payload=StaminaActionCostAppliedPayload(amount=amount, reason=reason),
    )


def is_dead(config: EffectiveConfig, resident: ResidentPhysicalState) -> bool:
    """A living resident whose health has reached the minimum must die this tick."""
    return resident.alive and resident.health <= config.needs.min_value


def condition_fact(
    before: ResidentPhysicalState, after: ResidentPhysicalState
) -> PendingFact | None:
    """One combined ``condition_updated`` for the tick, or ``None`` if nothing changed."""
    if before.id != after.id:
        raise ValueError("before and after must be the same resident")
    fields = ("satiety", "hydration", "stamina", "health")
    if all(getattr(before, f) == getattr(after, f) for f in fields):
        return None
    return PendingFact(
        type="condition_updated",
        actor_id=before.id,
        target_id=None,
        payload=ConditionUpdatedPayload(
            resident_id=before.id,
            satiety_before=before.satiety,
            satiety_after=after.satiety,
            hydration_before=before.hydration,
            hydration_after=after.hydration,
            stamina_before=before.stamina,
            stamina_after=after.stamina,
            health_before=before.health,
            health_after=after.health,
        ),
    )


# ---------------------------------------------------------------------------
# One-call composition for a tick with no settlement in between
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TickPhysiology:
    resident: ResidentPhysicalState
    facts: list[PendingFact]  # cost facts, then the combined ``condition_updated``


def step_physiology(
    config: EffectiveConfig,
    resident: ResidentPhysicalState,
    activity: TickActivity,
    resident_near_cave: bool,
) -> TickPhysiology:
    """Phase 2 then phase 5 for a tick whose completions change no needs (tests, vectors).

    The combined ``condition_updated`` compares the values before phase 2 with those after
    phase 5. The engine, which settles completions in between, composes the phase functions
    itself and builds the same fact with ``condition_fact``.
    """
    gained = apply_rest_sleep_gain(config, resident, activity.kind, resident_near_cave)
    result = apply_metabolism(config, gained, activity)
    facts = list(result.cost_facts)
    condition = condition_fact(resident, result.resident)
    if condition is not None:
        facts.append(condition)
    return TickPhysiology(result.resident, facts)
