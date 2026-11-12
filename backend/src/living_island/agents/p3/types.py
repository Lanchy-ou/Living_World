"""P3-only closed DTOs. Money is integer micro-CNY; no IO or legacy mutation."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from living_island.agents.types import IntentTemplate, PolicyConfig, RuleStateV0_1
from living_island.memory.p3_types import (
    ExperienceRecord,
    ExperienceState,
    OwnedIntentRef,
    RetrievalProfileId,
    canonical_sha256,
)
from living_island.world.protocol import (
    ActionFeedback,
    ActionParameters,
    ActionPlan,
    ActionTarget,
    ActionType,
    Coord,
    CursorTick,
    DecisionTrigger,
    EnvironmentalCue,
    HeardUtterance,
    NonNegInt,
    OwnCondition,
    OwnInventory,
    Perception,
    PosInt,
    ProtocolModel,
    Sha256Hex,
    TalkParameters,
    TileView,
    TransientSighting,
    VisibleEntity,
    check_action_shape,
)

MAX_PROJECTION_BYTES = 65536
MAX_STATIC_TILE_CANDIDATES = 128
PROMPT_VERSION = "p3-resident/0.1"
ACTION_SCHEMA_VERSION = "p3-actions/0.1"
PILOT_CEILING_MICRO_CNY = 150000000


def scalar_text(value: str, minimum: int, maximum: int) -> str:
    value.encode("utf-8", errors="strict")
    if not minimum <= len(value) <= maximum:
        raise ValueError(f"text must have {minimum}..{maximum} Unicode scalar values")
    return value


def build_goal_id(actor_id: str, sequence: int) -> str:
    if type(sequence) is not int or sequence < 0:
        raise ValueError("goal sequence must be a nonnegative integer")
    return f"{actor_id}:g{sequence:06d}"


def build_call_id(decision_id: str, attempt_index: int) -> str:
    if type(attempt_index) is not int or attempt_index < 0:
        raise ValueError("attempt index must be a nonnegative integer")
    return f"{decision_id}:a{attempt_index}"


class ProfileDocument(ProtocolModel):
    profile_schema_version: Literal["0.1"]
    profile_id: str
    values: Annotated[list[str], Field(max_length=8)]

    @field_validator("values")
    @classmethod
    def _values(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("profile values must be unique")
        for text in value:
            scalar_text(text, 1, 160)
        return value


class IdentitySource(ProtocolModel):
    actor_id: str
    display_name: str
    profile: ProfileDocument
    initial_direction: str

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        return scalar_text(value, 1, 120)

    @field_validator("initial_direction")
    @classmethod
    def _direction(cls, value: str) -> str:
        return scalar_text(value, 1, 500)


class ResidentIdentity(ProtocolModel):
    identity_schema_version: Literal["0.1"]
    actor_id: str
    display_name: str
    profile_id: str
    values: Annotated[list[str], Field(max_length=8)]
    initial_direction: str
    source_sha256: Sha256Hex

    @model_validator(mode="after")
    def _source(self) -> ResidentIdentity:
        source = IdentitySource(
            actor_id=self.actor_id,
            display_name=self.display_name,
            profile=ProfileDocument(
                profile_schema_version="0.1", profile_id=self.profile_id, values=self.values
            ),
            initial_direction=self.initial_direction,
        )
        if canonical_sha256(source) != self.source_sha256:
            raise ValueError("identity does not match its resolved source hash")
        return self


class OwnActionSuccessPredicate(ProtocolModel):
    kind: Literal["own_action_success"]
    action_type: ActionType
    target: ActionTarget | None
    parameters: ActionParameters

    @model_validator(mode="after")
    def _shape(self) -> OwnActionSuccessPredicate:
        check_action_shape(self.action_type, self.target, self.parameters)
        if isinstance(self.parameters, TalkParameters):
            scalar_text(self.parameters.text, 0, 500)
        return self


class UnverifiablePredicate(ProtocolModel):
    kind: Literal["unverifiable"]


CompletionPredicate = Annotated[
    OwnActionSuccessPredicate | UnverifiablePredicate, Field(discriminator="kind")
]


class GoalProposal(ProtocolModel):
    text: str
    completion: CompletionPredicate

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return scalar_text(value, 1, 240)


class GoalChange(ProtocolModel):
    operation: Literal["continue", "revise", "abandon"]
    expected_goal_id: str | None
    proposal: GoalProposal | None

    @model_validator(mode="after")
    def _operation(self) -> GoalChange:
        if (self.operation == "revise") != (self.proposal is not None):
            raise ValueError("only revise requires a proposal")
        if self.operation == "abandon" and self.expected_goal_id is None:
            raise ValueError("abandon requires a current goal")
        return self


class GoalEvidence(ProtocolModel):
    delivery_id: str
    observed_tick: NonNegInt
    owned_intent: OwnedIntentRef
    feedback: ActionFeedback


class Commitment(ProtocolModel):
    goal_id: str
    text: str
    completion: CompletionPredicate
    status: Literal["intended", "attempted", "observed_complete"]
    created_at_tick: NonNegInt
    evidence: GoalEvidence | None

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return scalar_text(value, 1, 240)


class GoalState(ProtocolModel):
    goal_schema_version: Literal["0.1"]
    current: Commitment | None
    next_goal_sequence: NonNegInt


class CognitiveDelta(ProtocolModel):
    delta_schema_version: Literal["0.1"]
    goal_change: GoalChange


class P3IntentTemplate(IntentTemplate):
    """Same action vocabulary; P3 authored-text limits do not alter legacy DTOs."""

    @model_validator(mode="after")
    def _authored_text(self) -> P3IntentTemplate:
        if self.reason is not None:
            scalar_text(self.reason, 0, 240)
        if isinstance(self.parameters, TalkParameters):
            scalar_text(self.parameters.text, 0, 500)
        return self


class DecisionProposal(ProtocolModel):
    proposal_schema_version: Literal["0.1"]
    actions: Annotated[list[P3IntentTemplate], Field(min_length=1)]
    cognitive_delta: CognitiveDelta


class ActionDescription(ProtocolModel):
    action_type: ActionType
    description: str


class ModelActionContract(ProtocolModel):
    action_schema_version: Literal["p3-actions/0.1"]
    descriptions: list[ActionDescription]
    proposal_schema: dict[str, JsonValue]


class ResidentCognitiveState(ProtocolModel):
    cognitive_schema_version: Literal["0.1"]
    actor_id: str
    identity: ResidentIdentity
    experience: ExperienceState
    goals: GoalState


class ContextProfile(ProtocolModel):
    context_profile_schema_version: Literal["0.1"]
    context_profile_id: str
    retrieval_profile: RetrievalProfileId
    projection_profile: Literal["p3-context-v0"]


class DecisionContextP3(ProtocolModel):
    context_schema_version: Literal["0.2"]
    perception: Perception
    identity: ResidentIdentity
    goals: GoalState
    recalled_experience: list[ExperienceRecord]
    owned_intents: list[OwnedIntentRef]


class ProviderPerception(ProtocolModel):
    schema_version: str
    actor_id: str
    tick: NonNegInt
    own_condition: OwnCondition
    own_position: Coord
    own_inventory: OwnInventory
    visible_tiles: list[TileView]
    visible_entities: list[VisibleEntity]
    transient_sightings: list[TransientSighting]
    explored_static_tiles: list[TileView]
    environmental_cues: list[EnvironmentalCue]
    heard_utterances: list[HeardUtterance]
    last_action_feedback: ActionFeedback | None


class ProviderProjection(ProtocolModel):
    projection_schema_version: Literal["0.1"]
    perception: ProviderPerception
    identity: ResidentIdentity
    goals: GoalState
    recalled_experience: list[ExperienceRecord]
    owned_intents: list[OwnedIntentRef]


class ExperienceInclusion(ProtocolModel):
    experience_id: str
    retrieved: bool
    projected: bool
    omission: Literal["retrieval_limit", "projection_bytes", "mandatory_oversize"] | None


class TileInclusion(ProtocolModel):
    position: Coord
    projected: bool
    omission: Literal["tile_limit", "projection_bytes", "mandatory_oversize"] | None


class InclusionManifest(ProtocolModel):
    manifest_schema_version: Literal["0.1"]
    context_profile_id: str
    retrieval_profile: RetrievalProfileId
    projection_profile: Literal["p3-context-v0"]
    store_next_sequence: NonNegInt
    retained_record_count: NonNegInt
    evicted_record_count: NonNegInt
    mandatory_fields: list[str]
    mandatory_bytes: NonNegInt
    projection_bytes: NonNegInt | None
    experiences: list[ExperienceInclusion]
    static_tiles: list[TileInclusion]


class ContextAssembly(ProtocolModel):
    assembly_schema_version: Literal["0.1"]
    context: DecisionContextP3
    context_sha256: Sha256Hex
    provider_projection: ProviderProjection | None
    projection_sha256: Sha256Hex | None
    manifest: InclusionManifest
    error: Literal["MANDATORY_OVERSIZE"] | None


class ProviderSettings(ProtocolModel):
    api: Literal["deepseek-responses"]
    reasoning_effort: Literal["none"]
    store: Literal[False]
    tools: Annotated[list[JsonValue], Field(max_length=0)]
    background: Literal[False]
    stream: Literal[False]
    input_counter_id: str
    input_counter_version: str


class DecisionLimits(ProtocolModel):
    profile_id: Literal["p3-bounded-v0.1"]
    max_attempts: Literal[2]
    attempt_timeout_ms: Literal[30000]
    decision_timeout_ms: Literal[60000]
    retry_delay_ms: Literal[0]
    max_input_tokens: Literal[32768]
    max_output_tokens: Literal[2048]
    max_request_bytes: Literal[131072]
    max_response_bytes: Literal[262144]


class PricingPin(ProtocolModel):
    currency: Literal["CNY"]
    date: str
    source_url: str
    input_micro_cny_per_million_tokens: NonNegInt
    output_micro_cny_per_million_tokens: NonNegInt


class P3PolicyConfig(ProtocolModel):
    config_schema_version: Literal["0.2"]
    policy_id: Literal["llm-v0", "rule-based-v0"]
    seed: Annotated[int, Field(ge=1, le=4294967295)]
    max_plan_actions: PosInt
    map_width: PosInt
    map_height: PosInt
    identity_sha256: Sha256Hex
    prompt_version: str
    prompt_sha256: Sha256Hex
    action_schema_version: str
    action_schema_sha256: Sha256Hex
    context_profile_id: str
    adapter_id: str
    adapter_version: str
    model_id: str
    provider_settings: ProviderSettings
    limits: DecisionLimits
    pricing: PricingPin
    fallback_config: PolicyConfig
    trial_registration_sha256: Sha256Hex


class DecisionRequestP3(ProtocolModel):
    request_schema_version: Literal["0.2"]
    actor_id: str
    tick: NonNegInt
    decision_ordinal: NonNegInt
    triggers: list[DecisionTrigger]
    context: DecisionContextP3


class SystemMessage(ProtocolModel):
    role: Literal["system"]
    content: str


class UserMessage(ProtocolModel):
    role: Literal["user"]
    content: str


class ProviderRequest(ProtocolModel):
    provider_request_version: Literal["0.1"]
    model_id: str
    messages: list[SystemMessage | UserMessage]
    response_schema: dict[str, JsonValue]
    settings: ProviderSettings
    max_output_tokens: Literal[2048]


class WireRequest(ProtocolModel):
    wire_schema_version: Literal["0.1"]
    method: Literal["POST"]
    origin: Literal["https://api.deepseek.com"]
    path: Literal["/responses"]
    content_type: Literal["application/json"]
    body_base64: str


class ProviderResult(ProtocolModel):
    provider_result_version: Literal["0.1"]
    outcome: Literal["response", "timeout", "provider_error", "output_limit"]
    raw_response: str | None
    raw_body_base64: str | None
    observed_body_bytes: NonNegInt
    response_complete: bool
    response_text: str | None
    provider_request_id: str | None
    token_input: NonNegInt | None
    token_output: NonNegInt | None
    latency_ms: NonNegInt | None
    provider_error_code: str | None


class CallReservation(ProtocolModel):
    allocation_key: Sha256Hex
    reservation_ordinal: NonNegInt
    call_id: str
    input_reserved: NonNegInt
    output_reserved: NonNegInt
    money_reserved: NonNegInt


class CallDebit(ProtocolModel):
    call_id: str
    input_reserved: NonNegInt
    output_reserved: NonNegInt
    money_reserved: NonNegInt
    input_reported: NonNegInt | None
    output_reported: NonNegInt | None
    input_charged: NonNegInt
    output_charged: NonNegInt
    money_charged: NonNegInt
    usage_unknown: bool


class BudgetCaps(ProtocolModel):
    attempts: NonNegInt
    input_tokens: NonNegInt
    output_tokens: NonNegInt
    micro_cny: NonNegInt


class BudgetLedgerP3(ProtocolModel):
    budget_schema_version: Literal["0.1"]
    allocation_key: Sha256Hex
    caps: BudgetCaps
    attempts_charged: NonNegInt
    input_charged: NonNegInt
    output_charged: NonNegInt
    money_charged: NonNegInt
    unknown_usage_count: NonNegInt
    recovery_debits: list[CallDebit]


class AllocationHead(ProtocolModel):
    checkpoint_sha256: Sha256Hex
    checkpoint_tick: NonNegInt
    input_manifest_sha256: Sha256Hex
    run_directory: str
    reservation_cursor: NonNegInt


class AllocationEntry(ProtocolModel):
    reservation: CallReservation
    provider_request_sha256: Sha256Hex
    wire_body_sha256: Sha256Hex
    state: Literal["reserved", "settled", "recovery"]
    debit: CallDebit | None
    terminal_call_sha256: Sha256Hex | None


class CaseAllocationP3(ProtocolModel):
    allocation_schema_version: Literal["0.1"]
    allocation_key: Sha256Hex
    registration_sha256: Sha256Hex
    case_id: str
    caps: BudgetCaps
    generation: NonNegInt
    status: Literal["ready", "running", "offline_only", "complete"]
    head: AllocationHead | None
    prepared_head: AllocationHead | None
    pending_recovery_sha256: Sha256Hex | None
    entries: list[AllocationEntry]


class P3PolicyPrivateState(ProtocolModel):
    private_schema_version: Literal["0.1"]
    mode: Literal["llm", "fallback"]
    fallback_state: RuleStateV0_1
    last_fallback_ordinal: NonNegInt | None


class ResidentRuntimeStateP3(ProtocolModel):
    runtime_schema_version: Literal["0.2"]
    actor_id: str
    policy_config: P3PolicyConfig
    next_decision_ordinal: NonNegInt
    latest_perception_tick: CursorTick
    cognitive_state: ResidentCognitiveState
    policy_private: P3PolicyPrivateState


DecisionErrorP3 = Literal[
    "INVALID_CONTEXT",
    "INVALID_PLAN",
    "INVALID_DELTA",
    "PARSE_ERROR",
    "TIMEOUT",
    "BUDGET",
    "PROVIDER_ERROR",
    "REPLAY_DIVERGED",
]
DetailCode = (
    Literal[
        "MANDATORY_OVERSIZE",
        "INPUT_LIMIT",
        "OUTPUT_LIMIT",
        "INVALID_JSON",
        "INVALID_ACTION",
        "INVALID_COGNITION",
        "ATTEMPT_TIMEOUT",
        "DECISION_TIMEOUT",
        "ADMISSION_DENIED",
        "PROVIDER_REJECTED",
        "INTERRUPTED_CALL",
        "RECOVERY_OFFLINE",
    ]
    | None
)


class DecisionRecordP3(ProtocolModel):
    record_schema_version: Literal["0.2"]
    run_id: str
    decision_id: str
    tick: NonNegInt
    actor_id: str
    decision_ordinal: NonNegInt
    policy_id: Literal["llm-v0", "rule-based-v0"]
    effective_policy_id: Literal["llm-v0", "rule-based-v0", "sim-fallback-wait"]
    triggers: list[DecisionTrigger]
    request_sha256: Sha256Hex
    status: Literal["ok", "error"]
    error_kind: DecisionErrorP3 | None
    detail_code: DetailCode
    plan: ActionPlan
    substituted: bool
    llm_call_id: str | None
    context_sha256: Sha256Hex
    projection_sha256: Sha256Hex | None
    accepted_delta: CognitiveDelta
    call_ids: list[str]
    state_before_sha256: Sha256Hex
    state_after_sha256: Sha256Hex
    fallback_error: Literal["INVALID_PLAN"] | None
    policy_private_after: P3PolicyPrivateState
    budget_debits: list[CallDebit]


class ContextRecordP3(ProtocolModel):
    context_record_version: Literal["0.1"]
    run_id: str
    decision_id: str
    request: DecisionRequestP3
    assembly: ContextAssembly
    provider_request: ProviderRequest | None


class AttemptDispatch(ProtocolModel):
    dispatch_schema_version: Literal["0.1"]
    run_id: str
    decision_id: str
    call_id: str
    actor_id: str
    tick: NonNegInt
    decision_ordinal: NonNegInt
    attempt_index: NonNegInt
    request_sha256: Sha256Hex
    context_sha256: Sha256Hex
    projection_sha256: Sha256Hex
    provider_request_sha256: Sha256Hex
    provider_request: ProviderRequest
    wire_request: WireRequest
    wire_body_sha256: Sha256Hex
    allocation_key: Sha256Hex
    reservation_ordinal: NonNegInt
    prompt_version: str
    action_schema_version: str
    adapter_id: str
    adapter_version: str
    model_id: str
    input_reserved: NonNegInt
    output_reserved: NonNegInt
    money_reserved: NonNegInt


class LLMCallRecordP3(ProtocolModel):
    call_schema_version: Literal["0.1"]
    run_id: str
    decision_id: str
    call_id: str
    actor_id: str
    tick: NonNegInt
    decision_ordinal: NonNegInt
    attempt_index: NonNegInt
    dispatch_sha256: Sha256Hex
    result: ProviderResult
    parsed_proposal: DecisionProposal | None
    validation_error: DecisionErrorP3 | None
    detail_code: DetailCode
    debit: CallDebit
