"""Run or inspect a calibrated P2 list under the CT-04 receipt protocol."""

import os
import platform
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from time import time_ns
from typing import Any, Literal

from living_island.persistence.v2.journal import store_once
from living_island.sim.v2 import cli
from living_island.world.v2.rules.schema import content_hash

from ..calibration.campaign import require_calibration
from ..calibration.pins import git
from ..calibration.reuse import reusable_evidence
from ..receipts import CasePlan, file_digest, timing
from ..runtime import run_or_resume
from .measurement import measure
from .observations import Arm, scenario
from .report import ARMS, Case, report

EN08 = "f8142919376de0ea2125fe3e443629c82dce8166"
D1_SEED = 2600456787
type Stage = Literal["development", "acceptance"]


def registered(stage: Stage) -> list[int]:
    prefix = (
        "development-s2-orig-base-" if stage == "development" else "acceptance-production-base-"
    )
    seeds = [
        int(name.removeprefix(prefix)) for name in cli.matrix_names() if name.startswith(prefix)
    ]
    if stage == "acceptance":
        seeds.remove(D1_SEED)
        seeds.insert(0, D1_SEED)
    return seeds


@dataclass(frozen=True)
class Job:
    out: Path
    seed: int
    arm: Arm
    plan: CasePlan
    inspect: bool
    reuse: tuple[Path, ...]


def execute(job: Job) -> Case:
    sub = Path(str(job.seed)) / job.arm
    directory = job.out / sub
    setup = partial(scenario, directory, job.seed, job.arm)
    prepared = setup()
    inputs = prepared.inputs(job.plan)
    for parent in (*job.reuse, job.out):
        source = parent / sub
        evidence = reusable_evidence(source, inputs, prepared.world.pack.source)
        if evidence is not None:
            uri = (source / "progress.sqlite").resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as db:
                elapsed = timing(db, job.plan, job.plan.horizon, True)
            directory = source
            break
    else:
        if job.inspect:
            raise ValueError("missing or mismatched completed receipt")
        progress = run_or_resume(directory, job.plan, setup)
        evidence = progress.evidence
        assert evidence is not None
        elapsed = progress.timing
    measured = measure(directory, evidence, job.seed)
    return Case(
        str(directory.resolve()),
        inputs,
        file_digest(directory / "cases" / f"{job.plan.case_index}.json"),
        file_digest(directory / "evidence.json"),
        elapsed,
        measured,
    )


def campaign(
    stage: Stage,
    calibration: Path,
    digest: str,
    out: Path,
    jobs: int,
    *,
    inspect: bool,
    reuse: tuple[Path, ...],
) -> dict[str, Any]:
    if not 1 <= jobs <= 4:
        raise ValueError("jobs must be 1 through 4")
    receipt = require_calibration(calibration, en08_revision=EN08, receipt_sha256=digest)
    seeds = registered(stage)
    revision = content_hash(
        [
            receipt.executable,
            git("rev-parse", "HEAD:backend/src/living_island/sim/v2/scenarios/starter.py"),
            git(
                "rev-parse",
                "HEAD:backend/src/living_island/sim/v2/scenarios/balance/observations.py",
            ),
        ]
    )
    # Pin the whole candidate and list before opening the first pair.
    scope = {
        "stage": stage,
        "seeds": seeds,
        "calibration_sha256": digest,
        "en08": EN08,
        "starter_tree": git("rev-parse", "HEAD:content/packs/starter-v1"),
        "implementation": revision,
        "measurement": git(
            "rev-parse", "HEAD:backend/src/living_island/sim/v2/scenarios/balance/measurement.py"
        ),
        "host": platform.node(),
        "processor": platform.processor(),
        "platform": platform.platform(),
        "worker_processes": jobs,
        "reuse": [str(p.resolve()) for p in reuse],
        "checkpoint_every": 24,
        "horizon": 1008,
        "policy": "rule-based-v0/base/visible",
        "d1_seed": D1_SEED,
        "budget_ns": 1800_000_000_000,
    }
    cli.bind_evidence(out, 1008)
    store_once(out / "round.json", cli.report_bytes(scope))
    failures = {}
    results = {}
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        pending = {}
        for index, seed in enumerate(seeds):
            for arm in ARMS:
                plan = CasePlan(
                    revision=revision,
                    runner="CT-04/PR-07",
                    controller="rule-based-v0/base/visible",
                    setup=content_hash([stage, seeds, "production"]),
                    observer=str(scope["measurement"]),
                    arm=arm,
                    case_index=index * 2 + ARMS.index(arm),
                    horizon=1008,
                    checkpoint_every=24,
                    budget_ns=1800_000_000_000
                    if stage == "acceptance" and seed == D1_SEED
                    else None,
                )
                pending[seed, arm] = pool.submit(execute, Job(out, seed, arm, plan, inspect, reuse))
        for key, future in pending.items():
            try:
                results[key] = future.result()
            except Exception as exc:
                failure = f"{type(exc).__name__}: {exc}"
                failures[f"{key[0]}/{key[1]}"] = failure
                store_once(
                    out / "failures" / f"{key[0]}-{key[1]}-{time_ns()}.json",
                    cli.report_bytes(failure),
                )
    result = report(seeds, results, failures, stage)
    result["pins"] = scope
    result["reviewed_head"] = git("rev-parse", "HEAD")
    result["measurement_tree"] = git(
        "rev-parse", "HEAD:backend/src/living_island/sim/v2/scenarios/balance"
    )
    data = cli.report_bytes(result)
    store_once(out / "reports" / f"{content_hash(result)}.json", data)
    tmp = out / f"report-{os.getpid()}.tmp"
    tmp.write_bytes(data)
    tmp.replace(out / "report.json")
    return result
