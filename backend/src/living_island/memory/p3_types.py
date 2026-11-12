"""Closed, resident-local P3 memory DTOs and pure canonical helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, Field

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


class DecisionSourceRef(ProtocolModel):
    source_kind: Literal["decision"]
    run_id: str
    decision_id: str
    decision_ordinal: NonNegInt


SourceRef = Annotated[DeliverySourceRef | DecisionSourceRef, Field(discriminator="source_kind")]


class OwnedIntentRef(ProtocolModel):
    intent: ActionIntent
    decision_id: str
    decision_ordinal: NonNegInt
    committed_tick: NonNegInt
    goal_id: str | None


class OwnStateData(ProtocolModel):
    condition: OwnCondition
    position: Coord
    inventory: OwnInventory


class FeedbackData(ProtocolModel):
    feedback: ActionFeedback
    owned_intent: OwnedIntentRef | None


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


class ExperienceRecord(ProtocolModel):
    experience_id: str
    owner_id: str
    sequence: NonNegInt
    observed_tick: NonNegInt
    kind: ExperienceKind
    source: SourceRef
    payload: ExperiencePayload


class ExperienceState(ProtocolModel):
    experience_schema_version: Literal["0.1"]
    owner_id: str
    last_ingested_tick: CursorTick
    next_sequence: NonNegInt
    records: list[ExperienceRecord]
    intent_refs: list[OwnedIntentRef]


RetrievalProfileId = Literal["recent-relevant-v0", "recent-only-fixture-v0"]


class RetrievalQuery(ProtocolModel):
    query_schema_version: Literal["0.1"]
    owner_id: str
    entity_ids: list[str]
    positions: list[Coord]


class RetrievalResult(ProtocolModel):
    ranked_experience_ids: list[str]
    selected_records: list[ExperienceRecord]


class RetrievalSelector(Protocol):
    """Trusted host-injected, source-pinned selector; never model-supplied code."""

    @property
    def retrieval_profile(self) -> RetrievalProfileId: ...

    @property
    def implementation_sha256(self) -> str: ...

    def retrieve(self, state: ExperienceState, query: RetrievalQuery) -> RetrievalResult: ...
