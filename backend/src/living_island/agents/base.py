"""Resident interface (typing only; no logic)."""

from typing import Protocol

from living_island.world.protocol import ActionPlan, Perception


class Resident(Protocol):
    """Anything that turns a perception into an action plan."""

    def decide(self, perception: Perception) -> ActionPlan: ...
