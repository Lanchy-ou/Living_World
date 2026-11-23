"""Synchronous logical calls. All retries use the same frozen wire request."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import cast

from living_island.agents.llm.provider import ByteTransport
from living_island.agents.v2.calls.contracts import Contract, Parsed
from living_island.agents.v2.calls.guard import Prepared
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.calls.provider import Clock, ErrorClass, Returned, attempt

_DELAYS: dict[ErrorClass, tuple[int, ...]] = {
    "timeout": (2, 4, 8),
    "server_error": (2, 4, 8),
    "rate_limit": (5, 10, 20, 40, 60),
    "invalid_output": (0,),
    "provider_error": (),
}


@dataclass(frozen=True)
class _ResponseText(Contract):
    """Keep the exact assistant text at the same boundary that parses it."""

    text: list[str] = field(default_factory=list)

    def parse(self, raw: str, *, has_running_action: bool) -> Parsed:
        parsed = super().parse(raw, has_running_action=has_running_action)
        self.text.append(raw)
        return parsed


@dataclass(frozen=True)
class ResidentReply(Returned):
    response_text: str | None


@dataclass(frozen=True)
class Caller:
    transport: ByteTransport
    clock: Clock
    delay: Callable[[float], None]

    def dispatch(self, prepared: Prepared, journal: Journal, *, running: bool) -> ResidentReply:
        contract = _ResponseText(prepared.contract.kind, prepared.contract.verbs)
        prepared = replace(prepared, contract=contract)
        counts: Counter[ErrorClass] = Counter()
        n = 0
        while True:
            result = cast(
                Returned,
                attempt(
                    prepared,
                    n=n,
                    has_running_action=running,
                    journal=journal,
                    transport=self.transport,
                    clock=self.clock,
                ),
            )
            error = result.terminal.error_class
            if error is None or counts[error] == len(_DELAYS[error]):
                return ResidentReply(
                    result.dispatch,
                    result.terminal,
                    result.terminal_cursor,
                    result.parsed,
                    contract.text[0] if contract.text else None,
                )
            delay = _DELAYS[error][counts[error]]
            if delay:
                self.delay(delay)
            counts[error] += 1
            n += 1
