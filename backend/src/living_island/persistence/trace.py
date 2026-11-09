"""Completion manifests and verified source streams for recorded policy (AI §4.3, §5)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from living_island.agents.types import DecisionRecord, DecisionTraceManifest
from living_island.events import WorldEvent
from living_island.world.content import WorldContent
from living_island.world.state import WorldState

from ._codec import (
    PersistenceError,
    decode_model,
    digest,
    encode,
    read_bytes,
    require_version,
    verify_identity,
)
from ._files import atomic_create
from .content import load_run_content
from .logs import DECISIONS_FILENAME, EVENTS_FILENAME, _decisions_from_bytes, _events_from_bytes

TRACE_FILENAME = "decision-trace.json"


@dataclass(frozen=True)
class LoadedTrace:
    path: Path
    manifest: DecisionTraceManifest
    sha256: str
    content: WorldContent
    events: tuple[WorldEvent, ...]
    _records_by_actor: dict[str, list[DecisionRecord]]

    def for_actor(self, actor_id: str) -> tuple[DecisionRecord, ...]:
        if actor_id not in self._records_by_actor:
            raise PersistenceError(self.path, "actor_id", f"no configured resident {actor_id!r}")
        return tuple(record.model_copy(deep=True) for record in self._records_by_actor[actor_id])


def _trace_records(
    directory: Path,
    manifest: DecisionTraceManifest,
    content: WorldContent,
    events_raw: bytes,
    decisions_raw: bytes,
) -> tuple[tuple[WorldEvent, ...], dict[str, list[DecisionRecord]]]:
    path = directory / TRACE_FILENAME
    run_id = manifest.run_id
    if run_id != content.config.meta.run_id:
        raise PersistenceError(path, "run_id", "must match retained config")
    for field, expected, raw in (
        ("events_sha256", manifest.events_sha256, events_raw),
        ("decisions_sha256", manifest.decisions_sha256, decisions_raw),
    ):
        verify_identity(path, field, digest(raw), expected)

    events_path, decisions_path = directory / EVENTS_FILENAME, directory / DECISIONS_FILENAME
    events = _events_from_bytes(events_path, events_raw, run_id, (), None)
    records = _decisions_from_bytes(decisions_path, decisions_raw, run_id, {}, None)
    if len(events) != manifest.event_count or not events:
        raise PersistenceError(path, "event_count", "must match the nonempty event stream")
    if len(records) != manifest.record_count:
        raise PersistenceError(path, "record_count", "must match the decision stream")
    if events[-1].tick > manifest.final_tick:
        raise PersistenceError(path, "final_tick", "events extend beyond final_tick")

    by_actor: dict[str, list[DecisionRecord]] = {r.id: [] for r in content.config.residents}
    for line, record in enumerate(records, 1):
        if record.tick >= manifest.final_tick:
            raise PersistenceError(
                decisions_path, "tick", "expected a committed decision", line=line
            )
        if record.actor_id not in by_actor:
            raise PersistenceError(
                decisions_path, "actor_id", "not a configured resident", line=line
            )
        by_actor[record.actor_id].append(record)
    return events, by_actor


def load_trace(directory: Path, *, expected_sha256: str | None = None) -> LoadedTrace:
    """Read immutable source inputs. Sim compares final_world_sha256 after re-execution."""
    path = directory / TRACE_FILENAME
    raw = read_bytes(path)
    manifest = decode_model(raw, DecisionTraceManifest, path, version_field="trace_schema_version")
    identity = digest(raw)
    if expected_sha256 is not None:
        verify_identity(path, "source_trace_sha256", identity, expected_sha256)
    content = load_run_content(
        directory, expected_config_hash=manifest.config_hash, expected_map_hash=manifest.map_hash
    )
    events, by_actor = _trace_records(
        directory,
        manifest,
        content,
        read_bytes(directory / EVENTS_FILENAME),
        read_bytes(directory / DECISIONS_FILENAME),
    )
    return LoadedTrace(path, manifest, identity, content, events, by_actor)


def write_trace(directory: Path, final_world: WorldState) -> DecisionTraceManifest:
    """Publish a completion manifest for full logs and the final committed world."""
    path = directory / TRACE_FILENAME
    require_version(path, "world.schema_version", final_world.schema_version)
    content = load_run_content(
        directory,
        expected_config_hash=final_world.config_hash,
        expected_map_hash=final_world.map_hash,
    )
    events_raw = read_bytes(directory / EVENTS_FILENAME)
    decisions_raw = read_bytes(directory / DECISIONS_FILENAME)
    manifest = DecisionTraceManifest(
        trace_schema_version="0.1",
        run_id=final_world.run_id,
        config_hash=content.config_hash,
        map_hash=content.map_hash,
        final_tick=final_world.tick,
        record_count=decisions_raw.count(b"\n"),
        event_count=final_world.event_log_cursor,
        decisions_sha256=digest(decisions_raw),
        events_sha256=digest(events_raw),
        final_world_sha256=digest(encode(final_world, path)),
    )
    _trace_records(directory, manifest, content, events_raw, decisions_raw)
    atomic_create(path, encode(manifest, path))
    return manifest
