"""CT-13, §9.4 and admission boundaries on short or synthetic receipts."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from functools import partial

import pytest


@pytest.fixture(scope="module")
def short_pair(tmp_path_factory):
    from living_island.sim.v2.scenarios.balance.campaign import Job, execute
    from living_island.sim.v2.scenarios.balance.observations import scenario
    from living_island.sim.v2.scenarios.balance.report import ARMS
    from living_island.sim.v2.scenarios.receipts import CasePlan
    from living_island.sim.v2.scenarios.runtime import run_or_resume

    out = tmp_path_factory.mktemp("ct06")
    seed = 20261108
    pair = {}
    for index, arm in enumerate(ARMS):
        plan = CasePlan(
            revision="short",
            runner="CT-04",
            controller="visible",
            setup="production",
            observer="CT-13",
            arm=arm,
            case_index=index,
            horizon=4,
            checkpoint_every=2,
        )
        job = Job(out, seed, arm, plan, False, ())
        if not index:
            directory = out / str(seed) / arm
            paused = run_or_resume(
                directory,
                plan,
                partial(scenario, directory, seed, arm),
                pause_after=lambda t: t == 2,
            )
            assert paused.evidence is None and paused.tick == 2
        case = execute(job)
        if not index:
            with ProcessPoolExecutor(max_workers=1) as pool:
                direct = pool.submit(execute, replace(job, out=out / "direct")).result()
            assert direct.measured == case.measured
            assert (
                execute(replace(job, out=out / "reuse", reuse=(out,))).details() == case.details()
            )
        assert execute(replace(job, inspect=True)).details() == case.details()
        pair[arm] = case
    return pair


def test_ct13_short_recovery_full_matrix_and_access(short_pair):
    from living_island.sim.v2.scenarios.balance.campaign import registered
    from living_island.sim.v2.scenarios.balance.report import ARMS, report

    seeds = registered("acceptance")
    assert seeds[0] == 2600456787 and len(seeds) == 20
    assert set(seeds).isdisjoint(registered("development"))
    cases = {}
    for seed in seeds:
        for arm in ARMS:
            case = short_pair[arm]
            run = replace(case.measured.metrics, final_tick=1008)
            measured = replace(case.measured, metrics=run)
            cases[seed, arm] = replace(
                case, inputs=case.inputs.model_copy(update={"seed": seed}), measured=measured
            )
    result = report(seeds, cases, {}, "acceptance")
    assert result["technical"] == result["verdict"] == "PASS"
    assert len(result["access_by_resident"]) == 60
    for arm in ARMS:
        summary = result["arms"][arm]
        assert summary["residents"] == summary["never_drinkers"] == 60
        assert summary["median_first_spring_drink"] == 1009
    assert result["d1_case"] == f"{seeds[0]}/starter-v1"
    for seed in seeds:
        case = cases[seed, ARMS[1]]
        days = {
            r: [{**day, "non_survival": 0} for day in entries]
            for r, entries in case.measured.days.items()
        }
        cases[seed, ARMS[1]] = replace(case, measured=replace(case.measured, days=days))
    below = report(seeds, cases, {}, "acceptance")
    assert below["ct_d9_at_least_30_percent"] is False and below["verdict"] == "PASS"
    assert report(seeds, cases, {"case": "invalid"}, "acceptance")["verdict"] == "FAIL"
    key = seeds[0], ARMS[1]
    original = cases[key]
    cases[key] = replace(
        original, inputs=original.inputs.model_copy(update={"map_sha256": "1" * 64})
    )
    assert report(seeds, cases, {}, "acceptance")["paired"]["pairs_used"] == 19
    cases[key] = short_pair[ARMS[1]]
    assert report(seeds, cases, {}, "acceptance")["technical"] == "FAIL"
    del cases[key]
    assert report(seeds, cases, {}, "acceptance")["arms"][ARMS[1]]["valid_cases"] == 19
    del cases[seeds[0], ARMS[0]]
    assert len(report(seeds, cases, {}, "acceptance")["paired"]["missing_cases"]) == 2


def test_ct13_exact_tolerance_edges():
    from living_island.sim.v2.scenarios.balance.report import tolerances

    c = {
        "residents": 60,
        "median_first_spring_drink": 100,
        "faints": 0,
        "deaths_by_cause": {},
        "totals": {"all_alive": 20, "ticks_deprived": 0},
    }
    t = {
        **c,
        "median_first_spring_drink": 112,
        "faints": 60,
        "totals": {"all_alive": 19, "ticks_deprived": 1440},
    }
    assert all(tolerances(c, t).values())
    assert tolerances(c, {**t, "median_first_spring_drink": 88})["spring_access"]
    for value in (87, 113):
        assert not tolerances(c, {**t, "median_first_spring_drink": value})["spring_access"]
    t.update(
        faints=61,
        median_first_spring_drink=113,
        deaths_by_cause={"new": 1},
        totals={"all_alive": 18, "ticks_deprived": 1441},
    )
    assert not any(tolerances(c, t).values())


def test_missing_calibration_refused_before_any_case(tmp_path):
    from living_island.sim.v2.scenarios.balance.campaign import campaign

    with pytest.raises(FileNotFoundError, match="receipt.json"):
        campaign(
            "development",
            tmp_path,
            "0" * 64,
            tmp_path / "out",
            4,
            equivalence_revision="a" * 40,
            inspect=False,
            reuse=(),
        )
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("jobs", [0, 5])
def test_worker_limit(tmp_path, jobs):
    from living_island.sim.v2.scenarios.balance.campaign import campaign

    with pytest.raises(ValueError, match="jobs"):
        campaign(
            "development",
            tmp_path,
            "0" * 64,
            tmp_path,
            jobs,
            equivalence_revision="a" * 40,
            inspect=False,
            reuse=(),
        )


def test_heavy_lock_excludes_concurrent_campaign_and_releases_on_failure(tmp_path):
    from living_island.sim.v2.scenarios.balance.campaign import heavy_lock

    path = tmp_path / "li-heavy.lock"
    with pytest.raises(FileExistsError), heavy_lock(path), heavy_lock(path):
        pytest.fail("concurrent campaign admitted")
    assert not path.exists()


@pytest.mark.parametrize("state,missing", [("equal", []), ("different", []), ("equal", ["case"])])
def test_wrapper_owns_lock_through_development_only(tmp_path, monkeypatch, state, missing):
    import json
    import sys
    from hashlib import sha256

    from living_island.sim.v2.scenarios.balance import development

    revision = "a" * 40
    evidence = tmp_path / f"acceptance-{revision}"
    lock = tmp_path / "heavy.lock"
    real_lock = development.heavy_lock
    monkeypatch.setattr(development, "heavy_lock", lambda: real_lock(lock))
    monkeypatch.setattr(development.cli, "ROOT", tmp_path)
    checkout = tmp_path / "pinned"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "wrapper",
            "--en08",
            str(evidence),
            "--jobs",
            "2",
            "--calibration-checkout",
            str(checkout),
        ],
    )
    out = tmp_path / "runs/m13/calibration-en10"
    calls = []
    raw = json.dumps(
        {
            "en08": {"revision": revision, "report_sha256": "1" * 64, "scope_sha256": "2" * 64},
            "status": state,
            "missing_cases": missing,
            "cases": [],
            "executable": {},
        }
    ).encode()

    def calibrate(command, *, cwd, check):
        assert lock.is_file() and cwd == checkout and check
        assert command[-6:] == ["--out", str(out), "--en08", str(evidence), "--jobs", "2"]
        calls.append("calibrate")
        out.mkdir(parents=True)
        (out / "receipt.json").write_bytes(raw)

    def develop(stage, calibration, digest, directory, jobs, **options):
        assert lock.is_file() and calibration == out
        assert digest == sha256(raw).hexdigest() and jobs == 2
        assert options["equivalence_revision"] == revision
        calls.append(stage)
        return {"verdict": "PASS"}

    monkeypatch.setattr(development.subprocess, "run", calibrate)
    monkeypatch.setattr(development, "campaign", develop)
    if state == "equal" and not missing:
        assert development.main() == 0 and calls == ["calibrate", "development"]
    else:
        with pytest.raises(ValueError, match="calibration"):
            development.main()
        assert calls == ["calibrate"]
    assert not lock.exists()


def test_observation_integrity_and_missing_case(short_pair, tmp_path):
    from pathlib import Path

    from living_island.sim.v2.scenarios.balance.campaign import Job, execute
    from living_island.sim.v2.scenarios.balance.measurement import measure
    from living_island.sim.v2.scenarios.receipts import Evidence

    case = short_pair["compat-v1"]
    with pytest.raises(ValueError, match="missing or mismatched"):
        execute(Job(tmp_path, case.inputs.seed, "compat-v1", case.inputs.plan, True, ()))
    directory = Path(case.directory)
    saved = Evidence.model_validate_json((directory / "evidence.json").read_bytes())
    altered = saved.model_copy(update={"observer": {**saved.observer, "0": "0" * 64}})
    with pytest.raises(ValueError, match="digest differs"):
        measure(directory, altered, case.inputs.seed)


def test_interval_classes_awareness_and_reach(short_pair):
    from pathlib import Path

    from living_island.sim.v2.scenarios.balance.measurement import action_class, time_use
    from living_island.sim.v2.scenarios.balance.observations import Interval, Opening
    from living_island.world.v2.protocol import Coord

    directory = Path(short_pair["compat-v1"].directory) / "observations"
    opening = Opening.model_validate_json((directory / "opening.json").read_bytes())
    first = Interval.model_validate_json((directory / "0.json").read_bytes())
    actor, template = next(iter(first.starts.items()))
    passive = {r.id: "unconscious" for r in opening.frame.residents if r.id != actor}
    pos = Coord(x=3, y=3)
    entries = [
        ("move_to", pos, "awake"),
        ("sleep", None, "awake"),
        ("sleep", None, "asleep"),
        ("wait", None, "unconscious"),
        ("move_to", pos, "awake"),
        ("move_to", pos, "awake"),
        ("gather", Coord(x=3, y=4), "awake"),
        ("move_to", pos, "awake"),
        ("gather", Coord(x=6, y=6), "awake"),
        ("move_to", pos, "awake"),
    ]
    rows = []
    for i, (verb, target, state) in enumerate(entries):
        start = template.model_copy(
            update={
                "verb": verb,
                "position": pos,
                "target": target,
                "item": "fruit_tree",
                "intent_id": str(i),
            }
        )
        rows.append(
            first.model_copy(
                update={
                    "starts": {actor: start},
                    "awareness": {**passive, actor: state},
                    "events": (
                        first.events[0].model_copy(
                            update={
                                "type": "action_started",
                                "actor_id": actor,
                                "intent_id": str(i),
                            }
                        ),
                    ),
                }
            )
        )
    daily = time_use(opening, rows)
    with pytest.raises(ValueError, match="do not reconcile"):
        time_use(opening, [rows[0].model_copy(update={"awareness": passive, "starts": {}})])
    with pytest.raises(ValueError, match="one paid awake attempt"):
        time_use(opening, [rows[0].model_copy(update={"events": ()})])
    day = daily[actor][0]
    assert (day["awake"], day["asleep"], day["unconscious"], day["living"]) == (8, 1, 1, 10)
    assert (day["survival"], day["exploring"]) == (5, 3)
    assert day["non_survival_fraction"]["decimal"] == "0.375000"
    assert (
        next(days[0] for other, days in daily.items() if other != actor)["survival_fraction"][
            "decimal"
        ]
        is None
    )
    for verb, item, spoken, kind in [
        ("wait", None, True, "social"),
        ("wait", None, False, "idle"),
        ("drop", "canteen", False, "survival"),
        ("pick_up", None, False, "crafting"),
        ("gather", None, False, "crafting"),
        ("combine", None, False, "crafting"),
    ]:
        assert (
            action_class(
                template.model_copy(update={"verb": verb, "item": item, "utterance": spoken})
            )
            == kind
        )
    with pytest.raises(ValueError, match="unmapped"):
        action_class(template.model_copy(update={"verb": "new"}))
