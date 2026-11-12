"""Closed, resident-local P3 memory DTOs and pure canonical helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from living_island.world.protocol import (
    ActionFeedback,
    ActionIntent,
    ActionPlan,
    Coord,
    CursorTick,
    EnvironmentalCue,
    HeardUtterance,
    NonNegInt,
    OwnCondition,
    OwnInventory,
    ProtocolModel,
    TransientSighting,
    VisibleEntity,
    format_delivery_id,
)

MAX_EXPERIENCE_RECORDS = 1024
MAX_EXPERIENCE_BYTES = 1048576
MAX_RECALLED_RECORDS = 16


def canonical_bytes(value: object) -> bytes:
    """Canonical UTF-8 JSON, with no floats, surrogate strings or final LF."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", warnings="error")

    def check(item: object) -> None:
        if item is None or isinstance(item, (bool, int)):
            return
        if isinstance(item, str):
            item.encode("utf-8", errors="strict")
        elif isinstance(item, list):
            for child in item:
                check(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("canonical object keys must be strings")
                check(key)
                check(child)
        else:
            raise ValueError("canonical JSON permits no floats or untyped objects")

    check(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_experience_id(owner_id: str, sequence: int) -> str:
    if type(sequence) is not int or sequence < 0:
        raise ValueError("sequence must be a nonnegative integer")
    return f"{owner_id}:e{sequence:06d}"


def build_decision_id(run_id: str, actor_id: str, ordinal: int) -> str:
    if type(ordinal) is not int or ordinal < 0:
        raise ValueError("ordinal must be a nonnegative integer")
    return f"{run_id}:d:{actor_id}:{ordinal:06d}"


class DeliverySourceRef(ProtocolModel):
    source_kind: Literal["delivery"]
    run_id: str
    delivery_id: str
    field: Literal[
        "own_state",
        "visible_entities",
        "transient_sightings",
        "environmental_cues",
        "heard_utterances",
        "last_action_feedback",
    ]
    index: NonNegInt | None

    @model_validator(mode="after")
    def _index_shape(self) -> DeliverySourceRef:
        scalar = self.field in {"own_state", "last_action_feedback"}
        if scalar != (self.index is None):
            raise ValueError("scalar delivery fields have null indices; arrays have indices")
        if not self.run_id:
            raise ValueError("source run_id must not be empty")
        canonical_bytes(self)
        return self


class DecisionSourceRef(ProtocolModel):
    source_kind: Literal["decision"]
    run_id: str
    decision_id: str
    decision_ordinal: NonNegInt

    @model_validator(mode="after")
    def _run(self) -> DecisionSourceRef:
        if not self.run_id:
            raise ValueError("source run_id must not be empty")
        canonical_bytes(self)
        return self


SourceRef = Annotated[DeliverySourceRef | DecisionSourceRef, Field(discriminator="source_kind")]


class OwnedIntentRef(ProtocolModel):
    intent: ActionIntent
    decision_id: str
    decision_ordinal: NonNegInt
    committed_tick: NonNegInt
    goal_id: str | None

    @model_validator(mode="after")
    def _identity(self) -> OwnedIntentRef:
        actor = self.intent.actor_id
        plan_id = f"{actor}:p{self.decision_ordinal:06d}"
        if self.intent.plan_id != plan_id:
            raise ValueError("owned intent plan ID must match its decision ordinal")
        prefix = plan_id + ":i"
        index = self.intent.intent_id.removeprefix(prefix)
        if (
            not self.intent.intent_id.startswith(prefix)
            or not index.isascii()
            or not index.isdigit()
        ):
            raise ValueError("owned intent ID must use the canonical plan/index builder")
        if index != str(int(index)):
            raise ValueError("intent index must have canonical decimal spelling")
        suffix = f":d:{actor}:{self.decision_ordinal:06d}"
        if not self.decision_id.endswith(suffix) or len(self.decision_id) == len(suffix):
            raise ValueError("owned intent decision ID must match its actor and ordinal")
        validate_goal_reference(self.goal_id, actor)
        canonical_bytes(self)
        return self


def validate_goal_reference(goal_id: str | None, actor_id: str) -> None:
    """Validate a resident-local goal ID without importing cognition or parsing actor IDs."""
    if goal_id is None:
        return
    prefix = actor_id + ":g"
    suffix = goal_id.removeprefix(prefix)
    if not goal_id.startswith(prefix) or not suffix.isascii() or not suffix.isdigit():
        raise ValueError("goal reference must belong to the same resident")
    if goal_id != f"{actor_id}:g{int(suffix):06d}":
        raise ValueError("goal reference must use the canonical sequence spelling")


class OwnStateData(ProtocolModel):
    condition: OwnCondition
    position: Coord
    inventory: OwnInventory


class FeedbackData(ProtocolModel):
    feedback: ActionFeedback
    owned_intent: OwnedIntentRef | None

    @model_validator(mode="after")
    def _matching_intent(self) -> FeedbackData:
        if self.owned_intent is not None:
            if self.feedback.intent_id != self.owned_intent.intent.intent_id:
                raise ValueError("feedback must match its embedded owned intent")
        return self


class AcceptedDecisionData(ProtocolModel):
    plan: ActionPlan
    goal_id: str | None


ExperienceKind = Literal[
    "own_state",
    "entity_seen",
    "transient_seen",
    "cue_seen",
    "heard_speech",
    "action_feedback",
    "accepted_decision",
]
ExperienceData = (
    OwnStateData
    | VisibleEntity
    | TransientSighting
    | EnvironmentalCue
    | HeardUtterance
    | FeedbackData
    | AcceptedDecisionData
)


class ExperiencePayload(ProtocolModel):
    information_kind: Literal["delivered", "interpretation"]
    confidence: Literal["unassessed"] | None
    data: ExperienceData

    @model_validator(mode="after")
    def _confidence(self) -> ExperiencePayload:
        if self.information_kind == "delivered" and self.confidence is not None:
            raise ValueError("delivered experience has null epistemic confidence")
        if self.information_kind == "interpretation" and self.confidence != "unassessed":
            raise ValueError("accepted intention has unassessed epistemic confidence")
        return self


class ExperienceRecord(ProtocolModel):
    experience_id: str
    owner_id: str
    sequence: NonNegInt
    observed_tick: NonNegInt
    kind: ExperienceKind
    source: SourceRef
    payload: ExperiencePayload

    @model_validator(mode="after")
    def _provenance(self) -> ExperienceRecord:
        if self.experience_id != build_experience_id(self.owner_id, self.sequence):
            raise ValueError("experience ID must match owner and sequence")
        expected: dict[ExperienceKind, type[BaseModel]] = {
            "own_state": OwnStateData,
            "entity_seen": VisibleEntity,
            "transient_seen": TransientSighting,
            "cue_seen": EnvironmentalCue,
            "heard_speech": HeardUtterance,
            "action_feedback": FeedbackData,
            "accepted_decision": AcceptedDecisionData,
        }
        if type(self.payload.data) is not expected[self.kind]:
            raise ValueError("experience payload must match its declared kind")
        if self.kind == "accepted_decision":
            if not isinstance(self.source, DecisionSourceRef):
                raise ValueError("accepted decisions require a decision source")
            if self.payload.information_kind != "interpretation":
                raise ValueError("accepted decisions are intentions, not delivered facts")
            if self.source.decision_id != build_decision_id(
                self.source.run_id, self.owner_id, self.source.decision_ordinal
            ):
                raise ValueError("decision source ID must match run, owner and ordinal")
            data = self.payload.data
            assert isinstance(data, AcceptedDecisionData)
            if (
                data.plan.actor_id != self.owner_id
                or data.plan.created_at_tick != self.observed_tick
            ):
                raise ValueError("accepted plan must belong to this owner and observed tick")
            plan_id = f"{self.owner_id}:p{self.source.decision_ordinal:06d}"
            if data.plan.plan_id != plan_id:
                raise ValueError("accepted plan ID must match the decision ordinal")
            if any(i.intent_id != f"{plan_id}:i{n}" for n, i in enumerate(data.plan.intents)):
                raise ValueError("accepted plan intent indices must be contiguous")
            validate_goal_reference(data.goal_id, self.owner_id)
        else:
            if not isinstance(self.source, DeliverySourceRef):
                raise ValueError("delivered records require a delivery source")
            fields = {
                "own_state": "own_state",
                "entity_seen": "visible_entities",
                "transient_seen": "transient_sightings",
                "cue_seen": "environmental_cues",
                "heard_speech": "heard_utterances",
                "action_feedback": "last_action_feedback",
            }
            if self.source.field != fields[self.kind]:
                raise ValueError("delivery source field must match the experience kind")
            if self.payload.information_kind != "delivered":
                raise ValueError("delivery records are delivered experience")
            if self.source.delivery_id != format_delivery_id(
                self.source.run_id, self.observed_tick, self.owner_id
            ):
                raise ValueError("delivery source ID must match run, owner and tick")
            data = self.payload.data
            if isinstance(data, FeedbackData) and data.owned_intent is not None:
                ref = data.owned_intent
                if ref.intent.actor_id != self.owner_id or ref.committed_tick >= self.observed_tick:
                    raise ValueError("feedback reference must be an earlier own accepted intent")
                if ref.decision_id != build_decision_id(
                    self.source.run_id, self.owner_id, ref.decision_ordinal
                ):
                    raise ValueError("feedback reference must belong to the source run")
        canonical_bytes(self)
        return self


class ExperienceState(ProtocolModel):
    experience_schema_version: Literal["0.1"]
    owner_id: str
    last_ingested_tick: CursorTick
    next_sequence: NonNegInt
    records: list[ExperienceRecord]
    intent_refs: list[OwnedIntentRef]

    @model_validator(mode="after")
    def _retained_suffix(self) -> ExperienceState:
        if self.last_ingested_tick == -1 and (
            self.next_sequence or self.records or self.intent_refs
        ):
            raise ValueError("an un-ingested store must be empty")
        first = self.next_sequence - len(self.records)
        if first < 0:
            raise ValueError("retained records cannot exceed the sequence cursor")
        runs: set[str] = set()
        for sequence, record in enumerate(self.records, start=first):
            if record.owner_id != self.owner_id or record.sequence != sequence:
                raise ValueError("records must be this owner's contiguous retained suffix")
            if record.observed_tick > self.last_ingested_tick:
                raise ValueError("record tick cannot exceed the ingestion cursor")
            runs.add(record.source.run_id)
        if len(runs) > 1:
            raise ValueError("a store cannot mix source runs")
        if len(self.records) > MAX_EXPERIENCE_RECORDS:
            raise ValueError("retained record count exceeds E-01")
        if (
            len(canonical_bytes([record.model_dump(mode="json") for record in self.records]))
            > MAX_EXPERIENCE_BYTES
        ):
            raise ValueError("retained record bytes exceed E-02")
        if self.intent_refs:
            first_ref = self.intent_refs[0]
            for index, ref in enumerate(self.intent_refs):
                if ref.intent.actor_id != self.owner_id:
                    raise ValueError("intent references must belong to the store owner")
                if (ref.decision_id, ref.decision_ordinal, ref.committed_tick, ref.goal_id) != (
                    first_ref.decision_id,
                    first_ref.decision_ordinal,
                    first_ref.committed_tick,
                    first_ref.goal_id,
                ):
                    raise ValueError("current intent references must represent one accepted plan")
                if ref.intent.intent_id != f"{ref.intent.plan_id}:i{index}":
                    raise ValueError("current intent indices must be contiguous")
                if ref.committed_tick > self.last_ingested_tick:
                    raise ValueError("current references cannot come from a future decision")
                if runs and ref.decision_id != build_decision_id(
                    next(iter(runs)), self.owner_id, ref.decision_ordinal
                ):
                    raise ValueError("intent references must belong to the store's source run")
        canonical_bytes(self.owner_id)
        return self


RetrievalProfileId = Literal["recent-relevant-v0", "recent-only-fixture-v0"]


class RetrievalQuery(ProtocolModel):
    query_schema_version: Literal["0.1"]
    owner_id: str
    entity_ids: list[str]
    positions: list[Coord]

    @model_validator(mode="after")
    def _ordered_keys(self) -> RetrievalQuery:
        encoded = [value.encode("utf-8", errors="strict") for value in self.entity_ids]
        if encoded != sorted(set(encoded)):
            raise ValueError("query entity IDs must be sorted and unique")
        positions = [(position.y, position.x) for position in self.positions]
        if positions != sorted(set(positions)):
            raise ValueError("query positions must be sorted by y,x and unique")
        canonical_bytes(self.owner_id)
        return self


class RetrievalResult(ProtocolModel):
    ranked_experience_ids: list[str]
    selected_records: list[ExperienceRecord]

    @model_validator(mode="after")
    def _unique_ids(self) -> RetrievalResult:
        if len(set(self.ranked_experience_ids)) != len(self.ranked_experience_ids):
            raise ValueError("ranked experience IDs must be unique")
        if len(self.selected_records) > MAX_RECALLED_RECORDS:
            raise ValueError("selected record count exceeds E-03")
        if [record.experience_id for record in self.selected_records] != self.ranked_experience_ids[
            : len(self.selected_records)
        ]:
            raise ValueError("selected records must follow the complete ranked prefix")
        canonical_bytes(self.ranked_experience_ids)
        return self


class RetrievalSelector(Protocol):
    """Trusted host-injected, source-pinned selector; never model-supplied code."""

    @property
    def retrieval_profile(self) -> RetrievalProfileId: ...

    @property
    def implementation_sha256(self) -> str: ...

    def retrieve(self, state: ExperienceState, query: RetrievalQuery) -> RetrievalResult: ...
