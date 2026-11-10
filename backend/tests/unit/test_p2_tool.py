"""P2-03: the batch tool (manifests, §6 refusals, rerun, report) and the §4 validity probes.

The end-to-end cases run through the real simulation CLI for 12 ticks in a throwaway git
repository (so the tests do not depend on this repository's history). The full 1008-tick
cases run through ``scripts/p2_experiments.py`` itself and are recorded in the task handoff.
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path
from typing import Any

import pytest
from p2_tool import SCRIPT_FIXTURE, commit_all, inprocess, make_repo, registry_for, tool

from living_island.agents.types import RuleParams
from living_island.analysis.validity import assess_validity
from living_island.contract.replay import GroundCanteenFrame, ReplayBundle
from living_island.world.protocol import Coord

TICKS = 12
SEEDS = [2195683955, 937154673]
RANDOM = tool.CaseSpec("s2-default", "orig", "p1-random")
SCRIPTED = tool.CaseSpec("s2-default", "orig", "p1-scripted")


def never(args: Any, repo: Path) -> Any:
    raise AssertionError("the runner must not be called when the tool refuses")


def refusal_code(call: Any) -> str:
    with pytest.raises(tool.Refusal) as caught:
        call()
    return str(caught.value.code)


def hash_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ----------------------------------------------------------------------------- end-to-end batch


@pytest.fixture(scope="module")
def e2e(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    repo, commit = make_repo(tmp_path_factory.mktemp("e2e"))
    result = tool.run_batch(
        "e2e",
        SEEDS,
        [RANDOM, SCRIPTED],
        ticks=TICKS,
        script_file=SCRIPT_FIXTURE,
        repo=repo,
        runner=inprocess,
        registry=registry_for(commit),
    )
    return {"repo": repo, "commit": commit, "result": result, "dir": repo / "runs" / "p2" / "e2e"}


def manifest_of(e2e: dict[str, Any], variant: str, seed: int) -> Any:
    case_id = f"s2-default.orig.{variant}.s{seed}"
    return tool.P2CaseManifest.model_validate_json(
        (e2e["dir"] / "manifests" / f"{case_id}.json").read_bytes()
    )


def test_every_e2e_case_is_valid_and_has_a_manifest(e2e: dict[str, Any]) -> None:
    result = e2e["result"]
    assert (len(result.manifests), result.invalid, result.failures) == (4, [], [])
    assert result.ok


def test_manifest_fields_for_the_p1_cases(e2e: dict[str, Any]) -> None:
    seed = SEEDS[0]
    scripted = manifest_of(e2e, "p1-scripted", seed)
    random = manifest_of(e2e, "p1-random", seed)
    out = f"runs/p2/e2e/cases/{scripted.case_id}"
    assert scripted.cli_args == [
        "run", "--config", "content/worlds/default.toml", "--ticks", str(TICKS),
        "--seed", str(seed), "--policy", "scripted", "--script", SCRIPT_FIXTURE,
        "--out", out, "--export-replay",
    ]  # fmt: skip
    assert random.cli_args[7:9] == ["--policy", "random"] and random.script_file is None
    assert (scripted.policy_id, random.policy_id) == ("scripted-v0", "random-v0")
    assert (scripted.rule_params, random.rule_params) == (None, None)
    assert scripted.script_sha256 is not None and random.script_sha256 is None
    assert scripted.script_file == SCRIPT_FIXTURE
    assert scripted.pin_commit == e2e["commit"] and scripted.code_commit == e2e["commit"]
    assert scripted.run_dir == f"cases/{scripted.case_id}" and scripted.batch_id == "e2e"
    assert scripted.scenario_id == "s2-default" and scripted.revision_label == "orig"


def test_two_seeds_sharing_one_run_id_get_distinct_cases(e2e: dict[str, Any]) -> None:
    first, second = (manifest_of(e2e, "p1-random", s) for s in SEEDS)
    assert first.run_id == second.run_id  # run_id comes from the scenario file (OQ-049)
    assert first.case_id != second.case_id and first.seed != second.seed
    assert first.config_sha256 != second.config_sha256  # the seed is part of the config
    assert first.events_sha256 != second.events_sha256
    paths = sorted(p.name for p in (e2e["dir"] / "manifests").glob("*.json"))
    assert len(paths) == len(set(paths)) == 4


def test_two_policy_arms_sharing_one_world_config_hash_get_distinct_cases(
    e2e: dict[str, Any],
) -> None:
    random, scripted = (manifest_of(e2e, v, SEEDS[0]) for v in ("p1-random", "p1-scripted"))
    assert random.config_sha256 == scripted.config_sha256  # one world, two policies
    assert random.map_sha256 == scripted.map_sha256
    assert random.case_id != scripted.case_id
    assert random.policy_config_sha256 != scripted.policy_config_sha256
    assert random.decisions_sha256 != scripted.decisions_sha256


def test_the_tool_writes_only_under_manifests_variants_and_summary(e2e: dict[str, Any]) -> None:
    top = sorted(p.name for p in e2e["dir"].iterdir())
    assert top == ["cases", "manifests", "summary"]  # cases/ is written by the CLI only
    assert (e2e["dir"] / "summary" / "cases.csv").is_file()
    assert (e2e["dir"] / "summary" / "metrics").is_dir()


def test_report_is_separate_and_never_writes_into_a_run_directory(e2e: dict[str, Any]) -> None:
    before = hash_tree(e2e["dir"] / "cases")
    summary = tool.run_report("e2e", ticks=TICKS, repo=e2e["repo"])
    assert summary == {"cases": 4, "invalid": []}
    assert hash_tree(e2e["dir"] / "cases") == before


def test_rerun_gives_identical_hashes_and_metrics(e2e: dict[str, Any]) -> None:
    report = tool.run_rerun("e2e", ticks=TICKS, repo=e2e["repo"], runner=inprocess)
    assert report["rerun_batch"] == "e2e-rerun1" and report["identical"] is True
    assert all(row["identical"] and not row["mismatches"] for row in report["cases"])
    rerun_dir = e2e["repo"] / "runs" / "p2" / "e2e-rerun1"
    for manifest in sorted((e2e["dir"] / "manifests").glob("*.json")):
        original = tool.P2CaseManifest.model_validate_json(manifest.read_bytes())
        events_a = (e2e["dir"] / original.run_dir / "events.jsonl").read_bytes()
        events_b = (rerun_dir / original.run_dir / "events.jsonl").read_bytes()
        assert events_a == events_b


def test_the_subprocess_runner_reproduces_the_in_process_run(small: dict[str, Any]) -> None:
    """The real ``python -m living_island`` path gives the same event log as the fast runner."""
    source = tool.read_manifests(small["repo"] / "runs" / "p2" / "small")[0]
    out = "runs/p2/subprocess/cases/" + source.case_id
    result = tool.run_cli(tool.replace_out(source.cli_args, out), small["repo"])
    assert result.returncode == 0, result.output
    again = tool.load_case(small["repo"] / out, ticks=6, cli_exit_code=0)
    assert again.inputs.trace is not None
    assert again.inputs.trace.events_sha256 == source.events_sha256
    assert again.inputs.trace.final_world_sha256 == source.final_world_sha256


def test_rerun_argv_replaces_only_the_out_value(e2e: dict[str, Any]) -> None:
    manifest = manifest_of(e2e, "p1-scripted", SEEDS[0])
    swapped = tool.replace_out(manifest.cli_args, "runs/p2/e2e-rerun9/cases/x")
    differences = [
        i for i, (a, b) in enumerate(zip(manifest.cli_args, swapped, strict=True)) if a != b
    ]
    assert differences == [manifest.cli_args.index("--out") + 1]
    assert swapped[differences[0]] == "runs/p2/e2e-rerun9/cases/x"


@pytest.fixture(scope="module")
def small(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    repo, commit = make_repo(tmp_path_factory.mktemp("small"))
    registry = registry_for(commit)
    tool.run_batch(
        "small", SEEDS[:1], [RANDOM], ticks=6, repo=repo, runner=inprocess, registry=registry
    )
    return {"repo": repo, "commit": commit}


def test_a_rerun_that_differs_is_reported_as_not_identical(small: dict[str, Any]) -> None:
    def other_seed(args: Any, repo: Path) -> Any:
        args = list(args)
        position = args.index("--seed") + 1
        args[position] = str(int(args[position]) + 1)
        return inprocess(args, repo)

    report = tool.run_rerun("small", number=7, ticks=6, repo=small["repo"], runner=other_seed)
    assert report["identical"] is False
    assert all("events_sha256" in row["mismatches"] for row in report["cases"])
    assert (
        small["repo"] / "runs" / "p2" / "small-rerun7" / "summary" / "rerun-report.json"
    ).is_file()


def test_rerun_refuses_an_existing_target_and_a_different_code_commit(
    small: dict[str, Any],
) -> None:
    repo = small["repo"]
    (repo / "runs" / "p2" / "small-rerun5").mkdir(parents=True)
    assert refusal_code(lambda: tool.run_rerun("small", number=5, ticks=6, repo=repo)) == (
        "BATCH_EXISTS"
    )
    (repo / "note.txt").write_text("code moved on\n", encoding="utf-8")
    commit_all(repo, "move HEAD")
    assert refusal_code(lambda: tool.run_rerun("small", ticks=6, repo=repo)) == "CODE_COMMIT"


# ----------------------------------------------------------------------------- §6 refusals


@pytest.mark.parametrize("batch_id", ["Bad_ID", "UPPER", "a b", "", "trailing/slash", "dot.id"])
def test_batch_id_must_match_the_pattern(tmp_path: Path, batch_id: str) -> None:
    repo, commit = make_repo(tmp_path)
    call = lambda: tool.run_batch(  # noqa: E731
        batch_id, SEEDS[:1], [RANDOM], ticks=6, repo=repo, runner=never,
        registry=registry_for(commit),
    )  # fmt: skip
    assert refusal_code(call) == "BATCH_ID"


def test_batch_id_must_be_unique(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    (repo / "runs" / "p2" / "taken").mkdir(parents=True)
    call = lambda: tool.run_batch(  # noqa: E731
        "taken", SEEDS[:1], [RANDOM], ticks=6, repo=repo, runner=never,
        registry=registry_for(commit),
    )  # fmt: skip
    assert refusal_code(call) == "BATCH_EXISTS"


def plan(repo: Path, registry: Any, specs: Any, **kw: Any) -> Any:
    return tool.plan_cases(
        repo,
        "plan",
        SEEDS[:1],
        specs,
        ticks=6,
        script_file=kw.pop("script_file", None),
        code_commit=tool.head_commit(repo),
        registry=registry,
        variants=tool.VARIANTS,
    )


def test_a_clean_repo_plans_without_refusal(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    s1 = tool.CaseSpec("s1-spring-visible", "orig", "p1-random")
    planned = plan(repo, registry_for(commit), [RANDOM, s1, SCRIPTED], script_file=SCRIPT_FIXTURE)
    assert [p[0] for p in planned] == [
        f"s2-default.orig.p1-random.s{SEEDS[0]}",
        f"s1-spring-visible.orig.p1-random.s{SEEDS[0]}",
        f"s2-default.orig.p1-scripted.s{SEEDS[0]}",
    ]


def test_a_fixture_pin_must_be_exactly_one_commit(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    s1 = tool.CaseSpec("s1-spring-visible", "orig", "p1-random")
    path = repo / "content" / "scenarios" / "s1-spring-visible" / "orig.toml"
    path.write_text(path.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8", newline="\n")
    commit_all(repo, "modify the fixture")  # two commits now touch the file
    assert refusal_code(lambda: plan(repo, registry_for(commit), [s1])) == "FIXTURE_PIN"


def test_config_hash_must_match_the_pin_revision(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    path = repo / "content" / "worlds" / "default.toml"
    text = path.read_text(encoding="utf-8")
    assert 'world_id = "default_island"' in text
    path.write_text(
        text.replace('world_id = "default_island"', 'world_id = "other_island"'),
        encoding="utf-8",
        newline="\n",
    )
    commit_all(repo, "change the default world")
    assert refusal_code(lambda: plan(repo, registry_for(commit), [RANDOM])) == "CONFIG_HASH"


def test_map_hash_must_match_the_pin_revision(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    path = repo / "content" / "worlds" / "default-island.map"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(",", ".", 1), encoding="utf-8", newline="\n")  # grass to sand
    commit_all(repo, "change the map")
    assert refusal_code(lambda: plan(repo, registry_for(commit), [RANDOM])) == "MAP_HASH"


def test_uncommitted_inputs_are_refused(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    registry = registry_for(commit)
    scenario = repo / "content" / "worlds" / "default.toml"
    original = scenario.read_text(encoding="utf-8")

    scenario.write_text(original + "# local edit\n", encoding="utf-8", newline="\n")
    assert refusal_code(lambda: plan(repo, registry, [RANDOM])) == "UNCOMMITTED"  # scenario file
    scenario.write_text(original, encoding="utf-8", newline="\n")

    map_file = repo / "content" / "worlds" / "default-island.map"
    map_original = map_file.read_text(encoding="utf-8")
    map_file.write_text(map_original, encoding="utf-8", newline="\r\n")
    assert refusal_code(lambda: plan(repo, registry, [RANDOM])) == "UNCOMMITTED"  # map file
    map_file.write_text(map_original, encoding="utf-8", newline="\n")

    script = repo / SCRIPT_FIXTURE
    script.write_text(script.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="\n")
    call = lambda: plan(repo, registry, [SCRIPTED], script_file=SCRIPT_FIXTURE)  # noqa: E731
    assert refusal_code(call) == "UNCOMMITTED"  # script file

    untracked = repo / "content" / "scenarios" / "s1-spring-visible" / "cand1.toml"
    untracked.write_text(original, encoding="utf-8", newline="\n")
    revision = tool.Revision(
        "s1-spring-visible", "cand1", "content/scenarios/s1-spring-visible/cand1.toml", None
    )
    extended = {**registry, ("s1-spring-visible", "cand1"): revision}
    cand = tool.CaseSpec("s1-spring-visible", "cand1", "p1-random")
    assert refusal_code(lambda: plan(repo, extended, [cand])) == "UNCOMMITTED"  # never committed


def test_unknown_variants_revisions_and_duplicates_are_refused(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    registry = registry_for(commit)
    unknown = tool.CaseSpec("s2-default", "orig", "no-such-variant")
    assert refusal_code(lambda: plan(repo, registry, [unknown])) == "VARIANT"
    m6 = tool.CaseSpec("s2-default", "m6", "p1-random")  # registered only after M6
    assert refusal_code(lambda: plan(repo, registry, [m6])) == "REVISION"
    assert refusal_code(lambda: plan(repo, registry, [RANDOM, RANDOM])) == "DUPLICATE_CASE"
    assert refusal_code(lambda: plan(repo, registry, [SCRIPTED])) == "SCRIPT_FILE"
    assert refusal_code(lambda: plan(repo, registry, [])) == "EMPTY_BATCH"


def test_effective_rule_params_must_match_the_registered_variant() -> None:
    base, restricted = tool.VARIANTS["base"], tool.VARIANTS["canteen-restricted"]
    tool.check_rule_params(base, base.rule_params)  # the registered value passes
    tool.check_rule_params(tool.VARIANTS["p1-random"], None)
    for variant, effective in (
        (base, restricted.rule_params),
        (restricted, base.rule_params),
        (base, base.rule_params.model_copy(update={"fruit_carry_target": 3})),
        (base, None),
        (tool.VARIANTS["p1-random"], base.rule_params),
    ):
        assert refusal_code(lambda v=variant, e=effective: tool.check_rule_params(v, e)) == (
            "RULE_PARAMS"
        )


def test_a_case_with_unexpected_effective_rule_params_gets_no_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, commit = make_repo(tmp_path)
    monkeypatch.setattr(
        tool, "effective_rule_params", lambda save: tool.VARIANTS["canteen-restricted"].rule_params
    )
    result = tool.run_batch(
        "bad-params",
        SEEDS[:1],
        [RANDOM],
        ticks=6,
        repo=repo,
        runner=inprocess,
        registry=registry_for(commit),
    )
    assert result.manifests == [] and not result.ok
    assert "RULE_PARAMS" in result.failures[0]["refusal"]
    assert not (repo / "runs" / "p2" / "bad-params" / "manifests").exists()


def test_the_registered_rule_variants_and_their_files() -> None:
    base = tool.VARIANTS["base"].rule_params
    assert isinstance(base, RuleParams)
    assert base.model_dump(mode="json") == {
        "rule_params_version": "0.1",
        "canteen_use": "enabled",
        "cue_use": "enabled",
        "fruit_carry_target": 2,
        "failed_target_retry_ticks": 36,
    }
    assert tool.VARIANTS["canteen-restricted"].rule_params == base.model_copy(
        update={"canteen_use": "restricted"}
    )
    assert tool.VARIANTS["cue-ignored"].rule_params == base.model_copy(
        update={"cue_use": "ignored"}
    )
    assert tool.VARIANTS["canteen-restricted"].flags == ("--rule-canteen", "restricted")
    assert tool.VARIANTS["cue-ignored"].flags == ("--rule-cue", "ignored")
    assert tool.VARIANTS["p1-random"].rule_params is None
    assert tool.VARIANTS["canteen-restricted"].policy_args(None) == [
        "--policy", "rule-based", "--rule-canteen", "restricted",
    ]  # fmt: skip
    assert tool.VARIANTS["p1-scripted"].policy_args("s.json") == [
        "--policy", "scripted", "--script", "s.json",
    ]  # fmt: skip
    assert refusal_code(lambda: tool.VARIANTS["p1-scripted"].policy_args(None)) == "SCRIPT_FILE"


def test_variant_files_are_written_for_rule_variants_only(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)

    def stop_after_planning(args: Any, repo: Path) -> Any:
        return tool.CliResult(1, "stub: no run")

    base = tool.CaseSpec("s2-default", "orig", "base")
    result = tool.run_batch(
        "variants", SEEDS[:1], [base, RANDOM], ticks=6, repo=repo, runner=stop_after_planning,
        registry=registry_for(commit),
    )  # fmt: skip
    folder = repo / "runs" / "p2" / "variants" / "variants"
    assert [p.name for p in folder.iterdir()] == ["base.json"]
    assert (folder / "base.json").read_text(encoding="utf-8").startswith('{"canteen_use":"enabled"')
    assert len(result.failures) == 2  # the stub run produced no trace: no manifest


def test_write_scope_is_limited_to_the_three_batch_folders(tmp_path: Path) -> None:
    for relative in ("cases/x.json", "../outside.json", "other/x.json", "x.json"):
        assert refusal_code(lambda r=relative: tool.write_batch_file(tmp_path, r, "x")) == (
            "WRITE_SCOPE"
        )
    assert tool.write_batch_file(tmp_path, "summary/ok.json", "{}").is_file()


# ----------------------------------------------------------------------------- seeds, args


def test_seed_lists_reproduce_the_spec_procedure() -> None:
    development = tool.generate_seed_list("development")
    acceptance = tool.generate_seed_list("acceptance", [development])
    assert tuple(development) == tool.DEVELOPMENT_SEEDS
    assert tuple(acceptance) == tool.ACCEPTANCE_SEEDS
    assert len(set(development) | set(acceptance)) == 40  # disjoint
    assert all(1 <= s <= 0xFFFFFFFF for s in development + acceptance)


def test_seed_and_case_parsing() -> None:
    assert tool.parse_seeds("3,5", None) == [3, 5]
    assert tool.parse_seeds(None, "development") == list(tool.DEVELOPMENT_SEEDS)
    for bad in (("1", "development"), (None, None), ("0", None), ("x", None), (None, "other")):
        assert refusal_code(lambda b=bad: tool.parse_seeds(*b)) == "SEEDS"
    assert tool.CaseSpec.parse("a:b:c") == tool.CaseSpec("a", "b", "c")
    assert refusal_code(lambda: tool.CaseSpec.parse("a:b")) == "CASE_SPEC"


def test_candidate_labels_resolve_only_in_the_scenario_form() -> None:
    assert tool.resolve_revision("s3-regrow288", "cand2").scenario_file == (
        "content/scenarios/s3-regrow288/cand2.toml"
    )
    for label in ("cand0", "cand01", "cand", "candx", "m6"):
        assert refusal_code(lambda x=label: tool.resolve_revision("s3-regrow288", x)) == "REVISION"
    assert refusal_code(lambda: tool.resolve_revision("s9-other", "cand1")) == "REVISION"
    assert tool.resolve_revision("s2-default", "orig").pin_commit == "04fde8b"


# ----------------------------------------------------------------------------- §4 validity probes


@pytest.fixture(scope="module")
def loaded(e2e: dict[str, Any]) -> Any:
    path = e2e["dir"] / "cases" / f"s2-default.orig.p1-scripted.s{SEEDS[0]}"
    return tool.load_case(path, ticks=TICKS, cli_exit_code=0)


def failed_checks(inputs: Any) -> tuple[int, ...]:
    return assess_validity(inputs).failed


def with_replay(inputs: Any, **update: Any) -> Any:
    return dataclasses.replace(inputs, replay=inputs.replay.model_copy(update=update))


def schema_valid(bundle: ReplayBundle) -> bool:
    ReplayBundle.model_validate_json(bundle.model_dump_json())
    return True


def test_a_real_run_passes_every_check(loaded: Any) -> None:
    report = assess_validity(loaded.inputs)
    assert report.valid and report.failed == ()
    assert [c.check for c in report.checks] == [1, 2, 3, 4, 5, 6, 7, 8]


def test_probe_canteen_removed_from_an_intermediate_frame(loaded: Any) -> None:
    replay = loaded.inputs.replay
    frame = replay.frames[1]
    stripped = frame.model_copy(
        update={
            "residents": [r.model_copy(update={"canteen_servings": None}) for r in frame.residents],
            "ground_canteen": None,
        }
    )
    frames = [*replay.frames[:1], stripped, *replay.frames[2:]]
    inputs = with_replay(loaded.inputs, frames=frames)
    assert schema_valid(inputs.replay)  # the bundle and the trace still load
    assert failed_checks(inputs) == (6,)  # only the frame invariant catches it
    assert any("0 locations" in p for p in assess_validity(inputs).checks[5].problems)


def test_probe_two_living_holders_plus_a_ground_canteen(loaded: Any) -> None:
    replay = loaded.inputs.replay
    frame = replay.frames[1]
    holder = next(r.id for r in frame.residents if r.canteen_servings is not None)
    other = next(r.id for r in frame.residents if r.alive and r.id != holder)
    both = frame.model_copy(
        update={
            "residents": [
                r.model_copy(update={"canteen_servings": 1}) if r.id == other else r
                for r in frame.residents
            ],
            "ground_canteen": GroundCanteenFrame(position=Coord(x=1, y=1), servings=1),
        }
    )
    inputs = with_replay(loaded.inputs, frames=[replay.frames[0], both, *replay.frames[2:]])
    assert schema_valid(inputs.replay)
    assert failed_checks(inputs) == (6,)
    assert any("3 locations" in p for p in assess_validity(inputs).checks[5].problems)


def test_probe_a_root_that_is_not_the_tick_zero_state(loaded: Any) -> None:
    inputs = loaded.inputs
    moved = dataclasses.replace(inputs, tick0=inputs.final)  # the final file offered as the root
    assert 3 in failed_checks(moved)
    problems = assess_validity(moved).checks[2].problems
    assert any("world.tick" in p for p in problems)

    world = inputs.tick0.world
    residents = [r.model_copy(update={"satiety": r.satiety - 1}) for r in world.residents]
    tampered = inputs.tick0.model_copy(
        update={"world": world.model_copy(update={"residents": residents})}
    )  # still tick 0, but no longer the world that world_initialized hashed
    swapped = dataclasses.replace(inputs, tick0=tampered)
    assert 3 in failed_checks(swapped)
    assert any("initial_snapshot_hash" in p for p in assess_validity(swapped).checks[2].problems)


def test_probe_a_replay_that_disagrees_with_the_trace(loaded: Any) -> None:
    """EV-12: one event payload byte differs inside replay.json (schema-valid)."""
    replay = loaded.inputs.replay
    index = next(i for i, e in enumerate(replay.events) if e.type == "condition_updated")
    event = replay.events[index]
    payload = event.payload.model_copy(update={"satiety_after": event.payload.satiety_after + 1})
    events = list(replay.events)
    events[index] = event.model_copy(update={"payload": payload})
    inputs = with_replay(loaded.inputs, events=events)
    assert schema_valid(inputs.replay)
    assert 5 in failed_checks(inputs)
    assert any("differs in bytes" in p for p in assess_validity(inputs).checks[4].problems)


def test_check_1_cli_exit_and_loadable_trace(loaded: Any) -> None:
    assert failed_checks(dataclasses.replace(loaded.inputs, cli_exit_code=1)) == (1,)
    gone = dataclasses.replace(
        loaded.inputs, trace=None, load_errors={"trace": "decision-trace.json is missing"}
    )
    failed = failed_checks(gone)
    assert 1 in failed and 2 in failed  # a missing trace fails every check that needs it


def test_check_2_final_tick_must_equal_the_configured_run_length(loaded: Any) -> None:
    assert failed_checks(dataclasses.replace(loaded.inputs, expected_ticks=TICKS + 1)) == (2,)


def test_check_3_tick_zero_cursors(loaded: Any) -> None:
    zero = loaded.inputs.tick0
    wrong_cursor = zero.model_copy(update={"decision_record_cursor": 1})
    assert failed_checks(dataclasses.replace(loaded.inputs, tick0=wrong_cursor)) == (3,)
    wrong_events = zero.model_copy(update={"event_cursor": zero.event_cursor + 1})
    assert failed_checks(dataclasses.replace(loaded.inputs, tick0=wrong_events)) == (3,)


def test_check_4_final_checkpoint_against_the_trace(loaded: Any) -> None:
    trace = loaded.inputs.trace
    for update in (
        {"final_world_sha256": "0" * 64},
        {"event_count": trace.event_count + 1},
        {"record_count": trace.record_count + 1},
    ):
        inputs = dataclasses.replace(loaded.inputs, trace=trace.model_copy(update=update))
        assert 4 in failed_checks(inputs), update


def test_check_5_header_frame_count_and_projections(loaded: Any) -> None:
    for update in (
        {"run_id": "other"},
        {"config_hash": "1" * 64},
        {"map_hash": "2" * 64},
        {"frames": loaded.inputs.replay.frames[:-1]},
    ):
        assert 5 in failed_checks(with_replay(loaded.inputs, **update)), list(update)
    replay = loaded.inputs.replay
    last = replay.frames[-1]
    changed = last.model_copy(
        update={
            "residents": [r.model_copy(update={"stamina": r.stamina - 1}) for r in last.residents]
        }
    )
    inputs = with_replay(loaded.inputs, frames=[*replay.frames[:-1], changed])
    assert any("F[T]" in p for p in assess_validity(inputs).checks[4].problems)
    first = replay.frames[0]
    moved = first.model_copy(
        update={
            "residents": [r.model_copy(update={"health": r.health - 1}) for r in first.residents]
        }
    )
    inputs = with_replay(loaded.inputs, frames=[moved, *replay.frames[1:]])
    assert any("F[0]" in p for p in assess_validity(inputs).checks[4].problems)


def test_check_6_trees_slots_and_conservation(loaded: Any) -> None:
    replay = loaded.inputs.replay
    frame = replay.frames[3]
    tree = frame.fruit_trees[0].model_copy(update={"stock": frame.fruit_trees[0].stock + 1})
    richer = frame.model_copy(update={"fruit_trees": [tree, *frame.fruit_trees[1:]]})
    inputs = with_replay(loaded.inputs, frames=[*replay.frames[:3], richer, *replay.frames[4:]])
    assert failed_checks(inputs) == (6,)
    assert any("fruit not conserved" in p for p in assess_validity(inputs).checks[5].problems)


def test_check_7_policy_config_must_be_identical_and_match_the_manifest(loaded: Any) -> None:
    zero = loaded.inputs.tick0
    states = list(zero.agent_state.runtime_states)
    states[1] = states[1].model_copy(
        update={"policy_config": states[1].policy_config.model_copy(update={"max_plan_actions": 4})}
    )
    agent_state = zero.agent_state.model_copy(update={"runtime_states": states})
    inputs = dataclasses.replace(
        loaded.inputs, tick0=zero.model_copy(update={"agent_state": agent_state})
    )
    assert 7 in failed_checks(inputs)
    mismatch = dataclasses.replace(loaded.inputs, expected_policy_config_sha256="3" * 64)
    assert failed_checks(mismatch) == (7,)
    manifest = manifest_digest(loaded)
    assert not failed_checks(
        dataclasses.replace(loaded.inputs, expected_policy_config_sha256=manifest)
    )


def manifest_digest(loaded: Any) -> str:
    return tool.canonical_sha256(tool.policy_config_of(loaded.inputs.tick0))


def test_check_8_no_substituted_decision(loaded: Any) -> None:
    records = list(loaded.inputs.records)
    records[0] = records[0].model_copy(update={"substituted": True})
    assert failed_checks(dataclasses.replace(loaded.inputs, records=tuple(records))) == (8,)


def test_rule_variant_manifests_on_the_rule_policy_stub(tmp_path: Path) -> None:
    repo, commit = make_repo(tmp_path)
    ids = ("base", "canteen-restricted", "cue-ignored")
    specs = [tool.CaseSpec("s2-default", "orig", v) for v in ids]
    result = tool.run_batch(
        "rule-variants",
        SEEDS[:1],
        specs,
        ticks=6,
        repo=repo,
        runner=inprocess,
        registry=registry_for(commit),
    )
    assert result.failures == [] and len(result.manifests) == 3
    by_variant = {m.policy_variant_id: m for m in result.manifests}
    for variant_id, manifest in by_variant.items():
        registered = tool.VARIANTS[variant_id].rule_params
        assert isinstance(manifest.rule_params, RuleParams)
        assert manifest.rule_params == registered  # the manifest holds the effective value
        assert manifest.policy_id == "rule-based-v0"
        stored = repo / "runs" / "p2" / "rule-variants" / "variants" / f"{variant_id}.json"
        assert RuleParams.model_validate_json(stored.read_text(encoding="utf-8")) == registered
    assert len({m.policy_config_sha256 for m in result.manifests}) == 3
    assert len({m.case_id for m in result.manifests}) == 3
    args = {v: m.cli_args[m.cli_args.index("--policy") :] for v, m in by_variant.items()}
    assert args["base"][:2] == ["--policy", "rule-based"] and "--rule-canteen" not in args["base"]
    assert args["canteen-restricted"][:4] == [
        "--policy", "rule-based", "--rule-canteen", "restricted",
    ]  # fmt: skip
    assert args["cue-ignored"][:4] == ["--policy", "rule-based", "--rule-cue", "ignored"]


def test_a_rule_case_run_with_the_wrong_switch_is_refused(tmp_path: Path) -> None:
    """The registry says ``canteen-restricted`` but the run used the default switches."""
    repo, commit = make_repo(tmp_path)
    variants = dict(tool.VARIANTS)
    variants["canteen-restricted"] = dataclasses.replace(variants["canteen-restricted"], flags=())
    spec = tool.CaseSpec("s2-default", "orig", "canteen-restricted")
    result = tool.run_batch(
        "wrong-switch",
        SEEDS[:1],
        [spec],
        ticks=6,
        repo=repo,
        runner=inprocess,
        registry=registry_for(commit),
        variants=variants,
    )
    assert result.manifests == [] and "RULE_PARAMS" in result.failures[0]["refusal"]
