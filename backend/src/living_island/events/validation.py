"""Read-only validation of event facts in world emission order (IC §3.1)."""

from __future__ import annotations

from collections.abc import Iterable

from living_island.world.facts import PAYLOAD_MODEL_BY_TYPE, WorldEvent, format_event_id


class EventValidationError(ValueError):
    def __init__(self, index: int, field: str, message: str):
        self.index = index
        self.field = field
        super().__init__(message)


class EventSequence:
    """Track validated event IDs for causal checks across batches and checkpoints."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._ids: set[str] = set()
        self._tick = -1
        self._seq = -1

    def validate(self, events: Iterable[WorldEvent]) -> None:
        """Accept a complete ordered batch, updating history only on success."""
        tick, seq = self._tick, self._seq
        batch: set[str] = set()
        for index, event in enumerate(events):
            if event.run_id != self.run_id:
                raise EventValidationError(index, "run_id", f"expected {self.run_id!r}")
            if event.event_id != format_event_id(event.run_id, event.tick, event.seq_in_tick):
                raise EventValidationError(index, "event_id", "does not match format_event_id")
            if event.event_id in self._ids or event.event_id in batch:
                raise EventValidationError(index, "event_id", "duplicate event ID")
            if event.tick < tick:
                raise EventValidationError(index, "tick", "event ticks must be monotonic")
            if tick == -1 and (event.tick != 0 or event.type != "world_initialized"):
                raise EventValidationError(index, "type", "first event must initialize tick zero")
            if event.type == "world_initialized" and tick != -1:
                raise EventValidationError(index, "type", "world_initialized must be first")
            expected = seq + 1 if event.tick == tick else 0
            if event.seq_in_tick != expected:
                raise EventValidationError(index, "seq_in_tick", f"expected {expected}")
            if type(event.payload) is not PAYLOAD_MODEL_BY_TYPE[event.type]:
                raise EventValidationError(index, "payload", f"expected payload for {event.type}")
            for cause in event.caused_by_event_ids:
                if cause not in self._ids and cause not in batch:
                    raise EventValidationError(
                        index, "caused_by_event_ids", f"{cause!r} has not been emitted"
                    )
            batch.add(event.event_id)
            tick, seq = event.tick, event.seq_in_tick
        self._ids.update(batch)
        self._tick, self._seq = tick, seq


def validate_events(events: Iterable[WorldEvent], run_id: str) -> None:
    """Validate events from initialization without changing the events themselves."""
    EventSequence(run_id).validate(events)
