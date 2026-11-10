"""P2-03: paired comparisons, pass lines, Wilson interval, EV-14 and EV-19."""

from __future__ import annotations

from typing import Any

from analysis_toys import LIMITS, Toy, worked_example

from living_island.analysis.compare import (
    DIRECTION,
    S5_SCALARS,
    RunSummary,
    arm_report,
    behavior_variation,
    paired_report,
    run_scalars,
    s1_line,
    s3_evidence,
    summarize_run,
    survival_line,
    wilson_interval,
)
from living_island.analysis.metrics import compute_run
from living_island.analysis.validity import frame_problems

RESIDENTS = ("ella", "ryan", "mia")


def summary(
    case_id: str,
    seed: int,
    *,
    valid: bool = True,
    access: tuple[str, str, str] = ("drank", "drank", "drank"),
    **scalars: int,
) -> RunSummary:
    values = dict.fromkeys(DIRECTION, 0)
    values.update(scalars)
    return RunSummary(
        case_id=case_id,
        seed=seed,
        valid=valid,
        final_tick=1008,
        scalars=values,
        access=dict(zip(RESIDENTS, access, strict=True)),
        residents=(),
        deaths_by_holder={"holder_at_death": 0, "nonholder_at_death": 0},
        death_categories={},
        evidence={"c1": [], "a1": [], "a2": []},
        signature={"discovery_order": [], "survival": {"a": True}},
    )


# --------------------------------------------------------------------------- Wilson, PD-05


def test_wilson_interval_for_15_of_20_matches_the_spec() -> None:
    low, high = wilson_interval(15, 20)
    assert f"{low * 100:.4f}" == "53.1299"
    assert f"{high * 100:.4f}" == "88.8138"


def test_survival_line_requires_the_gate_and_fifteen_seeds() -> None:
    def cases(alive: int, invalid: int = 0) -> list[RunSummary]:
        return [
            summary(
                f"c{i}",
                i,
                valid=i >= invalid,
                all_alive=int(i < alive),
            )
            for i in range(20)
        ]

    ok = survival_line(cases(15))
    assert (ok["technical_gate"], ok["all_alive_seeds"], ok["survival"]) == ("PASS", 15, "PASS")
    assert ok["wilson"]["lower_percent"] == "53.1299"
    assert survival_line(cases(14))["survival"] == "FAIL"
    gated = survival_line(cases(20, invalid=1))
    assert (gated["technical_gate"], gated["survival"]) == ("FAIL", "FAIL")
    assert gated["invalid_cases"] == ["c0"]
    assert survival_line(cases(20)[:19])["technical_gate"] == "FAIL"  # 19 cases, not 20


def test_s1_and_s3_lines() -> None:
    good = [summary(f"s{i}", i, all_alive=1) for i in range(20)]
    assert s1_line(good)["pass"] is True
    assert s1_line(good[:-1] + [summary("bad", 99, all_alive=0)])["pass"] is False
    assert s1_line(good[:-1] + [summary("inv", 99, valid=False, all_alive=1)])["invalid_cases"] == [
        "inv"
    ]

    def with_evidence(i: int, ids: list[str]) -> RunSummary:
        row = summary(f"s{i}", i)
        return RunSummary(**{**row.__dict__, "evidence": {"c1": ids, "a1": [], "a2": []}})

    s3 = [with_evidence(i, ["toy:1"]) for i in range(20)]
    assert s3_evidence(s3)["pass"] is True
    assert s3_evidence(s3[:-1] + [with_evidence(99, [])])["pass"] is False


def test_behavior_variation_uses_the_lexicographically_smallest_mode_on_ties() -> None:
    def with_signature(i: int, sig: dict[str, Any]) -> RunSummary:
        row = summary(f"v{i}", i)
        return RunSummary(**{**row.__dict__, "signature": sig})

    runs = [with_signature(0, {"k": 2}), with_signature(1, {"k": 1}), with_signature(2, {"k": 1})]
    assert behavior_variation(runs)["modal_signature"] == '{"k":1}'
    tied = [with_signature(0, {"k": 2}), with_signature(1, {"k": 1})]
    report = behavior_variation(tied)
    assert report["modal_signature"] == '{"k":1}' and report["differing"] == 1
    assert behavior_variation([])["valid_seeds"] == 0


# --------------------------------------------------------------------------- paired reports


def test_ev19_s5_access_split_and_empty_pairs() -> None:
    base = {
        1: summary("b1", 1, access=("drank", "drank", "not_found"), access_drank=2,
                   access_not_found=1, ticks_deprived_water=0),
        2: summary("b2", 2),
    }
    treat = {
        1: summary("t1", 1, access=("drank", "not_found", "not_found"), access_drank=1,
                   access_not_found=2, ticks_deprived_water=7),
        2: summary("t2", 2, valid=False),
    }
    report = paired_report(base, treat, S5_SCALARS)
    assert (report["pairs_used"], report["dropped_seeds"], report["technical"]) == (1, [2], "FAIL")
    assert report["invalid_cases"] == ["t2"]
    drank = report["scalars"]["access_drank"]
    assert (drank["median"], drank["min"], drank["max"]) == (-1, -1, -1)
    assert (drank["favoring_base"], drank["favoring_treatment"], drank["tied"]) == (1, 0, 0)
    assert report["scalars"]["access_not_found"]["median"] == 1
    assert "favoring_base" not in report["scalars"]["access_not_found"]  # descriptive
    water = report["scalars"]["ticks_deprived_water"]
    assert (water["median"], water["favoring_base"]) == (7, 1)
    table = report["access_transition"]
    assert table["order"] == ["drank", "found_not_drunk", "not_found"]
    assert table["counts"] == [[1, 0, 1], [0, 0, 0], [0, 0, 1]]

    # A second round where every pair is invalid: the fields stay present and empty.
    dead_base = {1: summary("b1", 1, valid=False), 2: summary("b2", 2, valid=False)}
    dead_treat = {1: summary("t1", 1, valid=False), 2: summary("t2", 2, valid=False)}
    empty = paired_report(dead_base, dead_treat, S5_SCALARS)
    assert (empty["pairs_used"], empty["technical"]) == (0, "FAIL")
    for name, row in empty["scalars"].items():
        assert (row["median"], row["min"], row["max"]) == (None, None, None), name
        if DIRECTION[name] is not None:
            assert (row["favoring_base"], row["favoring_treatment"], row["tied"]) == (0, 0, 0)
    assert empty["access_transition"]["counts"] == [[0, 0, 0]] * 3


def test_even_pair_count_median_is_the_mean_of_the_middle_values() -> None:
    base = {i: summary(f"b{i}", i) for i in range(4)}
    treat = {i: summary(f"t{i}", i, ticks_deprived=d) for i, d in enumerate([1, 2, 4, 9])}
    row = paired_report(base, treat, ["ticks_deprived"])["scalars"]["ticks_deprived"]
    assert row["median"] == 3  # (2 + 4) / 2
    assert (row["min"], row["max"]) == (1, 9)
    assert (row["favoring_base"], row["favoring_treatment"], row["tied"]) == (4, 0, 0)
    halves = {i: summary(f"t{i}", i, ticks_deprived=d) for i, d in enumerate([1, 2, 5, 9])}
    half = paired_report(base, halves, ["ticks_deprived"])["scalars"]["ticks_deprived"]
    assert half["median"] == {"exact": "7/2", "decimal": "3.500000"}
    third = {i: summary(f"t{i}", i, ticks_deprived=d) for i, d in enumerate([1, 2, 5])}
    assert paired_report({k: base[k] for k in third}, third, ["ticks_deprived"])["scalars"][
        "ticks_deprived"
    ]["median"] == 2


def test_a_missing_arm_makes_the_round_technically_fail() -> None:
    base = {1: summary("b1", 1), 2: summary("b2", 2)}
    treat = {1: summary("t1", 1)}
    report = paired_report(base, treat, ["deaths"], expected_seeds=[1, 2])
    assert report["technical"] == "FAIL"
    assert report["missing_cases"] == [{"seed": 2, "arm": "treatment"}]
    assert report["pairs_used"] == 1
    complete = paired_report(base, {**treat, 2: summary("t2", 2)}, ["deaths"])
    assert complete["technical"] == "PASS" and complete["pairs_used"] == 2


def test_favoring_directions() -> None:
    base = {i: summary(f"b{i}", i, gathers_completed=5, deaths=1) for i in range(3)}
    treat = {
        0: summary("t0", 0, gathers_completed=3, deaths=0),
        1: summary("t1", 1, gathers_completed=5, deaths=1),
        2: summary("t2", 2, gathers_completed=9, deaths=2),
    }
    rows = paired_report(base, treat, ["gathers_completed", "deaths"])["scalars"]
    gathers, deaths = rows["gathers_completed"], rows["deaths"]  # higher / lower is better
    assert (gathers["favoring_base"], gathers["favoring_treatment"], gathers["tied"]) == (1, 1, 1)
    assert (deaths["favoring_base"], deaths["favoring_treatment"], deaths["tied"]) == (1, 1, 1)


def test_scalars_and_arm_report_from_the_worked_example() -> None:
    data = worked_example().run()
    run = compute_run(data)
    scalars = run_scalars(run)
    assert scalars["deaths"] == 1 and scalars["all_alive"] == 0
    assert scalars["ticks_deprived_water"] == 2 and scalars["gathers_completed"] == 1
    assert scalars["discovered"] == 2 and scalars["access_drank"] == 1
    assert scalars["discovery_time_capped"] == 2 + 0 + 9  # c never found it: T + 1
    assert scalars["spring_drink_time_capped"] == 3 + 9 + 9
    assert (scalars["access_found_not_drunk"], scalars["access_not_found"]) == (1, 1)
    row = summarize_run("toy.case", 7, True, run, {"b": "found_not_drunk"})
    assert row.deaths_by_holder == {"holder_at_death": 0, "nonholder_at_death": 1}
    arm = arm_report([row])
    assert arm["totals"]["deaths"] == 1 and arm["valid_cases"] == 1
    assert arm["per_resident"]["b"]["exposure_ticks"] == 3
    rates = arm["per_resident"]["b"]["rates"]["ticks_deprived_water"]
    assert (rates["count"], rates["decimal"]) == (2, "0.666667")
    assert arm["deaths_by_holder_at_death"] == {"holder": 0, "nonholder": 1}


def test_a_canteen_holder_death_is_counted_by_holder_at_death() -> None:
    toy = Toy(T=8)
    toy.put("a", range(0, 5), canteen_servings=1)
    toy.alive_until("a", 4)
    toy.died(5, "a")
    run = compute_run(toy.run())
    assert run.resident("a").holder_at_death is True
    assert summarize_run("c", 1, True, run, {}).deaths_by_holder["holder_at_death"] == 1


def test_ev14_three_canteen_locations() -> None:
    toy = Toy(T=3)
    toy.put("a", range(0, 4), canteen_servings=1)
    frames = [toy.frame(k) for k in range(4)]
    assert frame_problems(tuple(frames), (), LIMITS) == []
    both = frames[1].model_copy(
        update={
            "residents": [
                r.model_copy(update={"canteen_servings": 1}) if r.id in ("a", "b") else r
                for r in frames[1].residents
            ],
            "ground_canteen": _ground(),
        }
    )
    frames[1] = both
    problems = frame_problems(tuple(frames), (), LIMITS)
    assert any("F[1]: the canteen has 3 locations" in p for p in problems)


def _ground() -> Any:
    from living_island.contract.replay import GroundCanteenFrame
    from living_island.world.protocol import Coord

    return GroundCanteenFrame(position=Coord(x=0, y=2), servings=1)


def test_frame_problems_cover_capacity_trees_slots_and_conservation() -> None:
    toy = Toy(T=2)
    toy.put("a", range(0, 3), canteen_servings=1)
    frames = [toy.frame(k) for k in range(3)]
    assert frame_problems(tuple(frames), (), LIMITS) == []

    def mutate(index: int, **update: Any) -> list[str]:
        copy = list(frames)
        copy[index] = copy[index].model_copy(update=update)
        return frame_problems(tuple(copy), (), LIMITS)

    over = [r.model_copy(update={"canteen_servings": 3}) if r.id == "a" else r for r in frames[1].residents]
    assert any("servings out of range" in p for p in mutate(1, residents=over))
    full = [
        r.model_copy(update={"fruit_count": 3}) if r.id == "a" else r for r in frames[1].residents
    ]
    problems = mutate(1, residents=full)
    assert any("uses 4 slots" in p for p in problems)
    assert any("fruit not conserved" in p for p in problems)
    tree = frames[1].fruit_trees[0].model_copy(update={"stock": 7})
    assert any("stock 7 out of range" in p for p in mutate(1, fruit_trees=[tree]))
    dead_holder = [
        r.model_copy(update={"alive": False}) if r.id == "a" else r for r in frames[1].residents
    ]
    assert any("dead a holds items" in p for p in mutate(1, residents=dead_holder))
