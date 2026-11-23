"""Deterministic offline implementations of the clock and byte transport ports."""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from living_island.agents.llm.provider import TransportResponse


@dataclass
class FakeClock:
    epoch: datetime = datetime(2000, 1, 1, tzinfo=UTC)
    elapsed_ms: int = 0

    def now(self) -> datetime:
        return self.epoch + timedelta(milliseconds=self.elapsed_ms)

    def monotonic_ms(self) -> int:
        return self.elapsed_ms


@dataclass(frozen=True)
class ScriptedReply:
    response: TransportResponse
    delay_ms: int = 0


class FakeTransport:
    def __init__(self, clock: FakeClock, replies: Iterable[ScriptedReply]) -> None:
        self.clock = clock
        self.replies = deque(replies)
        self.dispatches: list[bytes] = []

    def exchange(self, body: bytes, timeout_ms: int) -> TransportResponse:
        self.dispatches.append(body)
        reply = self.replies.popleft()
        self.clock.elapsed_ms += reply.delay_ms
        return reply.response
