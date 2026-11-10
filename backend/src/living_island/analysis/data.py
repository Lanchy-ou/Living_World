"""Parsed-run view used by every metric (P2 experiments §3.0 notation and joins).

``RunData`` holds only parsed objects: the replay frames, the events, the decision records,
the map rows and the few config values the metrics need. It does no file IO.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from living_island.agents.types import DecisionRecord
from living_island.contract.replay import DisplayFrame, ResidentFrame
from living_island.events import WorldEvent


@dataclass(frozen=True)
class RunLimits:
    """Config values read from ``config.json`` (the only config the analysis consumes)."""

    min_value: int
    hydration_gain_per_serving: int
    canteen_capacity: int
    max_stock_per_tree: int
    slot_capacity: int
    tick_minutes: int

    @property
    def day_ticks(self) -> int:
        """``W = 1440 / time.tick_minutes`` (one game day, OQ-065)."""
        return 1440 // self.tick_minutes


def payload_of(event: WorldEvent) -> Any:
    """The typed payload; metrics read named fields per event type."""
    return event.payload


class RunData:
    """One run: frames ``F[0..T]``, events in emission order, decision records, map."""

    def __init__(
        self,
        run_id: str,
        frames: Sequence[DisplayFrame],
        events: Sequence[WorldEvent],
        records: Sequence[DecisionRecord],
        map_rows: Sequence[str],
        limits: RunLimits,
    ) -> None:
        if not frames:
            raise ValueError("a run needs at least the tick-zero frame")
        for index, frame in enumerate(frames):
            if frame.tick != index:
                raise ValueError(f"frame at index {index} has tick {frame.tick}")
        self.run_id = run_id
        self.frames = tuple(frames)
        self.events = tuple(events)
        self.records = tuple(records)
        self.map_rows = tuple(map_rows)
        self.limits = limits
        self.final_tick = self.frames[-1].tick  # T
        self.width = len(self.map_rows[0])
        self.residents = tuple(sorted(r.id for r in self.frames[0].residents))
        self._frame_residents: tuple[dict[str, ResidentFrame], ...] = tuple(
            {r.id: r for r in frame.residents} for frame in self.frames
        )
        self.spring_tiles = frozenset(
            (x, y) for y, row in enumerate(self.map_rows) for x, ch in enumerate(row) if ch == "S"
        )
        self.spring_indices = frozenset(y * self.width + x for x, y in self.spring_tiles)

        by_type: dict[str, list[WorldEvent]] = defaultdict(list)
        for event in self.events:
            by_type[event.type].append(event)
        self._by_type = dict(by_type)

        by_actor: dict[str, list[DecisionRecord]] = defaultdict(list)
        for record in sorted(self.records, key=lambda r: (r.actor_id, r.decision_ordinal)):
            by_actor[record.actor_id].append(record)
        self.records_by_actor = dict(by_actor)

        self.intents: dict[str, tuple[DecisionRecord, Any]] = {}
        for record in self.records:
            for intent in record.plan.intents:
                if intent.intent_id in self.intents:
                    raise ValueError(f"duplicate intent id {intent.intent_id}")
                self.intents[intent.intent_id] = (record, intent)

        self._death: dict[str, WorldEvent] = {}
        for event in self.of_type("resident_died"):
            self._death[payload_of(event).resident_id] = event

    # -- events -------------------------------------------------------------

    def of_type(self, event_type: str) -> list[WorldEvent]:
        return self._by_type.get(event_type, [])

    def death_event(self, resident_id: str) -> WorldEvent | None:
        return self._death.get(resident_id)

    def death_tick(self, resident_id: str) -> int | None:
        event = self._death.get(resident_id)
        return None if event is None else event.tick

    def end(self, resident_id: str) -> int:
        """Observation end: the death tick if the resident died, else ``T``."""
        tick = self.death_tick(resident_id)
        return self.final_tick if tick is None else tick

    # -- frames -------------------------------------------------------------

    def frame_of(self, tick: int, resident_id: str) -> ResidentFrame:
        return self._frame_residents[tick][resident_id]

    def alive(self, tick: int, resident_id: str) -> bool:
        return self._frame_residents[tick][resident_id].alive

    def spring_adjacent(self, position_x: int, position_y: int) -> bool:
        """Manhattan distance exactly 1 from a spring tile (RP F8)."""
        return any(
            (position_x + dx, position_y + dy) in self.spring_tiles
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0))
        )

    def tile_index(self, x: int, y: int) -> int:
        return y * self.width + x
