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
from living_island.world.facts import WorldInitializedPayload
from living_island.world.protocol import ProtocolModel

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
    prior = _Prefix((), (), source)
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
    return _Prefix(history, decisions, prior.root)


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


def open_resume_output(
    source_directory: Path,
    output_directory: Path,
    checkpoint_path: Path,
    *,
    prior_events: tuple[WorldEvent, ...] = (),
    trace_directory: Path | None = None,
) -> ResumeOutput:
    """Publish complete bootstrap artifacts for direct users of the storage port."""
    with stage_resume_output(
        source_directory,
        output_directory,
        checkpoint_path,
        prior_events=prior_events,
        trace_directory=trace_directory,
    ) as staged:
        pass
    output = output_directory.resolve()
    # Retain the validated writer sequences while moving their IO target with the files.
    staged.events._path = output / EVENTS_FILENAME
    staged.decisions._path = output / DECISIONS_FILENAME
    return ResumeOutput(
        staged.checkpoint,
        staged.content,
        staged.events,
        staged.decisions,
        staged.script,
        staged.trace,
        staged.history,
        output,
    )
