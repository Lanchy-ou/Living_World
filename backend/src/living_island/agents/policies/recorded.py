"""Recorded decisions from one verified actor slice (Agent Interface §4.3)."""

import json
from collections.abc import Sequence
from hashlib import sha256

from pydantic import JsonValue

from living_island.agents.types import (
    DecisionRecord,
    DecisionRequest,
    ErrorOutcome,
    ReplayedOutcome,
)


def request_sha256(request: DecisionRequest) -> str:
    # Agents cannot import the world content encoder. Request DTOs contain only
    # the integral JSON values covered by the canonical encoding in IC §6.3.
    encoded = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class ReplayDiverged(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"REPLAY_DIVERGED: {detail}")


class RecordedPolicy:
    policy_id = "recorded-v0"

    def __init__(self, actor_id: str, records: Sequence[DecisionRecord]) -> None:
        for ordinal, record in enumerate(records):
            if (record.actor_id, record.decision_ordinal, record.record_schema_version) != (
                actor_id,
                ordinal,
                "0.1",
            ):
                raise ReplayDiverged(f"{actor_id}: invalid record at ordinal {ordinal}")
        self._records = tuple(record.model_copy(deep=True) for record in records)

    def decide(self, request: DecisionRequest) -> ReplayedOutcome | ErrorOutcome:
        ordinal = request.decision_ordinal
        if ordinal < len(self._records):
            record = self._records[ordinal]
            if (
                record.actor_id == request.actor_id
                and record.tick == request.tick
                and record.triggers == request.triggers
                and record.request_sha256 == request_sha256(request)
            ):
                return ReplayedOutcome(
                    status="replayed",
                    policy_id="recorded-v0",
                    source_record=record.model_copy(deep=True),
                )
        return ErrorOutcome(
            status="error",
            policy_id=self.policy_id,
            error_kind="REPLAY_DIVERGED",
            detail=f"{request.actor_id} tick {request.tick}: record mismatch or missing {ordinal}",
        )

    def export_state(self) -> dict[str, JsonValue]:
        return {}
