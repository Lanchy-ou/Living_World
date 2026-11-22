"""Durable packet ingestion, partitioned by observed boundary within one run."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import NonNegativeInt, model_validator

from living_island.world.v2.engine import World
from living_island.world.v2.protocol import BoundaryDelivery, VersionedMessage
from living_island.world.v2.rules.schema import canonical_json_bytes

from .._codec import PersistenceError
from .._files import atomic_create


class PacketBatch(VersionedMessage):
    run_id: str
    observed_tick: NonNegativeInt
    packets: tuple[BoundaryDelivery, ...]

    @model_validator(mode="after")
    def check_packets(self) -> "PacketBatch":
        actor_ids = [packet.actor_id for packet in self.packets]
        if actor_ids != sorted(set(actor_ids)) or any(
            packet.observed_tick != self.observed_tick for packet in self.packets
        ):
            raise ValueError("expected one packet per resident in boundary order")
        return self


def store_once(path: Path, data: bytes) -> None:
    """Publish an immutable file, or verify identical bytes on retry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            atomic_create(path, data)
            return
        except PersistenceError:
            if not path.is_file():
                raise
    if path.read_bytes() != data:
        raise ValueError(f"{path}: re-ingestion differs from the stored bytes")


@dataclass(frozen=True)
class PacketJournal:
    directory: Path
    run_id: str

    def _path(self, tick: int) -> Path:
        return self.directory / f"{tick}.json"

    def _pending(self, world: World) -> PacketBatch:
        if world.run_id != self.run_id:
            raise ValueError("packet journal belongs to a different run")
        return PacketBatch.model_construct(
            schema_version="wap/0.1",
            run_id=self.run_id,
            observed_tick=world.tick,
            packets=world.pending_packets(),
        )

    def ingest(self, world: World) -> dict[str, str]:
        """Record exact packets before returning the IDs eligible to acknowledge."""
        batch = self._pending(world)
        store_once(
            self._path(batch.observed_tick), canonical_json_bytes(batch.model_dump(mode="json"))
        )
        return {packet.actor_id: packet.delivery_id for packet in batch.packets}

    def verify(self, world: World) -> dict[str, str]:
        """Compare the replayed packet batch against the recorded bytes."""
        batch = self._pending(world)
        if self._path(batch.observed_tick).read_bytes() != canonical_json_bytes(
            batch.model_dump(mode="json")
        ):
            raise ValueError(f"packet journal differs at boundary {batch.observed_tick}")
        return {packet.actor_id: packet.delivery_id for packet in batch.packets}

    def read(self, tick: int) -> tuple[BoundaryDelivery, ...]:
        data = self._path(tick).read_bytes()
        batch = PacketBatch.model_validate_json(data)
        if (batch.run_id, batch.observed_tick) != (self.run_id, tick):
            raise ValueError("packet batch identity differs from the journal boundary")
        if canonical_json_bytes(batch.model_dump(mode="json")) != data:
            raise ValueError("expected canonical packet journal bytes")
        return batch.packets

    def check_prefix(self, first_tick: int, next_tick: int) -> None:
        """Check that all immutable batches in the checkpoint prefix exist."""
        for tick in range(first_tick, next_tick):
            if not self._path(tick).is_file():
                raise ValueError(f"missing packet journal boundary {tick}")
