"""The packet-to-submission port for a v2 resident."""

from typing import Protocol

from living_island.world.v2.protocol import BoundaryDelivery, TurnSubmission


class AgentPort(Protocol):
    def submit(self, packet: BoundaryDelivery, /) -> TurnSubmission:
        """Answer a scheduled turn using the resident's boundary packet."""
        ...
