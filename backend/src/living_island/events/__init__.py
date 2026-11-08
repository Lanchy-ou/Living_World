"""Read-only access to objective world facts and the narrative projection.

Responsibility:
    Re-export the canonical fact models owned by ``living_island.world.facts`` (amendment
    A1) and project them into timelines and stories (``narrative``).

Must NOT:
    Allocate event IDs or define a second event model. Let the narrative invent facts that
    are not in the event log. Import ``living_island.sim`` or ``living_island.persistence``.
"""

from living_island.world.facts import (
    PAYLOAD_MODEL_BY_TYPE,
    EventType,
    TypedEventPayload,
    WorldEvent,
    format_event_id,
)

__all__ = [
    "PAYLOAD_MODEL_BY_TYPE",
    "EventType",
    "TypedEventPayload",
    "WorldEvent",
    "format_event_id",
]
