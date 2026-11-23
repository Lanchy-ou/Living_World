"""Case-local checkpoint locations, evidence digests and active attempt timing."""

import platform
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from itertools import takewhile
from pathlib import Path
from time import perf_counter_ns, time_ns
from typing import Literal, NamedTuple

from pydantic import NonNegativeInt, PositiveInt

from living_island.persistence.v2.manifest import Digest, RunManifest
from living_island.world.v2.protocol import IntegerJson, ProtocolModel

type State = dict[str, IntegerJson]


class CasePlan(ProtocolModel):
    """Identities supplied by the downstream command before its first tick."""

    revision: str
    runner: str
    controller: str
    setup: str
    observer: str
    arm: str
    case_index: NonNegativeInt
    horizon: NonNegativeInt
    checkpoint_every: PositiveInt
    budget_ns: PositiveInt | None = None


class Inputs(ProtocolModel):
    plan: CasePlan
    content: RunManifest
    seed: int
    config_blob_sha256: Digest
    effective_config_sha256: Digest
    map_blob_sha256: Digest
    map_sha256: Digest
    opening_tick: int
    opening_sha256: Digest


class Cursor(ProtocolModel):
    controller: State
    observer: State
    prefix_sha256: Digest


class Checkpoint(NamedTuple):
    tick: int
    attempt: int
    sha256: str

    @property
    def location(self) -> str:
        return f"checkpoints/{self.attempt}-{self.tick}.json"


class Evidence(ProtocolModel):
    run_id: str
    case_index: int
    inputs_sha256: Digest
    opening_tick: int
    final_tick: int
    final_snapshot_sha256: Digest
    prefix_sha256: Digest
    checkpoint: str
    checkpoint_sha256: Digest
    observer: State
    provider_calls: Literal[0] = 0


class CaseReceipt(ProtocolModel):
    """A PR-07 case receipt extended with relative M13 evidence and timing links."""

    case: str
    projection_sha256: Digest
    difference: None = None
    evidence_path: str
    evidence_sha256: Digest
    timing_db: str


type AttemptStatus = Literal["active", "interrupted", "failed", "paused", "evidence_ready"]


class Attempt(ProtocolModel):
    number: int
    host: str
    started_ns: int
    sampled_ns: int
    active_ns: int
    resumed_tick: int | None
    last_checkpoint_tick: int | None
    attempt_limit_ns: int | None
    status: AttemptStatus
    failure: str | None


class Timing(ProtocolModel):
    attempts: tuple[Attempt, ...]
    active_ns: int
    downtime_ns: int
    unclassified_gap_ns: int
    verdict: Literal["unbudgeted", "partial", "within", "exceeded", "indeterminate"]
    ticks_per_second: float | None


@dataclass(frozen=True)
class Clock:
    def monotonic_ns(self) -> int:
        return perf_counter_ns()

    def wall_ns(self) -> int:
        return time_ns()


def file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


@contextmanager
def case_writer(directory: Path) -> Iterator[sqlite3.Connection]:
    """SQLite releases the exclusive writer on process death, including on Windows."""
    directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(directory / "progress.sqlite", isolation_level=None)) as db:
        db.execute("PRAGMA locking_mode=EXCLUSIVE")
        db.execute("BEGIN EXCLUSIVE")
        db.execute(
            "CREATE TABLE IF NOT EXISTS attempts (number INTEGER PRIMARY KEY, host TEXT,"
            " started_ns INTEGER, sampled_ns INTEGER, active_ns INTEGER, resumed_tick INTEGER,"
            " attempt_limit_ns INTEGER, status TEXT, failure TEXT)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS checkpoints (tick INTEGER PRIMARY KEY,"
            " attempt INTEGER, sha256 TEXT)"
        )
        db.commit()
        db.execute("UPDATE attempts SET status='interrupted' WHERE status='active'")
        yield db


@dataclass
class ActiveAttempt:
    db: sqlite3.Connection
    clock: Clock
    start: int
    number: int

    @classmethod
    def begin(
        cls,
        db: sqlite3.Connection,
        clock: Clock,
        start: int,
        started_ns: int,
        attempt_limit_ns: int | None,
    ) -> "ActiveAttempt":
        (number,) = db.execute("SELECT coalesce(max(number),0)+1 FROM attempts").fetchone()
        db.execute(
            "INSERT INTO attempts VALUES (?,?,?,?,0,NULL,?,'active',NULL)",
            (number, platform.node(), started_ns, started_ns, attempt_limit_ns),
        )
        return cls(db, clock, start, number)

    def sample(self, status: AttemptStatus = "active", failure: str | None = None) -> int:
        elapsed = self.clock.monotonic_ns() - self.start
        self.db.execute(
            "UPDATE attempts SET active_ns=?, sampled_ns=?, status=?, failure=? WHERE number=?",
            (elapsed, self.clock.wall_ns(), status, failure, self.number),
        )
        return elapsed

    def resumed_at(self, tick: int) -> None:
        self.db.execute("UPDATE attempts SET resumed_tick=? WHERE number=?", (tick, self.number))


def checkpoints(db: sqlite3.Connection) -> list[Checkpoint]:
    return [
        Checkpoint(*row)
        for row in db.execute("SELECT tick, attempt, sha256 FROM checkpoints ORDER BY tick")
    ]


def timing(
    db: sqlite3.Connection,
    plan: CasePlan,
    ticks: int,
    finished: bool,
) -> Timing:
    reader = db.execute(
        "SELECT attempts.*, coalesce((SELECT max(tick) FROM checkpoints WHERE attempt=number),"
        " resumed_tick) AS last_checkpoint_tick FROM attempts ORDER BY number"
    )
    fields = [column[0] for column in reader.description]
    attempts = tuple(Attempt(**dict(zip(fields, row, strict=True))) for row in reader)
    # The measurement ends at the first verified durable evidence handoff.
    # Later inspections remain in the history without changing a budget verdict.
    before_handoff = sum(1 for _ in takewhile(lambda a: a.status != "evidence_ready", attempts))
    measured = attempts[: before_handoff + 1]
    active = sum(attempt.active_ns for attempt in measured)
    downtime = gap = 0
    uncertain = any(attempt.status == "interrupted" for attempt in measured)
    for previous, current in zip(measured, measured[1:], strict=False):
        interval = max(0, current.started_ns - previous.sampled_ns)
        if previous.status == "interrupted":
            gap += interval
        else:
            downtime += interval
    verdict: Literal["unbudgeted", "partial", "within", "exceeded", "indeterminate"]
    if plan.budget_ns is None:
        verdict = "unbudgeted"
    elif uncertain:
        verdict = "indeterminate"
    elif not finished:
        verdict = "partial"
    else:
        verdict = "within" if active <= plan.budget_ns else "exceeded"
    return Timing(
        attempts=attempts,
        active_ns=active,
        downtime_ns=downtime,
        unclassified_gap_ns=gap,
        verdict=verdict,
        ticks_per_second=ticks * 1_000_000_000 / active if active and not uncertain else None,
    )
