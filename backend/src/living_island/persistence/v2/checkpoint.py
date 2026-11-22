"""Publish the world, sim-owned state and the committed packet prefix together."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import NonNegativeInt

from living_island.world.v2.engine import World
from living_island.world.v2.engine.snapshot import encode_snapshot, restore_snapshot
from living_island.world.v2.protocol import IntegerJson, VersionedMessage
from living_island.world.v2.rules import Pack
from living_island.world.v2.rules.schema import canonical_json_bytes

from .._files import atomic_create
from .journal import PacketJournal


class _Checkpoint(VersionedMessage):
    run_id: str
    first_journal_tick: NonNegativeInt
    next_journal_tick: NonNegativeInt
    world_snapshot: str
    sim_checkpoint: dict[str, IntegerJson]


@dataclass(frozen=True)
class RestoredCheckpoint:
    world: World
    sim_checkpoint: dict[str, IntegerJson]
    first_journal_tick: int


def save_checkpoint(
    path: Path,
    world: World,
    journal: PacketJournal,
    sim_checkpoint: dict[str, IntegerJson],
    *,
    first_journal_tick: int = 0,
) -> None:
    """Atomically publish a completed boundary before the next acknowledgement."""
    checkpoint = _Checkpoint(
        schema_version="wap/0.1",
        run_id=world.run_id,
        first_journal_tick=first_journal_tick,
        next_journal_tick=world.tick,
        world_snapshot=encode_snapshot(world).decode("utf-8"),
        sim_checkpoint=sim_checkpoint,
    )
    _check_prefix(checkpoint, journal)
    atomic_create(path, canonical_json_bytes(checkpoint.model_dump(mode="json")))


def load_checkpoint(
    path: Path,
    pack: Pack,
    journal: PacketJournal,
) -> RestoredCheckpoint:
    data = path.read_bytes()
    checkpoint = _Checkpoint.model_validate_json(data)
    if canonical_json_bytes(checkpoint.model_dump(mode="json")) != data:
        raise ValueError("expected canonical checkpoint bytes")
    world = restore_snapshot(checkpoint.world_snapshot.encode("utf-8"), pack)
    if checkpoint.run_id != world.run_id:
        raise ValueError("checkpoint and world must belong to the same run")
    if checkpoint.next_journal_tick != world.tick:
        raise ValueError("checkpoint journal prefix must end before the pending boundary")
    _check_prefix(checkpoint, journal)
    return RestoredCheckpoint(world, checkpoint.sim_checkpoint, checkpoint.first_journal_tick)


def _check_prefix(checkpoint: _Checkpoint, journal: PacketJournal) -> None:
    if checkpoint.run_id != journal.run_id:
        raise ValueError("checkpoint and packet journal must belong to the same run")
    if checkpoint.first_journal_tick > checkpoint.next_journal_tick:
        raise ValueError("checkpoint journal prefix must end before the pending boundary")
    journal.check_prefix(checkpoint.first_journal_tick, checkpoint.next_journal_tick)
