"""Policy and ResidentRuntime protocols (Agent Interface §2.1-§2.2; typing only)."""

from __future__ import annotations

from typing import Protocol

from pydantic import JsonValue

from living_island.agents.types import (
    DecisionOutcome,
    DecisionRecord,
    DecisionRequest,
    ResidentRuntimeState,
)
from living_island.world.protocol import BoundaryPerceptionDelivery, DecisionTrigger


class Policy(Protocol):
    """Turns one request into a finite outcome; no file IO, no world access."""

    @property
    def policy_id(self) -> str:
        raise NotImplementedError

    def decide(self, request: DecisionRequest) -> DecisionOutcome:
        raise NotImplementedError

    def export_state(self) -> dict[str, JsonValue]:
        """Policy-private state for saving; ``{}`` if none."""
        raise NotImplementedError


class ResidentRuntime(Protocol):
    """One instance per resident; the only agent object sim talks to."""

    @property
    def actor_id(self) -> str:
        raise NotImplementedError

    def ingest(self, delivery: BoundaryPerceptionDelivery) -> None:
        raise NotImplementedError

    def make_request(self, tick: int, triggers: list[DecisionTrigger]) -> DecisionRequest:
        raise NotImplementedError

    def decide(self, request: DecisionRequest) -> DecisionOutcome:
        raise NotImplementedError

    def commit_decision(self, record: DecisionRecord) -> None:
        raise NotImplementedError

    def export_state(self) -> ResidentRuntimeState:
        raise NotImplementedError
