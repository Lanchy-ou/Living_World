"""Spool committed display frames and publish the bundle for a completed full run."""

from os import SEEK_END
from pathlib import Path

from pydantic import ValidationError

from living_island.contract.projections import project_frame
from living_island.contract.replay import (
    ConditionBounds,
    DisplayFrame,
    LegendEntry,
    ReplayBundle,
    ReplayClock,
    ReplayMap,
    ReplayResident,
)
from living_island.world.facts import WorldEvent
from living_island.world.protocol import TERRAIN_BY_SYMBOL
from living_island.world.state import WorldState

from ._codec import PersistenceError, decode_model, encode
from ._files import atomic_create, create_file
from .trace import load_trace

FRAMES_FILENAME = "frames.jsonl"
REPLAY_FILENAME = "replay.json"


class FrameSpool:
    """Create the spool on the tick-zero callback, after the runner checks the output."""

    def __init__(self, directory: Path) -> None:
        self.path = directory.resolve() / FRAMES_FILENAME

    def __call__(self, snapshot: WorldState, new_events: tuple[WorldEvent, ...]) -> None:
        frame = project_frame(snapshot, len(new_events))
        raw = encode(frame, self.path, line=snapshot.tick + 1) + b"\n"
        if snapshot.tick == 0:
            create_file(self.path, raw)
            return
        try:
            with self.path.open("r+b") as stream:
                stream.seek(0, SEEK_END)
                stream.write(raw)
        except OSError as exc:
            raise PersistenceError(self.path, "file", str(exc), line=snapshot.tick + 1) from exc


def export_replay(directory: Path) -> None:
    """Publish only after the full frame sequence and verified event log agree."""
    trace = load_trace(directory)
    config = trace.content.config
    spool = directory / FRAMES_FILENAME
    try:
        with spool.open("rb") as stream:
            frames = []
            for line, raw in enumerate(stream, 1):
                if not raw.endswith(b"\n"):
                    raise PersistenceError(spool, "JSONL", "missing final LF", line=line)
                frames.append(decode_model(raw[:-1], DisplayFrame, spool, line=line))
    except OSError as exc:
        raise PersistenceError(spool, "file", str(exc)) from exc
    expected_frames = trace.manifest.final_tick + 1
    if len(frames) != expected_frames:
        raise PersistenceError(spool, "frame_ticks", f"expected {expected_frames} frames")

    path = directory / REPLAY_FILENAME
    try:
        bundle = ReplayBundle(
            replay_schema_version="0.1",
            run_id=trace.manifest.run_id,
            world_id=config.meta.world_id,
            config_hash=trace.content.config_hash,
            map_hash=trace.content.map_hash,
            clock=ReplayClock(
                tick_minutes=config.time.tick_minutes,
                start_hour=config.time.start_hour,
                day_start_hour=config.time.day_start_hour,
                day_end_hour=config.time.day_end_hour,
            ),
            condition_bounds=ConditionBounds(
                min_value=config.needs.min_value, max_value=config.needs.max_value
            ),
            map=ReplayMap(
                width=config.map.width,
                height=config.map.height,
                rows=list(trace.content.map_rows),
                terrain_legend=[
                    LegendEntry(symbol=symbol, terrain=terrain)
                    for symbol, terrain in TERRAIN_BY_SYMBOL.items()
                ],
            ),
            residents=[
                ReplayResident(id=resident.id, display_name=resident.name)
                for resident in sorted(config.residents, key=lambda resident: resident.id)
            ],
            frames=list(frames),
            events=list(trace.events),
        )
    except ValidationError as exc:
        raise PersistenceError(path, "replay", str(exc)) from exc
    atomic_create(path, encode(bundle, path) + b"\n")
