"""Resident interface (typing only; no logic)."""

from typing import Protocol

from living_island.world.protocol import ActionIntent, Observation


class Resident(Protocol):
    """Anything that turns an observation into an intent proposal."""

    def decide(self, observation: Observation) -> ActionIntent: ...
