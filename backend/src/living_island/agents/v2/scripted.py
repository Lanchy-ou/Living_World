"""Fixed, per-resident submissions for coordinator tests."""

from collections import deque
from collections.abc import Mapping, Sequence

from living_island.world.v2.protocol import BoundaryDelivery, TurnSubmission


class ScriptedAgent:
    def __init__(self, scripts: Mapping[str, Sequence[TurnSubmission]]) -> None:
        self._remaining = {actor_id: deque(script) for actor_id, script in scripts.items()}

    def submit(self, packet: BoundaryDelivery, /) -> TurnSubmission:
        return self._remaining[packet.actor_id].popleft()
