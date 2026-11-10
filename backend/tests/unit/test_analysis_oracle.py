"""P2-03: the §8 worked example and every §8.1 counterexample vector, with spec values."""

from __future__ import annotations

from dataclasses import replace

from analysis_toys import (
    LIMITS,
    Toy,
    drink_intent,
    gather_intent,
    give_intent,
    move_intent,
    pick_up_intent,
    talk_accept_intent,
    talk_refuse_intent,
    worked_example,
)

from living_island.analysis.compare import death_categories
from living_island.analysis.metrics import (
    compute_run,
    decimal6,
    rate,
    timing_summaries,
    transfer_then_drink,
)
from living_island.analysis.validity import frame_problems


def metrics_of(toy: Toy):
    data = toy.run()
    return data, compute_run(data)


# --------------------------------------------------------------------------- §8 worked example


def test_worked_example_per_resident_metrics() -> None:
    _, run = metrics_of(worked_example())
    a, b, c = run.residents
    assert (a.resident_id, b.resident_id, c.resident_id) == ("a", "b", "c")
    assert (a.first_spring_discovery_tick, b.first_spring_discovery_tick) == (2, 0)
    assert c.first_spring_discovery_tick is None
    assert (a.first_drink_tick, a.first_spring_drink_tick) == (3, 3)
    assert (b.first_drink_tick, b.first_spring_drink_tick) == (None, None)
    assert (c.first_drink_tick, c.first_spring_drink_tick) == (None, None)
    assert (a.alive_at_T, a.death_tick) == (True, None)
    assert (b.alive_at_T, b.death_tick, b.death_cause) == (False, 3, "DEPRIVATION")
    assert (c.alive_at_T, c.death_tick) == (True, None)
    assert (a.ticks_alive, a.exposure_ticks) == (8, 8)
    assert (b.ticks_alive, b.exposure_ticks) == (2, 3)
    assert (c.ticks_alive, c.exposure_ticks) == (8, 8)
    assert (a.ticks_deprived_water, b.ticks_deprived_water, c.ticks_deprived_water) == (0, 2, 0)
    assert (a.water_only_visits, a.dedicated_water_trips) == (2, 1)
    assert (b.water_only_visits, b.dedicated_water_trips) == (0, 0)
    assert (c.water_only_visits, c.dedicated_water_trips) == (0, 0)
    assert (a.gathers_completed, b.gathers_completed, c.gathers_completed) == (1, 0, 0)
    assert (a.hydration_cap_waste, b.hydration_cap_waste) == (3000, 0)
    assert (a.water_access, b.water_access, c.water_access) == (
        "drank",
        "found_not_drunk",
        "not_found",
    )


def test_worked_example_per_run_metrics() -> None:
    data, run = metrics_of(worked_example())
    assert [(i.failure_event_id, i.match_event_id) for i in run.c1] == [
        ("toy:0000000005:000002", "toy:0000000005:000000")
    ]
    assert [(i.failure_event_id, i.actor_id, i.next_decision_ordinal) for i in run.a1] == [
        ("toy:0000000005:000002", "c", 2)
    ]
    assert run.a2 == ()  # (c,2) also meets A2 but is already the D of an A1
    assert death_categories(data, run) == {"b": "found_not_drunk"}


def test_worked_example_visit_boundaries() -> None:
    """a's visits are F[2..3] and F[6..8]; the tick-2 move_to completion is travel."""
    from living_island.analysis.metrics import visits

    data = worked_example().run()
    assert visits(data, "a") == [(2, 3), (6, 8)]


def test_rates_are_exact_fractions_with_six_decimals() -> None:
    value = rate(2, 3)
    assert (value.count, value.exposure_ticks, value.decimal) == (2, 3, "0.666667")
    assert rate(1, 0).decimal is None  # T = 0: rates are null
    assert decimal6(__import__("fractions").Fraction(-1, 3)) == "-0.333333"


# --------------------------------------------------------------------------- §8.1 vectors


def test_ev01_arrival_move_only_is_not_a_water_visit() -> None:
    toy = Toy(T=8)
    toy.put("a", [2, 3], x=4, y=1)
    toy.succeeded(2, "a", "move_to")
    _, run = metrics_of(toy)
    a = run.resident("a")
    assert (a.water_only_visits, a.dedicated_water_trips) == (0, 0)


def test_ev02_survivor_found_never_drank() -> None:
    toy = Toy(T=8)
    toy.explored(4, "a", [11])
    _, run = metrics_of(toy)
    a = run.resident("a")
    assert (a.water_access, a.alive_at_T, a.first_spring_discovery_tick) == (
        "found_not_drunk",
        True,
        4,
    )
    summary = timing_summaries([a])
    assert summary["discovery_to_first_spring_drink"]["n"] == 0  # excluded from the summary
    assert summary["not_drank_by_survival"] == {"found_not_drunk/alive": 1}


def test_ev03_canteen_drink_before_discovery() -> None:
    toy = Toy(T=10)
    toy.drank(2, "a", "canteen", 4000, 10000, servings_after=1)
    toy.explored(5, "a", [11])
    toy.alive_until("a", 6)
    toy.died(7, "a")
    data, run = metrics_of(toy)
    a = run.resident("a")
    assert (a.first_drink_tick, a.first_spring_drink_tick) == (2, None)
    assert a.water_access == "found_not_drunk"
    assert death_categories(data, run)["a"] == "found_not_drunk"
    assert timing_summaries([a])["discovery_to_first_spring_drink"]["n"] == 0


def test_ev04_late_dehydration_after_a_drink() -> None:
    toy = Toy(T=100)
    toy.explored(2, "a", [11])
    toy.drank(3, "a", "spring", 4000, 10000)
    toy.put("a", range(50, 61), hydration=0)
    toy.alive_until("a", 59)
    toy.died(60, "a")
    data, run = metrics_of(toy)
    assert death_categories(data, run) == {"a": "post_access_dehydration"}


def food_death_toy() -> Toy:
    toy = Toy(T=400)
    toy.explored(2, "a", [11])
    toy.drank(3, "a", "spring", 4000, 10000)
    toy.put("a", range(300, 311), satiety=0)
    toy.alive_until("a", 309)
    toy.died(310, "a")
    toy.trees(range(0, 401), 0)
    return toy


def test_ev05_food_deaths_case_a_supply_shortfall() -> None:
    data, run = metrics_of(food_death_toy())
    assert death_categories(data, run) == {"a": "food_supply_shortfall"}


def test_ev05_food_deaths_case_b_tree_stock_inside_the_run() -> None:
    toy = food_death_toy()
    toy.trees(305, 1)
    data, run = metrics_of(toy)
    assert death_categories(data, run) == {"a": "food_access_shortfall"}


def test_ev05_food_deaths_case_c_fruit_carried_by_another_resident() -> None:
    toy = food_death_toy()
    toy.put("b", range(0, 401), fruit_count=1)
    data, run = metrics_of(toy)
    assert death_categories(data, run) == {"a": "food_access_shortfall"}


def repeat_toy(second_plan: list[dict[str, object]]) -> Toy:
    toy = Toy(T=10)
    toy.decision("c", 1, 3, [gather_intent()])
    toy.failed(5, "c", "gather", "RESOURCE_TAKEN", intent="c:p000001:i0")
    toy.decision("c", 2, 5, second_plan, triggers=("ACTION_FAILED",))
    toy.decision("c", 3, 7, [move_intent(0, 2)])
    return toy


def test_ev06_repeated_attempt_is_a_repeat_not_an_a1() -> None:
    _, run = metrics_of(repeat_toy([gather_intent()]))
    assert run.a1 == ()
    assert [i.failure_event_id for i in run.repeats] == ["toy:0000000005:000000"]
    assert run.repeats[0].next_decision_ordinal == 2  # (c,3) is not examined


def test_ev06_a_different_plan_is_an_a1() -> None:
    _, run = metrics_of(repeat_toy([move_intent(0, 2)]))
    assert len(run.a1) == 1 and run.repeats == ()


def test_ev07_null_target_failure_is_not_an_a1_candidate() -> None:
    toy = Toy(T=8)
    toy.decision("a", 1, 2, [drink_intent("spring")])
    toy.failed(4, "a", "drink", "OUT_OF_REACH", intent="a:p000001:i0")
    toy.decision("a", 2, 4, [drink_intent("spring")], triggers=("ACTION_FAILED",))
    _, run = metrics_of(toy)
    assert (run.a1, run.repeats, run.unresolved) == ((), (), ())


def test_ev08_two_successes_one_failure_matches_the_smallest_seq() -> None:
    toy = Toy(T=8, residents=("a", "b", "c", "d"))
    toy.decision("c", 1, 3, [gather_intent()])
    toy.gathered(5, "a", seq=0)
    toy.gathered(5, "d", seq=3)
    toy.failed(5, "c", "gather", "RESOURCE_TAKEN", intent="c:p000001:i0", seq=5)
    _, run = metrics_of(toy)
    assert [(i.failure_event_id, i.match_event_id) for i in run.c1] == [
        ("toy:0000000005:000005", "toy:0000000005:000000")
    ]


def test_ev09_give_into_a_full_inventory_counts_for_the_recipient() -> None:
    toy = Toy(T=8)
    toy.decision("a", 1, 2, [give_intent("b", "fruit", 1)])
    toy.failed(4, "a", "give", "INVENTORY_FULL", target="b", intent="a:p000001:i0")
    _, run = metrics_of(toy)
    b, a = run.resident("b"), run.resident("a")
    assert (b.slot_full_incidents.not_holding_canteen, b.slot_full_incidents.holding_canteen) == (
        1,
        0,
    )
    assert (a.slot_full_incidents.holding_canteen, a.slot_full_incidents.not_holding_canteen) == (
        0,
        0,
    )


def test_ev09b_gather_is_attributed_to_the_actor_split_by_held_canteen() -> None:
    toy = Toy(T=8)
    toy.put("a", range(0, 9), canteen_servings=1)
    toy.decision("a", 1, 2, [gather_intent()])
    toy.failed(4, "a", "gather", "INVENTORY_FULL", intent="a:p000001:i0")
    _, run = metrics_of(toy)
    assert run.resident("a").slot_full_incidents.holding_canteen == 1


def test_ev10_canteen_removed_from_a_frame_breaks_uniqueness() -> None:
    toy = Toy(T=3)
    toy.put("a", range(0, 4), canteen_servings=1)
    assert frame_problems(tuple(toy.frame(k) for k in range(4)), (), LIMITS) == []
    frames = [toy.frame(k) for k in range(4)]
    frames[1] = frames[1].model_copy(
        update={
            "residents": [
                r.model_copy(update={"canteen_servings": None}) for r in frames[1].residents
            ],
            "ground_canteen": None,
        }
    )
    problems = frame_problems(tuple(frames), (), LIMITS)
    assert any("F[1]: the canteen has 0 locations" in p for p in problems)


def test_ev11_transfer_then_drink_window_and_intervening_give() -> None:
    def build(variant_a: bool, c_drinks: bool = True) -> int:
        toy = Toy(T=160)
        toy.given(10, "a", "b")
        toy.drank(154, "b", "canteen", 3000, 9000, servings_after=0)
        if variant_a:
            toy.given(100, "b", "c")
            if c_drinks:
                toy.drank(120, "c", "canteen", 3000, 9000, servings_after=0)
        return transfer_then_drink(toy.run())

    assert LIMITS.day_ticks == 144
    assert build(False) == 1  # 154 <= 10 + 144
    assert build(True) == 1  # only G(b->c); G(a->b) has an intervening give from b
    assert build(True, c_drinks=False) == 0  # G(a->b) alone is not counted


def test_ev11_a_drink_after_the_window_does_not_count() -> None:
    toy = Toy(T=200)
    toy.given(10, "a", "b")
    toy.drank(155, "b", "canteen", 3000, 9000, servings_after=0)
    assert transfer_then_drink(toy.run()) == 0
    same_tick = Toy(T=20)
    same_tick.given(10, "a", "b")
    same_tick.drank(10, "b", "canteen", 3000, 9000, servings_after=0)
    assert transfer_then_drink(same_tick.run()) == 0  # same-tick events are excluded


def test_ev13_frontier_signature() -> None:
    toy = Toy(T=8)
    toy.decision("a", 1, 3, [move_intent(4, 1)])
    toy.explored(4, "a", [10])  # index of (4,1) = 1*6+4
    _, run = metrics_of(toy)
    assert run.signature["early_frontiers"]["a"] == [[4, 1]]

    later = Toy(T=8)
    later.explored(3, "a", [10])
    later.decision("a", 1, 4, [move_intent(4, 1)])
    _, again = metrics_of(later)
    assert again.signature["early_frontiers"]["a"] == []


def test_ev15_pick_up_of_a_different_item_is_not_a_c1_match() -> None:
    toy = Toy(T=10)
    toy.decision("c", 1, 8, [pick_up_intent(2, 1, "canteen")])
    toy.event(
        "item_picked_up",
        9,
        {
            "resident_id": "a",
            "position": {"x": 2, "y": 1},
            "item_type": "fruit",
            "quantity": 1,
            "canteen_id": None,
        },
        actor="a",
        seq=0,
    )
    toy.failed(9, "c", "pick_up", "ITEM_TAKEN", intent="c:p000001:i0", seq=2)
    _, run = metrics_of(toy)
    assert run.c1 == ()


def test_ev15b_pick_up_of_the_same_item_is_a_c1_match() -> None:
    toy = Toy(T=10)
    toy.decision("c", 1, 8, [pick_up_intent(2, 1, "fruit")])
    toy.event(
        "item_picked_up",
        9,
        {
            "resident_id": "a",
            "position": {"x": 2, "y": 1},
            "item_type": "fruit",
            "quantity": 1,
            "canteen_id": None,
        },
        actor="a",
        seq=0,
    )
    toy.failed(9, "c", "pick_up", "ITEM_TAKEN", intent="c:p000001:i0", seq=2)
    _, run = metrics_of(toy)
    assert len(run.c1) == 1


def test_ev16_failure_at_the_final_tick_is_unresolved() -> None:
    toy = Toy(T=8)
    toy.decision("c", 1, 3, [gather_intent()])
    toy.failed(8, "c", "gather", "RESOURCE_TAKEN", intent="c:p000001:i0")
    _, run = metrics_of(toy)
    assert (len(run.unresolved), run.a1, run.repeats) == (1, (), ())


def test_ev17_death_before_the_next_decision_is_unresolved() -> None:
    toy = Toy(T=10)
    toy.decision("c", 1, 3, [move_intent(0, 2)])
    toy.failed(6, "c", "move_to", "NO_PATH", intent="c:p000001:i0")
    toy.alive_until("c", 5)
    toy.died(6, "c")
    _, run = metrics_of(toy)
    assert (len(run.unresolved), run.a1, run.repeats) == (1, (), ())


def give_failure_toy(next_plan: list[dict[str, object]]) -> Toy:
    toy = Toy(T=10)
    toy.decision("a", 1, 1, [give_intent("b", "canteen", 1)])
    toy.failed(4, "a", "give", "OUT_OF_REACH", target="b", intent="a:p000001:i0")
    toy.decision("a", 2, 4, next_plan, triggers=("ACTION_FAILED",))
    return toy


def test_ev18_talk_refuse_after_a_failed_give_is_an_a1() -> None:
    _, run = metrics_of(give_failure_toy([talk_refuse_intent("b", "u")]))
    assert (len(run.a1), len(run.repeats)) == (1, 0)


def test_ev18_a_give_to_the_same_resident_is_a_repeat() -> None:
    _, run = metrics_of(
        give_failure_toy([talk_accept_intent("b", "u"), give_intent("b", "canteen", 1)])
    )
    assert (len(run.a1), len(run.repeats)) == (0, 1)


def test_a2_counts_a_record_once_and_cites_the_latest_depletion() -> None:
    toy = Toy(T=10)
    toy.trees(range(0, 4), 1).trees(range(4, 11), 0)
    toy.decision("a", 1, 2, [gather_intent()])
    toy.gathered(3, "b", seq=0)  # depletes t1 (stock_after 0) before a's next decision
    toy.decision("a", 2, 5, [move_intent(1, 1)])
    _, run = metrics_of(toy)
    assert [(i.actor_id, i.decision_ordinal, i.tree_id) for i in run.a2] == [("a", 2, "t1")]
    assert run.a2[0].depletion_event_id == "toy:0000000003:000000"
    again = Toy(T=10)
    again.trees(range(0, 4), 1).trees(range(4, 11), 0)
    again.decision("a", 1, 2, [gather_intent()])
    again.decision("a", 2, 5, [gather_intent()])  # targets the empty tree again: no A2
    assert compute_run(again.run()).a2 == ()


def test_limits_replace_is_a_plain_dataclass() -> None:
    assert replace(LIMITS, tick_minutes=20).day_ticks == 72
