"""Exact, fail-closed DeepSeek Responses mapping; no resident or budget ownership.

There is deliberately no certified production input counter in this version. See
tests/fixtures/p3/provider/README.md for the proof gap. Preparing and auditing are
pure; counting or completing a production attempt refuses before transport access.
The offline adapter exercises the same byte transport and response mapper.
"""

from __future__ import annotations

import base64
import http.client
import json
import socket
import time
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from typing import Literal, Protocol

from living_island.agents.p3.prompts import build_model_action_contract
from living_island.agents.p3.types import (
    ProviderRequest,
    ProviderResult,
    WireRequest,
    decode_base64,
)
from living_island.memory.p3_types import canonical_bytes

ADAPTER_ID = "deepseek-responses-v0"
ADAPTER_VERSION = "0.1"
MODEL_ID = "deepseek-flash"
MAX_REQUEST_BYTES = 131072
MAX_RESPONSE_BYTES = 262144
MAX_INPUT_TOKENS = 32768
MAX_OUTPUT_TOKENS = 2048
MAX_TIMEOUT_MS = 30000


class InputCounterUnavailable(ValueError):
    """Startup refusal, never a guessed reservation or a retryable provider fault."""

    def __init__(self) -> None:
        super().__init__("INPUT_COUNTER_UNAVAILABLE")


@dataclass(frozen=True)
class TransportResponse:
    """Bounded transport evidence; body=None distinguishes no response from empty."""

    status: int | None
    body: bytes | None
    complete: bool
    fault: Literal["timeout", "transport_error"] | None = None


class ByteTransport(Protocol):
    """One synchronous attempt, no retries, redirects, decoding or JSON rewriting."""

    def exchange(self, body: bytes, timeout_ms: int) -> TransportResponse: ...


class HTTPSByteTransport:
    """One-shot stdlib HTTPS, with a total deadline and bounded raw reads.

    The launcher injects a credential; this class never reads files/environment.
    No SDK is used, hence no SDK retry/default serialization path exists. A daemon
    worker bounds DNS/TLS/header stalls as well as reads. Cancellation closes the
    socket and discards late evidence. A still-running worker prevents another
    exchange on this transport; it never publishes resident state or audit rows.
    The coordinator remains responsible for allocation, call IDs and scheduling.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key or any(ord(c) < 33 or ord(c) > 126 for c in api_key):
            raise ValueError("invalid injected credential")
        self._api_key = api_key
        self._pending: Thread | None = None

    def _connection(self, timeout: float) -> http.client.HTTPSConnection:
        return http.client.HTTPSConnection("api.deepseek.com", timeout=timeout)

    def exchange(self, body: bytes, timeout_ms: int) -> TransportResponse:
        _check_timeout(timeout_ms)
        if self._pending is not None and self._pending.is_alive():
            return TransportResponse(None, None, False, "transport_error")
        deadline = time.monotonic() + timeout_ms / 1000
        cancelled = Event()
        # Each byte occurs in at most one queue chunk; the worker reads cap+1 total.
        evidence: Queue[tuple[int | None, bytes | None, bool, str | None] | Exception] = Queue()
        connection = self._connection(timeout_ms / 1000)

        def remaining() -> float:
            value = deadline - time.monotonic()
            if cancelled.is_set() or value <= 0:
                raise TimeoutError
            return value

        def worker() -> None:
            try:
                connection.connect()
                connection.timeout = remaining()
                if connection.sock is not None:
                    connection.sock.settimeout(remaining())
                connection.request(
                    "POST",
                    "/responses",
                    body=body,
                    headers={
                        "Authorization": "Bearer " + self._api_key,
                        "Content-Type": "application/json",
                    },
                )
                remaining()
                response = connection.getresponse()
                # Headers are never retained. Encodings other than identity are
                # not decoded and cannot expand beyond the raw-byte read bound.
                evidence.put((response.status, b"", False, None))
                read = 0
                while read <= MAX_RESPONSE_BYTES:
                    if connection.sock is not None:
                        connection.sock.settimeout(remaining())
                    else:
                        remaining()
                    try:
                        chunk = response.read1(MAX_RESPONSE_BYTES + 1 - read)
                    except http.client.IncompleteRead as exc:
                        # A chunked response can fail after actually reading data.
                        # Preserve that prefix, never discard it as an absent body.
                        if len(exc.partial) > MAX_RESPONSE_BYTES + 1 - read:
                            raise ValueError("transport exceeded the bounded read") from None
                        evidence.put((response.status, exc.partial, False, None))
                        raise
                    remaining()
                    if not chunk:
                        if response.length not in (None, 0):
                            raise http.client.IncompleteRead(b"")
                        evidence.put((response.status, None, True, None))
                        return
                    read += len(chunk)
                    evidence.put((response.status, chunk, False, None))
                evidence.put((response.status, None, False, "overflow"))
            except TimeoutError:
                evidence.put((None, None, False, "timeout"))
            except (OSError, http.client.HTTPException):
                # Exception messages may contain credentials or server content.
                evidence.put((None, None, False, "transport_error"))
            except Exception as exc:
                # Programming defects stop the caller rather than becoming fallback.
                evidence.put(exc)
            finally:
                connection.close()

        self._pending = Thread(target=worker, name="p3-provider-attempt", daemon=True)
        self._pending.start()
        status: int | None = None
        retained: bytearray | None = None
        try:
            while True:
                try:
                    item = evidence.get(timeout=remaining())
                    remaining()
                except (Empty, TimeoutError):
                    return TransportResponse(
                        status, bytes(retained) if retained is not None else None, False, "timeout"
                    )
                if isinstance(item, Exception):
                    raise item
                code, chunk, complete, fault = item
                if code is not None:
                    status = code
                if chunk is not None:
                    if retained is None:
                        retained = bytearray()
                    retained.extend(chunk)
                raw = bytes(retained) if retained is not None else None
                if complete or fault == "overflow":
                    return TransportResponse(status, raw, complete)
                if fault == "timeout":
                    return TransportResponse(status, raw, False, "timeout")
                if fault == "transport_error":
                    return TransportResponse(status, raw, False, "transport_error")
        finally:
            cancelled.set()
            sock = connection.sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()


def _check_timeout(timeout_ms: int) -> None:
    if type(timeout_ms) is not int or not 0 < timeout_ms <= MAX_TIMEOUT_MS:
        raise ValueError("attempt timeout must be an integer in 1..30000 ms")


def prepare_request(request: ProviderRequest) -> WireRequest:
    """Validate the frozen mapping and serialize exactly once into retained bytes."""
    request = ProviderRequest.model_validate(request.model_dump(mode="json"))
    if request.model_id != MODEL_ID:
        raise ValueError("unsupported pinned model; alias substitution is forbidden")
    if request.response_schema != build_model_action_contract().proposal_schema:
        raise ValueError("request must use the pinned DecisionProposal schema")
    if len(canonical_bytes(request)) > MAX_REQUEST_BYTES:
        raise ValueError("INPUT_LIMIT: canonical provider request exceeds B-08")
    body = canonical_bytes(
        {
            "model": request.model_id,
            "input": [message.model_dump(mode="json") for message in request.messages],
            "reasoning": {"effort": request.settings.reasoning_effort},
            "max_output_tokens": request.max_output_tokens,
            "stream": request.settings.stream,
            "tools": request.settings.tools,
            "tool_choice": "none",
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "resident_decision",
                    "schema": request.response_schema,
                }
            },
        }
    )
    if len(body) > MAX_REQUEST_BYTES:
        raise ValueError("INPUT_LIMIT: prepared wire body exceeds B-08")
    return WireRequest(
        wire_schema_version="0.1",
        method="POST",
        origin="https://api.deepseek.com",
        path="/responses",
        content_type="application/json",
        body_base64=base64.b64encode(body).decode("ascii"),
    )


def verified_body(request: ProviderRequest, wire: WireRequest) -> bytes:
    """Compare the whole envelope, then return the retained bytes, not a re-encoding."""
    wire = WireRequest.model_validate(wire.model_dump(mode="json"))
    if wire != prepare_request(request):
        raise ValueError("prepared wire request mismatch")
    return decode_base64(wire.body_base64)


class DeepSeekResponsesAdapter:
    """Production port; uncertified counters cannot be injected around the refusal."""

    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def __init__(self, transport: ByteTransport | None = None) -> None:
        self._transport = transport

    def prepare(self, request: ProviderRequest) -> WireRequest:
        return prepare_request(request)

    def count_input_tokens(self, request: ProviderRequest, wire: WireRequest) -> int:
        verified_body(request, wire)
        raise InputCounterUnavailable

    def complete(
        self, request: ProviderRequest, wire: WireRequest, timeout_ms: int
    ) -> ProviderResult:
        _check_timeout(timeout_ms)
        body = verified_body(request, wire)
        # Refuse even if the caller accidentally bypassed startup/admission.
        count = self.count_input_tokens(request, wire)
        if type(count) is not int or not 0 <= count <= MAX_INPUT_TOKENS:
            raise ValueError("INPUT_LIMIT: input counter exceeds B-05")
        if self._transport is None:
            raise ValueError("provider transport is not configured")
        start = time.monotonic_ns()
        raw = self._transport.exchange(body, timeout_ms)
        latency = max(0, (time.monotonic_ns() - start) // 1000000)
        if latency >= timeout_ms and raw.fault != "timeout":
            raw = TransportResponse(raw.status, raw.body, False, "timeout")
        return map_response(raw, latency_ms=latency)


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite JSON number")


def _label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return None
    return value


def _usage(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _output_text(value: object) -> str | None:
    if not isinstance(value, list) or len(value) != 1:
        return None
    message = value[0]
    if not isinstance(message, dict) or (
        message.get("type"),
        message.get("role"),
        message.get("status"),
    ) != ("message", "assistant", "completed"):
        return None
    content = message.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return None
    part = content[0]
    if not isinstance(part, dict) or part.get("type") != "output_text":
        return None
    text = part.get("text")
    if not isinstance(text, str):
        return None
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return None
    return text


def map_response(raw: TransportResponse, *, latency_ms: int | None) -> ProviderResult:
    """Pure envelope mapping; proposal/action/delta validation belongs to the runtime."""
    if raw.body is not None and len(raw.body) > MAX_RESPONSE_BYTES + 1:
        raise ValueError("transport violated the cap-plus-one read contract")
    body = raw.body[:MAX_RESPONSE_BYTES] if raw.body is not None else None
    try:
        decoded = body.decode("utf-8", errors="strict") if body is not None else None
    except UnicodeDecodeError:
        decoded = None
    observed = len(raw.body) if raw.body is not None else 0
    outcome: Literal["response", "timeout", "provider_error", "output_limit"] = "response"
    complete = raw.complete
    text = request_id = error = None
    token_input = token_output = None
    if observed > MAX_RESPONSE_BYTES:
        outcome, complete, error = "output_limit", False, "RESPONSE_BYTES_LIMIT"
    elif raw.fault == "timeout":
        outcome, complete, error = "timeout", False, "ATTEMPT_TIMEOUT"
    elif raw.fault is not None or not raw.complete:
        outcome, complete, error = "provider_error", False, "TRANSPORT_ERROR"
    else:
        envelope: object = None
        try:
            if decoded is not None:
                envelope = json.loads(
                    decoded, object_pairs_hook=_object_pairs, parse_constant=_reject_constant
                )
        except (ValueError, RecursionError):
            pass
        if isinstance(envelope, dict):
            request_id = _label(envelope.get("id"))
            usage = envelope.get("usage")
            if isinstance(usage, dict):
                token_input = _usage(usage.get("input_tokens"))
                token_output = _usage(usage.get("output_tokens"))
            status = envelope.get("status")
            if status == "incomplete" or (
                token_output is not None and token_output > MAX_OUTPUT_TOKENS
            ):
                outcome, complete, error = "output_limit", False, "INCOMPLETE_OUTPUT"
            elif status == "failed" or envelope.get("error") is not None:
                outcome, error = "provider_error", "PROVIDER_REJECTED"
                detail = envelope.get("error")
                if isinstance(detail, dict):
                    error = _label(detail.get("code")) or error
            elif status == "completed":
                text = _output_text(envelope.get("output"))
            elif status is not None:
                outcome, error = "provider_error", "INVALID_RESPONSE_STATUS"
        if raw.status is None or not 200 <= raw.status < 300:
            outcome, text, error = "provider_error", None, f"HTTP_{raw.status or 'UNKNOWN'}"
    return ProviderResult(
        provider_result_version="0.1",
        outcome=outcome,
        raw_response=decoded,
        raw_body_base64=base64.b64encode(body).decode("ascii") if body is not None else None,
        observed_body_bytes=observed,
        response_complete=complete,
        response_text=text,
        provider_request_id=request_id,
        token_input=token_input,
        token_output=token_output,
        latency_ms=latency_ms,
        provider_error_code=error,
    )
