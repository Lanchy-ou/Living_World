"""Deterministic offline provider: scripted bytes, logical time, no network seam."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO

from living_island.agents.llm.provider import (
    MAX_INPUT_TOKENS,
    MAX_RESPONSE_BYTES,
    DeepSeekResponsesAdapter,
    TransportResponse,
    _check_timeout,
    map_response,
    verified_body,
)
from living_island.agents.p3.types import ProviderRequest, ProviderResult, WireRequest

COUNTER_ID = "fixture-wire-bytes"
COUNTER_VERSION = "0.1"


@dataclass(frozen=True)
class FakeReply:
    """A local response script, never a URL, callback or source of remote IO."""

    body: bytes | None
    status: int | None = 200
    complete: bool = True
    elapsed_ms: int = 0
    transport_error: bool = False

    def __post_init__(self) -> None:
        if self.body is not None and type(self.body) is not bytes:
            raise ValueError("fixture body must be bytes or null")
        if type(self.elapsed_ms) is not int or self.elapsed_ms < 0:
            raise ValueError("fixture elapsed time must be a nonnegative integer")


class FakeProviderAdapter(DeepSeekResponsesAdapter):
    """The fixture defines one input unit per exact wire byte, including schema.

    For any prepared byte string b, splitting into single-byte units is a bijection
    with indices [0,len(b)); len(b) is therefore an exact count (and upper bound).
    This is NOT a DeepSeek tokenizer and cannot enable the production adapter.
    Each complete consumes one script entry; no retries or wall-clock randomness.
    """

    adapter_id = "fixture-deepseek-responses-v0"
    adapter_version = "0.1"

    def __init__(self, replies: Sequence[FakeReply]) -> None:
        super().__init__()
        if any(type(reply) is not FakeReply for reply in replies):
            raise ValueError("fake provider accepts only local FakeReply values")
        self._replies = tuple(replies)
        self._cursor = 0
        self._sent: list[bytes] = []
        self._read_sizes: list[int] = []

    @property
    def sent_bodies(self) -> tuple[bytes, ...]:
        return tuple(self._sent)

    @property
    def read_sizes(self) -> tuple[int, ...]:
        return tuple(self._read_sizes)

    def count_input_tokens(self, request: ProviderRequest, wire: WireRequest) -> int:
        body = verified_body(request, wire)
        if (request.settings.input_counter_id, request.settings.input_counter_version) != (
            COUNTER_ID,
            COUNTER_VERSION,
        ):
            raise ValueError("fixture counter identity mismatch")
        return len(body)

    def complete(
        self, request: ProviderRequest, wire: WireRequest, timeout_ms: int
    ) -> ProviderResult:
        _check_timeout(timeout_ms)
        body = verified_body(request, wire)
        if self.count_input_tokens(request, wire) > MAX_INPUT_TOKENS:
            raise ValueError("INPUT_LIMIT: input counter exceeds B-05")
        if self._cursor >= len(self._replies):
            raise ValueError("offline provider script exhausted")
        reply = self._replies[self._cursor]
        self._cursor += 1
        self._sent.append(body)
        # Simulate the same bounded receiver, even for arbitrarily large fixtures.
        raw = BytesIO(reply.body).read(MAX_RESPONSE_BYTES + 1) if reply.body is not None else None
        self._read_sizes.append(len(raw) if raw is not None else 0)
        timed_out = reply.elapsed_ms >= timeout_ms
        return map_response(
            TransportResponse(
                reply.status,
                raw,
                reply.complete and not timed_out and not reply.transport_error,
                "timeout" if timed_out else "transport_error" if reply.transport_error else None,
            ),
            latency_ms=min(reply.elapsed_ms, timeout_ms),
        )
