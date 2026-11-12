"""Typed P3 seams only; IO implementations belong to later tasks."""

from __future__ import annotations

from typing import Protocol

from living_island.agents.p3.types import (
    AttemptDispatch,
    CallDebit,
    CallReservation,
    ContextRecordP3,
    DecisionRecordP3,
    DecisionRequestP3,
    LLMCallRecordP3,
    P3PolicyPrivateState,
    ProviderRequest,
    ProviderResult,
    ResidentRuntimeStateP3,
    WireRequest,
)
from living_island.world.protocol import ActionPlan, BoundaryPerceptionDelivery, DecisionTrigger


class ProviderAdapter(Protocol):
    def prepare(self, request: ProviderRequest) -> WireRequest: ...

    def count_input_tokens(self, request: ProviderRequest, wire: WireRequest) -> int: ...

    def complete(
        self, request: ProviderRequest, wire: WireRequest, timeout_ms: int
    ) -> ProviderResult: ...


class DecisionBudgetPort(Protocol):
    def admit(
        self,
        call_id: str,
        input_tokens: int,
        output_tokens: int,
        provider_request_sha256: str,
        wire_body_sha256: str,
    ) -> CallReservation | None: ...

    def commit(self, decision_id: str, debits: list[CallDebit]) -> None: ...


class AttemptJournalPort(Protocol):
    def stage_context(self, record: ContextRecordP3) -> None: ...

    def before_call(self, context: ContextRecordP3, record: AttemptDispatch) -> None: ...

    def after_call(self, record: LLMCallRecordP3) -> None: ...


class InvalidFallbackPlan(ValueError):
    """A malformed rule proposal, not an unexpected adapter failure."""


class FallbackAdapter(Protocol):
    """Return a staged plan/private successor; the caller alone commits either.

    decide raises InvalidFallbackPlan only for a malformed rule proposal. The
    caller handles that typed failure with one wait substitute and keeps the
    entire prior private state. Other programming and IO failures propagate.
    """

    def decide(
        self, request: DecisionRequestP3, state: P3PolicyPrivateState
    ) -> tuple[ActionPlan, P3PolicyPrivateState]: ...


class ResidentRuntimeP3(Protocol):
    def ingest(self, delivery: BoundaryPerceptionDelivery) -> None: ...

    def make_request(self, tick: int, triggers: list[DecisionTrigger]) -> DecisionRequestP3: ...

    def decide(self, request: DecisionRequestP3) -> DecisionRecordP3: ...

    def commit_decision(self, record: DecisionRecordP3) -> None: ...

    def export_state(self) -> ResidentRuntimeStateP3: ...
