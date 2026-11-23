"""Run one case up to its next checkpoint or verified evidence handoff."""

import gzip
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
from living_island.persistence.v2.journal import PacketJournal, store_once
from living_island.persistence.v2.manifest import RunManifest
from living_island.persistence.v2.replay import (
    RecordedBoundary,
    ReplayedBoundary,
    RuleStore,
    replay,
)
from living_island.sim.v2 import cli
from living_island.sim.v2.compat.policy_host import (
    PolicyCheckpoint,
    PolicyHost,
    PolicySession,
    restore_policies,
)
from living_island.sim.v2.manifest import TerminalStop
from living_island.sim.v2.runner import Runner
from living_island.sim.v2.turns import TurnRequest
from living_island.world.v2.engine import TickResult, World
from living_island.world.v2.engine.snapshot import encode_snapshot
from living_island.world.v2.protocol import (
    BoundaryDelivery,
    ModelTurn,
    TurnSubmission,
    encode_event_line,
)
from living_island.world.v2.rules import Pack
from living_island.world.v2.rules.schema import canonical_json_bytes, content_hash

from .receipts import (
    ActiveAttempt,
    CasePlan,
    CaseReceipt,
    Checkpoint,
    Clock,
    Cursor,
    Evidence,
    Inputs,
    State,
    Timing,
    case_writer,
    checkpoints,
    file_digest,
    timing,
)

_TURN = TypeAdapter(RecordedBoundary)
_CLOCK = Clock()


class Script(Protocol):
    """A program owns its position and per-resident work between packet deliveries."""

    def deliver(self, packet: BoundaryDelivery) -> bool: ...
    def choose(self, request: TurnRequest) -> ModelTurn | TerminalStop: ...
    def checkpoint(self) -> State: ...


class Session(Protocol):
    runner: Runner

    def advance(self) -> TickResult | None: ...
    def checkpoint(self) -> State: ...


type SessionFactory = Callable[[World, PacketJournal, State | None], Session]


@dataclass
class _ScriptSession:
    runner: Runner
    script: Script

    def advance(self) -> TickResult | None:
        return self.runner.advance()

    def checkpoint(self) -> State:
        return self.script.checkpoint()


def scripted(restore: Callable[[State | None], Script]) -> SessionFactory:
    def make(world: World, journal: PacketJournal, state: State | None) -> Session:
        script = restore(state)

        def decide(request: TurnRequest) -> TurnSubmission | TerminalStop:
            choice = script.choose(request)
            match choice:
                case TerminalStop():
                    return choice
                case ModelTurn():
                    return request.bind(choice)

        runner = Runner(world, decide, deliver=script.deliver, journal=journal)
        return _ScriptSession(runner, script)

    return make


def rule_based(
    hosts: Callable[[dict[str, PolicyCheckpoint] | None], Mapping[str, PolicyHost]],
) -> SessionFactory:
    def make(world: World, journal: PacketJournal, state: State | None) -> Session:
        restored = None if state is None else restore_policies(state)
        return PolicySession(world, hosts(restored), journal)

    return make


@dataclass(frozen=True)
class Boundary:
    """Objective observer inputs. Read the closing snapshot during this callback."""

    tick: int
    turns: RecordedBoundary
    result: TickResult
    opening_packets: Callable[[], tuple[BoundaryDelivery, ...]]
    closing_snapshot: Callable[[], bytes]


type Observer = Callable[[State, Boundary], State]


@dataclass(frozen=True)
class Scenario:
    """The setup factory supplies a freshly initialized, optionally staged world."""

    world: World
    config_blob_sha256: str
    map_blob_sha256: str
    session: SessionFactory
    observe: Observer

    def inputs(self, plan: CasePlan) -> Inputs:
        state = self.world.state
        return Inputs(
            plan=plan,
            content=RunManifest.capture(self.world.run_id, self.world.pack.source),
            seed=state.seed,
            config_blob_sha256=self.config_blob_sha256,
            effective_config_sha256=state.config_hash,
            map_blob_sha256=self.map_blob_sha256,
            map_sha256=state.map_hash,
            opening_tick=self.world.tick,
            opening_sha256=sha256(encode_snapshot(self.world)).hexdigest(),
        )


def _prefix(directory: Path, previous: str, tick: int) -> str:
    # Bind the exact packet and turn/event bytes in tick order.
    return content_hash(
        [
            previous,
            file_digest(directory / f"packets/{tick}.json"),
            file_digest(directory / f"turns/{tick}.json"),
        ]
    )


def _opening_prefix(directory: Path) -> str:
    return content_hash(
        [file_digest(directory / "inputs.json"), file_digest(directory / "opening-events.jsonl")]
    )


def _checkpoint_path(directory: Path, point: Checkpoint) -> Path:
    path = directory / point.location
    if file_digest(path) != point.sha256:
        raise ValueError(f"checkpoint digest differs at tick {point.tick}")
    return path


def _restore(
    directory: Path, point: Checkpoint, inputs: Inputs, pack: Pack, journal: PacketJournal
) -> tuple[World, Cursor]:
    loaded = load_checkpoint(_checkpoint_path(directory, point), pack, journal)
    cursor = Cursor.model_validate(loaded.sim_checkpoint)
    prefix = _opening_prefix(directory)
    for tick in range(inputs.opening_tick, point.tick):
        prefix = _prefix(directory, prefix, tick)
    if prefix != cursor.prefix_sha256:
        raise ValueError(f"committed witness prefix differs at tick {point.tick}")
    return loaded.world, cursor


@dataclass
class _Run:
    directory: Path
    world: World
    journal: PacketJournal
    session: Session
    observer: Observer
    totals: State
    prefix: str

    def advance(self) -> None:
        tick = self.world.tick
        result = self.session.advance()
        if result is None:
            raise ValueError(
                f"controller stopped at tick {tick}: {self.session.runner.manifest.stop}"
            )
        record = self.session.runner.manifest.boundaries.pop().for_replay()
        store_once(
            self.directory / f"turns/{tick}.json",
            canonical_json_bytes(_TURN.dump_python(record, mode="json")),
        )
        self.prefix = _prefix(self.directory, self.prefix, tick)
        self.totals = self.observer(
            self.totals,
            Boundary(
                tick,
                record,
                deepcopy(result),
                partial(self.journal.read, tick),
                partial(encode_snapshot, self.world),
            ),
        )

    def save(self, attempt: ActiveAttempt, first_tick: int) -> Checkpoint:
        tick = self.world.tick
        path = self.directory / "checkpoints" / f"{attempt.number}-{tick}.json"
        path.parent.mkdir(exist_ok=True)
        cursor = Cursor(
            controller=self.session.checkpoint(), observer=self.totals, prefix_sha256=self.prefix
        )
        save_checkpoint(
            path,
            self.world,
            self.journal,
            cursor.model_dump(mode="json"),
            first_journal_tick=first_tick,
        )
        point = Checkpoint(tick, attempt.number, file_digest(path))
        attempt.db.execute("INSERT INTO checkpoints VALUES (?,?,?)", point)
        return point


def _verified_evidence(
    directory: Path, inputs: Inputs, pack: Pack, history: list[Checkpoint]
) -> Evidence:
    for previous in history[:-1]:
        _checkpoint_path(directory, previous)
    point = history[-1]
    journal = PacketJournal(directory / "packets", inputs.content.run_id)
    restored, cursor = _restore(directory, point, inputs, pack, journal)
    return Evidence(
        run_id=inputs.content.run_id,
        case_index=inputs.plan.case_index,
        inputs_sha256=file_digest(directory / "inputs.json"),
        opening_tick=inputs.opening_tick,
        final_tick=restored.tick,
        final_snapshot_sha256=sha256(encode_snapshot(restored)).hexdigest(),
        prefix_sha256=cursor.prefix_sha256,
        checkpoint=point.location,
        checkpoint_sha256=point.sha256,
        observer=cursor.observer,
    )


def _open(
    directory: Path, scenario: Scenario, inputs: Inputs, attempt: ActiveAttempt
) -> tuple[_Run, Checkpoint]:
    world = scenario.world
    store_once(
        directory / "opening-events.jsonl", b"".join(map(encode_event_line, world.initial_events))
    )
    journal = PacketJournal(directory / "packets", world.run_id)
    points = checkpoints(attempt.db)
    controller = None
    totals: State = {}
    prefix = _opening_prefix(directory)
    if points:
        world, cursor = _restore(directory, points[-1], inputs, world.pack.source, journal)
        controller, totals, prefix = cursor.controller, cursor.observer, cursor.prefix_sha256
    session = scenario.session(world, journal, controller)
    run = _Run(directory, world, journal, session, scenario.observe, totals, prefix)
    point = points[-1] if points else run.save(attempt, world.tick)
    attempt.resumed_at(world.tick)
    return run, point


@dataclass(frozen=True)
class Progress:
    tick: int
    checkpoint: str
    evidence: Evidence | None
    timing: Timing


@dataclass(frozen=True)
class CampaignCase:
    plan: CasePlan
    setup: Callable[[], Scenario]


def _advance(
    directory: Path,
    scenario: Scenario,
    inputs: Inputs,
    attempt: ActiveAttempt,
    pause_after: Callable[[int], bool],
    attempt_limit_ns: int | None,
) -> tuple[Checkpoint, Evidence | None]:
    run, point = _open(directory, scenario, inputs, attempt)
    end = inputs.opening_tick + inputs.plan.horizon
    while run.world.tick < end:
        elapsed = attempt.sample()
        if attempt_limit_ns is not None and elapsed >= attempt_limit_ns:
            break
        run.advance()
        tick = run.world.tick
        pause = pause_after(tick)
        if pause or tick == end or tick - point.tick == inputs.plan.checkpoint_every:
            point = run.save(attempt, point.tick)
        if pause:
            break
    else:
        evidence = _verified_evidence(
            directory, inputs, scenario.world.pack.source, checkpoints(attempt.db)
        )
        path = directory / "evidence.json"
        store_once(path, canonical_json_bytes(evidence.model_dump(mode="json")))
        return point, evidence
    if point.tick != run.world.tick:
        point = run.save(attempt, point.tick)
    return point, None


def _record_case(
    campaign: Path,
    directory: Path,
    case: CampaignCase,
    through: int,
    pause_after: Callable[[int], bool],
    attempt_limit_ns: int | None,
    clock: Clock,
) -> Progress:
    name = str(case.plan.case_index)
    archive = campaign / "inputs" / f"{name}.json.gz"
    receipt = campaign / "cases" / f"{name}.json"
    output = directory / "evidence.json"
    evidence_path = output.relative_to(campaign).as_posix()
    timing_path = (directory / "progress.sqlite").relative_to(campaign).as_posix()
    with case_writer(directory) as db:
        start, wall = clock.monotonic_ns(), clock.wall_ns()
        begin = partial(ActiveAttempt.begin, db, clock, start, wall, attempt_limit_ns)
        attempt = None if receipt.is_file() else begin()
        try:
            scenario = case.setup()
            inputs = scenario.inputs(case.plan)
            pins = canonical_json_bytes(inputs.model_dump(mode="json"))
            if attempt is None:
                # PR-07 checks the registered case name and digest of its immutable input.
                saved = CaseReceipt.model_validate(cli.run_recorded(archive, campaign, through))
                if gzip.decompress(archive.read_bytes()) != pins:
                    raise ValueError(f"{archive}: requested scenario inputs differ")
                evidence = _verified_evidence(
                    directory, inputs, scenario.world.pack.source, checkpoints(db)
                )
                expected = content_hash(evidence.model_dump(mode="json"))
                if (
                    (saved.evidence_path, saved.timing_db) != (evidence_path, timing_path)
                    or saved.evidence_sha256 != expected
                    or file_digest(output) != expected
                ):
                    raise ValueError(f"{receipt}: recorded scenario outputs differ")
                return Progress(
                    evidence.final_tick,
                    evidence.checkpoint,
                    evidence,
                    timing(db, case.plan, case.plan.horizon, True),
                )

            store_once(directory / "inputs.json", pins)
            store_once(archive, gzip.compress(pins, mtime=0))
            point, evidence = _advance(
                directory, scenario, inputs, attempt, pause_after, attempt_limit_ns
            )
            if evidence is None:
                attempt.sample("paused")
                return Progress(
                    point.tick,
                    point.location,
                    None,
                    timing(db, case.plan, point.tick - inputs.opening_tick, False),
                )
            completed = CaseReceipt(
                case=name,
                projection_sha256=file_digest(archive),
                evidence_path=evidence_path,
                evidence_sha256=file_digest(output),
                timing_db=timing_path,
            )
            store_once(receipt, cli.report_bytes(completed.model_dump(mode="json")))
            attempt.sample("evidence_ready")
            return Progress(
                point.tick, point.location, evidence, timing(db, case.plan, case.plan.horizon, True)
            )
        except BaseException as exc:
            (attempt or begin()).sample("failed", f"{type(exc).__name__}: {exc}")
            raise


def run_or_resume(
    directory: Path,
    plan: CasePlan,
    setup: Callable[[], Scenario],
    *,
    pause_after: Callable[[int], bool] = lambda tick: False,
    attempt_limit_ns: int | None = None,
    clock: Clock = _CLOCK,
) -> Progress:
    """Drive a single case in its stable directory. Horizon counts ticks from setup.

    A caller may request a clean pause after any settled tick, including the last.
    A later call with the same pins continues with the checkpoint's pending packet.
    An evidence handoff is ready only after the entire requested horizon verifies.
    """
    cli.bind_evidence(directory, plan.horizon)
    return _record_case(
        directory,
        directory,
        CampaignCase(plan, setup),
        plan.horizon,
        pause_after,
        attempt_limit_ns,
        clock,
    )


def run_campaign(
    directory: Path,
    cases: Sequence[CampaignCase],
    *,
    pause_after: Callable[[int, int], bool] = lambda index, tick: False,
    attempt_limit_ns: int | None = None,
    clock: Clock = _CLOCK,
) -> tuple[Progress, ...]:
    """Verify saved cases in order and resume at the first unfinished checkpoint."""
    indices = [case.plan.case_index for case in cases]
    if len(indices) != len(set(indices)):
        raise ValueError("campaign case indices must be unique")
    through = max((case.plan.horizon for case in cases), default=0)
    cli.bind_evidence(directory, through)
    results = []
    for case in cases:
        index = case.plan.case_index
        progress = _record_case(
            directory,
            directory / "work" / str(index),
            case,
            through,
            partial(pause_after, index),
            attempt_limit_ns,
            clock,
        )
        results.append(progress)
        if progress.evidence is None:
            break
    return tuple(results)


def replay_case(directory: Path, pack: Pack) -> Iterator[ReplayedBoundary]:
    """Replay the verified committed prefix, using recorded turns and no controller."""
    inputs = Inputs.model_validate_json((directory / "inputs.json").read_bytes())
    journal = PacketJournal(directory / "packets", inputs.content.run_id)
    uri = (directory / "progress.sqlite").resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        points = checkpoints(db)
    first, last = points[0], points[-1]
    _restore(directory, last, inputs, pack, journal)
    world, _ = _restore(directory, first, inputs, pack, journal)
    records = (
        _TURN.validate_json((directory / f"turns/{tick}.json").read_bytes())
        for tick in range(first.tick, last.tick)
    )
    yield from replay(
        encode_snapshot(world), inputs.content, pack, journal, RuleStore(directory), records
    )
