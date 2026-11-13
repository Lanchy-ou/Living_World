"""Exact, fail-closed DeepSeek Responses mapping; no resident or budget ownership.

The pure production counter bounds the pinned Flash-1017 prompt, including schema
framing. Its tokenizer nonexpansion proof and immutable public source artifacts
are retained in tests/fixtures/p3/provider. No tokenizer download, credential
lookup, model call or empirical estimate participates in counting.
"""

from __future__ import annotations

import base64
import http.client
import json
import re
import socket
import time
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from heapq import heapify, heappop, heappush
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
ADAPTER_VERSION = "0.3"
MODEL_ID = "deepseek-flash"
COUNTER_ID = "deepseek-flash1017-byte-upper-bound"
COUNTER_VERSION = "0.2"
COUNTER_MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
COUNTER_TOKENIZER_SHA256 = "c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b"
_SCHEMA_PREFIX = (
    "\n\n## Response Format:\n\nYou MUST strictly adhere to the following schema to reply:\n"
)
_MERGE_PREFIX_SIZE = 4096
_ASCII_DIGITS = re.compile(r"[0-9]{1,3}")
# Exact ASCII restriction of the pinned tokenizer's final Split regex. In
# particular, re.ASCII excludes U+001C..001F from Python's default whitespace.
_ASCII_SPLIT = re.compile(
    r"[!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~][A-Za-z]+"
    r"|[^\r\nA-Za-z\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]?[A-Za-z]+"
    r"| ?[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]+[\r\n]*"
    r"|\s*[\r\n]+|\s+(?!\S)|\s+",
    re.ASCII,
)
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
                evidence.put((response.status, None, False, None))
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
                        if exc.partial:
                            evidence.put((response.status, exc.partial, False, None))
                        raise
                    if not chunk:
                        if response.length not in (None, 0):
                            raise http.client.IncompleteRead(b"")
                        remaining()
                        evidence.put((response.status, b"", True, None))
                        return
                    read += len(chunk)
                    evidence.put((response.status, chunk, False, None))
                    remaining()
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

        def capture(
            item: tuple[int | None, bytes | None, bool, str | None] | Exception,
        ) -> tuple[int | None, bytes | None, bool, str | None]:
            nonlocal status, retained
            if isinstance(item, Exception):
                raise item
            code, chunk, _, _ = item
            if code is not None:
                status = code
            if chunk is not None:
                if retained is None:
                    retained = bytearray()
                retained.extend(chunk)
            return item

        def timed_out() -> TransportResponse:
            cancelled.set()
            # Freeze all evidence already received, including a chunk queued just
            # before the deadline. Never promote a queued success after timeout.
            # Anything published after this snapshot is late, audit-only evidence
            # and cannot modify this returned terminal value.
            while True:
                try:
                    capture(evidence.get_nowait())
                except Empty:
                    break
            return TransportResponse(
                status, bytes(retained) if retained is not None else None, False, "timeout"
            )

        try:
            while True:
                try:
                    item = evidence.get(timeout=remaining())
                except (Empty, TimeoutError):
                    return timed_out()
                _, _, complete, fault = capture(item)
                try:
                    remaining()
                except TimeoutError:
                    return timed_out()
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
    if canonical_bytes(request.response_schema) != canonical_bytes(
        build_model_action_contract().proposal_schema
    ):
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


def _isolated_parts(text: str, pattern: re.Pattern[str]) -> Iterator[str]:
    """Preserve each match and each unmatched gap as a separate nonempty part."""
    end = 0
    for match in pattern.finditer(text):
        if match.start() > end:
            yield text[end : match.start()]
        yield match.group()
        end = match.end()
    if end < len(text):
        yield text[end:]


def _ascii_parts(text: str) -> Iterator[str]:
    # First isolate digit groups; the intervening CJK/Japanese splitter is a
    # no-op on ASCII. The last splitter must run separately within each part.
    for part in _isolated_parts(text, _ASCII_DIGITS):
        yield from _isolated_parts(part, _ASCII_SPLIT)


def _ascii_word_bound(word: str) -> int:
    """Execute a true prefix of BPE using rank then original left-position order.

    A linked symbol list and heap avoid quadratic rescans of long ASCII words.
    Each merge removes one symbol and enqueues at most two neighboring pairs;
    total heap operations are O(n), each O(log n), and storage is O(n).
    """
    symbols = [bytes((value,)) for value in word.encode("ascii")]
    size = len(symbols)
    previous = list(range(-1, size - 1))
    following = list(range(1, size)) + [-1]
    queue = [
        (rank, index)
        for index in range(size - 1)
        if (rank := _ASCII_MERGES.get((symbols[index], symbols[index + 1]))) is not None
    ]
    heapify(queue)
    count = size

    def enqueue(left: int) -> None:
        if left != -1 and (right := following[left]) != -1:
            if (rank := _ASCII_MERGES.get((symbols[left], symbols[right]))) is not None:
                heappush(queue, (rank, left))

    while queue:
        rank, left = heappop(queue)
        right = following[left]
        if right == -1 or _ASCII_MERGES.get((symbols[left], symbols[right])) != rank:
            continue  # A neighbor changed or this left symbol was removed.
        symbols[left] += symbols[right]
        symbols[right] = b""
        following[left] = following[right]
        following[right] = -1
        if following[left] != -1:
            previous[following[left]] = left
        count -= 1
        enqueue(previous[left])
        enqueue(left)
    return count


def _plain_token_bound(text: str) -> int:
    """Tighten only complete ASCII spans; all other spans keep the byte proof."""
    if not text.isascii():
        return len(text.encode("utf-8"))
    return sum(_ascii_word_bound(part) for part in _ascii_parts(text))


class DeepSeekResponsesAdapter:
    """Production port with a certified counter for the frozen Flash-1017 lane.

    Registration owns revalidating the model alias and pinning this implementation;
    the counter has no IO and cannot establish current hosted alias identity.
    """

    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def __init__(self, transport: ByteTransport | None = None) -> None:
        self._transport = transport

    def prepare(self, request: ProviderRequest) -> WireRequest:
        return prepare_request(request)

    def count_input_tokens(self, request: ProviderRequest, wire: WireRequest) -> int:
        body = verified_body(request, wire)
        if (request.settings.input_counter_id, request.settings.input_counter_version) != (
            COUNTER_ID,
            COUNTER_VERSION,
        ):
            raise InputCounterUnavailable
        # Count the retained wire, including the schema's provider-side expansion.
        # Stop ASCII BPE after a certified rank prefix; subsequent merges can
        # only reduce the count. Non-ASCII spans retain the original byte bound.
        # System and schema form ONE ordinary span: an artificial split could
        # change merge priorities. Only structural markers separate spans.
        payload = json.loads(body)
        schema = json.dumps(
            payload["text"]["format"]["schema"], ensure_ascii=False, separators=(", ", ": ")
        )
        return (
            5
            + _plain_token_bound(payload["input"][0]["content"] + _SCHEMA_PREFIX + schema)
            + _plain_token_bound(payload["input"][1]["content"])
        )

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
                if "model" in envelope and envelope["model"] != MODEL_ID:
                    outcome, error = "provider_error", "RESPONSE_MODEL_MISMATCH"
                else:
                    # An alias echo (or its absence) cannot attest hosted weights;
                    # version/pricing evidence must still be checked at registration.
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


# Mechanically extracted ASCII-reachable pairs from ranks [0, 4096) of the
# pinned Flash-1017 tokenizer. The offline certificate test verifies every rank
# against the complete artifact. Each decoded line is: rank left_hex right_hex.
# No runtime artifact lookup, optional tokenizer package or IO is required.
_ASCII_MERGE_DATA = (
    "c-oD9S+eA~j_iM|B9<T$9G8=4i2X02;qCyX%zDqdt<vr#brci_5X9gBuXnxPv%L!bf0S2!kNqCMFGIavul646J^HKr"
    "|GZ~?jraKA@6#)Ijz6OAKPqhJVuSW7XmR4_{#L2)>yQ6?6~phnozmE#zt{O?FHAJyO_jwbpI6!FjK72GM(dT`oY$*X"
    "7UruOfA#&Ujlc4D*i{q;pNv;s>|A|SG&p|WW4_G)@{6|&O>(S0T4S@LzKr7^KQC+SaDN&4iLsBDso{-jnw+l>ii<^i"
    "HSf|l=BD+Sg3qhrCmf!CvT>w7uC_RfpI7(hy7$M2*tHVt)%`EVC+dr@frj||>YB6fS06dauRgglKd-JO@jqhj(7?Dj"
    "*Iv--e!m8roYfm0ob7I}!P)i(CTH9GIoXx&h03<SU;e4dmL_}9%4<$`Wxl4yQeMmF^4HheS9=w%+juSf1^wKds>RQ@"
    "{aPGRU9Y7PZJ(6I*==5!{8)Xh#WiTJh55x`_r*WiYx4{K`Q7-Z{@Nm=AE(5NKbu}Ed<N>Qx!PVvF9rx2^muV-KE`rk"
    "NQ2Z}u7$On+sRpk?SB_#b7qSZ_9Xomr|gP<UgDsd_dvAm<1dA)!)+1Njo*lzyZ5D5E}H*Fbc`>Oe)Zoe_)`%N{*HzA"
    "IY+BiTgAsg${mfpcbdiQ`1hS;r`oqklEJPn7=e?mQ@wf14WGdzvTqGDE7B@W>+f$j44a?zvd>t-)+mic(EJ$)xnMm?"
    "uSxM<HkG;EF}_LS^BwM#3<klTgMxd^tJAK(HQ5F9U~s0I|7Emj*H;3ISFl~nm>|09-|~UY!O^3s5q+JU)s9jRQp6jB"
    "B*!lXA#awsM$NxF(T}(Jye*B)N3gj5*!38@lQ8xX$F?*Nc&ZkB<`-M&J|p{z@%fuuOv>=JjdkwHDV=^NSzOuRsbW&~"
    "x?(<-mkW2=_LBCIGe1yo(_hC~#UHON@BnYOUR!(xWzjO}z812)_Uk3Cl8?k&5e<(oFJX?r&-^Pv#m;_7#bl~zk4J~t"
    "SFPG>{!7p_D9CBGf=z!wt9YZ6nw+iIt(}B6jD2e0=-9sGhj`nG6HAIxoE>~yJIniTlcWUNt`_b2y40ri0+X&yTmnzK"
    "lRBuqHm*G>rS>aEgVUqD?F&a$bqe;bnD?GE>l^_i0mXjnoEfnu1xHjD`|l_ZvL_xvg=6(m4YEMZ0NF2A*1yfI8mm0^"
    "zdQa_Neuke)H(2tUtzH|-{6BiW@U2i7tisjlc`|cNYCP&l@#q82a|?5Tby@{*XerlRH;ie@$mywT+iFyI(j+2T}k{p"
    "QbmLQduPFzFYoj2F}@FaxJS@2PF;@1`)XH-vlwOYsR8Qt_l*?%u737jH?P9UV4&tpJKC<Ko#jV3&$ao-OW0SURx8@k"
    "9cQ!CD>hpmKvpz0e6Qx-@}7WZYkZ+f20}^49(JpdW-*rq?SMLC7nlWa^itDWL%cBVAJa;hiTis`o6h3mCDAoocb>|_"
    "(@R`eh$0XdK00;{5(CDEG9-l`&XaiULQe+1FNtAt<X!FHDc3>c1h3tq2m|E~$u;6E;A=L>C&{gBh==*p$=&T7z~V*F"
    "qxS_1vGtq+lka~crv;UI3*@wVx|9FncPn-t#tCTwJOWaeDA2ozveOmVgZW%ZIG6=JB)1jC8u{&<;%T;a^xeO(gU(p4"
    ";^8chpg)wwt-oIF0+lyP!0oDJqLk!7p&$Y;`B(q=KQHC3`u6gUakz9>$~&GqT_#^|MSPhp`aCsKXPz7l^hqvYe3z~1"
    "%i^t7`@V$$>^&uS)j8ilsT)+&$Xg{EwK{^_RTDp`URshB_)C5%=BI)4F3IzalpTEl=QWA8Go%X_X>D^i`i$eZ<hPSN"
    "vVq@zwBuVy42yfJf$Ne28--xs+jkF}1lNN1C<W&ZZIT~MZ~C`7Da$}lttS<*{T?zAzA#8beR#=&+VPZ3K;z=)AfGjE"
    "fM{cgrRxn!wODt2B4ne+U2s+lvhd^xoB+WAy^Yo1F&F!aql|Ct7M#vo0hjdY_wj)iJE<b1SMz<@w!~iV9VCHo4#72r"
    "<W_ztL&%2=@JrdprJsJa*h8*1Ts$NDmzRRNya%0Uzob9ZYRVp7Hm(gy_+^*!QEn;p-?OO~NonNI>~n{(RIpRK(<eww"
    "9Hf(%&Yh=5uRWzeFOQTZyqp{#OSAc81;yb6=+xG55_c*_HR#NBBd1Yu3GbJ+7^8mE-y!8gJA(3NlGHo6@rKmcDLGKl"
    "L%S{IRqvwLc-B(?8nHSkYd?Ln%sx(Pa&3pC<L&p9p>^tXO!SxjBCd=xp?Arc(B>+oHE)Gdu1=FaW}I|BtC%uML!Ht<"
    "ybbAgyV&9!pik+k(PKyiAOGj289W8&R+of3p)FQ@33I(h^w)n$jtZ*tuR1^NAOGhnB}ITrC6p2YTKtfg^j+_@bIR|O"
    "3}&dAeM{>5_@3=M73kq*?HRnWC9gw2y`)2<M2hBa98S@AcX^3Y@<3^e_xadIxnl0OmrI;akRpdPvF`1Wo+l-|0j^to"
    "MbLIh+3|8UIb}zGpOywn2U3?wfs?y+fd0Dl!(lO6@GpE(H28~C_{VGdKHeMTBPcDYtWFPux>w_QJX$KtDEHLn_?9H2"
    ">7^;H13hx;!>r)%J2b-a8q~y6R~wX7sYC}S9^{+B`Qu5R%;hztZ&61ZutLxbGltgC-yK>t{|@a3SaFnLHejEo_<+xY"
    "=(Nl7F)(pkvd$1iatXZVl7RNFw@wY~UBA2}ZEr}}z^`N}a9SK&CY+CJ_+wkHHrmp8UQycQtn)Rm5+^juvL5~Ml1b+E"
    "KF<r^>O4Cp&ig-DT=aBaob4jx2)MFnb6)$Mn$`@RO0zp*7vMQJovTt?bKX6VE(P04%ICjcCMA%*CRo8A(evbKFT21b"
    "Kc&cm5rk}tcbX&?^pj`&81Xe|RNtWUY3DSZeu#SA-a4HpEd-LHr;WqS@lIM7yj|yx7yi9w(<%7nCF2Tv8?D8e>%Ans"
    "M(@EbIa42esmTZjI-X6ssJAE0YwL8J-GZtMO-w08``3D!(){SgEIB<>+Vc`m>#g6D7Jp;Kot}-d^aS|~j)a;Qxt&w_"
    "9Q~Hb(EAZQ()aVEh$MT!oJl+W&U|t?t{5r&|9L{*|M^>8wk!T(#K`<RRO(M#OQs?AmDV$HrwNPMFJy(eC~}AGV6G7)"
    "!SRb{i!Xq#)|M`dIoL27O_Sv9;~=+w*Wso9P8n>HGowYBEtg9hI9M+)mEa(Q6uvG_PSsvsuCq;2s(JZ&hW~hdhfX$L"
    "t6a1;buV#rT&cx9B3s=m$36pFpyUQk5e$cv4|E3mUyWiPIpq?KH=Qbr+;?hk!b(m4D{0$%3u_qVl4X$ZBo{AP52&3k"
    "^5d|Q;k)F?-1QSyOAHjd2|COoSLVz{{n!ujt)8+l%3&>J8D<K}_1LXT6fRYdI@RhU&j<8Wa_*FL_vLk2V6bl9qj9Ci"
    "{aWPRDJ{dE+TYS>)`(L8qaBC;<6A@eOUw$zdhw}6>Xu~WzrtkC7#Xb%+OOYUTjE<@+HunRJCZI)0EL!ZODP1sUM+Mm"
    "AJ3MZ!@s_3SmjVA|Np|AfzPik>kDZEwE9C0*md9q$+_QlqqSG?lJ?q?ndwv5<o(=$-s?>ZT0a(seYH6EikGQNQC8oV"
    "BtKZ5F>h2=yexh*`Q6HWu}dR``&XsK#cXXdg)vgY-L&{pO2e<JNw4QDZEA5kNjJ2(u+{Dw5(CBri|=oq2issG0wrwO"
    "f0xe1Z7npPFE1Y}i<ei<2u9sx@n^eXEAyFZHR#yqsp%94=|+#m>0Nf-?LIfyOVK|>OqY>%3wsk<>DQ5mv4Xo>oH5>S"
    "(tm2_yRYLg;P`r4UA$l8(wNY~7-<E<T#Xs08QcI@oSpt%@@(z>O-nF!Juk<pf^GGpF_5RTzk?o;Y{9km;;Dyc&XesU"
    "j=DwLCM(T$%H|oP*;%r3i>sl9nd6~_W>a<+efsE}%B2f!N-jLX{V?ZDZ0$_UJNy^d6`}}D$Ja&sBD?{Yi19}ouUtho"
    "NP0i+j~S}<oD!_cmL;{^tL>?mbC>wTTUZ>Zrf%TJlYVrThp$s^X(1VT)%U{>3~64pciJ+%!gH8n+k}z-s@#^c&0k@#"
    "&~`4D$%%#6th_^*L4~@id@z@-_i-&;(&;eg@a`D5B^^EOof3yv#^X3QemLmYmlK{7T7wGY7IjM!%dgH@bPNps=T`BH"
    "L`cb3<x0~9x3=l;<T3UK#U2!+?vtnYGk}q73xggotxCTwmmD9Q44)(GdK#h$-EiI=e2d2LTLUdTVSd6Xa#0JMCOQam"
    "7Q6ClazDMg#vyiNf0iskk~c@b#Rkt@ZJqXLodn;5#wdG?rrqV$c2w4HlJd^enrEsP(DO}klB~=t(0P1;jh;EqlSyTR"
    "Q%*W#$n{?BP+#X4it`<GUy8QQ;49@O#a}j2dYJPoDmpi1B`t;GIt?~*0oJq^@s~A)SU3f1yR|}8dCvUdEXZev5#m>N"
    "o#WVvWvZ#rDdpd2@HQ0)Hn3Wt$Q6=@PHw$$P{ETIJ^^|hou&71S4y88vJHDxrkCslw91hj*{dssAkB?-X=$|kQ5!3z"
    "%W*kT)UPS=!+%vs&P^`B@ZeFJ!S7(|m?@|h81rV>?F%`;CUqAw?eh|ym~5K<KK*wJ@Urq~NCs0Vw}%CSGeOIs2AB4e"
    "sU@DV-t52(n>~9fhshtRE_^`kR5ma8co(^wu_&t!H%M83xo`0x?D#Q_YsoM#r*K$}K-?v^4PM%XMNpm0D`8SYd;55L"
    "*)18g+u@k-BqrNO=eEoQm+`kLqxo>*Tntwj4jnv@_6iU6WnmI-sQCDPU_~i#GvetNibs}UYcep#=Jh4k;?+{p8-vct"
    "!6@UA=|R8kxa>rcV|t>v<6MV-{J3jYm}Clkj&sLfwPk3j@c;YP-`hJT4bDg3LdN1qix2dCJebE&$X^9_l-fkCsZ;?&"
    ">IcOZ+BRMmJj8DC-5-s&v?woXt?`lYQIe3^Be~t<)Gc@ro<h-4Z5Adsi9!WFOiZ=*86S+B>+;Jw!Iq>Sude@1LB&g("
    "l6~P~^(&kv=rMsPsl#}cBJ(#;8-?D`!~;|qkjPr_(Ge&Kh@5P5$W`_SMN3*>i!yK)xv9J=+a#JFp^`yU3Pq_@N_M#s"
    "{9_~^oqZ<3H&=k0`baTV*2RY#u)s?i*5JyfWjNx?VN2tbuj`@G;&-x3wO|;PMyW;<wpVUpNu+%YrJKLq^oZy$B>EpB"
    "qv{sHJ9Dz@3enpcBleiQrLut;stK+bA#nO53!#X3iEy1-Fe$t8q(=p!A?JqOGYNn*Sdo<!iqR2TtmJPiR#G@E`OAH@"
    "YQ0fYz$YCVumD4b_lHo4KUka$->5Ws8;Dq`=~VA@Z}<bbI@BE@xdw1#cD+-7@k&U9Y{F`2N#rze%gR}U4<CI<W3}Y^"
    "{M+D`(~C58J>66O=r6sRZMPaGYkew&%z|RSm7rK59kwGjulBBKtI|lu-3_lU2f_)2sQ4Se7I|_d++kv10vp-)PQS2Z"
    "PD?}X4E|`qBh=X2Hsp}wUNWI+e$tLmj3%+LPYphhr43c|Nao%~gD=;JN4?FkR0bWy*VN>++k?Ytk_whbug#lvvO12V"
    "g35*Y=jEX)bRO@+aKd{W+F!AiM+{+2c4SNpblrj&|4M8?$4dD*?2Fae-hPJ=Z<{UvF3~=c3n~H<fdcnT1cUyvLq6Sr"
    "Ql;g#h>JIY%{HCC;WG7yx0UJ}RXGy*ml1M1e>)R$K-kqqHp^ceXWo`j0gp56b%vs)co=Xkh_sYHf%T$D+oWp27k!iv"
    "x}rg$9~c!e7FjM#`aK%*4eNV_kg=MJ#Yu;gxqs*?>K{~(?@oW+M`e)4aCT0!EB$(?lyJ+$iPx+i3md*4?r3~LUY0JO"
    "m{)rod|(*ppU@XSu}0y(o;rFoE3$KI)#1`cp9yZe9<sNE6|S^4&wzhW-T8eu%l$zY6e=6+Ej&c5z+e@{`M#|iUUg08"
    "n^Hv^@@nMwMw(qQnj!Huw5>Mm0Fbaw+L|@aq{c1T!Vu(Do&{Z2J+HPS92Pz3$9w=PK(j4dmY%p}#M1x{qLZ7pElF7T"
    "5QN~71aZ8GAA0`$fsTxzST5R@rRFfRwv(A~pzMK=8>EhKD`Hu8P>=9N6^DE1>LlwO1~{7YO2?k8Jls3Z&mRH@=|6|y"
    "AmM`!^e)3M?I`e~OC9JKT_-rH$q>=6nd%&0Ew>yEprdrk9cm&R=``G{vfpv+_jEQA0tw5>R3GVhjDr)^)a232nntWG"
    "5eh!^xrMdVF6-E0>A)&IPD}3J&h69^=n0SbgAh6)%@5-byyTi}{I!+TZrN^oid~qWX2*(9VJqq_?0Tw<_ko1NYd(Gg"
    "6PmzmO=Q19yT>F0kY{iicrmAh8c*+b<lfjwT}VBt(K`G(j1Hm!Y|t*Fip3GqN4Ul)`cgjYG%fPfkQ<($-cHcQ`IVem"
    "6yWKTzm+GlwQrf!(8(!N4b2R2!pm&-tLjd^7K`i$TK|!G(JSQ~gzDI;L0?*m6<!lAl91HVy%pFk90^_9i(3%g%k4uq"
    "b%+6U&Ra<C^3LaoHXh8-sW8H%ny^dG8_PQ`;RCs(@YRnlZ0;2>cl>UY#Er3HT-$+SYOd%L2@g(t+B(sRA>XOpUKoEQ"
    "I4a@6J9gqj${bY-qsD5Qx4uwm)B-z-6x|aAK5D{e<766v_tPOuwL%bp7GVA|EL+BBFr3A+aU2v%$rrg5W;#b88a$Ln"
    "ea>bme?O?m$nX#uhVA(K1QhxT28V$(In6OK+Lbf=%)i<(`o>-nwjilbt+y2-@JAxa;Q7{sogY12Y`)bw!95VZF~yMK"
    "ci5TPTo1`kJ5eA6Kjm=FjUK|lC)g!m2L82%c1NmHd_LlU#>mDIg`^$~Ij#Z*P{vHuLkK-%3QWumG-9Y~mv;NJZGBnN"
    "0*Fl=;DjnOa99M!Trv5?nU|0y(2XTRMi&B>D2p%py!5Luq70pYI$?BB4Q<gMY(PqjV`uP8*qnwersQj(Q2j;eG6ivG"
    "2`(>$jqz_YBnYk9Ugx}{DuX@+ID)LE5g31^N0w3u;1KP@wV68P?5NOF-h~-r4<59K>hp~U>7*%i#uj29R$%4<eh5SE"
    "tf4kwk4_wEsq7HhAR8-xqfJRpIt2A+tcOl8!5y6A7P)Bo_jc>#sIGU~TKU&okG&8paD}aUi7n5TjF<8W0S|D`VReOg"
    "NWUy!9`D#xF}V^MN9=MvTE`O6^<WE$Ce|-lL>B{}+;)v;&qTG#ti-N#(H)xT?P%vesP@DtqB3q(g%i-zTUsMNLJs61"
    "CDLxvnt@<PN1VX=FYV}a$PbMEa0fQAzbRzokLFSMi6s0<k+VrjpR?b}G>qyqFzR&J|Ac*d&i$}JYb95G2(I`f6}_I}"
    "7<0{cBFPH?5zy~3rM~T;=3($#Od{;olbfe0P6l8Ify2DGZnKoO;oSSN*gOoDoDYGjC;^iwM|xT=P{RJsR~0-*hP-en"
    "QjKO$*R^kn4k0FN=KDxxi%vVb@m00-ZnCk`k5+!6y52`ESXJ`VLb1vDgW|XW5?(#%2`>7wnuaq}ZaZ^DRfYuxytMjG"
    "R7F_<S^q+jst)+ia#|NWsSpcMjy4831W}tP+F^K=9RfA~=)Y6IV;QH!y%ziGq>NTDRC<lU7SM%$^I4pDc*MAjhXk?4"
    "En`=`0VdAldkKPRKGy4oIhQ5O(3fVBDi>WK9MIUIEAW6_5lBbDV#x=6=tM>l9sT-y8b~6NNMU(cwV6l0`g|Z1R8u5L"
    "EQ)`M<M7Hjs_T&!R~}2B5YQIRp<n8{3mExCpYv~d+-M^&SS-h}5UhZ5GPr4^rCCR$pca(3QPJT`yAyyHvQU5Hmqb^T"
    "BTfQJA?RJ%rBFCqD7Ir8->6Ex7pBsyBjm$t@MXoMKF-ChFpnxRNN)WC<OK+(plD&t4C3B3@Rl^4#X9af9;Se*Ek`Vd"
    "Fx9H=AmFfC1rFo;7|QU7!5!jpsGhk4N$TL<77#x6)B^YIMc-(!xwF{P&?FYK70Q$n_HKa;vcMZ4+N{z?oj^o?FcSBt"
    "186HGiF|Fwf_X1+Fe4Ie))Y|02=|;hCE<4X)#G(65@DAnilS%?D}0<kDbF66fw+psb8L&BOVQmltjp7ZZZC1rkAAb#"
    "c&lT4F99}C-1U7TJNIr!rl-)jcMts%tGiEN#;?Sh>^Tg2Ka8ciuIqlMMNk>A7aBrT&m7Su;SYj%5hZoOZtx2*z880("
    ">o3IeRUQv`1<KGLiN{{)=R81opUicEd#}J_NUYv8E>r+8WMNI(4<`>TM;uQTD&yXQ^^!_-B{HF2G|TshGK7ucqv&g)"
    "@_psumu3{)1@ixnV8JUr*@14U7tMM7QbRgSej*m_!p2wtF?+Gy(mbkD+V6`)Rbx^)wRLH*O!z<g)k1`S)xdGY9-X1>"
    "S7ABwF~%$%<~xniH31qSqQ69X;Sm?G<Rhz#R|cULEJkedz*@oh{wH49PsBevIj&&xk~R<57w6z9uDQY#2+wqBtA?ci"
    "3KOr`9#>2%kHqOPr`-n+7g-woW)EgNV6PdpAn{9~laoK8^W(q`xr+n;9~0$!`v%I@Yo&`ymOXz^ZoH1(xMvoW4zQo*"
    "om7FX+|mhE0VhezSp|$_T4GNsU?lZdl(^H;lN7N7p3l92hW7nc&2OAmvK7{g+r33v0R-DlrV#+5Bw_*dm!0rDgv(xm"
    "5)^o#Ds)^z=s>m8u#5ZzFx-a)rvh!_JK9)GjU(2mTp4k~4UF({FhI2SaE-ItWpRw(35!xA;<G4>?0m6aff7fXwcLJv"
    "RO@>_5R$bBjD_LeIF*n75;}MM(h$@fF~SPOMhLLoTG2OW#R%?aps=vy7Q0@L7^2<rwRRnxdS_3=wHCpxh%$#1#$tQV"
    "H~{d8)(=93zZ-{)J9V|HSadiUWW%ea-B3bSkHG+3vM7j>tJv#}iDXl~9RtaZK>*V7!&u!ij<r|SavTF_cPMCxj19mQ"
    "#ddgczf<U`g*&;GIGdw`a;3G=Z|8ZHH&46qaQHGG%#9t!?0<=5*Oe0d;|HrImXMV77f3Nqi4wx2Oqiy&?oh=vL{-JL"
    "EA}<@+6uUeWC(n1TVi!dVtxucukC!TKlYR8c#i{`=H%BaDOqlUT8~TZJFMEZ^2p`ZK&1tEu%Ob9=ZW#@@|A7|J@e&x"
    "+rHFy2FU+mXlMO{F!n2iD#WSZ2ud*(M9qt+$jl;iUgjB8`yGF#nE1()TQ;AH2k94y*<rAJXu}N4P9Tf0RJAJ1<D;S0"
    "c>o39s75#ih(=qx+I7rV=pPZu5O*p7EDGI4H<;ZdAW8b&JYt~4pbG3tLK16zc*P#vn*sJEk&F^cYi;#u-R88(3OQ~M"
    "_~D0@N4uX-JEy6u<^E3hVg=9z!$3ZP2!OhU&nlP;%}mTV0Au2Zl2w)8pwAVy39%U<Sw@J+HDdh3K~t+#$(vaM+=3QS"
    "l#dNiXfB=Fp!KH;%Odb089|*Tqli_N?<GS{YNf&_&t|PUmdg$9sf^>F=hr(9_77)xG48iwv}+`a7s2{9W1}euX^ki@"
    "C(6dF`$j(@6T|h_^i!looWHMZV=<(1c2kxSxwlZ=0U-HB8i%yuF{gtaJKe7y-0>yh0M-r>UZsaCzaqL{k!aO?@1Yal"
    "C`Jra{HENX^hksP1eLb4=@d1YD(cB5;ad~F>w)5pA^Z=P@L&q7KrX4KF(F0CF^s$azJG;oC7dWs^s4so74bC*Ww-sb"
    "0^kzBdUlg<t&FTj){BGqMx`V$XtG*wzN8cxcEdAJ?J{uRYKmE+-Y85OHhc-`0oe&~?mEXH{v`!4AzwPNY}K@fBS53t"
    "@gh(+xWzxhT{eXufm{TVtk%}eyg<c7yd2Mu=0qoNLs-|PbRQ$##%volA0`B-M83!#&A-r&89dxZvgO3o9(E&~OYGb{"
    "Pi!QJ7Rc`kM@X2_)byr!gBPc|jNJycz1qxJ3Cxhh?<yl^4Y<okF-w&Y>V0G@n@gI`rqw~L6F8T9u#&WYA|V4Flvqx!"
    "z>+f?a|<`bMZw8dM0*4Xs48`WH}gr@TD3LLBw)NkZ_8c_E@In`=R&(@x0AeqA|J9SxXQ+TvLozE31Tec7JkDiq2abG"
    "{liAv75P|XQYfL_65vAKiyxGu#-iC){tv-+nL4G(15fW&ZINh<rzEP1b;e-6^<ciAfjkvJ7=f3o(k{p^MwJUdm+-xE"
    "0Ck0wO64KYEF+D36^NFQvQV)ba|OPMNBxG_h(HBZacP4Rpd1~P4~bDxkbqaPO~;Ycka$7Z1TR*g9k8vNwC1#4@a#sX"
    "TR45y(1<OH;nMxkKKcZ<CqpeO(JcFMC@T3vkR~Up@7qv>96O1<elWboq)_DTK(NRVGf)}Qwb`<NlCX6YR}vOGL4SkL"
    "G8M57Rk?p!`1FNZs%`!iG0NV|5g<8CmG8TZP^n-vI2G`GUGK;v0<E^Cmrr6Y*KftH(D4uGOE5lEhT!>(#rJBahr^I|"
    "WCLJ!BI>QJDs$a2P=)3pK+BAba25F>7<Gi=`kPWXmc7FeI+4rhI!01IRPs#eR|&HQaur?m;1Ku|Q|>e6Lh83;KQOmd"
    "uon>PVLZ&0bR{CR^V21j4*aA%KwC37Y%jM!@Pq2pYV&8Dw^lqpYP(WRWLQlN08Hjn>JNc9B-zLm@hvA$1?B}zRtmrg"
    "*uftjXa`h<FdazxbR8ForBDm}3z#j7PP{)n)o`x$ut3FzBD$q0Q%Vis%2xPXaQkHTz2CMN%s<44Of|(p*Bjyz+Cm>!"
    "0QOk1M-($!IPP<@%pOtA5m$`ks?Pw=f@b@Cgop9>!cvC{$T!lxbbDxOk2$-kXwLL32STmV2Ylec6?m5i@GrgwO*KNc"
    "YhYfIk#?Do<_SAyZ&ny=mjD?d-Qf?DYr`K(T1Qc7*Nz_uUkNq!ArByV1*9KL&bIf%y4JZlJHcmFSuE21ReOd@L#dF4"
    ")b|P%7&*VvIT%4q{-CDe7KhuoGU%b8GD3Hfr>72un##b5JQo>JU76@2(`$`#N85d)dP4<}imXI%Refx*kqKU;z5-hV"
    "CXCO>NPGZqb;xQYMm4nUmd;7i2Jkb959aSjpxN-5$VU+QuWm!c5HNIxT~6uIc9>H_R~&X7d4eg^j4YbPro;wdhykkk"
    "O;2h)pqjM955)nd^c1N!N*vvS&4?of>i||J0qdBZmJZJ&#f%8?R(!!XQ@6>@i35wNH$H(mqi?DPbY_N8n{&|Z;Ic4&"
    "=vF^+@l*h3!XZaO=qLV+aVY%tI_^YP_ksJzz8d3tC&te!C(BD3%Ek!T{Uf}k3VHL`ESxcBge6BBGoqM#h>&BJ13JZb"
    "BGOi}EPgvJg4i)_Jbq5)FqH!&fAHloS9;=5*(bpnc^a~XC~jZ*_LP!Q`U0x$0WLtdmO^G^gh?V4ACZ<RkWL7ofapYC"
    "$mr{i!$e1HpmA#0n3cJ&J>d)Sg*~38fA%!P)Kys#XGYdB_CA3vkqArsb6zDgz^Ph~55wixNC-&tm+)<s=}SVTA}g7~"
    "lj~SvI+H6CN>yYunKES0YajPI{U@_r2OG+&kl*M8&*&Z**Xm@>($LnXpsPBa<0DL=Cu0yru34YBnXk!rW`u3Bjg_(7"
    "gSiit6-%HYuhKH1B5`A#FSSSLS*+c(+moiapsGwK`tru+o3=9j0jG}~gK78pdb`4{ukf2X6&X+2VlW3|vm=##P*qGa"
    "<@R)9rN<)RKmvs;m1Fw%f0G#k{}W(eey^7Uph7lBN)zo@--_I-qy6Lm0|3ZXGk6@CEk%xURMOJIUvC;$@R4y*cf{I`"
    "J4-_g%e1~cBH0XAa3mSg-ZsZ0Itb|}BNtP|`d6TVpemx72zelrOi(8tD_JRekX~bc2nw*$TY=*P0Tg}=RQf}L<jaFL"
    "49wy>W-4}Y(_c%P$W&E%Xv}T@LMGUH?&_rlqA4xN$|ZrYh#+ao+?kkD#;`5nNnn90kkCnyx~@P?e{L8@to)*W-12l?"
    "S9{+%SL(WM8I$eI2iNDXm69)xd1PCeKLBji01SPETB-mH{Us7D`jI*TQgz8XO<&kXHK4v?1V|5BP7cw|@zr)XmyTU-"
    "O@NGU7@b%5oi>kuw>*k5HdA&WuKx-vHS&|ns|3<T-j@0kMS<#MC)nb0k<BHuzAh#xd?*pCNtMMAl+Xny9GM&SsC7WH"
    "Vvc;&-WktcSLD24aYh=Ra5Jv3K8J~4pW7L|CCXj>=||MhdcUJ~M?9K&_<Q9fc0s4dAr4Z5g16E*tn4n4(e{zvMdB2o"
    "N(u=eKVGwNw`0~K5?bsAbE_EU{p`~mnGH$Rb>nillEP_xQ7&K`x6erCY_5-v(O=>B>&jzP$KTp%8se)hi~(p}V)g;m"
    "*R@Yr3C`o?drlcyDiXQ~u3UHOtlxmXMn{pprGN1g%HBfn8!G!@Zg~i;qMThqq{BpSNZ8;<C^GAZ=2U2<5VBAW_&W9%"
    "uu8xVEEMMh%lnN78EA|b1>5*iuc}}%NV9wA`&0(rb_3>6?GTA8i<4(G+q&~Xv6^TouEw_OX}n>pRv*Cu5>0Ss7A5-a"
    "VYh;5B-Rihrjco3IP10!E}-c%JCm;F(ZqZ+AK9Mp)m9$?2Yk>U0gOBwBFT(}Cb`e{`>WY~r%Gizy(ErYRi2wG(^>>m"
    "-Q6DceCkk<jOO>D$_g<>$Bf!q;ZjPl#=dvU7IbiiGlNNLe#y4>xKR~VOlOM=i_$ky9tv2hk-}z$kg_ASKwNG>UFoB+"
    "_PQfgdK^NV@^VYR8Gu(UE<jlD=N#oWa@eHDEj1uvu!fS13xk!ZKQa=oZi>(Sq~@xCU(G{n0&4sT@o?{Y{IUFN$V=hr"
    "QZIMpWyzlmf)4O0nwA^$a~rT&pzn?1am2+r=8sI?7N(Wv>8Xfbuk?2&5=8oF<;R%|#YhhnfOyEK#<V!!nQIz`<SlL4"
    "ZfKUm0!-knG&Eag#}P)4S)U_6PI)41On5A&0Yl{$DGO}{CN$RL^_Bq6bhCt5=6~w%Ox$8ueL{#fMOXuZ3yh?ocqb0C"
    "zymR{j6(YD3ZK$#U$jekNSa(4d~nYDH1LMr=6||PdJ=z_&-qfqsS#<jk()<`U$n;S1(fH;WXK3@8`ZEz+A+l8;b0^m"
    "8cJz8+`2%C*wxlU|3jzxl}Wf!@zH!CyQD$j0U{G~2yoX0wrL=0P#%A{j)c{esa)xH@Rh-MLPIY`&4h4Vs*$!oG%?e_"
    "@Ij@%(*<jaMpB<<duA$OBQjuLiCsy@nqd~PR`~7|8zdTEO|HzAs&DTD`qdyLklJ<Y&#08!VaYX2oJizs7dOacWiB#d"
    "^y}<`Ah9)$LMLu!0Cg!az<}X8G6lZ@gIm{pGkIt3%Y6rG<1<_NI?&plnbkWp!0!W;!aXh&vI&t_)wn!J3V*eSg|y;9"
    "KLYGVb!0RID(l9Cd$q)oC^sV>P~YUuF<=XSxPSr6S{W#BMZTu*Y^H_>h@Leo^$~)}-d0PM8B-2CR@}a!v6dR_iH<%i"
    "bsls`)$bL7$$3X+p&9w94B)Ly{fRHbE)EX`a?C5i(0{yX_(Ka(9b?nM|Cbw;Ero+uEzJl2VuJNzxeLPs|I&^J`}ShX"
    "&PSelVZdex-^W<U@lZgZK8}hpkON<kJWgfEfCWo^&PvNLI@|-$0#9NoKw4=#Ge`3Sy*$%o>Ct?!(Zk-9(+FF5^!e9?"
    "0)5}^jy#Qk5li5_bPOX->{p8z!1On1aI_>zRC;7gj57xaGUdj#G7=$<?u>KL<GzC{Fu7<iEpfjOzsE7J8TJtj<a{%4"
    "pujL_#BZjEn;k1TkMo67BZqXTC<atnrhc=c(9<fyS>rF*bbdR$Vp=vuhzlCY2fKvNT6;`dLDR9v<4#zy)a)>kd*1<O"
    "xX(c%v~osrSOSl=$UABEN&q-6binS9Tx6zeQW9H@zm@>Ta7DiGAZR5V>lRor=B_j#!6u_!tTK~cnxPG#uz(loSL10B"
    "#sk+(B8tfZANIL(t68myktCoa@Ej(bSi%J@JPTHj`3#-1la_^jwDQQX5u{qJg?k(~V%Ruomw8?wYtbFlZIQDGn~9ud"
    ")4YYITV`6sEH^t)%n<hVPHYj~&rsV5x!{*tDvmlQcT93SiTyzpNKmBoF;?TM0Ld1R(9`T<^+@(3t&e!v9<o>l-dgSH"
    "at*jA9?``4?NixV-AC!vie)JIBo$WK*fUH74-QY~0uESL{^AdH<h5X1Z>;yR38A{5UPG?rOkAIW<*^pCoRn_g?Dk}s"
    "N#pATIb6Alz8l(szFW;JyTlV~TxldrBzIbk1S@h%(X@kyC0soC!qSB)9~9$eCTZJvkl{LwpG#!vCrsCPH19-`sIG9A"
    "^E3OM$>S~HX{J<NHyXl_Tj{<S!m9KPJ6WXlV+(}68m5HN&TiQKkz!m63%mVEzGQ;C5d(p5@D3YAQJ`WGoy@;vCL2(#"
    ";ei}$3&oj?1(hZL9g6$NQ6}-x<VOEF0{{f>kdY~XKKY}vH{EVnOW@n>>M>+-QhcN7Qk=}K!oMBA8^^<Y+1~Bbc)1O+"
    "i}n2N#2L_(ZA7~5zr(A{QcuZKz-oqihToJ!s_87g&qsb@y=6o<UbG_tG*EB4xki|`F3xst*Ws6K25Oz80n{4KOcpsw"
    "L;Y#({mgrBg0QuNB(=!YWRbmG@2tP|voqb1%iM(~>(?D(_b|m<+|N_OF~pzo;<KciK(}RZr~%*Rf+Yvl6GoiF>if=Q"
    "1lb_+Uj8bIA3s5y?nnQf0v@*$bgVH&t|z5>%H(2(j8Byjzh+8{QIpukkPe)SC!Wm{LplCL!%E>awVyCsw`0%j;maFm"
    "7Ky2$Rf!X}o(WxqxiY&`kj8yWD}W6$%beNXfePmVje+k-jm8adAZ#BRoBV+ivvcCxbtSY;2MsO(f|@c=w6Hmyu^@pH"
    "NQ}k)zBaSuUmMjC>eLb8+sVO}zb@A!{)!JugpO}j?Es%<xCzwK9buom9OyQuvi3o7yanFT2+l=Akzz{^Z&%~(FfgTh"
    ">UqUhz}_Nxnzf^}aIfOlq5jdWRJEPRzRV71$PIOrg-8W8GAuDBUn!x4MK!_Z68LIN1ND&+4l{~ylP`TvH^Bu^&zhYj"
    "MJ2^7EZKcs5w=c?D>`NEG=S&)IBXb8%b7=CTPF0_^N$|b!=Kk;UIX~5<z#c?L>_fL$iRQ9fUU{id<T1kF{GsfQ2QC^"
    "y9_BdU4+!nMTq|3m}hi2;Bq7;0JaO2M(_|m*E4PiQ`<9s5Hs1=)98o9xjGAk-fPS)W^G(2Arx8=mziQ(=-Ifb0fR_U"
    "W=2>t`=CS9;s@)_uN_`NYxBBgd9or6YEnxA+iEkEzscuz78IS*Wn+=v)gp&gcy*0AtSo~h4}VZLtG}|g>&IJGC{EG3"
    "9$bPC?4*50)2qD`TV_gf)pR@|!PSF1D!CPW1t!Q}KlcP!6TJ4g?@TyAS_M#<w`2D<3jqK)zbKHlgxH?!fflzzoqZk3"
    "tiXRtqsVGI7Tu|zt@krWwe`5;R8Tkz*q#osl$d*IcP`<<2R9nD>y35iI@MkUj!$4B>%4gQ-0jzoQ&IX&@VZ{@5zmF2"
    ">kjlUJQU*Gx<%@d^h0e<3Dm0W{|{35e}xi1K*iQA@oF2D^8OdyWZiCBNprd3PAW-cil8-IOVxgHg|2nWdBSpJOo8E2"
    "swvB+S6bdt$;ybda(J!X_@+wNjv;~8Uo_tXf0TLef`tbzF@Y?2kjblYt6*>M8!c{~8AY@PeVjOy&83I61h!Dvf_lGG"
    "dCW+M$4;FT7ja7=L+0`dLwXZ4GpAQi&KQnyFg-xyuhP&G5$`166BDb5Sp%q%lmFK&U{n6!)+=Kst~5&tb=WObb6ttm"
    "&lS0*<XUrvD8i;zzq9tDN*52OVnuQrMvGWi_MhuWn?16Rg#Cbn4U<P0dwOPi-om3;-}V6gQppo4kr|dz$$Y7Yl_)(|"
    "%gYW0L`=gP`!TNayfA~;JYFXtT*ifQ$GK8g10vAI;T}&+p#i=q{D1+Tc;E7104QdHEo1(#h_Eo^|8kX$mlPQ@fbCF="
    ";+n2lWp*0F8f8ALY`CRTSA%2P1YK-@=<;Fj1BMg;EA7Kkdl(Y%6=xc<1Mx2_T?x?MmDY=wK%tU;n`6im@Niy769e#&"
    "s&AUV2e);*RSkB^_QN-Ux7rOjM=QEJaRysMDzAr`SZTakB($<f;U#CwIIg0>vuK_S%QhZqD)D#W`<WfuM!%EsV}^TV"
    "V#k&RD6z_YhWo<)&d6_pL7eGLv>}5?54*805knd>S-paz1B*DXe<bNaTS<>gb8L)TXN;f)_D3I+x`&&`GA|oHzV9r{"
    "9P~Vi@7QDrSjW+cNAmG~v{lC=FD=~46fwq0M=SE3E3*T{Xx5dv*4U|4{)x4qIc}s!MN)w-F*_Vm2JA>2CI`w%eriL~"
    "g`$n9W|K(_IaE$AVgo2qF4`|t+CTOZ@_VKQLkdjpx6S;Ecs?^`fT%27=XwRE7z)L_>icnM09;su(@s>=aWB-PO=iUm"
    "@7KH@H$q^(bWd7F0FvY;Evo1Weq9pW#@l9<JPFszmb}|VA4$>TfLC?RY>B%GPP%ZL^*a8Xg{ne%Ql}324v<B_##m&6"
    "3O1Lfi*K>SA3S;hTL|GoZz5HEXg}<F-A9~hX)2y}-D#Hepac+24oppv)%S_;K-JzE3Szvl?UU$h3*cg4@a#@xM$pD_"
    "p}aX>Ud|h!YJ&JR#-{j6G!Df_TxlNLEd$x{V4UQC=y;n4ToY0aJJ5ETb!uFqz+v_qaIYbX=~$dv><8_#VBZ>9mrpzV"
    "uFPOIBAgXfrKbgT_WevB%Sjsdy$|TrBS6CUTdHyFZ-na(*`;LNo+B@Z=J7Q%wfxR4i2ej<N_M&(7#UNJGr@N=Ox+^a"
    "S%N<N!HQe8`I9Ab18tsLg0#`rx-U%?Ghphn9e$3f#MHH*c#v!4PZ-6%lS^YhY36(zW(-*`EG}cd>Bn#z^QFtCP%L+n"
    "_!OX)!WWV?EoBMZ=Pu{=fN4#}xA3T3SN|vKmu;;_oRO{vGu{e!E`>0m7XNVu@Kcf%r0K3Q!o!Jg$#b&erYn)#ikr*t"
    "p2Hpc^X|X%3zb{nr*~Gj&V>*s|LUr|Lx$h3C;lYaZCp$D%gZiw_^-MiDSEk{fIBLJ-y+`{2QRyy@`Rf*uPNP;<t=s("
    "KDFeTQC^1wkFtP6PNj1RLxL``Q!)?(_EAABwvOduPrf$p_&PS$W-6*7E}}0zZ|c^PD)r}|dq!n$_`Jo~kcusHPut?v"
    "i98>baqXB|0>VguZCpXckBy9f$kt_DplpZrB=q=P1+O%0<0P20xX!LiA&Ao+kVh~&+$bK2upYWWCS+4e%!m1w{h9qQ"
    "k0K!#F%h~2ucfv9A=4~^F)~G%t$ExzcAp>k!_rk<6p3+TUS!@x#ZIzK&BG!YR^E6%-<c4~D=T~&AKZS9Tdy;M$CTYI"
    "jPcCfcAxVAQo?xTlNguejqpY7tE4{=G@)zrq=rA_8euG3gd*9#=8XnaE9-%%B{6KJHpHVDVk`iak=+Cp*{x)~4J6k-"
    "H!vmI(gdSy`J?qOa8U;yGr;Y<4%vXNJXE%&ACN;f{k8q~^wOLCWOobSBJbsk9Li_K15#NN_xgoL<u7Fz(8Ptu5t)A<"
    "l7LcXQen#r`gl;^S7-#n&<LvB;d9>YL?=h;bK8Pcog@{un?gKkSXKr(>ZGXje<6T)INr}3Fs4iWl%Lm>VXkRMZzXm7"
    "eTbO{Q7N#>?(JMzuEBNP$Q|b+pq0|XKrzByw1be;8|x&2{7+WMlO57@OW=RN865w(?&t&#h<Cysh%3J`9#=S@CFM<1"
    "2O71-YJS4^tze$}-3ZOrVYX+v6OynK^31{*sH+Eiz$I<Zd1oKit9hZv<M`c70DjD!ksPmQ8XJ6ajXP}|hq>nanP|tD"
    "H7{-kGG@%90)^l5Zto-ZFl!!zj%~-So8fEN=VGack<r_3mpr3Wcfq$SF0GN7zD0sO(7@1P-H6sy8W~jD4eHLHY__ny"
    "SR!N<#d=>A8FSOFlQl~w%m$cd|IwxBO%Tm~Zs%^g(NK(Qpql0qRG2qQm%X)%_b%%u#m4IkKMCq;f@B7a0M(N_92KS("
    "<2+O`*@EJZqdr-B<86lfz6_!PfZ5}h0$%RS3ebSA6wzS}yj2PeDYB~N<3QP+kozV>(2d<{a0Rq1o*bKcwMT&3#d&Iq"
    "sl~UOvV&k!`t?NMu$f*SQp6V?M4E%Y%<K)2OWr7K7b<Z*2OU7|>L-PSGh}Eq?dlOC$AuqP-i(DxeO$+*AS-luv`4b~"
    "`x=9$)OvAy8ZZ26*O>R+4;(y1{a>a{Al1w}%^RAY_vHeOW9Hc($$TcpGZS_O>X_?acQEaq?V4$@-N!1@4#*O5;eXka"
    "+qK$*ziSrPczT8P=#KcfC>1na$2cN#Zu8qKT(~!QaBAqg9nYr-@qYkhG5x>"
)
_ASCII_MERGES = {
    (bytes.fromhex(left), bytes.fromhex(right)): int(rank)
    for rank, left, right in (
        line.split()
        for line in zlib.decompress(base64.b85decode(_ASCII_MERGE_DATA))
        .decode("ascii")
        .splitlines()
    )
}
