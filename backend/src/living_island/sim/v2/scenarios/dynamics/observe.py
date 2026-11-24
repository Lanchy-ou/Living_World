"""Collect named, replayable excerpts and admit only expected boundary outcomes."""

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256

from pydantic import BaseModel

from living_island.world.v2.engine.state import Awareness, Entity, Resident
from living_island.world.v2.protocol import BoundaryDelivery, WorldEvent

from ..receipts import State
from ..runtime import Boundary
from .fixture import ACTOR


class Snapshot(BaseModel):
    """Only the objective fields used by the mechanics observer."""

    needs: dict[str, dict[str, int]]
    awareness: dict[str, Awareness]
    entities: dict[str, Entity]
    residents: dict[str, Resident]
    pending_deliveries: dict[str, BoundaryDelivery]


@dataclass(frozen=True)
class Frame:
    boundary: Boundary
    state: Snapshot
    opening: dict[str, BoundaryDelivery]

    @property
    def tick(self) -> int:
        return self.boundary.tick + 1

    def rules(self, rule_id: str, subject: str | None = None) -> tuple[WorldEvent, ...]:
        return tuple(
            event
            for event in self.boundary.result.events
            if event.type == "world_rule_applied"
            and event.payload["rule_id"] == rule_id
            and (subject is None or event.target_id == subject)
        )

    def events(self, kind: str, actor: str = ACTOR) -> tuple[WorldEvent, ...]:
        return tuple(
            event
            for event in self.boundary.result.events
            if event.type == kind and event.actor_id == actor
        )

    def check(self, result: bool, fact: str) -> None:
        if not result:
            raise ValueError(f"completed tick {self.tick}: {fact}")


type Inspection = Callable[[Frame], None]


@dataclass(frozen=True)
class Witness:
    inspect: Inspection
    excerpts: dict[int, str] = field(default_factory=dict)

    def __call__(self, state: State, boundary: Boundary) -> State:
        raw = boundary.closing_snapshot()
        snapshot = Snapshot.model_validate_json(raw)
        opening = {packet.actor_id: packet for packet in boundary.opening_packets()}
        frame = Frame(boundary, snapshot, opening)
        self.inspect(frame)
        label = self.excerpts.get(frame.tick)
        if label is None:
            return state
        return {
            **state,
            label: {
                "completed_tick": frame.tick,
                "snapshot_sha256": sha256(raw).hexdigest(),
                "turns": f"turns/{boundary.tick}.json",
                "opening_packets": f"packets/{boundary.tick}.json",
                "closing_deliveries": [
                    packet.model_dump(mode="json")
                    for packet in snapshot.pending_deliveries.values()
                ],
                "intents": [result.intent_id for result in boundary.result.actions],
                "events": [event.model_dump(mode="json") for event in boundary.result.events],
                **snapshot.model_dump(mode="json", include={"needs", "entities"}),
                "awareness": {
                    actor: awareness.kind for actor, awareness in snapshot.awareness.items()
                },
            },
        }
