"""Drive the two logical calls against one confirming packet's frozen inputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from living_island.agents.llm.provider import ByteTransport
from living_island.agents.v2.calls.changes import ChangeSetOutput
from living_island.agents.v2.calls.contracts import Contract, Parsed, Selection, digest
from living_island.agents.v2.calls.guard import (
    Admitted,
    Assembly,
    Call,
    Candidate,
    Prepared,
    PreparedRecord,
    prepare,
)
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.agents.v2.calls.provider import (
    Clock,
    Dispatch,
    Interrupted,
    Returned,
    Terminal,
    attempt,
    restore,
)
from living_island.agents.v2.calls.wire import Wire
from living_island.memory.v2.changes import StagedChangeSet, stage_change_set
from living_island.memory.v2.store import MemoryStore
from living_island.memory.v2.validation import decode_change_set

from .inputs import FixedInput

type Stage = Literal["selection", "change_set", "ready", "cancelled"]
type Failure = Literal["parse", "provider", "stopped_unfit"]
type Cancellation = Literal["woken", "death"]
type Kind = Literal["consolidation_selection", "consolidation_change_set"]
type Outcome = Literal["adopted", "abandoned", "failed", "stopped_unfit"]


class Authorized(Fact):
    call: Call
    kind: Kind
    assembly: Assembly


class AttemptSlot(Fact):
    dispatch: Dispatch
    dispatch_cursor: str
    terminal: Terminal | None = None
    terminal_cursor: str | None = None


class LogicalCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorized: Authorized
    prepared: PreparedRecord | None = None
    prepared_cursor: str | None = None
    admitted_wire: str | None = None
    attempts: list[AttemptSlot] = Field(default_factory=list)
    outcome: Outcome | None = None
    retry_at: datetime | None = None

    @property
    def call(self) -> Call:
        return self.authorized.call

    @property
    def sent(self) -> Candidate | None:
        return self.attempts[0].dispatch.sent if self.attempts else None


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: Stage = "selection"
    reason: Failure | Cancellation | None = None
    calls: list[LogicalCall]
    selection: Selection | None = None
    selected: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()
    change_set: ChangeSetOutput | None = None
    interrupted: Interrupted | None = None

    @field_serializer("change_set", when_used="unless-none")
    def _sent_fields(self, output: ChangeSetOutput) -> dict[str, Any]:
        # MF-02 distinguishes an omitted optional update from an explicit null.
        return output.model_dump(mode="json", by_alias=True, exclude_unset=True)


class CallDisposition(Fact):
    """The durable joins reconstruct the logical record without a second copy of the wire."""

    record_schema: Literal["cr/0.1"] = "cr/0.1"
    authorized_cursor: str
    prepared_cursor: str | None
    attempts: tuple[tuple[str, str | None], ...]
    outcome: Outcome
    ignored: tuple[str, ...]


class _Sealed(Exception):
    """A boundary sealed this call before its exclusive journal claim."""


@dataclass(frozen=True)
class _DispatchJournal(Journal):
    claim: Callable[[Dispatch], str]

    def fact(self, call_id: str, slot: str, fact: Fact, *, exclusive: bool = False) -> str:
        if exclusive:
            # DL-01's only exclusive publication is the typed pre-exchange dispatch.
            return self.claim(cast(Dispatch, fact))
        return super().fact(call_id, slot, fact)


def _authorize(call: Call, kind: Kind, assembly: Assembly, journal: Journal) -> LogicalCall:
    authorized = Authorized(call=call, kind=kind, assembly=assembly)
    journal.fact(call.call_id, "authorized", authorized)
    return LogicalCall(authorized=authorized)


def _retry_seconds(call: LogicalCall, terminal: Terminal) -> int | None:
    # Three retries total per logical consolidation call, including any parse retry.
    if terminal.n >= 3:
        return None
    if terminal.error_class == "invalid_output":
        if any(
            slot.terminal and slot.terminal.error_class == "invalid_output"
            for slot in call.attempts[:-1]
        ):
            return None
        return 0
    if terminal.error_class == "rate_limit":
        return (5, 10, 20)[terminal.n]
    if terminal.error_class in ("timeout", "server_error"):
        return (2, 4, 8)[terminal.n]
    return None


class Workflow:
    """The world thread may checkpoint or seal while a worker is in transport.exchange."""

    def __init__(self, fixed: FixedInput, state: WorkflowState, journal: Journal) -> None:
        self.fixed = fixed
        self._state = state
        self._journal = journal
        self._lock = Lock()
        self._worker = Lock()

    @classmethod
    def start(
        cls,
        fixed: FixedInput,
        *,
        resident_id: str,
        period_id: str,
        tick: int,
        journal: Journal,
    ) -> Self:
        call = Call(
            call_id=f"{period_id}:{tick}:selection",
            resident_id=resident_id,
            period_id=period_id,
            tick=tick,
            consolidation_period=period_id,
        )
        selection = _authorize(call, "consolidation_selection", fixed.assembly(), journal)
        return cls(fixed, WorkflowState(calls=[selection]), journal)

    @classmethod
    def resume(cls, fixed: FixedInput, state: WorkflowState, journal: Journal) -> Self:
        return cls(fixed, state.model_copy(deep=True), journal)

    def checkpoint(self) -> WorkflowState:
        with self._lock:
            return self._state.model_copy(deep=True)

    @property
    def state(self) -> WorkflowState:
        return self.checkpoint()

    @property
    def sent_pending_ids(self) -> tuple[str, ...]:
        call = self._state.calls[-1]
        if call.authorized.kind == "consolidation_change_set" and call.sent:
            return self.fixed.sent_pending(call.sent.manifest)
        return ()

    def staged(self, base_store: MemoryStore, tick: int) -> StagedChangeSet:
        """Called for the successful, ready change set, after the world death check."""
        state = self._state
        call = state.calls[-1]
        output = cast(ChangeSetOutput, state.change_set)
        proposal = decode_change_set(
            output.model_dump_json(by_alias=True, exclude_unset=True), self.fixed.base_version
        )
        sent = self.fixed.sent(call.call, cast(Candidate, call.sent).manifest)
        return stage_change_set(base_store, proposal, sent, tick)

    def _prepare(self, logical: LogicalCall) -> None:
        authorized = logical.authorized
        prepared = prepare(
            authorized.call, Contract(authorized.kind), authorized.assembly, self._journal
        )
        logical.prepared = prepared.record
        logical.prepared_cursor = prepared.cursor
        if prepared.admitted is None:
            logical.outcome = "stopped_unfit"
            self._state.stage = "ready"
            self._state.reason = "stopped_unfit"
        else:
            logical.admitted_wire = prepared.admitted.wire.body.decode()

    def _claim(self, dispatch: Dispatch) -> str:
        with self._lock:
            if self._state.stage == "cancelled":
                raise _Sealed
            cursor = self._journal.fact(
                dispatch.call.call_id, f"{dispatch.n}.dispatch", dispatch, exclusive=True
            )
            self._state.calls[-1].attempts.append(
                AttemptSlot(dispatch=dispatch, dispatch_cursor=cursor)
            )
            return cursor

    def advance(self, transport: ByteTransport, clock: Clock) -> float:
        """Prepare or dispatch one authorized attempt. Return the remaining wall-clock backoff."""
        # A host can offer work from a scheduler more than once. Only one worker owns it.
        if not self._worker.acquire(blocking=False):
            return 0
        try:
            with self._lock:
                if self._state.stage in ("ready", "cancelled"):
                    return 0
                logical = self._state.calls[-1]
                if logical.prepared is None:
                    self._prepare(logical)
                    return 0
                if logical.attempts and logical.attempts[-1].terminal is None:
                    # A restored in-flight call needs its journal terminal, never a resend.
                    return 0
                if logical.retry_at and logical.retry_at > clock.now():
                    return (logical.retry_at - clock.now()).total_seconds()
                record = logical.prepared
                candidate = record.candidates[cast(int, record.admitted_candidate)]
                wire = Wire(
                    cast(str, logical.admitted_wire).encode(), candidate.manifest.tokens_total
                )
                prepared = Prepared(
                    record,
                    cast(str, logical.prepared_cursor),
                    Contract(logical.authorized.kind),
                    Admitted(candidate, wire),
                )
            try:
                returned = cast(
                    Returned,
                    attempt(
                        prepared,
                        n=len(logical.attempts),
                        has_running_action=False,
                        journal=_DispatchJournal(
                            self._journal.keep, self._journal.create, self._claim
                        ),
                        transport=transport,
                        clock=clock,
                    ),
                )
            except _Sealed:
                return 0
            with self._lock:
                # DL-01 already published the terminal, including a late one, for inspection.
                if self._state.stage == "cancelled":
                    return 0
                return self._finish(logical, returned.terminal, returned.parsed)
        finally:
            self._worker.release()

    def _finish(self, logical: LogicalCall, terminal: Terminal, parsed: Parsed | None) -> int:
        logical.attempts[-1] = logical.attempts[-1].model_copy(
            update={
                "terminal": terminal,
                "terminal_cursor": Journal.cursor(terminal.call_id, f"{terminal.n}.terminal"),
            }
        )
        logical.retry_at = None
        if terminal.error_class:
            delay = _retry_seconds(logical, terminal)
            if delay is not None:
                logical.retry_at = terminal.ended_at + timedelta(seconds=delay)
                return delay
            logical.outcome = "failed"
            self._state.reason = "parse" if terminal.error_class == "invalid_output" else "provider"
            self._state.stage = "ready"
        elif logical.authorized.kind == "consolidation_selection":
            selection = cast(Selection, parsed)
            choice = self.fixed.select(selection.read)
            change_call = logical.call.model_copy(
                update={"call_id": f"{logical.call.period_id}:{logical.call.tick}:change_set"}
            )
            change = _authorize(
                change_call,
                "consolidation_change_set",
                self.fixed.assembly(choice, change_set_id=change_call.call_id),
                self._journal,
            )
            logical.outcome = "adopted"
            self._state.selection = selection
            self._state.selected = choice.selected
            self._state.ignored = choice.ignored
            self._state.calls.append(change)
            self._state.stage = "change_set"
        else:
            logical.outcome = "adopted"
            self._state.change_set = cast(ChangeSetOutput, parsed)
            self._state.stage = "ready"
        return 0

    def recover(
        self, dispatch: Dispatch, terminal: Terminal | None, parsed_bytes: bytes | None
    ) -> Interrupted | None:
        """Consume the persistence owner's next durable dispatch, including a suffix after save."""
        with self._lock:
            if self._state.stage in ("cancelled", "ready"):
                return None
            if self._state.interrupted is not None:
                return self._state.interrupted
            logical = self._state.calls[-1]
            if logical.prepared is None:
                self._prepare(logical)
            record = cast(PreparedRecord, logical.prepared)
            index = record.admitted_candidate
            last = logical.attempts[-1] if logical.attempts else None
            open_slot = last if last and last.terminal is None else None
            expected_n = len(logical.attempts) - int(open_slot is not None)
            if (
                dispatch.call != logical.call
                or dispatch.n != expected_n
                or dispatch.prepared_cursor != logical.prepared_cursor
                or dispatch.settings != record.settings
                or index is None
                or dispatch.sent != record.candidates[index]
                or dispatch.request_sha256 != dispatch.sent.wire_sha256
                or (open_slot is not None and open_slot.dispatch != dispatch)
            ):
                raise ValueError("journal dispatch differs from the authorized attempt")
            result = restore(dispatch, terminal)
            parsed = None
            if isinstance(result, Terminal):
                if (result.error_class is None) != (
                    parsed_bytes is not None
                ) or result.parsed_ref != (
                    digest(parsed_bytes) if parsed_bytes is not None else None
                ):
                    raise ValueError("parsed output differs from the journal terminal")
                if parsed_bytes is not None:
                    parsed = Contract(logical.authorized.kind).parse(
                        parsed_bytes.decode(), has_running_action=False
                    )
            if open_slot is None:
                logical.attempts.append(
                    AttemptSlot(
                        dispatch=dispatch,
                        dispatch_cursor=Journal.cursor(
                            dispatch.call.call_id, f"{dispatch.n}.dispatch"
                        ),
                    )
                )
            if isinstance(result, Interrupted):
                self._state.interrupted = result
                return result
            self._finish(logical, result, parsed)
            return None

    def cancel(self, reason: Cancellation) -> None:
        with self._lock:
            self._state.stage = "cancelled"
            self._state.reason = reason
            for logical in self._state.calls:
                logical.outcome = "abandoned"
            self._publish()

    def publish(self) -> None:
        """Publish each final logical outcome when the deterministic boundary applies it."""
        with self._lock:
            self._publish()

    def _publish(self) -> None:
        for logical in self._state.calls:
            key = logical.call.call_id
            receipt = CallDisposition(
                authorized_cursor=Journal.cursor(key, "authorized"),
                prepared_cursor=logical.prepared_cursor,
                attempts=tuple((a.dispatch_cursor, a.terminal_cursor) for a in logical.attempts),
                outcome=cast(Outcome, logical.outcome),
                ignored=self._state.ignored
                if logical.authorized.kind == "consolidation_selection"
                else (),
            )
            self._journal.fact(key, "outcome", receipt)
