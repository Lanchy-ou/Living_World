"""Run one case up to its next checkpoint or verified evidence handoff."""

import sqlite3
from collections.abc import Callable, Iterator, Mapping
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
    inputs: Inputs
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

    def evidence(self, history: list[Checkpoint]) -> Evidence:
        # Reopen the final durable files before handing any evidence to the campaign.
        for previous in history[:-1]:
            _checkpoint_path(self.directory, previous)
        point = history[-1]
        restored, cursor = _restore(
            self.directory, point, self.inputs, self.world.pack.source, self.journal
        )
        evidence = Evidence(
            run_id=self.inputs.content.run_id,
            case_index=self.inputs.plan.case_index,
            inputs_sha256=file_digest(self.directory / "inputs.json"),
            opening_tick=self.inputs.opening_tick,
            final_tick=restored.tick,
            final_snapshot_sha256=sha256(encode_snapshot(restored)).hexdigest(),
            prefix_sha256=cursor.prefix_sha256,
            checkpoint=point.location,
            checkpoint_sha256=point.sha256,
            observer=cursor.observer,
        )
        path = self.directory / "evidence.json"
        store_once(path, canonical_json_bytes(evidence.model_dump(mode="json")))
        return Evidence.model_validate_json(path.read_bytes())


def _open(
    directory: Path, scenario: Scenario, inputs: Inputs, attempt: ActiveAttempt
) -> tuple[_Run, Checkpoint]:
    store_once(directory / "inputs.json", canonical_json_bytes(inputs.model_dump(mode="json")))
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
    run = _Run(directory, inputs, world, journal, session, scenario.observe, totals, prefix)
    point = points[-1] if points else run.save(attempt, world.tick)
    attempt.resumed_at(world.tick)
    return run, point


@dataclass(frozen=True)
class Progress:
    tick: int
    checkpoint: str
    evidence: Evidence | None
    timing: Timing


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
    with case_writer(directory) as db:
        attempt = ActiveAttempt.begin(db, clock, attempt_limit_ns)
        try:
            scenario = setup()
            inputs = scenario.inputs(plan)
            run, point = _open(directory, scenario, inputs, attempt)
            end = inputs.opening_tick + plan.horizon
            while run.world.tick < end:
                elapsed = attempt.sample()
                if attempt_limit_ns is not None and elapsed >= attempt_limit_ns:
                    break
                run.advance()
                tick = run.world.tick
                pause = pause_after(tick)
                if pause or tick == end or tick - point.tick == plan.checkpoint_every:
                    point = run.save(attempt, point.tick)
                if pause:
                    break
            else:
                evidence = run.evidence(checkpoints(db))
                attempt.sample("evidence_ready")
                return Progress(
                    point.tick, point.location, evidence, timing(db, plan, plan.horizon, True)
                )
            if point.tick != run.world.tick:
                point = run.save(attempt, point.tick)
            attempt.sample("paused")
            return Progress(
                point.tick,
                point.location,
                None,
                timing(db, plan, point.tick - inputs.opening_tick, False),
            )
        except BaseException as exc:
            attempt.sample("failed", f"{type(exc).__name__}: {exc}")
            raise


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
