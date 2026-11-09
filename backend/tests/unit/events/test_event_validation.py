"""The event validator checks facts in emission order without allocating IDs."""

import pytest

from living_island.events import WorldEvent, format_event_id
from living_island.events.validation import EventSequence, EventValidationError, validate_events


def fact(tick: int, seq: int, *causes: str) -> WorldEvent:
    first = (tick, seq) == (0, 0)
    return WorldEvent.model_validate(
        {
            "schema_version": "0.1",
            "run_id": "island",
            "event_id": format_event_id("island", tick, seq),
            "tick": tick,
            "seq_in_tick": seq,
            "type": "world_initialized" if first else "fruit_regrew",
            "actor_id": None,
            "target_id": None,
            "intent_id": None,
            "llm_call_id": None,
            "caused_by_event_ids": list(causes),
            "payload": (
                {"config_hash": "a" * 64, "map_hash": "b" * 64, "initial_snapshot_hash": "c" * 64}
                if first
                else {"tree_id": "fruit_01", "quantity": 1, "stock_before": 0, "stock_after": 1}
            ),
        }
    )


def test_validates_across_batches_and_empty_ticks() -> None:
    initial = fact(0, 0)
    later = fact(3, 0, initial.event_id)
    same_tick = fact(3, 1, initial.event_id, later.event_id)
    before = [event.model_dump() for event in (initial, later, same_tick)]
    validator = EventSequence("island")
    validator.validate([initial, later])
    validator.validate([same_tick])
    assert [event.model_dump() for event in (initial, later, same_tick)] == before


@pytest.mark.parametrize(
    ("events", "field"),
    [
        ([fact(1, 0)], "type"),
        ([fact(0, 0), fact(0, 0)], "event_id"),
        ([fact(0, 0), fact(1, 1)], "seq_in_tick"),
        ([fact(0, 0), fact(1, 0), fact(1, 2)], "seq_in_tick"),
        ([fact(0, 0), fact(2, 0), fact(1, 0)], "tick"),
        ([fact(0, 0), fact(1, 0, fact(2, 0).event_id), fact(2, 0)], "caused_by_event_ids"),
        ([fact(0, 0), fact(1, 0, "unknown")], "caused_by_event_ids"),
        ([fact(0, 0).model_copy(update={"event_id": "bad"})], "event_id"),
        ([fact(0, 0).model_copy(update={"run_id": "other"})], "run_id"),
        ([fact(0, 0).model_copy(update={"payload": fact(1, 0).payload})], "payload"),
    ],
)
def test_invalid_event_sequences(events: list[WorldEvent], field: str) -> None:
    with pytest.raises(EventValidationError) as error:
        validate_events(events, "island")
    assert error.value.field == field


def test_rejected_batch_does_not_advance_history() -> None:
    validator = EventSequence("island")
    first = fact(0, 0)
    with pytest.raises(EventValidationError):
        validator.validate([first, fact(1, 0, "unknown")])
    validator.validate([first, fact(1, 0, first.event_id)])
