"""Verify or record the preselected M13 D1 rule-based week."""

import gzip
import platform
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, time_ns
from typing import Literal

from pydantic import BaseModel, ConfigDict

from living_island.persistence.v2.journal import store_once
from living_island.persistence.v2.manifest import Digest, RunManifest
from living_island.sim.v2 import cli
from living_island.sim.v2.compat.registry import REGISTRY
from living_island.world.v2.engine import initialize
from living_island.world.v2.engine.snapshot import encode_snapshot
from living_island.world.v2.rules import Pack, load_vocabulary
from living_island.world.v2.rules.schema import content_hash

from ..balance.campaign import D1_SEED, registered
from ..balance.observations import Arm, scenario
from ..calibration.pins import git
from ..calibration.reuse import reusable_evidence
from ..receipts import (
    CasePlan,
    CaseReceipt,
    Checkpoint,
    Evidence,
    Inputs,
    Timing,
    checkpoints,
    file_digest,
)
from ..receipts import timing as read_timing
from ..runtime import _verified_evidence, run_or_resume
from ..starter import load_starter_pack

HORIZON = 1008
BUDGET_NS = 1_800_000_000_000
ARM: Arm = "starter-v1"
POLICY = "rule-based-v0/base/visible"
CHECKPOINT_EVERY = 24
SCENARIOS = "backend/src/living_island/sim/v2/scenarios"
DRIVER = f"{SCENARIOS}/runtime.py"
_SCOPE = ("backend/src", "backend/uv.lock", "backend/tests/fixtures/v1_projection", "content")
# The campaign scope includes unrelated work merged after CT-06. Compare the
# paths that produce the D1 workload when admitting the earlier case.
_WORKLOAD = (
    "backend/src/living_island/world",
    "backend/src/living_island/agents",
    "backend/src/living_island/persistence",
    "backend/src/living_island/sim/equivalence",
    *(
        f"backend/src/living_island/sim/v2/{name}"
        for name in ("cli.py", "compat", "manifest.py", "runner.py", "turns.py")
    ),
    DRIVER,
    *(f"{SCENARIOS}/{name}" for name in ("receipts.py", "starter.py", "balance")),
    *_SCOPE[1:3],
    "content/packs",
    "content/vocabulary",
)


class _Round(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    stage: Literal["acceptance"]
    seeds: list[int]
    d1_seed: int
    horizon: Literal[1008]
    budget_ns: Literal[1800000000000]
    policy: Literal["rule-based-v0/base/visible"]
    checkpoint_every: Literal[24]
    calibration_sha256: Digest
    starter_tree: str
    implementation: Digest
    measurement: str
    host: str
    processor: str
    platform: str
    worker_processes: int

    def plan(self) -> CasePlan:
        return CasePlan(
            arm=ARM,
            budget_ns=BUDGET_NS,
            case_index=1,
            checkpoint_every=CHECKPOINT_EVERY,
            controller=POLICY,
            horizon=HORIZON,
            observer=self.measurement,
            revision=self.implementation,
            runner="CT-04/PR-07",
            setup=content_hash([self.stage, self.seeds, "production"]),
        )


class _Case(BaseModel):
    model_config = ConfigDict(strict=True)
    inputs: Inputs
    case_receipt: str
    evidence: Literal["evidence.json"]
    timing_db: Literal["progress.sqlite"]
    receipt_sha256: Digest
    evidence_sha256: Digest
    timing: Timing | None = None


class _Report(BaseModel):
    model_config = ConfigDict(strict=True)
    stage: Literal["acceptance"]
    technical: Literal["PASS"]
    verdict: Literal["PASS"]
    pins: _Round
    reviewed_head: str
    measurement_tree: str
    d1_case: str
    cases: dict[str, _Case]


class _Scope(BaseModel):
    model_config = ConfigDict(strict=True)
    through: Literal[1008]
    git: dict[str, str]


def _tree_pins(revision: str, paths: tuple[str, ...]) -> dict[str, str]:
    hashes = git("rev-parse", *(f"{revision}:{path}" for path in paths)).splitlines()
    return dict(zip(paths, hashes, strict=True))


def _source_pins(
    balance: Path, revision: str, round_: _Round, measurement_tree: str
) -> dict[str, str]:
    scope = _Scope.model_validate_json((balance / "scope.json").read_bytes())
    if scope.git != _tree_pins(revision, _SCOPE):
        raise ValueError("CT-06 scope does not match the recorded Git revision")
    archived = _tree_pins(revision, _WORKLOAD)
    if (
        archived != _tree_pins("HEAD", _WORKLOAD)
        or subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", *_WORKLOAD], cwd=cli.ROOT
        ).returncode
    ):
        raise ValueError("the registered D1 workload differs from the accepted revision")
    if (
        archived[f"{SCENARIOS}/balance"] != measurement_tree
        or git("rev-parse", f"{revision}:{SCENARIOS}/balance/measurement.py") != round_.measurement
        or git("rev-parse", f"{revision}:content/packs/starter-v1") != round_.starter_tree
    ):
        raise ValueError(
            "the balance measurement or candidate pins differ from the accepted revision"
        )
    return {"source_commit": revision, "driver_git_blob": archived[DRIVER]}


def _expected(directory: Path, round_: _Round) -> tuple[Inputs, Pack, tuple[str, ...]]:
    production = REGISTRY["production"]
    config = directory / "config/production.toml"
    layout = directory / "config" / f"{production.map_digest}.map"
    if (file_digest(config), file_digest(layout)) != (production.digest, production.map_digest):
        raise ValueError("the archived config or S2 m6 map differs from the production registry")
    starter = load_starter_pack(
        config,
        cli.PACK.parent / ARM,
        load_vocabulary(cli.VOCABULARY),
        map_path=layout,
        seed=round_.d1_seed,
    )
    world = initialize(starter.pack, starter.setup)
    residents = tuple(sorted(world.state.residents))
    inputs = Inputs(
        plan=round_.plan(),
        content=RunManifest.capture(world.run_id, starter.pack),
        seed=world.state.seed,
        config_blob_sha256=production.digest,
        effective_config_sha256=world.state.config_hash,
        map_blob_sha256=production.map_digest,
        map_sha256=world.state.map_hash,
        opening_tick=world.tick,
        opening_sha256=sha256(encode_snapshot(world)).hexdigest(),
    )
    return inputs, starter.pack, residents


@contextmanager
def _read_db(directory: Path) -> Iterator[sqlite3.Connection]:
    uri = (directory / "progress.sqlite").resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        yield db


@dataclass(frozen=True)
class Selection:
    directory: Path
    round: _Round
    inputs: Inputs
    residents: tuple[str, ...]
    evidence: Evidence
    timing: Timing | None
    provenance: dict[str, str]


def _select(balance: Path) -> Selection:
    round_path = balance / "round.json"
    round_ = _Round.model_validate_json(round_path.read_bytes())
    if round_.seeds != registered("acceptance") or round_.d1_seed != round_.seeds[0]:
        raise ValueError("the D1 seed must be preselected by the registered acceptance list")
    case_key = f"{round_.d1_seed}/{ARM}"
    report_path = balance / "report.json"
    report = _Report.model_validate_json(report_path.read_bytes())
    if report.pins != round_ or report.d1_case != case_key:
        raise ValueError("the balance report differs from the predeclared D1 registration")
    source = _source_pins(balance, report.reviewed_head, round_, report.measurement_tree)
    directory = balance / case_key
    row = report.cases[case_key]
    expected, pack, residents = _expected(directory, round_)
    inputs_path = directory / "inputs.json"
    raw = inputs_path.read_bytes()
    if len(residents) != 3 or Inputs.model_validate_json(raw) != expected or row.inputs != expected:
        raise ValueError("D1 case inputs differ from the registered three-resident workload")
    receipt_path = directory / "cases/1.json"
    receipt = CaseReceipt.model_validate_json(receipt_path.read_bytes())
    archive = directory / "inputs/1.json.gz"
    evidence_path = directory / row.evidence
    evidence_hash = file_digest(evidence_path)
    evidence = Evidence.model_validate_json(evidence_path.read_bytes())
    if (
        row.case_receipt != "cases/1.json"
        or file_digest(receipt_path) != row.receipt_sha256
        or receipt.case != "1"
        or receipt.projection_sha256 != file_digest(archive)
        or gzip.decompress(archive.read_bytes()) != raw
        or receipt.evidence_path != row.evidence
        or receipt.timing_db != row.timing_db
        or receipt.evidence_sha256 != evidence_hash
        or row.evidence_sha256 != evidence_hash
        or evidence.inputs_sha256 != sha256(raw).hexdigest()
        or evidence.run_id != expected.content.run_id
        or evidence.case_index != 1
        or (evidence.opening_tick, evidence.final_tick) != (0, HORIZON)
    ):
        raise ValueError("CT-06 receipt does not prove a complete matching D1 case")
    db_path = directory / row.timing_db
    measured = None
    timing_digest = None
    if db_path.is_file():
        if reusable_evidence(directory, expected, pack) != evidence:
            raise ValueError("CT-06 case does not match the verified checkpoint")
        with _read_db(directory) as db:
            recorded = read_timing(db, expected.plan, HORIZON, True)
        measured = recorded if recorded.attempts else None
        timing_digest = file_digest(db_path)
    if row.timing is not None and measured != row.timing:
        raise ValueError("CT-06 timing claimed by the report cannot be verified from the database")
    if timing_digest is None:
        attempt, tick = map(int, Path(evidence.checkpoint).stem.split("-"))
        point = Checkpoint(tick, attempt, evidence.checkpoint_sha256)
        if (
            point.location != evidence.checkpoint
            or _verified_evidence(directory, expected, pack, [point]) != evidence
        ):
            raise ValueError("CT-06 case does not match the archived final checkpoint")
    return Selection(
        directory,
        round_,
        expected,
        residents,
        evidence,
        measured,
        {
            **source,
            "balance_report_sha256": file_digest(report_path),
            "balance_round_sha256": file_digest(round_path),
            "case_receipt_sha256": row.receipt_sha256,
            "evidence_sha256": evidence_hash,
            **({"timing_db_sha256": timing_digest} if timing_digest is not None else {}),
        },
    )


type Verdict = Literal["PASS", "BUDGET_MISS", "INDETERMINATE", "PARTIAL"]


def verdict(plan: CasePlan, tick: int, evidence: Evidence | None, measured: Timing) -> Verdict:
    if plan.budget_ns is not None and measured.active_ns > plan.budget_ns:
        return "BUDGET_MISS"
    handoff = None
    for attempt in measured.attempts:
        if attempt.status in ("active", "interrupted") or attempt.active_ns < 0:
            return "INDETERMINATE"
        if attempt.status == "evidence_ready":
            handoff = attempt
            break
    if evidence is None:
        return "PARTIAL"
    if (
        tick != plan.horizon
        or evidence.final_tick != tick
        or handoff is None
        or handoff.last_checkpoint_tick != tick
        or measured.active_ns <= 0
        or measured.verdict != "within"
    ):
        return "INDETERMINATE"
    return "PASS"


def _record(selection: Selection, out: Path) -> tuple[int, Evidence | None, Timing]:
    directory = out / "case"
    plan = selection.inputs.plan
    existing = (directory / "progress.sqlite").is_file()
    prior = 0
    if existing:
        with _read_db(directory) as db:
            points = checkpoints(db)
            tick = points[-1].tick if points else 0
            measured = read_timing(db, plan, tick, False)
        prior = measured.active_ns
        # Keep the previous measurement even if an earlier invocation stopped
        # before publishing the CT-10 summary.
        if prior >= BUDGET_NS and not (directory / "cases/1.json").is_file():
            return tick, None, measured
    progress = run_or_resume(
        directory,
        plan,
        lambda: scenario(directory, selection.inputs.seed, ARM),
        attempt_limit_ns=max(1, BUDGET_NS - prior),
    )
    return progress.tick, progress.evidence, progress.timing


def publish(balance: Path, out: Path, *, verify_only: bool = False) -> tuple[Verdict, Path]:
    started = perf_counter_ns()
    selection = _select(balance)
    verification_ns = perf_counter_ns() - started
    plan = selection.inputs.plan
    round_ = selection.round
    host = {"host": round_.host, "processor": round_.processor, "platform": round_.platform}
    execution = {"worker_processes": round_.worker_processes, **host}
    provenance = selection.provenance
    measured = selection.timing
    evidence: Evidence | None = selection.evidence
    tick = selection.evidence.final_tick
    directory = selection.directory
    reused = measured is not None
    if measured is None:
        if verify_only:
            raise ValueError("timing was never captured for the selected treatment case")
        directory = out / "case"
        execution = {
            "host": platform.node(),
            "processor": platform.processor(),
            "platform": platform.platform(),
            "worker_processes": 1,
        }
        source = {
            "source_commit": git("rev-parse", "HEAD"),
            "driver_git_blob": git("rev-parse", f"HEAD:{DRIVER}"),
        }
        registration = {"execution": execution, **source, **provenance}
        store_once(out / "recording.json", cli.report_bytes(registration))
        tick, evidence, measured = _record(selection, out)
        provenance = {**provenance, **source}
        if evidence is not None:
            provenance.update(
                case_receipt_sha256=file_digest(directory / "cases/1.json"),
                evidence_sha256=file_digest(directory / "evidence.json"),
            )
        provenance["timing_db_sha256"] = file_digest(directory / "progress.sqlite")
    result = verdict(plan, tick, evidence, measured)
    record = {
        "verdict": result,
        "reused_acceptance_case": reused,
        "case": str(directory.resolve()),
        "original_d1_seed": D1_SEED,
        "geometry": "S2 m6 production",
        "resident_ids": selection.residents,
        "inputs": selection.inputs.model_dump(mode="json"),
        "calibration_sha256": round_.calibration_sha256,
        "starter_tree": round_.starter_tree,
        "execution": execution,
        "provenance": provenance,
        "last_committed_tick": tick,
        "checkpoint": evidence.checkpoint if evidence else None,
        "checkpoint_sha256": evidence.checkpoint_sha256 if evidence else None,
        "provider_calls": evidence.provider_calls if evidence else None,
        "elapsed_seconds": measured.active_ns / 1_000_000_000,
        "timing": measured.model_dump(mode="json"),
        "excluded_time": (
            "Between recorded stops and restarts; attempt statuses retain the reasons. "
            "An unclassified gap cannot substantiate a pass."
        ),
    }
    payload = cli.report_bytes(record)
    path = out / "reports" / f"{sha256(payload).hexdigest()}.json"
    store_once(path, payload)
    if result in ("PASS", "BUDGET_MISS") or reused:
        path = out / "receipt.json"
        store_once(path, payload)
    store_once(
        out / "verification" / f"{time_ns()}.json",
        cli.report_bytes(
            {
                "receipt_sha256": file_digest(path),
                "independent_verification_ns": verification_ns,
            }
        ),
    )
    return result, path
