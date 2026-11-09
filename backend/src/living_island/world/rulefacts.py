"""Facts produced by the pure physical rule functions (no event IDs).

Rule functions in ``resources``, ``physiology``, ``canteen`` and ``death`` return typed
payloads from ``world/facts.py`` wrapped in a ``PendingFact``. The engine (P1-04) allocates
the event ID, tick and sequence when it appends them through ``append_fact``; nothing here
allocates IDs or touches the event log.

Calling convention for every rule module (use it consistently):

* functions are pure value functions: they never mutate their arguments;
* anything that changes is returned as a new object (a deep copy for whole ``WorldState``);
* the facts come back in catalog order, ready to append in that order;
* callers (P1-04) check action preconditions first; a violated precondition raises
  ``ValueError`` instead of being clamped away.
"""

from __future__ import annotations

from dataclasses import dataclass

from living_island.world.facts import PAYLOAD_MODEL_BY_TYPE, EventType, TypedEventPayload


@dataclass(frozen=True)
class PendingFact:
    """One objective fact waiting for its event ID."""

    type: EventType
    actor_id: str | None
    target_id: str | None
    payload: TypedEventPayload

    def __post_init__(self) -> None:
        if type(self.payload) is not PAYLOAD_MODEL_BY_TYPE[self.type]:
            raise ValueError(f"payload does not match fact type {self.type}")
