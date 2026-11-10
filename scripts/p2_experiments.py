"""P2 batch experiment tool: batch, rerun and report commands (P2 experiments spec §6, §7).

Run from the repo root or from ``backend`` through uv, for example::

    uv run --directory backend python ../scripts/p2_experiments.py batch \\
        --batch-id demo --seeds 2195683955 --case s2-default:orig:p1-random

The tool writes only under ``runs/p2/<batch_id>/{manifests,variants,summary}``. Each case's run
directory (``cases/<case_id>``) is written by the simulation CLI and never by this tool. The
long matrix runs only through this separate command, outside default CI (OQ-053).
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import posixpath
import subprocess
import sys
import tomllib
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from living_island.agents.types import PolicyConfig, RuleParams
from living_island.analysis.canon import canonical_bytes_of_data, canonical_sha256
from living_island.analysis.compare import (
    S4_SCALARS,
    S5_SCALARS,
    RunSummary,
    arm_report,
    behavior_variation,
    death_categories,
    paired_report,
    s1_line,
    s3_evidence,
    summarize_run,
    survival_line,
)
from living_island.analysis.data import RunData, RunLimits, payload_of
from living_island.analysis.manifest import P2CaseManifest, case_id_of, is_valid_batch_id
from living_island.analysis.metrics import compute_run, timing_summaries
from living_island.analysis.validity import ValidityInputs, ValidityReport, assess_validity
from living_island.contract.replay import ReplayBundle
from living_island.contract.save import SavePackage
from living_island.persistence.checkpoints import read_checkpoint
from living_island.persistence.trace import load_trace
from living_island.world.content import WorldContent, build_world_content, config_hash

ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = "runs/p2"
# §4 check 2 and the §6 argv: an experiment case is exactly this long. Not a CLI option; tests
# that run short cases lower it (the only seam), so a short run is never reported as valid.
REQUIRED_TICKS = 1008
MANIFEST_VERSION = "0.1"
WRITABLE_PARTS = ("manifests", "variants", "summary")

# §2 seed lists (reproduced by ``generate_seed_list``; a test checks both).
DEVELOPMENT_SEEDS = (
    2195683955, 937154673, 1452436788, 1883209505, 497199041, 3459030352, 2507182619,
    3698676642, 2144999532, 1263016932, 2344699806, 1011827743, 2104929825, 2520148199,
    201486072, 1021125776, 1334592829, 3695162045, 3976177611, 404876745,
)  # fmt: skip
ACCEPTANCE_SEEDS = (
    2600456787, 3335059634, 2733016023, 958049702, 3486741106, 1557484054, 4155892942,
    3501343423, 330361958, 3178109895, 969717619, 857949281, 2170312666, 1007489817,
    2560155364, 1802799976, 1569596598, 646834264, 2122883013, 598561891,
)  # fmt: skip
SEED_LISTS = {"development": DEVELOPMENT_SEEDS, "acceptance": ACCEPTANCE_SEEDS}


class Refusal(ValueError):
    """The tool refuses a batch or case (§6); ``code`` names the rule."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# ---------------------------------------------------------------------------
# Seeds (§2)
# ---------------------------------------------------------------------------


def generate_seed_list(
    name: str, earlier: Sequence[Sequence[int]] = (), count: int = 20
) -> list[int]:
    """``seed = 1 + uint32_be(SHA-256("living-island/p2/<name>/<i>")[0:4]) mod (2^32 - 1)``.

    Values in an earlier list (or already drawn) are skipped; generation stops at ``count``.
    """
    seen = {seed for seeds in earlier for seed in seeds}
    seeds: list[int] = []
    index = 0
    while len(seeds) < count:
        digest = sha256(f"living-island/p2/{name}/{index}".encode()).digest()
        seed = 1 + int.from_bytes(digest[:4], "big") % (2**32 - 1)
        index += 1
        if seed not in seen:
            seen.add(seed)
            seeds.append(seed)
    return seeds


# ---------------------------------------------------------------------------
# Registries (§6)
# ---------------------------------------------------------------------------

RULE_DEFAULTS = RuleParams(
    rule_params_version="0.1",
    canteen_use="enabled",
    cue_use="enabled",
    fruit_carry_target=2,
    failed_target_retry_ticks=36,
)


@dataclass(frozen=True)
class Variant:
    """A registered policy variant: immutable, an ID always means the same parameters."""

    variant_id: str
    policy_id: str  # tick-0 policy_config.policy_id
    flags: tuple[str, ...]  # CLI flags after ``--policy ...``
    rule_params: RuleParams | None
    needs_script: bool = False

    def policy_args(self, script_file: str | None) -> list[str]:
        if self.needs_script:
            if script_file is None:
                raise Refusal("SCRIPT_FILE", f"variant {self.variant_id} needs a script file")
            return ["--policy", "scripted", "--script", script_file]
        if self.policy_id == "random-v0":
            return ["--policy", "random"]
        return ["--policy", "rule-based", *self.flags]


VARIANTS: dict[str, Variant] = {
    v.variant_id: v
    for v in (
        Variant("base", "rule-based-v0", (), RULE_DEFAULTS),
        Variant(
            "canteen-restricted",
            "rule-based-v0",
            ("--rule-canteen", "restricted"),
            RULE_DEFAULTS.model_copy(update={"canteen_use": "restricted"}),
        ),
        Variant(
            "cue-ignored",
            "rule-based-v0",
            ("--rule-cue", "ignored"),
            RULE_DEFAULTS.model_copy(update={"cue_use": "ignored"}),
        ),
        Variant("p1-random", "random-v0", (), None),
        Variant("p1-scripted", "scripted-v0", (), None, needs_script=True),
    )
}


@dataclass(frozen=True)
class Revision:
    """One revision of one scenario: its file and pin commit (``None`` = its only commit)."""

    scenario_id: str
    label: str
    scenario_file: str
    pin_commit: str | None

    @property
    def is_fixture(self) -> bool:
        return self.pin_commit is None


# §6 table. S2 ``m6`` is registered by P2-04 once the M6 sign-off names its commit.
REGISTRY: dict[tuple[str, str], Revision] = {
    ("s2-default", "orig"): Revision(
        "s2-default", "orig", "content/worlds/default.toml", "04fde8b"
    ),
    **{
        (sid, "orig"): Revision(sid, "orig", f"content/scenarios/{sid}/orig.toml", None)
        for sid in ("s1-spring-visible", "s3-regrow288", "s4-decay120")
    },
}
CANDIDATE_SCENARIOS = ("s1-spring-visible", "s2-default", "s3-regrow288", "s4-decay120")


def resolve_revision(
    scenario_id: str,
    label: str,
    registry: Mapping[tuple[str, str], Revision] = REGISTRY,
) -> Revision:
    found = registry.get((scenario_id, label))
    if found is not None:
        return found
    if (
        registry is REGISTRY
        and scenario_id in CANDIDATE_SCENARIOS
        and label.startswith("cand")
        and label[4:].isdigit()
        and int(label[4:]) >= 1
        and str(int(label[4:])) == label[4:]
    ):
        return Revision(scenario_id, label, f"content/scenarios/{scenario_id}/{label}.toml", None)
    raise Refusal("REVISION", f"({scenario_id}, {label}) is not a registered scenario revision")


@dataclass(frozen=True)
class CaseSpec:
    scenario_id: str
    label: str
    variant_id: str

    @classmethod
    def parse(cls, text: str) -> CaseSpec:
        parts = text.split(":")
        if len(parts) != 3 or not all(parts):
            raise Refusal("CASE_SPEC", f"expected scenario:label:variant, got {text!r}")
        return cls(*parts)


# ---------------------------------------------------------------------------
# Git inputs (§6 refusals)
# ---------------------------------------------------------------------------


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)


def git_text(repo: Path, *args: str) -> str:
    done = git(repo, *args)
    if done.returncode != 0:
        raise Refusal("GIT", f"git {' '.join(args)} failed: {done.stderr.decode(errors='replace')}")
    return done.stdout.decode().strip()


def head_commit(repo: Path) -> str:
    return git_text(repo, "rev-parse", "HEAD")


def blob_at(repo: Path, revision: str, path: str) -> bytes:
    done = git(repo, "show", f"{revision}:{path}")
    if done.returncode != 0:
        raise Refusal("UNCOMMITTED", f"{path} does not exist at {revision}")
    return done.stdout


def map_path_of(scenario_file: str, config: Mapping[str, Any]) -> str:
    layout = config["map"]["layout_file"]
    return posixpath.normpath(posixpath.join(posixpath.dirname(scenario_file), layout))


def content_at(repo: Path, revision: str, scenario_file: str) -> tuple[WorldContent, str]:
    """Build the content a scenario file resolves to at a revision; also return its map path."""
    config = tomllib.loads(blob_at(repo, revision, scenario_file).decode("utf-8"))
    map_path = map_path_of(scenario_file, config)
    return build_world_content(config, blob_at(repo, revision, map_path)), map_path


def require_committed(repo: Path, code_commit: str, path: str) -> None:
    """Refuse an input that is not a committed blob at ``code_commit`` or differs from it.

    Untracked and ignored files have no blob at the commit, so a status check is not enough.
    """
    if posixpath.normpath(path) != path or path.startswith(("/", "../")) or "\\" in path:
        raise Refusal("UNCOMMITTED", f"{path!r} is not a normalized repo-relative path")
    if git(repo, "cat-file", "-e", f"{code_commit}:{path}").returncode != 0:
        raise Refusal("UNCOMMITTED", f"{path} is not a committed file at {code_commit}")
    if not (repo / path).is_file():
        raise Refusal("UNCOMMITTED", f"{path} is missing from the working tree")
    if git(repo, "diff", "--quiet", code_commit, "--", path).returncode != 0:
        raise Refusal("UNCOMMITTED", f"{path} differs from its committed blob at {code_commit}")


@dataclass(frozen=True)
class VerifiedInputs:
    revision: Revision
    pin_commit: str
    content_revision_sha256: str
    map_path: str


def verify_inputs(
    repo: Path, revision: Revision, code_commit: str, extra_files: Sequence[str] = ()
) -> VerifiedInputs:
    """Enforce the fixture pin, the identity check and the uncommitted-input refusal."""
    file = revision.scenario_file
    at_code, map_path = content_at(repo, code_commit, file)
    if revision.pin_commit is None:
        commits = git_text(repo, "log", "--format=%H", code_commit, "--", file).split()
        if len(commits) != 1:
            raise Refusal(
                "FIXTURE_PIN",
                f"{file} has {len(commits)} commits at {code_commit}; a fixture needs exactly one",
            )
        pin = commits[0]
    else:
        pin = git_text(repo, "rev-parse", f"{revision.pin_commit}^{{commit}}")
    at_pin, _ = content_at(repo, pin, file)
    if config_hash(at_code.config) != config_hash(at_pin.config):
        raise Refusal("CONFIG_HASH", f"{file} at {code_commit} differs from the pin {pin}")
    if at_code.map_hash != at_pin.map_hash:
        raise Refusal("MAP_HASH", f"the map of {file} at {code_commit} differs from the pin {pin}")
    for path in (file, map_path, *extra_files):
        require_committed(repo, code_commit, path)
    return VerifiedInputs(revision, pin, config_hash(at_pin.config), map_path)


# ---------------------------------------------------------------------------
# Running one case
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CliResult:
    returncode: int
    output: str


Runner = Callable[[Sequence[str], Path], CliResult]


def run_cli(cli_args: Sequence[str], repo: Path) -> CliResult:
    """Run ``python -m living_island <cli_args>`` from the repo root."""
    done = subprocess.run(
        [sys.executable, "-m", "living_island", *cli_args],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    text = done.stdout.decode(errors="replace") + done.stderr.decode(errors="replace")
    return CliResult(done.returncode, text)


def build_cli_args(
    scenario_file: str,
    ticks: int,
    seed: int,
    policy_args: Sequence[str],
    out: str,
) -> list[str]:
    """Exactly: ``run --config F --ticks N --seed S <policy args> --out OUT --export-replay``."""
    return [
        "run",
        "--config",
        scenario_file,
        "--ticks",
        str(ticks),
        "--seed",
        str(seed),
        *policy_args,
        "--out",
        out,
        "--export-replay",
    ]


def replace_out(cli_args: Sequence[str], new_out: str) -> list[str]:
    """The rerun argv: ``cli_args`` with only the value after ``--out`` replaced (B08)."""
    args = list(cli_args)
    args[args.index("--out") + 1] = new_out
    return args


@dataclass
class LoadedCase:
    run_dir: Path
    cli_exit_code: int | None
    inputs: ValidityInputs
    data: RunData | None
    load_errors: dict[str, str] = field(default_factory=dict)


def _limits_of(content: WorldContent) -> RunLimits:
    config = content.config
    return RunLimits(
        min_value=config.needs.min_value,
        hydration_gain_per_serving=config.needs.hydration_gain_per_serving,
        canteen_capacity=config.canteen.capacity_servings,
        max_stock_per_tree=config.fruit.max_stock_per_tree,
        slot_capacity=config.inventory.slot_capacity,
        tick_minutes=config.time.tick_minutes,
    )


def load_case(
    run_dir: Path,
    *,
    cli_exit_code: int | None,
    expected_policy_config_sha256: str | None = None,
) -> LoadedCase:
    """Read a case directory through the read-only persistence API; never write to it."""
    errors: dict[str, str] = {}
    trace = events = records = content = None
    try:
        loaded = load_trace(run_dir)
        trace, events, content = loaded.manifest, loaded.events, loaded.content
        records = tuple(
            record
            for resident in sorted(r.id for r in content.config.residents)
            for record in loaded.for_actor(resident)
        )
    except (ValueError, OSError) as exc:
        errors["trace"] = str(exc)
    final_tick = trace.final_tick if trace is not None else REQUIRED_TICKS

    def checkpoint(tick: int, name: str) -> SavePackage | None:
        if content is None:
            errors[name] = "no retained content"
            return None
        try:
            return read_checkpoint(run_dir / f"checkpoint-{tick:010d}.json", content)
        except (ValueError, OSError) as exc:
            errors[name] = str(exc)
            return None

    tick0, final = checkpoint(0, "tick0"), checkpoint(final_tick, "final")
    replay: ReplayBundle | None = None
    try:
        replay = ReplayBundle.model_validate_json((run_dir / "replay.json").read_bytes())
    except (ValueError, OSError) as exc:
        errors["replay"] = str(exc)
    limits = _limits_of(content) if content is not None else None
    inputs = ValidityInputs(
        cli_exit_code=cli_exit_code,
        expected_ticks=REQUIRED_TICKS,
        limits=limits,
        trace=trace,
        events=events,
        records=records,
        tick0=tick0,
        final=final,
        replay=replay,
        expected_policy_config_sha256=expected_policy_config_sha256,
        load_errors=errors,
    )
    data = None
    if replay is not None and events is not None and records is not None and limits is not None:
        data = RunData(replay.run_id, replay.frames, events, records, replay.map.rows, limits)
    return LoadedCase(run_dir, cli_exit_code, inputs, data, errors)


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------


def policy_config_of(save: SavePackage) -> PolicyConfig:
    return save.agent_state.runtime_states[0].policy_config


def effective_rule_params(save: SavePackage) -> RuleParams | None:
    """``rule_params`` from the tick-zero policy config (absent for P1 policies)."""
    return policy_config_of(save).rule_params


def check_rule_params(variant: Variant, effective: RuleParams | None) -> None:
    """Refuse a case whose effective ``rule_params`` differ from its registered variant."""
    expected = variant.rule_params
    if effective != expected:
        raise Refusal(
            "RULE_PARAMS",
            f"variant {variant.variant_id}: effective rule_params {effective!r} "
            f"differ from the registry {expected!r}",
        )


def build_manifest(
    *,
    batch_id: str,
    case_id: str,
    verified: VerifiedInputs,
    variant: Variant,
    script_file: str | None,
    seed: int,
    cli_args: Sequence[str],
    loaded: LoadedCase,
    code_commit: str,
) -> P2CaseManifest:
    trace, tick0, events = loaded.inputs.trace, loaded.inputs.tick0, loaded.inputs.events
    if trace is None or tick0 is None or events is None:
        raise Refusal("NO_MANIFEST", f"{case_id}: the run did not produce a loadable trace")
    initialized = next((e for e in events if e.type == "world_initialized"), None)
    if initialized is None:
        raise Refusal("NO_MANIFEST", f"{case_id}: no world_initialized event")
    policy = policy_config_of(tick0)
    return P2CaseManifest(
        manifest_version=MANIFEST_VERSION,
        case_id=case_id,
        batch_id=batch_id,
        scenario_id=verified.revision.scenario_id,
        revision_label=verified.revision.label,
        scenario_file=verified.revision.scenario_file,
        pin_commit=verified.pin_commit,
        content_revision_sha256=verified.content_revision_sha256,
        script_file=script_file if variant.needs_script else None,
        seed=seed,
        cli_args=list(cli_args),
        policy_id=policy.policy_id,
        policy_variant_id=variant.variant_id,
        rule_params=effective_rule_params(tick0),
        script_sha256=policy.script_sha256,
        policy_config_sha256=canonical_sha256(policy),
        config_sha256=payload_of(initialized).config_hash,
        map_sha256=payload_of(initialized).map_hash,
        run_id=trace.run_id,
        run_dir=f"cases/{case_id}",
        events_sha256=trace.events_sha256,
        decisions_sha256=trace.decisions_sha256,
        final_world_sha256=trace.final_world_sha256,
        code_commit=code_commit,
    )


# ---------------------------------------------------------------------------
# Metric records and writing
# ---------------------------------------------------------------------------


def metric_record(loaded: LoadedCase) -> dict[str, Any]:
    """Validity plus every metric of one case, as JSON-ready data."""
    report: ValidityReport = assess_validity(loaded.inputs)
    record: dict[str, Any] = {
        "valid": report.valid,
        "validity": [dataclasses.asdict(c) for c in report.checks],
        "run": None,
        "death_categories": None,
        "timing": None,
    }
    if loaded.data is not None:
        run = compute_run(loaded.data)
        record["run"] = dataclasses.asdict(run)
        record["death_categories"] = death_categories(loaded.data, run)
        record["timing"] = timing_summaries(list(run.residents))
    return record


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_batch_file(batch_dir: Path, relative: str, text: str) -> Path:
    """Write under ``manifests``, ``variants`` or ``summary`` only; never into a run directory."""
    parts = Path(relative).parts
    if not parts or parts[0] not in WRITABLE_PARTS or ".." in parts:
        raise Refusal("WRITE_SCOPE", f"{relative} is outside manifests/variants/summary")
    path = batch_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def batch_dir_of(repo: Path, batch_id: str) -> Path:
    return repo / RUNS_ROOT / batch_id


def relative_batch(batch_id: str) -> str:
    return f"{RUNS_ROOT}/{batch_id}"


# ---------------------------------------------------------------------------
# Batch command
# ---------------------------------------------------------------------------


@dataclass
class BatchResult:
    batch_id: str
    manifests: list[P2CaseManifest] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures and not self.invalid


def plan_cases(
    repo: Path,
    batch_id: str,
    seeds: Sequence[int],
    specs: Sequence[CaseSpec],
    *,
    ticks: int,
    script_file: str | None,
    code_commit: str,
    registry: Mapping[tuple[str, str], Revision],
    variants: Mapping[str, Variant],
) -> list[tuple[str, int, CaseSpec, Variant, VerifiedInputs, list[str]]]:
    """Check every §6 refusal before any case runs; return the runnable plan."""
    if not is_valid_batch_id(batch_id):
        raise Refusal("BATCH_ID", f"batch_id {batch_id!r} must match [a-z0-9-]+")
    if (batch_dir_of(repo, batch_id)).exists():
        raise Refusal("BATCH_EXISTS", f"{relative_batch(batch_id)} already exists")
    if not seeds or not specs:
        raise Refusal("EMPTY_BATCH", "a batch needs at least one seed and one case")
    verified_by_revision: dict[tuple[str, str, bool], VerifiedInputs] = {}
    planned = []
    seen: set[str] = set()
    for spec in specs:
        variant = variants.get(spec.variant_id)
        if variant is None:
            raise Refusal("VARIANT", f"{spec.variant_id} is not a registered variant")
        extra = [script_file] if variant.needs_script and script_file is not None else []
        if variant.needs_script and script_file is None:
            raise Refusal("SCRIPT_FILE", f"variant {variant.variant_id} needs --script")
        revision = resolve_revision(spec.scenario_id, spec.label, registry)
        key = (spec.scenario_id, spec.label, bool(extra))
        if key not in verified_by_revision:
            verified_by_revision[key] = verify_inputs(repo, revision, code_commit, extra)
        verified = verified_by_revision[key]
        for seed in seeds:
            case_id = case_id_of(spec.scenario_id, spec.label, spec.variant_id, seed)
            if case_id in seen:
                raise Refusal("DUPLICATE_CASE", f"case {case_id} appears twice")
            seen.add(case_id)
            out = f"{relative_batch(batch_id)}/cases/{case_id}"
            policy_args = variant.policy_args(script_file)
            cli_args = build_cli_args(revision.scenario_file, ticks, seed, policy_args, out)
            planned.append((case_id, seed, spec, variant, verified, cli_args))
    return planned


def run_batch(
    batch_id: str,
    seeds: Sequence[int],
    specs: Sequence[CaseSpec],
    *,
    ticks: int | None = None,
    script_file: str | None = None,
    repo: Path = ROOT,
    runner: Runner = run_cli,
    registry: Mapping[tuple[str, str], Revision] = REGISTRY,
    variants: Mapping[str, Variant] = VARIANTS,
) -> BatchResult:
    code_commit = head_commit(repo)
    planned = plan_cases(
        repo,
        batch_id,
        seeds,
        specs,
        ticks=REQUIRED_TICKS if ticks is None else ticks,
        script_file=script_file,
        code_commit=code_commit,
        registry=registry,
        variants=variants,
    )
    batch_dir = batch_dir_of(repo, batch_id)
    result = BatchResult(batch_id)
    for variant in {p[3].variant_id: p[3] for p in planned}.values():
        if variant.rule_params is not None:
            write_batch_file(
                batch_dir,
                f"variants/{variant.variant_id}.json",
                canonical_bytes_text(variant.rule_params.model_dump(mode="json")),
            )
    records: dict[str, dict[str, Any]] = {}
    summaries: list[tuple[CaseSpec, RunSummary]] = []
    for case_id, seed, spec, variant, verified, cli_args in planned:
        print(f"[batch {batch_id}] {case_id}", flush=True)
        done = runner(cli_args, repo)
        write_batch_file(batch_dir, f"summary/logs/{case_id}.log", done.output)
        run_dir = batch_dir / "cases" / case_id
        loaded = load_case(run_dir, cli_exit_code=done.returncode)
        if done.returncode != 0:
            # §0, §4 check 1: a manifest exists only after the CLI exits 0. The exit status is
            # kept nowhere; the case directory without a manifest is what later commands see.
            record = metric_record(loaded)
            records[case_id] = record
            result.invalid.append(case_id)
            if loaded.data is not None:
                summaries.append((spec, summarize_run_of(loaded, case_id, seed, record)))
            continue
        try:
            tick0 = loaded.inputs.tick0
            if tick0 is not None:
                check_rule_params(variant, effective_rule_params(tick0))
            manifest = build_manifest(
                batch_id=batch_id,
                case_id=case_id,
                verified=verified,
                variant=variant,
                script_file=script_file,
                cli_args=cli_args,
                seed=seed,
                loaded=loaded,
                code_commit=code_commit,
            )
        except Refusal as refusal:
            result.failures.append({"case_id": case_id, "refusal": str(refusal)})
            continue
        write_batch_file(
            batch_dir, f"manifests/{case_id}.json", json_text(manifest.model_dump(mode="json"))
        )
        result.manifests.append(manifest)
        record = metric_record(loaded)
        records[case_id] = record
        if not record["valid"]:
            result.invalid.append(case_id)
        if loaded.data is not None:
            summaries.append((spec, summarize_run_of(loaded, case_id, seed, record)))
    write_summaries(batch_dir, result.manifests, records, summaries)
    if result.failures:
        write_batch_file(batch_dir, "summary/failures.json", json_text(result.failures))
    return result


def summarize_run_of(
    loaded: LoadedCase, case_id: str, seed: int, record: dict[str, Any]
) -> RunSummary:
    assert loaded.data is not None
    return summarize_run(
        case_id,
        seed,
        bool(record["valid"]),
        compute_run(loaded.data),
        record["death_categories"] or {},
    )


def canonical_bytes_text(value: Mapping[str, Any]) -> str:
    """Canonical JSON text of a plain mapping (sorted keys, no whitespace)."""
    return canonical_bytes_of_data(dict(value)).decode("utf-8") + "\n"


# ---------------------------------------------------------------------------
# Summaries and the report command
# ---------------------------------------------------------------------------


def write_summaries(
    batch_dir: Path,
    manifests: Sequence[P2CaseManifest],
    records: Mapping[str, dict[str, Any]],
    summaries: Sequence[tuple[CaseSpec, RunSummary]],
) -> None:
    for case_id, record in records.items():
        write_batch_file(batch_dir, f"summary/metrics/{case_id}.json", json_text(record))
    scalar_names = list(S4_SCALARS)
    lines = []
    for manifest in sorted(manifests, key=lambda m: m.case_id):
        record = records.get(manifest.case_id)
        by_case = {s.case_id: s for _, s in summaries}
        summary = by_case.get(manifest.case_id)
        failed = [] if record is None else [c["check"] for c in record["validity"] if not c["ok"]]
        row: dict[str, Any] = {
            "case_id": manifest.case_id,
            "scenario_id": manifest.scenario_id,
            "revision_label": manifest.revision_label,
            "variant": manifest.policy_variant_id,
            "seed": manifest.seed,
            "valid": "" if record is None else str(bool(record["valid"])).lower(),
            "failed_checks": " ".join(map(str, failed)),
        }
        for name in scalar_names:
            row[name] = "" if summary is None else summary.scalars[name]
        lines.append(row)
    columns = [
        "case_id", "scenario_id", "revision_label", "variant", "seed", "valid",
        "failed_checks", *scalar_names,
    ]  # fmt: skip
    path = batch_dir / "summary" / "cases.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(lines)
    comparisons = build_comparisons(summaries)
    if comparisons:
        write_batch_file(batch_dir, "summary/comparisons.json", json_text(comparisons))


def build_comparisons(summaries: Sequence[tuple[CaseSpec, RunSummary]]) -> dict[str, Any]:
    """Per scenario revision: arm reports, paired reports and the pass lines that apply.

    An S4/S5 round is gated on the development seed list only (§1, §2; §4: all 2 x 20 cases exist
    and are valid). The acceptance list is held out for S2 m6/base in P2-05, so a complete set of
    acceptance seeds is a technical FAIL here.
    """
    arms: dict[tuple[str, str], dict[str, dict[int, RunSummary]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for spec, summary in summaries:
        arms[(spec.scenario_id, spec.label)][spec.variant_id][summary.seed] = summary
    report: dict[str, Any] = {}
    for (scenario_id, label), by_variant in sorted(arms.items()):
        entry: dict[str, Any] = {
            "arms": {v: arm_report(list(cases.values())) for v, cases in sorted(by_variant.items())}
        }
        for treatment, scalars in (("canteen-restricted", S4_SCALARS), ("cue-ignored", S5_SCALARS)):
            if "base" in by_variant and treatment in by_variant:
                entry[f"paired_base_vs_{treatment}"] = paired_report(
                    by_variant["base"],
                    by_variant[treatment],
                    scalars,
                    expected_seeds=DEVELOPMENT_SEEDS,
                )
        if "base" in by_variant:
            base_cases = list(by_variant["base"].values())
            entry["behavioral_variation_base"] = behavior_variation(base_cases)
            if scenario_id == "s1-spring-visible":
                entry["s1_line"] = s1_line(base_cases)
            if scenario_id == "s3-regrow288":
                entry["s3_evidence"] = s3_evidence(base_cases)
            if scenario_id == "s2-default" and label == "m6":
                entry["pd05_survival"] = survival_line(base_cases)
        report[f"{scenario_id}.{label}"] = entry
    return report


def read_manifests(batch_dir: Path) -> list[P2CaseManifest]:
    if not batch_dir.is_dir():
        raise Refusal("NO_BATCH", f"{batch_dir} does not exist")
    folder = batch_dir / "manifests"
    if not folder.is_dir():
        return []
    return [
        P2CaseManifest.model_validate_json(path.read_bytes())
        for path in sorted(folder.glob("*.json"))
    ]


def unpublished_cases(batch_dir: Path, manifests: Sequence[P2CaseManifest]) -> list[str]:
    """Case directories without a manifest: the CLI did not exit 0 (§4 check 1), so invalid."""
    folder = batch_dir / "cases"
    published = {m.case_id for m in manifests}
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and p.name not in published)


def missing_cases(batch_dir: Path, manifests: Sequence[P2CaseManifest]) -> list[str]:
    """Registered (manifest) cases whose case directory does not exist."""
    return sorted(m.case_id for m in manifests if not (batch_dir / m.run_dir).is_dir())


def run_report(batch_id: str, *, repo: Path = ROOT) -> dict[str, Any]:
    """Compute metrics from existing case directories; separate from the batch command.

    Inputs are the declared artifacts and manifests only. A manifest exists only after the CLI
    exited 0, so its cases are judged with exit status 0; a case directory without a manifest is
    invalid, and a manifest without a case directory is missing.
    """
    batch_dir = batch_dir_of(repo, batch_id)
    manifests = read_manifests(batch_dir)
    unpublished = unpublished_cases(batch_dir, manifests)
    missing = missing_cases(batch_dir, manifests)
    records: dict[str, dict[str, Any]] = {}
    summaries: list[tuple[CaseSpec, RunSummary]] = []
    for manifest in manifests:
        if manifest.case_id in missing:
            continue
        loaded = load_case(
            batch_dir / manifest.run_dir,
            cli_exit_code=0,
            expected_policy_config_sha256=manifest.policy_config_sha256,
        )
        record = metric_record(loaded)
        records[manifest.case_id] = record
        if loaded.data is not None:
            spec = CaseSpec(
                manifest.scenario_id, manifest.revision_label, manifest.policy_variant_id
            )
            summaries.append(
                (spec, summarize_run_of(loaded, manifest.case_id, manifest.seed, record))
            )
    for case_id in unpublished:
        records[case_id] = metric_record(
            load_case(batch_dir / "cases" / case_id, cli_exit_code=None)
        )
    write_summaries(batch_dir, manifests, records, summaries)
    return {
        "cases": len(manifests) + len(unpublished),
        "invalid": sorted(c for c, r in records.items() if not r["valid"]),
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Rerun command (B08)
# ---------------------------------------------------------------------------

IDENTITY_FIELDS = (
    "events_sha256",
    "decisions_sha256",
    "final_world_sha256",
    "config_sha256",
    "map_sha256",
    "policy_config_sha256",
    "script_sha256",
    "run_id",
    "policy_id",
    "rule_params",
)


def next_rerun_number(repo: Path, batch_id: str) -> int:
    number = 1
    while batch_dir_of(repo, f"{batch_id}-rerun{number}").exists():
        number += 1
    return number


def run_rerun(
    batch_id: str,
    *,
    number: int | None = None,
    repo: Path = ROOT,
    runner: Runner = run_cli,
) -> dict[str, Any]:
    """Rerun every manifest of a batch into ``<batch_id>-rerun<n>`` and compare everything."""
    source_dir = batch_dir_of(repo, batch_id)
    manifests = read_manifests(source_dir)
    unpublished = unpublished_cases(source_dir, manifests)
    missing = missing_cases(source_dir, manifests)
    if not manifests and not unpublished:
        raise Refusal("NO_BATCH", f"{relative_batch(batch_id)} has no cases")
    commits = {m.code_commit for m in manifests}
    head = head_commit(repo)
    if manifests and commits != {head}:
        raise Refusal(
            "CODE_COMMIT", f"rerun at {head}; the manifests were run at {sorted(commits)}"
        )
    n = number if number is not None else next_rerun_number(repo, batch_id)
    rerun_id = f"{batch_id}-rerun{n}"
    rerun_dir = batch_dir_of(repo, rerun_id)
    if rerun_dir.exists():
        raise Refusal("BATCH_EXISTS", f"{relative_batch(rerun_id)} already exists")
    rows = []
    for manifest in manifests:
        out = f"{relative_batch(rerun_id)}/cases/{manifest.case_id}"
        args = replace_out(manifest.cli_args, out)
        done = runner(args, repo)
        write_batch_file(rerun_dir, f"summary/logs/{manifest.case_id}.log", done.output)
        again = load_case(
            rerun_dir / "cases" / manifest.case_id,
            cli_exit_code=done.returncode,
            expected_policy_config_sha256=manifest.policy_config_sha256,
        )
        original = load_case(source_dir / manifest.run_dir, cli_exit_code=0)  # it has a manifest
        mismatches = []
        if manifest.case_id in missing:
            mismatches.append("the source case directory is missing")
        if done.returncode != 0:
            mismatches.append(f"the rerun CLI exited {done.returncode}")
        trace, tick0, events = again.inputs.trace, again.inputs.tick0, again.inputs.events
        if trace is None or tick0 is None or events is None:
            mismatches.append("the rerun did not produce a loadable trace")
        else:
            rebuilt = rebuild_identity(trace, tick0, events)
            for name in IDENTITY_FIELDS:
                if rebuilt[name] != getattr(manifest, name):
                    mismatches.append(name)
        first, second = metric_record(original), metric_record(again)
        if json_text(first) != json_text(second):
            mismatches.append("metrics")
        rows.append(
            {"case_id": manifest.case_id, "identical": not mismatches, "mismatches": mismatches}
        )
    report = {
        "source_batch": batch_id,
        "rerun_batch": rerun_id,
        "code_commit": head,
        "cases": rows,
        "unpublished_cases": unpublished,  # case directory without a manifest: invalid
        "missing_cases": missing,
        "identical": all(r["identical"] for r in rows) and not unpublished and not missing,
    }
    write_batch_file(rerun_dir, "summary/rerun-report.json", json_text(report))
    return report


def rebuild_identity(trace: Any, tick0: SavePackage, events: Sequence[Any]) -> dict[str, Any]:
    initialized = next(e for e in events if e.type == "world_initialized")
    policy = policy_config_of(tick0)
    return {
        "events_sha256": trace.events_sha256,
        "decisions_sha256": trace.decisions_sha256,
        "final_world_sha256": trace.final_world_sha256,
        "config_sha256": payload_of(initialized).config_hash,
        "map_sha256": payload_of(initialized).map_hash,
        "policy_config_sha256": canonical_sha256(policy),
        "script_sha256": policy.script_sha256,
        "run_id": trace.run_id,
        "policy_id": policy.policy_id,
        "rule_params": effective_rule_params(tick0),
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_seeds(seeds: str | None, seed_list: str | None) -> list[int]:
    if (seeds is None) == (seed_list is None):
        raise Refusal("SEEDS", "give exactly one of --seeds and --seed-list")
    if seed_list is not None:
        if seed_list not in SEED_LISTS:
            raise Refusal("SEEDS", f"unknown seed list {seed_list!r}")
        return list(SEED_LISTS[seed_list])
    assert seeds is not None
    try:
        values = [int(part) for part in seeds.split(",") if part]
    except ValueError as exc:
        raise Refusal("SEEDS", f"--seeds must be comma-separated integers: {exc}") from exc
    if any(not 1 <= v <= 0xFFFFFFFF for v in values):
        raise Refusal("SEEDS", "seeds must be in 1..4294967295")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    batch = commands.add_parser("batch", help="run cases of a new batch")
    batch.add_argument("--batch-id", required=True)
    batch.add_argument("--seeds", help="comma-separated seeds")
    batch.add_argument("--seed-list", choices=sorted(SEED_LISTS))
    batch.add_argument("--case", action="append", required=True, metavar="SCENARIO:LABEL:VARIANT")
    batch.add_argument("--script", help="repo-relative script file for p1-scripted cases")
    rerun = commands.add_parser("rerun", help="rerun a batch into <batch_id>-rerun<n> and compare")
    rerun.add_argument("--batch-id", required=True)
    rerun.add_argument("--n", type=int)
    report = commands.add_parser("report", help="compute metrics from existing case directories")
    report.add_argument("--batch-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "batch":
            result = run_batch(
                args.batch_id,
                parse_seeds(args.seeds, args.seed_list),
                [CaseSpec.parse(text) for text in args.case],
                script_file=args.script,
            )
            print(
                f"batch {result.batch_id}: {len(result.manifests)} manifests, "
                f"{len(result.invalid)} invalid, {len(result.failures)} failures"
            )
            for failure in result.failures:
                print(f"  FAILED {failure['case_id']}: {failure['refusal']}", file=sys.stderr)
            for case_id in result.invalid:
                print(f"  INVALID {case_id}", file=sys.stderr)
            return 0 if result.ok else 1
        if args.command == "rerun":
            rerun_report = run_rerun(args.batch_id, number=args.n)
            print(f"rerun {rerun_report['rerun_batch']}: identical={rerun_report['identical']}")
            return 0 if rerun_report["identical"] else 1
        summary = run_report(args.batch_id)
        print(
            f"report {args.batch_id}: {summary['cases']} cases, invalid={summary['invalid']}, "
            f"missing={summary['missing']}"
        )
        return 0
    except Refusal as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
