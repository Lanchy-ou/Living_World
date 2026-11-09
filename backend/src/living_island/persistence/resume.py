"""Prepare continuation-only output from verified immutable source-run inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from living_island.contract.save import SavePackage
from living_island.events import WorldEvent
from living_island.world.content import WorldContent, canonical_json_bytes

from ._codec import PersistenceError, digest, read_bytes, verify_identity
from ._files import atomic_create
from .checkpoints import _decode_checkpoint, _verify_content
from .content import load_run_content, retain_run_content
from .logs import (
    DECISIONS_FILENAME,
    EVENTS_FILENAME,
    DecisionLogWriter,
    EventLogWriter,
    read_event_prefix,
)
from .scripts import SCRIPT_FILENAME, LoadedScript, load_script
from .trace import LoadedTrace, load_trace

ORIGIN_FILENAME = "resume-origin.json"


@dataclass(frozen=True)
class ResumeOutput:
    checkpoint: SavePackage
    content: WorldContent
    events: EventLogWriter
    decisions: DecisionLogWriter
    script: LoadedScript | None
    trace: LoadedTrace | None


def _check_output(source: Path, output: Path) -> None:
    if output.is_relative_to(source):
        raise PersistenceError(output, "output", "must be outside the source run directory")
    try:
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise PersistenceError(output, "output", "expected a new or empty output directory")
    except OSError as exc:
        raise PersistenceError(output, "output", str(exc)) from exc


def _runtime_inputs(
    source: Path,
    path: Path,
    save: SavePackage,
    content: WorldContent,
    trace_directory: Path | None,
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
            if not isinstance(cursor, int) or not 0 <= cursor <= len(actor_script.plans):
                raise PersistenceError(
                    path, "policy_state.cursor", f"invalid for {runtime.actor_id}"
                )
        if policy.source_trace_sha256 is not None:
            if trace_directory is None:
                raise PersistenceError(path, "source_trace_sha256", "requires a trace directory")
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


def open_resume_output(
    source_directory: Path,
    output_directory: Path,
    checkpoint_path: Path,
    *,
    prior_events: tuple[WorldEvent, ...] = (),
    trace_directory: Path | None = None,
) -> ResumeOutput:
    """Seed continuation writers with history and ordinals from a verified checkpoint.

    Supply the ancestor event prefix when the source is itself a continuation. Records
    from that prefix are used for causal validation and are never copied into the output.
    """
    source = source_directory.resolve()
    output = output_directory.resolve()
    _check_output(source, output)
    raw = read_bytes(checkpoint_path)
    save = _decode_checkpoint(checkpoint_path, raw)
    content = load_run_content(
        source,
        expected_config_hash=save.canonical_config_hash,
        expected_map_hash=save.canonical_map_hash,
    )
    _verify_content(checkpoint_path, save, content)
    script, trace = _runtime_inputs(source, checkpoint_path, save, content, trace_directory)
    world = save.world
    event_path = source / EVENTS_FILENAME
    history = read_event_prefix(event_path, world.run_id, save.event_cursor, prior=prior_events)
    if not history or history[-1].tick > world.tick:
        raise PersistenceError(event_path, "event_cursor", "invalid completed checkpoint prefix")
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PersistenceError(output, "output", str(exc)) from exc
    atomic_create(
        output / ORIGIN_FILENAME,
        canonical_json_bytes(
            {
                "source_run_id": world.run_id,
                "checkpoint_tick": world.tick,
                "checkpoint_sha256": digest(raw),
                "event_cursor": save.event_cursor,
                "decision_record_cursor": save.decision_record_cursor,
            }
        ),
    )
    retain_run_content(output, content)
    if script is not None:
        script.retain(output)
    return ResumeOutput(
        checkpoint=save,
        content=content,
        events=EventLogWriter(
            output / EVENTS_FILENAME, world.run_id, prior=history, after_tick=world.tick
        ),
        decisions=DecisionLogWriter(
            output / DECISIONS_FILENAME,
            world.run_id,
            ordinals={r.actor_id: r.next_decision_ordinal for r in save.agent_state.runtime_states},
            from_tick=world.tick,
        ),
        script=script,
        trace=trace,
    )
