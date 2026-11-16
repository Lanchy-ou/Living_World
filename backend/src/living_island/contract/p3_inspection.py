"""Closed P3 inspection DTOs and the read-only analysis type boundary.

Owner DTOs are reused verbatim. This module does not extend ReplayBundle.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Annotated, Literal

from pydantic import Field, model_validator

from living_island.agents.p3.types import (
    AllocationEntry as AllocationEntry,
)
from living_island.agents.p3.types import (
    AttemptDispatch as AttemptDispatch,
)
from living_island.agents.p3.types import (
    BudgetCaps as BudgetCaps,
)
from living_island.agents.p3.types import (
    CallDebit as CallDebit,
)
from living_island.agents.p3.types import (
    ContextRecordP3 as ContextRecordP3,
)
from living_island.agents.p3.types import (
    DecisionRecordP3 as DecisionRecordP3,
)
from living_island.agents.p3.types import (
    GoalState as GoalState,
)
from living_island.agents.p3.types import (
    LLMCallRecordP3 as LLMCallRecordP3,
)
from living_island.agents.p3.types import P3Model
from living_island.agents.p3.types import (
    ResidentIdentity as ResidentIdentity,
)
from living_island.agents.p3.types import (
    ResidentRuntimeStateP3 as ResidentRuntimeStateP3,
)
from living_island.memory.p3_types import (
    ExperienceRecord as ExperienceRecord,
)
from living_island.memory.p3_types import (
    canonical_bytes as canonical_bytes,
)
from living_island.memory.p3_types import (
    canonical_sha256 as canonical_sha256,
)
from living_island.world.protocol import NonNegInt, Sha256Hex

SHARD_LIMIT = 2_097_152
RECENT_LIMIT = 8


def decision_filename(decision_id: str) -> str:
    return f"decision-{sha256(decision_id.encode('utf-8')).hexdigest()}.json"


def sample_filename(tick: int, actor_id: str) -> str:
    return f"sample-{tick:010d}-{sha256(actor_id.encode('utf-8')).hexdigest()}.json"


class ShardRef(P3Model):
    file: str
    sha256: Sha256Hex


class InspectionDecisionRef(P3Model):
    decision_id: str
    actor_id: str
    tick: NonNegInt
    ordinal: NonNegInt
    shard: ShardRef

    @model_validator(mode="after")
    def _filename(self) -> InspectionDecisionRef:
        if self.shard.file != decision_filename(self.decision_id):
            raise ValueError("decision filename differs from typed identity")
        return self


class InspectionSampleRef(P3Model):
    actor_id: str
    tick: NonNegInt
    shard: ShardRef

    @model_validator(mode="after")
    def _filename(self) -> InspectionSampleRef:
        if self.shard.file != sample_filename(self.tick, self.actor_id):
            raise ValueError("sample filename differs from typed identity")
        return self


class InspectionActor(P3Model):
    actor_id: str
    identity: ResidentIdentity

    @model_validator(mode="after")
    def _identity(self) -> InspectionActor:
        if self.actor_id != self.identity.actor_id:
            raise ValueError("inspection actor identity mismatch")
        return self


class P3InspectionIndex(P3Model):
    inspection_schema_version: Literal["0.1"]
    run_id: str
    config_hash: Sha256Hex
    map_hash: Sha256Hex
    final_tick: NonNegInt
    replay_sha256: Sha256Hex
    trace_sha256: Sha256Hex
    registration_sha256: Sha256Hex
    actors: list[InspectionActor]
    decisions: list[InspectionDecisionRef]
    samples: list[InspectionSampleRef]

    @model_validator(mode="after")
    def _joins(self) -> P3InspectionIndex:
        actors = [a.actor_id for a in self.actors]
        if not actors or actors != sorted(set(actors)):
            raise ValueError("inspection actors must be sorted unique and nonempty")
        expected = [(tick, actor) for tick in range(self.final_tick + 1) for actor in actors]
        if [(s.tick, s.actor_id) for s in self.samples] != expected:
            raise ValueError("inspection needs every actor at every saved boundary")
        order = [(d.tick, d.actor_id, d.ordinal) for d in self.decisions]
        if order != sorted(set(order)) or len(order) > len(actors) * self.final_tick:
            raise ValueError("inspection decision order/cardinality mismatch")
        seen: dict[str, int] = dict.fromkeys(actors, 0)
        for ref in self.decisions:
            if ref.actor_id not in seen or ref.tick >= self.final_tick:
                raise ValueError("decision outside actor/horizon")
            if ref.ordinal != seen[ref.actor_id]:
                raise ValueError("decision ordinals must be contiguous per actor")
            expected_id = f"{self.run_id}:d:{ref.actor_id}:{ref.ordinal:06d}"
            if ref.decision_id != expected_id:
                raise ValueError("decision ID differs from index run/actor/ordinal")
            seen[ref.actor_id] += 1
        files = [r.shard.file for r in self.decisions] + [s.shard.file for s in self.samples]
        if len(files) != len(set(files)):
            raise ValueError("duplicate inspection filename")
        return self


class DecisionInspection(P3Model):
    inspection_schema_version: Literal["0.1"]
    record: DecisionRecordP3
    context: ContextRecordP3
    dispatches: list[AttemptDispatch]
    calls: list[LLMCallRecordP3]
    outcome_event_ids: list[str]

    @model_validator(mode="after")
    def _joins(self) -> DecisionInspection:
        r, c = self.record, self.context
        if (
            c.run_id,
            c.decision_id,
            c.request.tick,
            c.request.actor_id,
            c.request.decision_ordinal,
        ) != (r.run_id, r.decision_id, r.tick, r.actor_id, r.decision_ordinal):
            raise ValueError("decision/context identity mismatch")
        if (
            canonical_sha256(c.request),
            c.assembly.context_sha256,
            c.assembly.projection_sha256,
        ) != (r.request_sha256, r.context_sha256, r.projection_sha256):
            raise ValueError("decision/context hashes mismatch")
        if [d.call_id for d in self.dispatches] != r.call_ids:
            raise ValueError("dispatch chain differs from committed decision")
        if [c.call_id for c in self.calls] != r.call_ids:
            raise ValueError("call chain differs from committed decision")
        if [c.debit for c in self.calls] != r.budget_debits:
            raise ValueError("call debits differ from decision")
        for dispatch, call in zip(self.dispatches, self.calls, strict=True):
            identity = (r.run_id, r.decision_id, r.actor_id, r.tick, r.decision_ordinal)
            for row in (dispatch, call):
                if (
                    row.run_id,
                    row.decision_id,
                    row.actor_id,
                    row.tick,
                    row.decision_ordinal,
                ) != identity:
                    raise ValueError("foreign attempt in decision shard")
            if call.dispatch_sha256 != canonical_sha256(dispatch):
                raise ValueError("call does not hash its dispatch")
            if (
                dispatch.request_sha256,
                dispatch.context_sha256,
                dispatch.projection_sha256,
                dispatch.provider_request,
            ) != (r.request_sha256, r.context_sha256, r.projection_sha256, c.provider_request):
                raise ValueError("dispatch context/request mismatch")
        if len(self.outcome_event_ids) != len(set(self.outcome_event_ids)):
            raise ValueError("duplicate objective outcome reference")
        return self


class ResidentInspection(P3Model):
    inspection_schema_version: Literal["0.1"]
    tick: NonNegInt
    actor_id: str
    latest_perception_tick: Annotated[int, Field(ge=-1)]
    identity: ResidentIdentity
    goals: GoalState
    recent_experience: list[ExperienceRecord]
    retained_record_count: NonNegInt
    next_sequence: NonNegInt
    latest_decision_id: str | None
    state_sha256: Sha256Hex

    @model_validator(mode="after")
    def _sample(self) -> ResidentInspection:
        if self.identity.actor_id != self.actor_id or self.latest_perception_tick >= self.tick:
            raise ValueError("sample actor or pre-ingestion cursor mismatch")
        count = min(RECENT_LIMIT, self.retained_record_count)
        if self.retained_record_count > self.next_sequence or len(self.recent_experience) != count:
            raise ValueError("sample recent/retained count mismatch")
        if [e.sequence for e in self.recent_experience] != list(
            range(self.next_sequence - count, self.next_sequence)
        ):
            raise ValueError("recent experience must be the last retained sequence suffix")
        if any(
            e.owner_id != self.actor_id or e.observed_tick > self.latest_perception_tick
            for e in self.recent_experience
        ):
            raise ValueError("sample experience owner/cursor mismatch")
        return self
