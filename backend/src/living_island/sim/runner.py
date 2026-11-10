"""Bootstrap, publish, resume, and re-execute committed simulations."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from living_island.agents.base import ResidentRuntime
from living_island.agents.policies.recorded import ReplayDiverged
from living_island.agents.runtime import create_runtime
from living_island.agents.types import (
    DecisionRecord,
    OwnProfile,
    PolicyConfig,
    PolicyId,
    RuleParams,
)
from living_island.contract.save import SavePackage
from living_island.persistence.checkpoints import write_checkpoint
from living_island.persistence.content import retain_run_content
from living_island.persistence.logs import (
    DECISIONS_FILENAME,
    EVENTS_FILENAME,
    DecisionLogWriter,
    EventLogWriter,
)
from living_island.persistence.resume import check_output, stage_resume_output
from living_island.persistence.scripts import LoadedScript
from living_island.persistence.trace import LoadedTrace, load_trace, write_trace
from living_island.sim.boundary import BoundaryLoop
from living_island.sim.ports import BoundaryObserver
from living_island.world.content import WorldContent, canonical_json_bytes
from living_island.world.ports import WorldTickCommit, create_engine
from living_island.world.state import WorldState


@dataclass(frozen=True)
class RunResult:
    world: WorldState
    decision_record_cursor: int
    output: Path

    @property
    def world_sha256(self) -> str:
        return sha256(canonical_json_bytes(self.world.model_dump(mode="json"))).hexdigest()


def checkpoint_filename(tick: int) -> str:
    return f"checkpoint-{tick:010d}.json"


def _runtime_roster(
    content: WorldContent,
    policy_id: PolicyId | None,
    script: LoadedScript | None,
    trace: LoadedTrace | None,
    checkpoint: SavePackage | None = None,
    *,
    rule_params: RuleParams | None = None,
) -> list[ResidentRuntime]:
    cfg = content.config
    config = (
        PolicyConfig(
            policy_id=policy_id,
            seed=cfg.meta.seed,
            max_plan_actions=cfg.agents.max_plan_actions,
            map_width=cfg.map.width,
            map_height=cfg.map.height,
            script_sha256=script.sha256 if script is not None else None,
            source_trace_sha256=trace.sha256 if trace is not None else None,
            **({"rule_params": rule_params} if rule_params is not None else {}),
        )
        if policy_id is not None
        else None
    )
    saved = (
        {state.actor_id: state for state in checkpoint.agent_state.runtime_states}
        if checkpoint is not None
        else {}
    )
    runtimes = []
    for actor in sorted(cfg.residents, key=lambda actor: actor.id):
        restored = saved.get(actor.id)
        selected = restored.policy_config if restored is not None else config
        if selected is None:
            raise ValueError(f"{actor.id}: missing restored policy config")
        runtimes.append(
            create_runtime(
                actor.id,
                selected,
                OwnProfile(profile_id=actor.profile_id, initial_goal=actor.initial_goal),
                script.for_actor(actor.id)
                if script is not None and selected.policy_id == "scripted-v0"
                else None,
                trace.for_actor(actor.id)
                if trace is not None and selected.policy_id == "recorded-v0"
                else None,
                restored,
            )
        )
    return runtimes


class _ReplayCheck:
    def __init__(self, trace: LoadedTrace, start_cursor: int = 0) -> None:
        self._trace = trace
        self._event_cursor = start_cursor

    def boundary(self, commit: WorldTickCommit) -> None:
        end = self._event_cursor
        expected = self._trace.events
        while end < len(expected) and expected[end].tick <= commit.snapshot.tick:
            end += 1
        if len(commit.events) != end - self._event_cursor or any(
            canonical_json_bytes(actual.model_dump(mode="json"))
            != canonical_json_bytes(wanted.model_dump(mode="json"))
            for actual, wanted in zip(
                commit.events, expected[self._event_cursor : end], strict=True
            )
        ):
            raise ReplayDiverged(f"event bytes differ at tick {commit.snapshot.tick}")
        self._event_cursor = end

    def finish(self, result: RunResult) -> None:
        manifest = self._trace.manifest
        if self._event_cursor != manifest.event_count:
            raise ReplayDiverged("unconsumed source events")
        if result.decision_record_cursor != manifest.record_count:
            raise ReplayDiverged("unconsumed source decisions")
        if result.world_sha256 != manifest.final_world_sha256:
            raise ReplayDiverged("final world hash differs from source manifest")


def _drive(
    loop: BoundaryLoop,
    ticks: int,
    output: Path,
    events: EventLogWriter,
    decisions: DecisionLogWriter,
    observer: BoundaryObserver | None,
    *,
    fresh: bool,
    checkpoint_every: int | None = None,
    replay: _ReplayCheck | None = None,
) -> RunResult:
    final_tick = loop.boundary.snapshot.tick + ticks

    def checkpoint() -> None:
        save = loop.checkpoint()
        write_checkpoint(output / checkpoint_filename(save.world.tick), save)

    def publish(commit: WorldTickCommit, records: list[DecisionRecord]) -> None:
        if replay is not None:
            replay.boundary(commit)
        events.append(commit.events)
        decisions.append(records)
        if observer is not None:
            observer(
                commit.snapshot.model_copy(deep=True),
                tuple(event.model_copy(deep=True) for event in commit.events),
            )
        tick = commit.snapshot.tick
        if tick in (0, final_tick) or (
            checkpoint_every is not None and tick % checkpoint_every == 0
        ):
            checkpoint()

    if fresh:
        publish(loop.boundary, [])
    elif ticks == 0:
        checkpoint()
    for _ in range(ticks):
        commit, records = loop.advance()
        publish(commit, records)
    return RunResult(loop.boundary.snapshot, loop.decision_record_cursor, output)


def _validate_length(ticks: int, checkpoint_every: int | None = None) -> None:
    if ticks < 0:
        raise ValueError("ticks must be nonnegative")
    if checkpoint_every is not None and checkpoint_every <= 0:
        raise ValueError("checkpoint interval must be positive")


def _fresh_run(
    content: WorldContent,
    ticks: int,
    output: Path,
    policy_id: PolicyId,
    script: LoadedScript | None,
    trace: LoadedTrace | None,
    checkpoint_every: int | None,
    on_boundary_committed: BoundaryObserver | None,
    *,
    rule_params: RuleParams | None = None,
) -> RunResult:
    output = output.resolve()
    check_output(output, source=trace.path.parent.resolve() if trace is not None else None)
    loop = BoundaryLoop(
        create_engine(content, None),
        _runtime_roster(
            content,
            policy_id,
            script,
            trace,
            rule_params=rule_params,
        ),
    )
    output.mkdir(parents=True, exist_ok=True)
    try:
        retain_run_content(output, content)
        if script is not None:
            script.retain(output)
        run_id = content.config.meta.run_id
        replay = _ReplayCheck(trace) if trace is not None else None
        result = _drive(
            loop,
            ticks,
            output,
            EventLogWriter(output / EVENTS_FILENAME, run_id),
            DecisionLogWriter(output / DECISIONS_FILENAME, run_id),
            on_boundary_committed,
            fresh=True,
            checkpoint_every=checkpoint_every,
            replay=replay,
        )
        if replay is not None:
            replay.finish(result)
        write_trace(output, result.world)
    except Exception as exc:
        exc.add_note(f"Incomplete run output at {output}. Use a new --out directory to retry.")
        raise
    return result


def run(
    content: WorldContent,
    ticks: int,
    output: Path,
    *,
    script: LoadedScript | None = None,
    rule_params: RuleParams | None = None,
    checkpoint_every: int | None = None,
    on_boundary_committed: BoundaryObserver | None = None,
) -> RunResult:
    """Start a fresh random, scripted or rule-based run."""
    _validate_length(ticks, checkpoint_every)
    if script is not None and rule_params is not None:
        raise ValueError("script and rule_params are mutually exclusive")
    policy_id: PolicyId = "random-v0"
    if script is not None:
        policy_id = "scripted-v0"
    elif rule_params is not None:
        policy_id = "rule-based-v0"
    return _fresh_run(
        content,
        ticks,
        output,
        policy_id,
        script,
        None,
        checkpoint_every,
        on_boundary_committed,
        rule_params=rule_params,
    )


def resume(
    checkpoint: Path,
    source_run: Path,
    ticks: int,
    output: Path,
    *,
    on_boundary_committed: BoundaryObserver | None = None,
) -> RunResult:
    _validate_length(ticks)
    with stage_resume_output(source_run, output, checkpoint) as staged:
        save = staged.checkpoint
        runtimes = _runtime_roster(staged.content, None, staged.script, staged.trace, save)
        loop = BoundaryLoop(
            create_engine(staged.content, save.world, staged.history),
            runtimes,
            save,
        )
        replay = None
        if staged.trace is not None:
            if save.world.tick + ticks > staged.trace.manifest.final_tick:
                raise ReplayDiverged("requested continuation extends beyond the source trace")
            if staged.history != staged.trace.events[: save.event_cursor]:
                raise ReplayDiverged("checkpoint event prefix differs from the source trace")
            replay = _ReplayCheck(staged.trace, save.event_cursor)
        result = _drive(
            loop,
            ticks,
            staged.directory,
            staged.events,
            staged.decisions,
            on_boundary_committed,
            fresh=False,
            replay=replay,
        )
        if replay is not None and staged.trace is not None:
            if result.world.tick == staged.trace.manifest.final_tick:
                replay.finish(result)
    return RunResult(result.world, result.decision_record_cursor, output.resolve())


def reexecute(
    source_run: Path,
    output: Path,
    *,
    on_boundary_committed: BoundaryObserver | None = None,
) -> RunResult:
    try:
        trace = load_trace(source_run.resolve())
    except (ValueError, OSError) as exc:
        raise ReplayDiverged(str(exc)) from exc
    return _fresh_run(
        trace.content,
        trace.manifest.final_tick,
        output,
        "recorded-v0",
        None,
        trace,
        None,
        on_boundary_committed,
    )
