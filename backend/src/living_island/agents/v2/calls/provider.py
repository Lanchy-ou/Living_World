"""A single stateless attempt. Only the host decides to retry or adopt a result."""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from living_island.agents.llm import provider as p3

from .contracts import Parsed, json_bytes, read_json
from .guard import Call, Candidate, Prepared, Settings
from .journal import Fact, Journal
from .wire import RESERVE

type ErrorClass = Literal[
    "timeout", "rate_limit", "server_error", "provider_error", "invalid_output"
]


class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic_ms(self) -> int: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic_ms(self) -> int:
        return time.monotonic_ns() // 1_000_000


class Usage(Fact):
    input: int | None = None
    output: int | None = None
    cache_hit: int | None = None
    cache_miss: int | None = None

    @classmethod
    def from_provider(cls, raw: object) -> "Usage":
        if not isinstance(raw, dict):
            return cls()
        details = raw.get("input_tokens_details")
        total = p3._usage(raw.get("input_tokens"))
        hit = p3._usage(details.get("cached_tokens")) if isinstance(details, dict) else None
        if hit is None:
            hit = p3._usage(raw.get("prompt_cache_hit_tokens"))
        miss = p3._usage(raw.get("prompt_cache_miss_tokens"))
        if miss is None and hit is not None and total is not None and hit <= total:
            miss = total - hit
        return cls(
            input=total, output=p3._usage(raw.get("output_tokens")), cache_hit=hit, cache_miss=miss
        )


class Dispatch(Fact):
    call: Call
    n: int
    prepared_cursor: str
    request_sha256: str
    sent: Candidate
    settings: Settings
    started_at: datetime
    timeout_ms: int


type Admission = Callable[[Dispatch], str | None]


class BudgetStop(Exception):
    """An operator refused the proposed attempt before it was claimed or sent."""

    def __init__(self, dispatch: Dispatch, reason: str) -> None:
        super().__init__(reason)
        self.dispatch = dispatch
        self.reason = reason


_admission: ContextVar[Admission | None] = ContextVar("dispatch_admission", default=None)


@contextmanager
def dispatch_admission(admit: Admission) -> Iterator[None]:
    """Share one operator policy across the synchronous resident and consolidation calls."""
    token = _admission.set(admit)
    try:
        yield
    finally:
        _admission.reset(token)


class Terminal(Fact):
    call_id: str
    n: int
    dispatch_cursor: str
    request_sha256: str
    ended_at: datetime
    latency_ms: int
    error_class: ErrorClass | None
    error: str | None
    status: int | None
    provider_request_id: str | None
    raw_output_ref: str | None
    observed_body_bytes: int
    response_complete: bool
    reasoning_ref: str | None
    parsed_ref: str | None
    tokens: Usage
    missing_usage_reason: str | None


@dataclass(frozen=True)
class Returned:
    dispatch: Dispatch
    terminal: Terminal
    terminal_cursor: str
    parsed: Parsed | None


class Interrupted(Fact):
    dispatch: Dispatch
    reason: Literal["INTERRUPTED_CALL_RECOVERY_REQUIRED"] = "INTERRUPTED_CALL_RECOVERY_REQUIRED"
    tokens: Usage = Usage()
    missing_usage_reason: str = "terminal unavailable"
    latency_ms: None = None


def restore(dispatch: Dispatch, terminal: Terminal | None) -> Terminal | Interrupted:
    """Consume the host's durable disposition. No transport or writer is available."""
    if terminal is None:
        return Interrupted(dispatch=dispatch)
    if (terminal.call_id, terminal.n, terminal.request_sha256, terminal.dispatch_cursor) != (
        dispatch.call.call_id,
        dispatch.n,
        dispatch.request_sha256,
        Journal.cursor(dispatch.call.call_id, f"{dispatch.n}.dispatch"),
    ):
        raise ValueError("terminal belongs to a different dispatch")
    return terminal


def _error(
    raw: p3.TransportResponse,
    envelope: dict[str, Any],
    usage: Usage,
    elapsed: int,
    timeout_ms: int,
    overflow: bool,
) -> tuple[ErrorClass, str] | None:
    if raw.fault == "timeout" or elapsed >= timeout_ms:
        return "timeout", "ATTEMPT_TIMEOUT"
    if raw.fault or raw.status is None:
        return "server_error", "TRANSPORT_ERROR"
    if raw.status == 429:
        return "rate_limit", "HTTP_429"
    if raw.status >= 500:
        return "server_error", f"HTTP_{raw.status}"
    if not 200 <= raw.status < 300:
        return "provider_error", f"HTTP_{raw.status}"
    if overflow or not raw.complete or envelope.get("status") == "incomplete":
        return "invalid_output", "INCOMPLETE_OUTPUT"
    if usage.output is not None and usage.output > RESERVE:
        return "invalid_output", "OUTPUT_LIMIT"
    if envelope.get("error") is not None or envelope.get("status") == "failed":
        return "provider_error", "PROVIDER_REJECTED"
    if "model" in envelope and envelope["model"] != p3.MODEL_ID:
        return "provider_error", "RESPONSE_MODEL_MISMATCH"
    if envelope.get("status") != "completed":
        return "invalid_output", "INVALID_ENVELOPE"
    return None


def attempt(
    prepared: Prepared,
    *,
    n: int,
    has_running_action: bool,
    journal: Journal,
    transport: p3.ByteTransport,
    clock: Clock,
    timeout_ms: int = p3.MAX_TIMEOUT_MS,
    admit: Admission | None = None,
) -> Returned | None:
    """Claim the attempt durably before the sole exchange. All retries use new slots."""
    admitted = prepared.admitted
    if admitted is None:
        return None
    p3._check_timeout(timeout_ms)
    call = prepared.record.call
    dispatch = Dispatch(
        call=call,
        n=n,
        prepared_cursor=prepared.cursor,
        request_sha256=admitted.candidate.wire_sha256,
        sent=admitted.candidate,
        settings=prepared.record.settings,
        started_at=clock.now(),
        timeout_ms=timeout_ms,
    )
    admission = admit if admit is not None else _admission.get()
    if admission is not None and (reason := admission(dispatch)) is not None:
        raise BudgetStop(dispatch, reason)
    cursor = journal.fact(call.call_id, f"{n}.dispatch", dispatch, exclusive=True)
    start = clock.monotonic_ms()
    try:
        raw = transport.exchange(admitted.wire.body, timeout_ms)
    except TimeoutError:
        raw = p3.TransportResponse(None, None, False, "timeout")
    except OSError:
        raw = p3.TransportResponse(None, None, False, "transport_error")
    elapsed = clock.monotonic_ms() - start
    ended = clock.now()
    observed = len(raw.body) if raw.body is not None else 0
    overflow = observed > p3.MAX_RESPONSE_BYTES
    body = raw.body[: p3.MAX_RESPONSE_BYTES] if raw.body is not None else None
    raw_ref = journal.blob(body) if body is not None else None
    envelope: dict[str, Any] = {}
    if body is not None and raw.complete and not overflow:
        try:
            decoded = read_json(body.decode("utf-8"))
            if isinstance(decoded, dict):
                envelope = decoded
        except (ValueError, RecursionError):
            pass
    usage = Usage.from_provider(envelope.get("usage"))
    fault = _error(raw, envelope, usage, elapsed, timeout_ms, overflow)
    parsed: Parsed | None = None
    reasoning_ref = parsed_ref = None
    output = envelope.get("output")
    if isinstance(output, list):
        reasoning = [
            item for item in output if isinstance(item, dict) and item.get("type") == "reasoning"
        ]
        if reasoning:
            reasoning_ref = journal.blob(json_bytes(reasoning))
        output = [
            item
            for item in output
            if not (isinstance(item, dict) and item.get("type") == "reasoning")
        ]
    if fault is None:
        text = p3._output_text(output)
        if text is None:
            fault = ("invalid_output", "INVALID_ENVELOPE")
        else:
            try:
                parsed = prepared.contract.parse(text, has_running_action=has_running_action)
            except (ValueError, RecursionError):
                fault = ("invalid_output", "INVALID_MODEL_OUTPUT")
            else:
                parsed_ref = journal.blob(
                    json_bytes(parsed.model_dump(mode="json", by_alias=True, exclude_unset=True))
                )
    missing = [name for name, value in usage.model_dump().items() if value is None]
    terminal = Terminal(
        call_id=call.call_id,
        n=n,
        dispatch_cursor=cursor,
        request_sha256=dispatch.request_sha256,
        ended_at=ended,
        latency_ms=elapsed,
        error_class=fault[0] if fault else None,
        error=fault[1] if fault else None,
        status=raw.status,
        provider_request_id=p3._label(envelope.get("id")),
        raw_output_ref=raw_ref,
        observed_body_bytes=observed,
        response_complete=raw.complete and not overflow,
        reasoning_ref=reasoning_ref,
        parsed_ref=parsed_ref,
        tokens=usage,
        missing_usage_reason="Provider did not report usable " + ", ".join(missing)
        if missing
        else None,
    )
    terminal_cursor = journal.fact(call.call_id, f"{n}.terminal", terminal)
    return Returned(dispatch, terminal, terminal_cursor, parsed)
