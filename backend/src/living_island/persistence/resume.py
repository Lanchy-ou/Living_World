"""Verify source prefixes and atomically publish a continuation-only run."""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from tempfile import mkdtemp

from living_island.agents.types import DecisionRecord
from living_island.contract.save import SavePackage
from living_island.events import WorldEvent
from living_island.world.content import WorldContent, canonical_json_bytes
from living_island.world.facts import (
    ActionProgressedPayload,
    ActionStartedPayload,
    WorldInitializedPayload,
)
from living_island.world.protocol import ActionPlan, ProtocolModel
from living_island.world.state import ActiveAction

from ._codec import PersistenceError, decode_model, digest, encode, read_bytes, verify_identity
from ._files import atomic_create
from .checkpoints import _decode_checkpoint, _verify_content
from .content import load_run_content, retain_run_content
from .logs import (
    DECISIONS_FILENAME,
    EVENTS_FILENAME,
    DecisionLogWriter,
    EventLogWriter,
    _decisions_from_bytes,
    read_event_prefix,
)
from .scripts import SCRIPT_FILENAME, LoadedScript, load_script
from .trace import LoadedTrace, load_trace

ORIGIN_FILENAME = "resume-origin.json"
_PARENT_FILENAME = "resume-parent.json"


class _ParentLocator(ProtocolModel):
    """Local path hints only. The checkpoint and prefix are verified independently."""

    directory: str
    checkpoint: str


@dataclass(frozen=True)
class ResumeOutput:
    checkpoint: SavePackage
    content: WorldContent
    events: EventLogWriter
    decisions: DecisionLogWriter
    script: LoadedScript | None
    trace: LoadedTrace | None
    history: tuple[WorldEvent, ...]
    directory: Path


def check_output(output: Path, *, source: Path | None = None) -> None:
    if source is not None and output.is_relative_to(source):
        raise PersistenceError(output, "output", "must be outside the source run directory")
    try:
        if os.path.lexists(output) and (not output.is_dir() or any(output.iterdir())):
            raise PersistenceError(output, "output", "expected a new or empty output directory")
    except OSError as exc:
        raise PersistenceError(output, "output", str(exc)) from exc


def _runtime_inputs(
    source: Path,
    path: Path,
    save: SavePackage,
    content: WorldContent,
    trace_directory: Path,
) -> tuple[LoadedScript | None, LoadedTrace | None]:
    script = None
    trace = None
    for runtime in save.agent_state.runtime_states:
        policy = runtime.policy_config
        if policy.script_sha256 is not None:
            if script is None:
                script = load_script(
                    source / SCRIPT_FILENAME, content.config, expected_sha256=policy.script_sha256
                )
            verify_identity(path, "script_sha256", script.sha256, policy.script_sha256)
            actor_script = script.for_actor(runtime.actor_id)
            cursor = runtime.policy_state["cursor"]
            if type(cursor) is not int or cursor != min(
                runtime.next_decision_ordinal, len(actor_script.plans)
            ):
                raise PersistenceError(
                    path, "policy_state.cursor", f"invalid for {runtime.actor_id}"
                )
        if policy.source_trace_sha256 is not None:
            if trace is None:
                trace = load_trace(trace_directory, expected_sha256=policy.source_trace_sha256)
            verify_identity(path, "source_trace_sha256", trace.sha256, policy.source_trace_sha256)
            verify_identity(trace.path, "run_id", trace.manifest.run_id, save.world.run_id)
            verify_identity(
                trace.path, "config_hash", trace.manifest.config_hash, content.config_hash
            )
            verify_identity(trace.path, "map_hash", trace.manifest.map_hash, content.map_hash)
            if runtime.next_decision_ordinal > len(trace.for_actor(runtime.actor_id)):
                raise PersistenceError(
                    path, "next_decision_ordinal", f"exceeds trace for {runtime.actor_id}"
                )
    return script, trace


def _origin(save: SavePackage, raw: bytes) -> bytes:
    return canonical_json_bytes(
        {
            "source_run_id": save.world.run_id,
            "checkpoint_tick": save.world.tick,
            "checkpoint_sha256": digest(raw),
            "event_cursor": save.event_cursor,
            "decision_record_cursor": save.decision_record_cursor,
        }
    )


def _decision_prefix(
    path: Path,
    save: SavePackage,
    prior: tuple[DecisionRecord, ...],
    from_tick: int | None,
) -> tuple[DecisionRecord, ...]:
    remaining = save.decision_record_cursor - len(prior)
    if remaining < 0:
        raise PersistenceError(path, "decision_record_cursor", "earlier history exceeds cursor")
    try:
        with path.open("rb") as stream:
            raw = b"".join(islice(stream, remaining))
            lookahead = stream.readline()
    except OSError as exc:
        raise PersistenceError(path, "file", str(exc)) from exc
    # A complete next line detects an understated cursor. A torn future line is
    # outside the committed prefix, just as it is for the event log.
    if lookahead.endswith(b"\n"):
        raw += lookahead
    records = _decisions_from_bytes(
        path,
        raw,
        save.world.run_id,
        Counter(r.actor_id for r in prior),
        from_tick,
    )
    prefix = prior + tuple(r for r in records if r.tick < save.world.tick)
    if len(prefix) != save.decision_record_cursor:
        raise PersistenceError(path, "decision_record_cursor", "does not match source decisions")
    by_actor = {state.actor_id: state for state in save.agent_state.runtime_states}
    actual = Counter(record.actor_id for record in prefix)
    expected = Counter({actor: state.next_decision_ordinal for actor, state in by_actor.items()})
    if actual != expected:
        raise PersistenceError(path, "next_decision_ordinal", "does not match source decisions")
    if any(record.tick > by_actor[record.actor_id].latest_perception_tick for record in prefix):
        raise PersistenceError(path, "tick", "decision follows its actor's last ingestion")
    return prefix


@dataclass(frozen=True)
class _Prefix:
    events: tuple[WorldEvent, ...]
    decisions: tuple[DecisionRecord, ...]
    root: Path
    initial: SavePackage | None
    has_rule_runtime: bool


def _verify_active_progress(
    path: Path,
    save: SavePackage,
    action: ActiveAction,
    started: WorldEvent,
    progressed: WorldEvent | None,
) -> None:
    if (
        progressed is None
        or progressed.tick != save.world.tick
        or not isinstance(progressed.payload, ActionProgressedPayload)
        or action.tick_started != started.tick - 1
        or action.elapsed_ticks != save.world.tick - action.tick_started
        or (
            action.intent.action_type,
            action.elapsed_ticks,
            action.remaining_ticks,
            action.route_cursor,
        )
        != (
            progressed.payload.action_type,
            progressed.payload.elapsed_ticks,
            progressed.payload.remaining_ticks,
            progressed.payload.route_cursor,
        )
    ):
        raise PersistenceError(path, "active_actions", "active progress differs from event prefix")


def _verify_plan_progress(
    path: Path,
    save: SavePackage,
    events: tuple[WorldEvent, ...],
    decisions: tuple[DecisionRecord, ...],
) -> None:
    """Resolve queues against decisions and their actually started/finished prefix.

    Legacy scheduling commits only while idle and starts the first intent immediately.
    Deferred triggers do not discard the suffix until the next idle scheduling phase;
    failure, interruption and death discard it at the completed boundary itself.
    """
    latest = {record.actor_id: record for record in decisions}
    starts: dict[str, list[WorldEvent]] = {}
    terminals: dict[str, WorldEvent] = {}
    progress: dict[str, WorldEvent] = {}
    for event in events:
        if event.intent_id is None:
            continue
        if event.type == "action_started":
            starts.setdefault(event.intent_id, []).append(event)
        elif event.type in ("action_succeeded", "action_failed", "action_interrupted"):
            terminals[event.intent_id] = event
        elif event.type == "action_progressed":
            progress[event.intent_id] = event

    active = {action.intent.actor_id: action for action in save.world.active_actions}
    expected_active: set[str] = set()
    expected_queues: dict[str, ActionPlan] = {}
    for resident in save.world.residents:
        record = latest.get(resident.id)
        if record is None:
            continue
        plan = record.plan
        count = 0
        terminal = None
        for intent in plan.intents:
            rows = starts.get(intent.intent_id, [])
            if not rows:
                break
            if len(rows) != 1:
                raise PersistenceError(path, "queued_plans", "intent started more than once")
            started = rows[0]
            payload = started.payload
            if (
                started.actor_id != resident.id
                or not isinstance(payload, ActionStartedPayload)
                or (payload.plan_id, payload.action_type) != (plan.plan_id, intent.action_type)
                or (count == 0 and started.tick != record.tick + 1)
                or (count > 0 and (terminal is None or terminal.type != "action_succeeded"))
                or (terminal is not None and started.tick <= terminal.tick)
            ):
                raise PersistenceError(path, "queued_plans", "invalid committed plan progress")
            count += 1
            terminal = terminals.get(intent.intent_id)
            if terminal is None:
                expected_active.add(resident.id)
                action = active.get(resident.id)
                if not resident.alive or action is None or action.intent != intent:
                    raise PersistenceError(
                        path, "active_actions", "active intent differs from committed plan progress"
                    )
                _verify_active_progress(path, save, action, started, progress.get(intent.intent_id))
        if count == 0 or any(intent.intent_id in starts for intent in plan.intents[count:]):
            raise PersistenceError(path, "queued_plans", "started intents must be a plan prefix")
        remaining = plan.intents[count:]
        if (
            resident.alive
            and remaining
            and (terminal is None or terminal.type == "action_succeeded")
        ):
            expected_queues[resident.id] = plan.model_copy(update={"intents": remaining})

    if len(active) != len(save.world.active_actions) or set(active) != expected_active:
        raise PersistenceError(
            path, "active_actions", "active intents differ from committed progress"
        )
    queued = save.agent_state.queued_plans
    if (
        len(queued) != len(expected_queues)
        or {plan.actor_id: plan for plan in queued} != expected_queues
    ):
        raise PersistenceError(
            path, "queued_plans", "must equal the complete unstarted committed plan suffix"
        )


def _verify_policy_identity(path: Path, save: SavePackage, baseline: SavePackage) -> None:
    expected = {r.actor_id: r.policy_config for r in baseline.agent_state.runtime_states}
    actual = {r.actor_id: r.policy_config for r in save.agent_state.runtime_states}
    if actual != expected:
        raise PersistenceError(
            path, "policy_config", "differs from source run policy configuration"
        )


def _prefix(source: Path, output: Path, save: SavePackage, seen: frozenset[Path]) -> _Prefix:
    if source in seen:
        raise PersistenceError(source, "resume parent", "cycle in continuation ancestry")
    check_output(output, source=source)
    origin_path = source / ORIGIN_FILENAME
    prior = _Prefix((), (), source, None, False)
    from_tick = None
    if origin_path.exists():
        locator_path = source / _PARENT_FILENAME
        parent = decode_model(read_bytes(locator_path), _ParentLocator, locator_path)
        checkpoint_path = (source / parent.checkpoint).resolve()
        raw = read_bytes(checkpoint_path)
        checkpoint = _decode_checkpoint(checkpoint_path, raw)
        if read_bytes(origin_path) != _origin(checkpoint, raw):
            raise PersistenceError(origin_path, "checkpoint_sha256", "origin does not match parent")
        if checkpoint.world.tick > save.world.tick:
            raise PersistenceError(origin_path, "checkpoint_tick", "parent is after requested save")
        ancestor = (source / parent.directory).resolve()
        content = load_run_content(
            ancestor,
            expected_config_hash=save.canonical_config_hash,
            expected_map_hash=save.canonical_map_hash,
        )
        _verify_content(checkpoint_path, checkpoint, content)
        _verify_policy_identity(origin_path, save, checkpoint)
        prior = _prefix(ancestor, output, checkpoint, seen | {source})
        from_tick = checkpoint.world.tick
    else:
        initial_path = source / "checkpoint-0000000000.json"
        if initial_path.is_file():
            initial = _decode_checkpoint(initial_path, read_bytes(initial_path))
            _verify_policy_identity(initial_path, save, initial)
            prior = _Prefix((), (), source, initial, False)

    event_path = source / EVENTS_FILENAME
    history = read_event_prefix(
        event_path, save.world.run_id, save.event_cursor, prior=prior.events
    )
    if not history or history[-1].tick > save.world.tick:
        raise PersistenceError(event_path, "event_cursor", "invalid completed checkpoint prefix")
    initialized = history[0].payload
    if not isinstance(initialized, WorldInitializedPayload) or (
        initialized.config_hash,
        initialized.map_hash,
    ) != (save.canonical_config_hash, save.canonical_map_hash):
        raise PersistenceError(event_path, "world_initialized", "does not match retained inputs")
    if from_tick is not None and any(
        event.tick <= from_tick for event in history[len(prior.events) :]
    ):
        raise PersistenceError(event_path, "tick", "expected a post-checkpoint event")
    decisions = _decision_prefix(source / DECISIONS_FILENAME, save, prior.decisions, from_tick)
    _verify_plan_progress(source, save, history, decisions)
    has_rule_runtime = prior.has_rule_runtime or any(
        runtime.policy_config.policy_id == "rule-based-v0"
        for runtime in save.agent_state.runtime_states
    )
    return _Prefix(history, decisions, prior.root, prior.initial, has_rule_runtime)


def _verify_rule_lineage(source: Path, prefix: _Prefix, content: WorldContent) -> None:
    rule_lineage = prefix.has_rule_runtime or any(
        "rule-based-v0" in (record.policy_id, record.effective_policy_id)
        for record in prefix.decisions
    )
    if not rule_lineage:
        return
    path = prefix.root / "checkpoint-0000000000.json"
    initial = prefix.initial
    if initial is None:
        raise PersistenceError(path, "rule_lineage", "missing root tick-zero checkpoint")
    if prefix.root != source:
        content = load_run_content(
            prefix.root,
            expected_config_hash=content.config_hash,
            expected_map_hash=content.map_hash,
        )
    _verify_content(path, initial, content)
    initialized = prefix.events[0].payload
    if (
        initial.world.tick != 0
        or initial.decision_record_cursor != 0
        or initial.event_cursor != sum(event.tick == 0 for event in prefix.events)
        or not isinstance(initialized, WorldInitializedPayload)
        or digest(encode(initial.world, path)) != initialized.initial_snapshot_hash
    ):
        raise PersistenceError(
            path, "rule_lineage", "checkpoint is not the verified tick-zero root"
        )

    # _prefix already verifies identity along every hop and against this root.
    policy_ids = {
        runtime.actor_id: runtime.policy_config.policy_id
        for runtime in initial.agent_state.runtime_states
    }
    for record in prefix.decisions:
        expected = policy_ids[record.actor_id]
        if expected != "recorded-v0" and expected != record.policy_id:
            raise PersistenceError(
                path, "policy_id", f"prefix decision for {record.actor_id} must use {expected}"
            )


def _locator_path(target: Path, output: Path) -> str:
    try:
        return os.path.relpath(target, output)
    except ValueError:
        # Windows cannot express a relative path between separate drives.
        return str(target)


@contextmanager
def stage_resume_output(
    source_directory: Path,
    output_directory: Path,
    checkpoint_path: Path,
    *,
    prior_events: tuple[WorldEvent, ...] = (),
    trace_directory: Path | None = None,
) -> Iterator[ResumeOutput]:
    """Run inside a private sibling directory and publish it only on successful exit."""
    source, output, checkpoint_path = (
        source_directory.resolve(),
        output_directory.resolve(),
        checkpoint_path.resolve(),
    )
    check_output(output, source=source)
    raw = read_bytes(checkpoint_path)
    save = _decode_checkpoint(checkpoint_path, raw)
    content = load_run_content(
        source,
        expected_config_hash=save.canonical_config_hash,
        expected_map_hash=save.canonical_map_hash,
    )
    _verify_content(checkpoint_path, save, content)
    prefix = _prefix(source, output, save, frozenset())
    _verify_rule_lineage(source, prefix, content)
    if prior_events and prefix.events[: len(prior_events)] != prior_events:
        raise PersistenceError(source, "prior_events", "supplied prefix disagrees with ancestry")
    script, trace = _runtime_inputs(
        source,
        checkpoint_path,
        save,
        content,
        trace_directory or prefix.root,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(mkdtemp(prefix=f".{output.name}.resume-", dir=output.parent))
    try:
        atomic_create(stage / ORIGIN_FILENAME, _origin(save, raw))
        locator = stage / _PARENT_FILENAME
        atomic_create(
            locator,
            encode(
                _ParentLocator(
                    directory=_locator_path(source, output),
                    checkpoint=_locator_path(checkpoint_path, output),
                ),
                locator,
            ),
        )
        retain_run_content(stage, content)
        if script is not None:
            script.retain(stage)
        result = ResumeOutput(
            checkpoint=save,
            content=content,
            events=EventLogWriter(
                stage / EVENTS_FILENAME,
                save.world.run_id,
                prior=prefix.events,
                after_tick=save.world.tick,
            ),
            decisions=DecisionLogWriter(
                stage / DECISIONS_FILENAME,
                save.world.run_id,
                ordinals={
                    r.actor_id: r.next_decision_ordinal for r in save.agent_state.runtime_states
                },
                from_tick=save.world.tick,
            ),
            script=script,
            trace=trace,
            history=prefix.events,
            directory=stage,
        )
        yield result
        check_output(output, source=source)
        if output.is_dir():
            output.rmdir()
        stage.rename(output)
    except Exception as exc:
        exc.add_note(f"Unpublished continuation staging directory: {stage}")
        raise
