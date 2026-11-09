"""Metabolism, recovery, costs, deprivation and the no-resource death vectors (WR §3, BN §1)."""

from __future__ import annotations

from typing import Any

import pytest
from world_builders import default_content, fresh_state, resident

from living_island.world.content import EffectiveConfig
from living_island.world.physiology import (
    TickActivity,
    apply_metabolism,
    apply_rest_sleep_gain,
    condition_fact,
    hydration_after_drinking,
    is_dead,
    near_cave,
    satiety_after_eating,
    step_physiology,
)
from living_island.world.protocol import Coord
from living_island.world.state import ResidentPhysicalState


def cfg() -> EffectiveConfig:
    return default_content().config


def ella(**update: Any) -> ResidentPhysicalState:
    base = resident(fresh_state(default_content()), "ella").model_copy(deep=True)
    for key, value in update.items():
        setattr(base, key, value)
    return base


def zero_costs() -> EffectiveConfig:
    c = cfg()
    needs = c.needs.model_copy(update={"satiety_decay_per_tick": 0, "hydration_decay_per_tick": 0})
    return c.model_copy(update={"needs": needs})


# ------------------------------------------------------------------ no-resource death vectors


def test_no_water_hydration_zero_at_tick_80_and_death_at_tick_222() -> None:
    """Balance notes §1: food is not limiting; 8000 hydration at 100 per tick."""
    c = cfg()
    r = ella()  # initial needs from default content
    assert (r.satiety, r.hydration, r.health) == (7500, 8000, 10000)
    hydration_zero_tick = death_tick = None
    for tick in range(1, 400):
        r = step_physiology(c, r, TickActivity(), False).resident
        if hydration_zero_tick is None and r.hydration == 0:
            hydration_zero_tick = tick
        assert r.satiety > 0  # food never limits before death
        if is_dead(c, r):
            death_tick = tick
            break
    assert hydration_zero_tick == 80
    assert death_tick == 222


def test_no_water_health_loss_starts_the_same_tick_hydration_reaches_zero() -> None:
    c = cfg()
    r = ella()
    for _ in range(79):
        r = step_physiology(c, r, TickActivity(), False).resident
    assert (r.hydration, r.health) == (100, 10000)
    r = step_physiology(c, r, TickActivity(), False).resident  # tick 80
    assert (r.hydration, r.health) == (0, 10000 - 70)


def test_no_food_death_at_tick_442_with_water_sustained() -> None:
    c = cfg()
    r = ella()
    for tick in range(1, 600):
        r = r.model_copy(update={"hydration": c.needs.max_value})  # water always available
        r = step_physiology(c, r, TickActivity(), False).resident
        if is_dead(c, r):
            assert tick == 442
            return
    raise AssertionError("never died")


# ------------------------------------------------------------------ metabolism


def test_satiety_and_hydration_decay_every_tick_including_rest_and_sleep() -> None:
    c = cfg()
    for kind in ("other", "rest", "sleep"):
        out = step_physiology(c, ella(), TickActivity(kind=kind), False).resident  # type: ignore[arg-type]
        assert out.satiety == 7500 - c.needs.satiety_decay_per_tick
        assert out.hydration == 8000 - c.needs.hydration_decay_per_tick


def test_awake_decay_applies_unless_sleeping() -> None:
    c = cfg()
    n = c.needs
    other = step_physiology(c, ella(stamina=5000), TickActivity(), False).resident
    assert other.stamina == 5000 - n.stamina_awake_decay_per_tick
    rest = step_physiology(c, ella(stamina=5000), TickActivity(kind="rest"), False).resident
    assert rest.stamina == 5000 + n.stamina_rest_gain_per_tick - n.stamina_awake_decay_per_tick


def test_final_sleep_tick_gets_sleep_recovery_and_no_awake_decay() -> None:
    c = cfg()
    n = c.needs
    r = ella(stamina=5000, health=9000)
    out = step_physiology(c, r, TickActivity(kind="sleep"), False).resident
    assert out.stamina == 5000 + n.stamina_sleep_gain_per_tick  # no awake decay
    assert out.health == 9000 + n.health_recovery_sleep_per_tick  # eligible for recovery


def test_movement_extra_cost_applies_once_for_many_tiles() -> None:
    c = cfg()
    n = c.needs
    one = step_physiology(c, ella(stamina=5000), TickActivity(tiles_traversed=1), False)
    many = step_physiology(c, ella(stamina=5000), TickActivity(tiles_traversed=8), False)
    expected = 5000 - n.stamina_awake_decay_per_tick - n.stamina_move_extra_cost_per_tick
    assert one.resident.stamina == many.resident.stamina == expected
    assert [f.payload.reason for f in many.facts if f.type == "stamina_action_cost_applied"] == [  # type: ignore[attr-defined]
        "move"
    ]


def test_no_traversal_means_no_movement_cost() -> None:
    c = cfg()
    out = step_physiology(c, ella(stamina=5000), TickActivity(tiles_traversed=0), False)
    assert out.resident.stamina == 5000 - c.needs.stamina_awake_decay_per_tick
    assert not [f for f in out.facts if f.type == "stamina_action_cost_applied"]


def test_gather_completion_cost_applies_once() -> None:
    c = cfg()
    n = c.needs
    out = step_physiology(c, ella(stamina=5000), TickActivity(gather_completed=True), False)
    assert (
        out.resident.stamina
        == 5000 - n.stamina_awake_decay_per_tick - n.stamina_gather_cost_per_completion
    )
    [cost] = [f for f in out.facts if f.type == "stamina_action_cost_applied"]
    assert (cost.payload.amount, cost.payload.reason) == (  # type: ignore[attr-defined]
        n.stamina_gather_cost_per_completion,
        "gather",
    )


def test_phase_two_gain_is_clamped_before_phase_five_decay() -> None:
    c = cfg()
    n = c.needs
    top = n.max_value - 10
    out = step_physiology(c, ella(stamina=top), TickActivity(kind="rest"), False).resident
    # gain clamps to max first, then awake decay applies: not clamp(top + gain - decay).
    assert out.stamina == n.max_value - n.stamina_awake_decay_per_tick


def test_values_clamp_at_the_minimum() -> None:
    c = cfg()
    out = step_physiology(
        c, ella(satiety=5, hydration=0, stamina=10, health=30), TickActivity(), False
    )
    r = out.resident
    assert (r.satiety, r.hydration, r.stamina) == (0, 0, 0)
    assert r.health == 0  # 30 - 70 clamps at the minimum


def test_cave_bonus_on_and_orthogonally_next_to_the_cave_but_not_diagonally() -> None:
    c = cfg()
    n = c.needs
    cave = Coord(x=13, y=32)
    cases = {
        (13, 32): True,  # on the cave
        (12, 32): True,
        (14, 32): True,
        (13, 31): True,
        (13, 33): True,  # orthogonal neighbours
        (12, 31): False,
        (14, 33): False,  # diagonals
        (15, 32): False,
        (13, 34): False,  # two away
    }
    for (x, y), expected in cases.items():
        assert near_cave(Coord(x=x, y=y), cave) is expected, (x, y)
        r = ella(stamina=1000, position=Coord(x=x, y=y))
        out = apply_rest_sleep_gain(c, r, "sleep", near_cave(r.position, cave))
        bonus = n.stamina_sleep_cave_bonus_per_tick if expected else 0
        assert out.stamina == 1000 + n.stamina_sleep_gain_per_tick + bonus, (x, y)


def test_cave_bonus_never_applies_to_rest() -> None:
    c = cfg()
    out = apply_rest_sleep_gain(c, ella(stamina=1000), "rest", True)
    assert out.stamina == 1000 + c.needs.stamina_rest_gain_per_tick
    assert apply_rest_sleep_gain(c, ella(stamina=1000), "other", True).stamina == 1000


# ------------------------------------------------------------------ deprivation and recovery


def test_deprivation_is_applied_once_when_both_needs_are_at_minimum() -> None:
    c = cfg()
    out = step_physiology(c, ella(satiety=0, hydration=0), TickActivity(), False).resident
    assert out.health == 10000 - c.needs.health_loss_per_tick_if_deprived
    either = step_physiology(c, ella(satiety=0), TickActivity(), False).resident
    assert either.health == out.health


def test_sleep_recovery_needs_both_needs_above_their_thresholds_and_no_deprivation() -> None:
    c = cfg()
    n = c.needs
    recovery = n.health_recovery_sleep_per_tick
    hi = n.max_value
    sleeping = TickActivity(kind="sleep")
    ok = step_physiology(c, ella(health=5000, satiety=hi, hydration=hi), sleeping, False).resident
    assert ok.health == 5000 + recovery
    low_food = ella(health=5000, satiety=n.health_recovery_min_satiety, hydration=hi)
    # after decay satiety falls below the threshold: no recovery, no deprivation either
    assert step_physiology(c, low_food, sleeping, False).resident.health == 5000
    awake = step_physiology(c, ella(health=5000, satiety=hi, hydration=hi), TickActivity(), False)
    assert awake.resident.health == 5000
    resting = step_physiology(
        c, ella(health=5000, satiety=hi, hydration=hi), TickActivity(kind="rest"), False
    )
    assert resting.resident.health == 5000


def test_health_recovery_is_capped_at_the_maximum() -> None:
    c = cfg()
    out = step_physiology(
        c,
        ella(health=c.needs.max_value - 1, satiety=c.needs.max_value, hydration=c.needs.max_value),
        TickActivity(kind="sleep"),
        False,
    ).resident
    assert out.health == c.needs.max_value


def test_deprivation_beats_sleep_recovery() -> None:
    c = cfg()
    out = step_physiology(
        c,
        ella(health=5000, satiety=0, hydration=c.needs.max_value),
        TickActivity(kind="sleep"),
        False,
    ).resident
    assert out.health == 5000 - c.needs.health_loss_per_tick_if_deprived


# ------------------------------------------------------------------ eat and drink helpers


def test_eat_and_drink_gains_are_capped() -> None:
    c = cfg()
    n = c.needs
    assert satiety_after_eating(c, 1000) == 1000 + n.satiety_gain_per_fruit
    assert satiety_after_eating(c, n.max_value - 1) == n.max_value
    assert hydration_after_drinking(c, 1000) == 1000 + n.hydration_gain_per_serving
    assert hydration_after_drinking(c, n.max_value) == n.max_value


# ------------------------------------------------------------------ facts and guards


def test_condition_fact_combines_the_tick_and_is_absent_without_change() -> None:
    c = cfg()
    before = ella(stamina=5000, health=9000)
    out = step_physiology(c, before, TickActivity(kind="sleep"), False)
    fact = out.facts[-1]
    assert fact.type == "condition_updated" and fact.actor_id == "ella"
    p: Any = fact.payload
    assert (p.stamina_before, p.stamina_after) == (5000, out.resident.stamina)
    assert (p.health_before, p.health_after) == (9000, out.resident.health)
    assert (p.satiety_before, p.hydration_before) == (7500, 8000)
    assert condition_fact(before, before.model_copy(deep=True)) is None
    with pytest.raises(ValueError):
        condition_fact(before, resident(fresh_state(default_content()), "mia"))


def test_cost_facts_precede_the_condition_fact() -> None:
    c = cfg()
    out = step_physiology(
        c, ella(stamina=5000), TickActivity(tiles_traversed=3, gather_completed=True), False
    )
    assert [f.type for f in out.facts] == [
        "stamina_action_cost_applied",
        "stamina_action_cost_applied",
        "condition_updated",
    ]
    assert [f.payload.reason for f in out.facts[:2]] == ["move", "gather"]  # type: ignore[attr-defined]


def test_zero_configured_costs_emit_no_cost_fact() -> None:
    c = cfg()
    needs = c.needs.model_copy(
        update={"stamina_move_extra_cost_per_tick": 0, "stamina_gather_cost_per_completion": 0}
    )
    c0 = c.model_copy(update={"needs": needs})
    out = apply_metabolism(c0, ella(), TickActivity(tiles_traversed=2, gather_completed=True))
    assert out.cost_facts == []


def test_dead_residents_are_refused_and_inputs_are_never_mutated() -> None:
    c = cfg()
    dead = ella(alive=False)
    with pytest.raises(ValueError, match="dead"):
        apply_metabolism(c, dead, TickActivity())
    with pytest.raises(ValueError, match="dead"):
        apply_rest_sleep_gain(c, dead, "sleep", True)
    living = ella()
    snapshot = living.model_dump()
    step_physiology(c, living, TickActivity(kind="sleep", tiles_traversed=2), True)
    assert living.model_dump() == snapshot
    with pytest.raises(ValueError):
        TickActivity(tiles_traversed=-1)


def test_zero_decay_config_changes_nothing_but_the_action_effects() -> None:
    c = zero_costs()
    out = step_physiology(c, ella(), TickActivity(kind="rest"), False).resident
    assert out.satiety == 7500 and out.hydration == 8000


def test_identical_inputs_give_byte_identical_physiology_results() -> None:
    import re

    from living_island.world.content import canonical_json_bytes

    c = cfg()

    def run() -> bytes:
        out = step_physiology(
            c,
            ella(stamina=5000),
            TickActivity(kind="other", tiles_traversed=4, gather_completed=True),
            False,
        )
        facts: list[Any] = [
            {
                "type": f.type,
                "actor": f.actor_id,
                "target": f.target_id,
                "payload": f.payload.model_dump(mode="json"),
            }
            for f in out.facts
        ]
        return canonical_json_bytes(
            {"resident": out.resident.model_dump(mode="json"), "facts": facts}
        )

    first = run()
    assert first == run()
    assert not re.search(rb"[0-9]\.[0-9]", first)  # integers only
