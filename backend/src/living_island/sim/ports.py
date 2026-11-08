"""Sim-side ports (implementation plan §2.1).

``BoundaryObserver`` is a synchronous callback invoked once per committed boundary
(fresh tick zero and each newly completed tick). It is not an agent interface.
"""

from __future__ import annotations

from typing import Protocol

from living_island.world.facts import WorldEvent
from living_island.world.state import WorldState


class BoundaryObserver(Protocol):
    def __call__(self, snapshot: WorldState, new_events: tuple[WorldEvent, ...]) -> None:
        raise NotImplementedError
