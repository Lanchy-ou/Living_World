"""World-only recording and deterministic replay from completed boundaries."""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from living_island.world.v2.engine import TickResult, World
from living_island.world.v2.engine.snapshot import encode_snapshot, restore_snapshot
from living_island.world.v2.engine.tick import FallbackFact
from living_island.world.v2.protocol import (
    ProtocolModel,
    TurnSubmission,
    WorldEvent,
    decode,
    encode_event_line,
)
from living_island.world.v2.rules import Pack
from living_island.world.v2.rules.schema import Table

from .journal import PacketJournal, store_once
from .manifest import Digest, RunManifest


class _RuleAdded(ProtocolModel):
    rule_id: str
    content_hash: Digest
    provenance: dict[str, object]


@dataclass(frozen=True)
class RuleStore:
    run_directory: Path

    def _path(self, content_hash: str) -> Path:
        return self.run_directory / "rules" / f"{content_hash}.json"

    def _store(self, content_hash: str, data: bytes) -> None:
        store_once(self._path(content_hash), data)

    def _read(self, addition: _RuleAdded) -> bytes:
        return self._path(addition.content_hash).read_bytes()


@dataclass(frozen=True)
class RecordedBoundary:
    submissions: tuple[TurnSubmission, ...]
    event_lines: bytes
    fallbacks: tuple[FallbackFact, ...] = ()


@dataclass(frozen=True)
class ReplayedBoundary:
    snapshot: bytes
    event_lines: bytes


def record_boundary(
    world: World,
    journal: PacketJournal,
    store: RuleStore,
    submissions: Sequence[TurnSubmission] = (),
    *,
    rule_additions: Sequence[Table] = (),
) -> TickResult:
    """Journal the pending packets and persist new rules before their events."""
    return world.step(
        submissions,
        acknowledged=journal.ingest(world),
        rule_additions=rule_additions,
        store_rule=store._store,
    )


def _verify_rule(expected: Iterator[str], content_hash: str, _data: bytes) -> None:
    recorded_hash = next(expected)
    if content_hash != recorded_hash:
        raise ValueError(f"rule content does not match recorded hash {recorded_hash}")


def replay(
    snapshot: bytes,
    manifest: RunManifest,
    pack: Pack,
    journal: PacketJournal,
    store: RuleStore,
    boundaries: Iterable[RecordedBoundary],
) -> Iterator[ReplayedBoundary]:
    """Replay the log segment following the starting snapshot's event cursor."""
    manifest.check_content(pack)
    world = restore_snapshot(snapshot, pack)
    if world.run_id != manifest.run_id:
        raise ValueError("snapshot belongs to a different run than the manifest")
    for boundary in boundaries:
        events = [decode(WorldEvent, line) for line in boundary.event_lines.splitlines()]
        additions = [
            _RuleAdded.model_validate(event.payload)
            for event in events
            if event.type == "rule_added"
        ]
        files = [store._read(addition) for addition in additions]
        expected = (addition.content_hash for addition in additions)

        result = world.step(
            boundary.submissions,
            acknowledged=journal.verify(world),
            rule_additions=files,
            store_rule=partial(_verify_rule, expected),
            fallbacks=boundary.fallbacks,
        )
        event_lines = b"".join(map(encode_event_line, result.events))
        if event_lines != boundary.event_lines:
            raise ValueError(f"event log differs after replaying boundary {world.tick - 1}")
        yield ReplayedBoundary(encode_snapshot(world), event_lines)
