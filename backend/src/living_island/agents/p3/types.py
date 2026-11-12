"""P3-only closed DTOs. Money is integer micro-CNY; no IO or legacy mutation."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import ConfigDict, Field, JsonValue, field_validator, model_validator

from living_island.agents.types import (
    IntentTemplate,
    PolicyConfig,
    ResidentRuntimeState,
    RuleStateV0_1,
    build_intent_id,
    build_plan_id,
    require_initial_or_triggered,
)
from living_island.memory.p3_types import (
    ExperienceRecord,
    ExperienceState,
    OwnedIntentRef,
    RetrievalProfileId,
    build_decision_id,
    canonical_bytes,
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
    format_delivery_id,
    is_canonical_trigger_order,
)


class P3Model(ProtocolModel):
    """Strict literals also distinguish false from zero; legacy types stay untouched."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always"
    )

    @model_validator(mode="before")
    @classmethod
    def _strict_literals(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            for name, field in cls.model_fields.items():
                if name in data and get_origin(field.annotation) is Literal:
                    value = data[name]
                    if not any(
                        type(value) is type(v) and value == v for v in get_args(field.annotation)
                    ):
                        raise ValueError(f"{name} requires its exact typed literal")
        return data

    @model_validator(mode="after")
    def _canonical_values(self) -> P3Model:
        # The shared scalar-string rule covers IDs and nested typed targets too.
        canonical_bytes(self)
        return self


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


class ProfileDocument(P3Model):
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


class IdentitySource(P3Model):
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


class ResidentIdentity(P3Model):
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


class OwnActionSuccessPredicate(P3Model):
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


class UnverifiablePredicate(P3Model):
    kind: Literal["unverifiable"]


CompletionPredicate = Annotated[
    OwnActionSuccessPredicate | UnverifiablePredicate, Field(discriminator="kind")
]


class GoalProposal(P3Model):
    text: str
    completion: CompletionPredicate

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return scalar_text(value, 1, 240)


class GoalChange(P3Model):
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


class GoalEvidence(P3Model):
    delivery_id: str
    observed_tick: NonNegInt
    owned_intent: OwnedIntentRef
    feedback: ActionFeedback

    @model_validator(mode="after")
    def _evidence(self) -> GoalEvidence:
        ref = self.owned_intent
        actor = ref.intent.actor_id
        suffix = f":d:{actor}:{ref.decision_ordinal:06d}"
        if not ref.decision_id.endswith(suffix) or len(ref.decision_id) <= len(suffix):
            raise ValueError("evidence reference has no valid own decision identity")
        run_id = ref.decision_id[: -len(suffix)]
        if self.delivery_id != format_delivery_id(run_id, self.observed_tick, actor):
            raise ValueError("evidence delivery must belong to the reference's run and actor")
        if self.feedback.intent_id != ref.intent.intent_id or ref.goal_id is None:
            raise ValueError("evidence must identify an owned goal intent")
        if self.observed_tick <= ref.committed_tick:
            raise ValueError("feedback must follow commitment")
        return self


class Commitment(P3Model):
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

    @model_validator(mode="after")
    def _status(self) -> Commitment:
        if self.status == "intended":
            if self.evidence is not None:
                raise ValueError("intended has no delivered verdict")
            return self
        if self.evidence is None:
            raise ValueError("attempted/completed require copied evidence")
        ref = self.evidence.owned_intent
        if ref.goal_id != self.goal_id or ref.committed_tick < self.created_at_tick:
            raise ValueError("evidence must be accepted for this goal after its creation")
        complete = (
            self.evidence.feedback.status == "success"
            and isinstance(self.completion, OwnActionSuccessPredicate)
            and self.completion.action_type == ref.intent.action_type
            and self.completion.target == ref.intent.target
            and self.completion.parameters == ref.intent.parameters
        )
        if (self.status == "observed_complete") != complete:
            raise ValueError("completion must match the exact own successful action")
        return self


class GoalState(P3Model):
    goal_schema_version: Literal["0.1"]
    current: Commitment | None
    next_goal_sequence: NonNegInt

    @model_validator(mode="after")
    def _sequence(self) -> GoalState:
        if self.current is not None and self.next_goal_sequence == 0:
            raise ValueError("current goal must have an allocated sequence")
        return self


class CognitiveDelta(P3Model):
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


class DecisionProposal(P3Model):
    proposal_schema_version: Literal["0.1"]
    actions: Annotated[list[P3IntentTemplate], Field(min_length=1)]
    cognitive_delta: CognitiveDelta


class ActionDescription(P3Model):
    action_type: ActionType
    description: str


class ModelActionContract(P3Model):
    action_schema_version: Literal["p3-actions/0.1"]
    descriptions: list[ActionDescription]
    proposal_schema: dict[str, JsonValue]


class ResidentCognitiveState(P3Model):
    cognitive_schema_version: Literal["0.1"]
    actor_id: str
    identity: ResidentIdentity
    experience: ExperienceState
    goals: GoalState

    @model_validator(mode="after")
    def _owner(self) -> ResidentCognitiveState:
        if self.identity.actor_id != self.actor_id or self.experience.owner_id != self.actor_id:
            raise ValueError("cognitive state is resident-local")
        check_goal_scope(
            self.goals,
            self.actor_id,
            self.experience.last_ingested_tick,
            self.experience.records,
            self.experience.intent_refs,
        )
        return self


class ContextProfile(P3Model):
    context_profile_schema_version: Literal["0.1"]
    context_profile_id: str
    retrieval_profile: RetrievalProfileId
    projection_profile: Literal["p3-context-v0"]

    @model_validator(mode="after")
    def _binding(self) -> ContextProfile:
        if CONTEXT_PROFILES.get(self.context_profile_id) != self.retrieval_profile:
            raise ValueError("unknown or mismatched context/retrieval profile")
        return self


class DecisionContextP3(P3Model):
    context_schema_version: Literal["0.2"]
    perception: Perception
    identity: ResidentIdentity
    goals: GoalState
    recalled_experience: list[ExperienceRecord]
    owned_intents: list[OwnedIntentRef]

    @model_validator(mode="after")
    def _owner(self) -> DecisionContextP3:
        check_context_owner(
            self.perception.actor_id,
            self.perception.tick,
            self.identity,
            self.goals,
            self.recalled_experience,
            self.owned_intents,
        )
        return self


class ProviderPerception(P3Model):
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

    @model_validator(mode="after")
    def _perception(self) -> ProviderPerception:
        Perception.model_validate(self.model_dump(mode="json"))
        positions = [(t.position.y, t.position.x) for t in self.explored_static_tiles]
        if positions != sorted(set(positions)):
            raise ValueError("projected static tiles must be sorted and unique")
        return self


class ProviderProjection(P3Model):
    projection_schema_version: Literal["0.1"]
    perception: ProviderPerception
    identity: ResidentIdentity
    goals: GoalState
    recalled_experience: list[ExperienceRecord]
    owned_intents: list[OwnedIntentRef]

    @model_validator(mode="after")
    def _owner(self) -> ProviderProjection:
        check_context_owner(
            self.perception.actor_id,
            self.perception.tick,
            self.identity,
            self.goals,
            self.recalled_experience,
            self.owned_intents,
        )
        return self


class ExperienceInclusion(P3Model):
    experience_id: str
    retrieved: bool
    projected: bool
    omission: Literal["retrieval_limit", "projection_bytes", "mandatory_oversize"] | None

    @model_validator(mode="after")
    def _flags(self) -> ExperienceInclusion:
        expected = (
            {None}
            if self.projected
            else {"projection_bytes", "mandatory_oversize"}
            if self.retrieved
            else {"retrieval_limit"}
        )
        if self.omission not in expected or (self.projected and not self.retrieved):
            raise ValueError("inclusion flags and omission disagree")
        return self


class TileInclusion(P3Model):
    position: Coord
    projected: bool
    omission: Literal["tile_limit", "projection_bytes", "mandatory_oversize"] | None

    @model_validator(mode="after")
    def _flags(self) -> TileInclusion:
        if self.projected != (self.omission is None):
            raise ValueError("tile inclusion and omission disagree")
        return self


class InclusionManifest(P3Model):
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

    @model_validator(mode="after")
    def _manifest(self) -> InclusionManifest:
        ContextProfile(
            context_profile_schema_version="0.1",
            context_profile_id=self.context_profile_id,
            retrieval_profile=self.retrieval_profile,
            projection_profile=self.projection_profile,
        )
        if self.mandatory_fields != list(MANDATORY_FIELDS):
            raise ValueError("mandatory field list must be exact")
        if self.retained_record_count + self.evicted_record_count != self.store_next_sequence:
            raise ValueError("retention counts do not match sequence")
        ids = [r.experience_id for r in self.experiences]
        if len(ids) != self.retained_record_count or len(set(ids)) != len(ids):
            raise ValueError("manifest must list every retained record once")
        positions = [(t.position.y, t.position.x) for t in self.static_tiles]
        if len(set(positions)) != len(positions):
            raise ValueError("manifest tile positions must be unique")
        return self


class ContextAssembly(P3Model):
    assembly_schema_version: Literal["0.1"]
    context: DecisionContextP3
    context_sha256: Sha256Hex
    provider_projection: ProviderProjection | None
    projection_sha256: Sha256Hex | None
    manifest: InclusionManifest
    error: Literal["MANDATORY_OVERSIZE"] | None

    @model_validator(mode="after")
    def _assembly(self) -> ContextAssembly:
        if self.context_sha256 != canonical_sha256(self.context):
            raise ValueError("full context hash mismatch")
        recalled = self.context.recalled_experience
        retrieved = [r.experience_id for r in self.manifest.experiences if r.retrieved]
        if retrieved != [r.experience_id for r in recalled]:
            raise ValueError("retrieved order must match the full context")
        mandatory = ProviderProjection(
            projection_schema_version="0.1",
            perception=ProviderPerception.model_validate(
                {
                    **self.context.perception.model_dump(mode="json"),
                    "explored_static_tiles": [],
                }
            ),
            identity=self.context.identity,
            goals=self.context.goals,
            recalled_experience=[],
            owned_intents=self.context.owned_intents,
        )
        if len(canonical_bytes(mandatory)) != self.manifest.mandatory_bytes:
            raise ValueError("mandatory byte count mismatch")
        if [r.retrieved for r in self.manifest.experiences] != [
            i < 16 for i in range(len(self.manifest.experiences))
        ]:
            raise ValueError("retrieval must use the exact bounded rank prefix")
        origin = self.context.perception.own_position
        terrain_rank = {"spring": 0, "cave": 1, "fruit_tree": 2, "damp_moss": 3}
        ranked_tiles = sorted(
            self.context.perception.explored_static_tiles,
            key=lambda t: (
                terrain_rank.get(t.terrain, 4),
                abs(t.position.x - origin.x) + abs(t.position.y - origin.y),
                t.position.y,
                t.position.x,
            ),
        )
        if [t.position for t in self.manifest.static_tiles] != [t.position for t in ranked_tiles]:
            raise ValueError("manifest must disclose every explored tile in selection order")
        p = self.provider_projection
        if self.error is not None:
            if p is not None or self.projection_sha256 is not None:
                raise ValueError("oversize has no provider projection")
            if self.manifest.projection_bytes is not None:
                raise ValueError("oversize has no projection byte count")
            if self.manifest.mandatory_bytes <= MAX_PROJECTION_BYTES:
                raise ValueError("oversize must exceed the mandatory bound")
            if any(
                r.projected or (r.retrieved and r.omission != "mandatory_oversize")
                for r in self.manifest.experiences
            ):
                raise ValueError("oversize manifest must disclose every omitted recall")
            if any(t.omission != "mandatory_oversize" for t in self.manifest.static_tiles):
                raise ValueError("oversize must omit all static tiles")
            return self
        if p is None or self.projection_sha256 != canonical_sha256(p):
            raise ValueError("successful assembly must have a verified projection")
        if self.manifest.mandatory_bytes > MAX_PROJECTION_BYTES:
            raise ValueError("successful projection cannot have oversized mandatory fields")
        for index, tile in enumerate(self.manifest.static_tiles):
            if (tile.omission == "tile_limit") != (index >= MAX_STATIC_TILE_CANDIDATES):
                raise ValueError("tile_limit must identify exactly the non-candidate suffix")
            if tile.omission == "mandatory_oversize":
                raise ValueError("successful projection has no mandatory-overflow omissions")
        if any(r.omission == "mandatory_oversize" for r in self.manifest.experiences):
            raise ValueError("successful projection has no mandatory-overflow omissions")
        size = len(canonical_bytes(p))
        if size > MAX_PROJECTION_BYTES or size != self.manifest.projection_bytes:
            raise ValueError("projection byte count/bound mismatch")
        if (p.identity, p.goals, p.owned_intents) != (
            self.context.identity,
            self.context.goals,
            self.context.owned_intents,
        ):
            raise ValueError("projection cannot alter mandatory resident data")
        exclude = {"explored_static_tiles"}
        if p.perception.model_dump(exclude=exclude) != self.context.perception.model_dump(
            exclude=exclude
        ):
            raise ValueError("projection cannot alter current perception")
        projected = [r.experience_id for r in self.manifest.experiences if r.projected]
        if projected != [r.experience_id for r in p.recalled_experience]:
            raise ValueError("projected recall does not match manifest")
        originals = {r.experience_id: r for r in recalled}
        if any(originals.get(r.experience_id) != r for r in p.recalled_experience):
            raise ValueError("projected records must be whole original copies")
        originals_tiles = {
            (t.position.x, t.position.y): t for t in self.context.perception.explored_static_tiles
        }
        projected_positions = {
            (t.position.x, t.position.y) for t in p.perception.explored_static_tiles
        }
        manifest_positions = {
            (t.position.x, t.position.y) for t in self.manifest.static_tiles if t.projected
        }
        if projected_positions != manifest_positions:
            raise ValueError("projected tiles do not match manifest")
        if any(
            originals_tiles.get((t.position.x, t.position.y)) != t
            for t in p.perception.explored_static_tiles
        ):
            raise ValueError("projection cannot invent static geography")
        return self


class ProviderSettings(P3Model):
    api: Literal["deepseek-responses"]
    reasoning_effort: Literal["none"]
    store: Literal[False]
    tools: Annotated[list[JsonValue], Field(max_length=0)]
    background: Literal[False]
    stream: Literal[False]
    input_counter_id: str
    input_counter_version: str


class DecisionLimits(P3Model):
    profile_id: Literal["p3-bounded-v0.1"]
    max_attempts: Literal[2]
    attempt_timeout_ms: Literal[30000]
    decision_timeout_ms: Literal[60000]
    retry_delay_ms: Literal[0]
    max_input_tokens: Literal[32768]
    max_output_tokens: Literal[2048]
    max_request_bytes: Literal[131072]
    max_response_bytes: Literal[262144]


class PricingPin(P3Model):
    currency: Literal["CNY"]
    date: str
    source_url: str
    input_micro_cny_per_million_tokens: NonNegInt
    output_micro_cny_per_million_tokens: NonNegInt

    @field_validator("date")
    @classmethod
    def _date(cls, value: str) -> str:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("price date must be YYYY-MM-DD")
        return value


class P3PolicyConfig(P3Model):
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

    @model_validator(mode="after")
    def _config(self) -> P3PolicyConfig:
        if self.context_profile_id not in CONTEXT_PROFILES:
            raise ValueError("unknown context profile")
        if (
            self.prompt_version != PROMPT_VERSION
            or self.action_schema_version != ACTION_SCHEMA_VERSION
        ):
            raise ValueError("unknown prompt/action schema version")
        cfg = self.fallback_config
        if (cfg.policy_id, cfg.seed, cfg.max_plan_actions, cfg.map_width, cfg.map_height) != (
            "rule-based-v0",
            self.seed,
            self.max_plan_actions,
            self.map_width,
            self.map_height,
        ):
            raise ValueError("fallback must use the same frozen rule configuration")
        params = cfg.rule_params
        if params is None or (
            params.canteen_use,
            params.cue_use,
            params.fruit_carry_target,
            params.failed_target_retry_ticks,
        ) != ("enabled", "enabled", 2, 36):
            raise ValueError("P3 fallback requires the frozen base rule parameters")
        return self


class DecisionRequestP3(P3Model):
    request_schema_version: Literal["0.2"]
    actor_id: str
    tick: NonNegInt
    decision_ordinal: NonNegInt
    triggers: list[DecisionTrigger]
    context: DecisionContextP3

    @model_validator(mode="after")
    def _request(self) -> DecisionRequestP3:
        if (self.context.perception.actor_id, self.context.perception.tick) != (
            self.actor_id,
            self.tick,
        ):
            raise ValueError("request and own packet disagree")
        if not is_canonical_trigger_order(self.triggers):
            raise ValueError("triggers must be canonical and unique")
        require_initial_or_triggered(self.tick, self.decision_ordinal, self.triggers)
        return self


class SystemMessage(P3Model):
    role: Literal["system"]
    content: str


class UserMessage(P3Model):
    role: Literal["user"]
    content: str


class ProviderRequest(P3Model):
    provider_request_version: Literal["0.1"]
    model_id: str
    messages: list[SystemMessage | UserMessage]
    response_schema: dict[str, JsonValue]
    settings: ProviderSettings
    max_output_tokens: Literal[2048]

    @model_validator(mode="after")
    def _messages(self) -> ProviderRequest:
        if len(self.messages) != 2 or [m.role for m in self.messages] != ["system", "user"]:
            raise ValueError("provider request has exactly system/user messages")
        canonical_bytes(self)
        return self


class WireRequest(P3Model):
    wire_schema_version: Literal["0.1"]
    method: Literal["POST"]
    origin: Literal["https://api.deepseek.com"]
    path: Literal["/responses"]
    content_type: Literal["application/json"]
    body_base64: str

    @field_validator("body_base64")
    @classmethod
    def _body(cls, value: str) -> str:
        decode_base64(value)
        return value


class ProviderResult(P3Model):
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

    @model_validator(mode="after")
    def _body(self) -> ProviderResult:
        if self.raw_body_base64 is None:
            if self.raw_response is not None or self.observed_body_bytes != 0:
                raise ValueError("no body cannot have decoded text or observed bytes")
        else:
            body = decode_base64(self.raw_body_base64)
            if len(body) > 262144 or self.observed_body_bytes != len(body) + (
                1 if self.observed_body_bytes > 262144 else 0
            ):
                raise ValueError("retained bytes must equal observed bytes up to one sentinel")
            try:
                decoded = body.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                decoded = None
            if self.raw_response != decoded:
                raise ValueError("raw_response must be exact strict UTF-8 decoding or null")
        if self.observed_body_bytes > 262144:
            if self.outcome != "output_limit" or self.response_complete:
                raise ValueError("response sentinel requires incomplete output_limit")
        if not self.response_complete and self.response_text is not None:
            raise ValueError("incomplete output cannot be extracted/parsed")
        return self


class CallReservation(P3Model):
    allocation_key: Sha256Hex
    reservation_ordinal: NonNegInt
    call_id: str
    input_reserved: NonNegInt
    output_reserved: NonNegInt
    money_reserved: NonNegInt


class CallDebit(P3Model):
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

    @model_validator(mode="after")
    def _usage(self) -> CallDebit:
        unknown = self.input_reported is None or self.output_reported is None
        if self.usage_unknown != unknown:
            raise ValueError("unknown usage must preserve nullable reports")
        if unknown and self.money_charged < self.money_reserved:
            raise ValueError("unknown usage cannot refund the money reservation")
        for reserved, reported, charged in [
            (self.input_reserved, self.input_reported, self.input_charged),
            (self.output_reserved, self.output_reported, self.output_charged),
        ]:
            if charged < (reported or 0) or (unknown and charged < reserved):
                raise ValueError("charged usage cannot erase known usage or unknown reservation")
        return self


class BudgetCaps(P3Model):
    attempts: NonNegInt
    input_tokens: NonNegInt
    output_tokens: NonNegInt
    micro_cny: NonNegInt


class BudgetLedgerP3(P3Model):
    budget_schema_version: Literal["0.1"]
    allocation_key: Sha256Hex
    caps: BudgetCaps
    attempts_charged: NonNegInt
    input_charged: NonNegInt
    output_charged: NonNegInt
    money_charged: NonNegInt
    unknown_usage_count: NonNegInt
    recovery_debits: list[CallDebit]

    @model_validator(mode="after")
    def _ledger(self) -> BudgetLedgerP3:
        ids = [d.call_id for d in self.recovery_debits]
        if len(ids) != len(set(ids)) or len(ids) > self.attempts_charged:
            raise ValueError("recovery entries must be unique consumed attempts")
        if self.unknown_usage_count > self.attempts_charged:
            raise ValueError("unknown count cannot exceed attempts")
        if (
            sum(d.input_charged for d in self.recovery_debits) > self.input_charged
            or sum(d.output_charged for d in self.recovery_debits) > self.output_charged
            or sum(d.money_charged for d in self.recovery_debits) > self.money_charged
        ):
            raise ValueError("recovery charges cannot exceed ledger totals")
        return self


class AllocationHead(P3Model):
    checkpoint_sha256: Sha256Hex
    checkpoint_tick: NonNegInt
    input_manifest_sha256: Sha256Hex
    run_directory: str
    reservation_cursor: NonNegInt


class AllocationEntry(P3Model):
    reservation: CallReservation
    provider_request_sha256: Sha256Hex
    wire_body_sha256: Sha256Hex
    state: Literal["reserved", "settled", "recovery"]
    debit: CallDebit | None
    terminal_call_sha256: Sha256Hex | None

    @model_validator(mode="after")
    def _entry(self) -> AllocationEntry:
        if self.state == "reserved":
            if self.debit is not None or self.terminal_call_sha256 is not None:
                raise ValueError("reserved entries have no settlement")
            return self
        if self.debit is None or (self.state == "settled" and self.terminal_call_sha256 is None):
            raise ValueError("finalized entry needs debit/terminal evidence")
        r, d = self.reservation, self.debit
        if (r.call_id, r.input_reserved, r.output_reserved, r.money_reserved) != (
            d.call_id,
            d.input_reserved,
            d.output_reserved,
            d.money_reserved,
        ):
            raise ValueError("entry reservation and debit disagree")
        if self.state == "recovery" and (
            d.input_charged < r.input_reserved
            or d.output_charged < r.output_reserved
            or d.money_charged < r.money_reserved
        ):
            raise ValueError("recovery cannot refund a reservation")
        return self


class CaseAllocationP3(P3Model):
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

    @model_validator(mode="after")
    def _allocation(self) -> CaseAllocationP3:
        key = canonical_sha256(
            {"registration_sha256": self.registration_sha256, "case_id": self.case_id}
        )
        if self.allocation_key != key:
            raise ValueError("allocation must identify its registered case")
        ids = []
        for ordinal, entry in enumerate(self.entries):
            if (entry.reservation.allocation_key, entry.reservation.reservation_ordinal) != (
                key,
                ordinal,
            ):
                raise ValueError("allocation entries require one key and contiguous ordinals")
            ids.append(entry.reservation.call_id)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate reservation call ID")
        if self.head is None and self.entries:
            raise ValueError("no reservations before tick-zero publication")
        for head in (self.head, self.prepared_head):
            if head is not None and head.reservation_cursor > len(self.entries):
                raise ValueError("head cursor exceeds entries")
        if self.head is not None and any(
            e.state == "reserved" for e in self.entries[: self.head.reservation_cursor]
        ):
            raise ValueError("committed prefix cannot contain pending reservations")
        if self.pending_recovery_sha256 is not None and self.status != "offline_only":
            raise ValueError("pending recovery must latch offline mode")
        return self


class P3PolicyPrivateState(P3Model):
    private_schema_version: Literal["0.1"]
    mode: Literal["llm", "fallback"]
    fallback_state: RuleStateV0_1
    last_fallback_ordinal: NonNegInt | None


class ResidentRuntimeStateP3(P3Model):
    runtime_schema_version: Literal["0.2"]
    actor_id: str
    policy_config: P3PolicyConfig
    next_decision_ordinal: NonNegInt
    latest_perception_tick: CursorTick
    cognitive_state: ResidentCognitiveState
    policy_private: P3PolicyPrivateState

    @model_validator(mode="after")
    def _runtime(self) -> ResidentRuntimeStateP3:
        c = self.cognitive_state
        if (
            c.actor_id != self.actor_id
            or c.experience.last_ingested_tick != self.latest_perception_tick
        ):
            raise ValueError("runtime owner/cursor disagrees with cognitive state")
        if canonical_sha256(c.identity) != self.policy_config.identity_sha256:
            raise ValueError("runtime identity pin mismatch")
        refs = c.experience.intent_refs
        if len(refs) > self.policy_config.max_plan_actions or any(
            r.decision_ordinal >= self.next_decision_ordinal for r in refs
        ):
            raise ValueError("references must belong to a committed bounded plan")
        last = self.policy_private.last_fallback_ordinal
        if last is not None and last >= self.next_decision_ordinal:
            raise ValueError("fallback ordinal must be committed")
        if (
            self.policy_config.policy_id == "rule-based-v0"
            and self.policy_private.mode != "fallback"
        ):
            raise ValueError("rule-primary private mode is fallback")
        ResidentRuntimeState(
            actor_id=self.actor_id,
            policy_config=self.policy_config.fallback_config,
            next_decision_ordinal=self.next_decision_ordinal,
            latest_perception_tick=self.latest_perception_tick,
            policy_state=self.policy_private.fallback_state.model_dump(mode="json"),
        )
        return self


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


class DecisionRecordP3(P3Model):
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

    @model_validator(mode="after")
    def _record(self) -> DecisionRecordP3:
        decision_id = build_decision_id(self.run_id, self.actor_id, self.decision_ordinal)
        if self.decision_id != decision_id:
            raise ValueError("decision record ID mismatch")
        if not is_canonical_trigger_order(self.triggers):
            raise ValueError("decision triggers must be canonical")
        require_initial_or_triggered(self.tick, self.decision_ordinal, self.triggers)
        plan_id = build_plan_id(self.actor_id, self.decision_ordinal)
        if (self.plan.actor_id, self.plan.plan_id, self.plan.created_at_tick) != (
            self.actor_id,
            plan_id,
            self.tick,
        ) or [i.intent_id for i in self.plan.intents] != [
            build_intent_id(plan_id, i) for i in range(len(self.plan.intents))
        ]:
            raise ValueError("record plan must use the decision's actor/tick/ordinal")
        if len(self.call_ids) > 2 or self.call_ids != [
            build_call_id(decision_id, i) for i in range(len(self.call_ids))
        ]:
            raise ValueError("calls must be the bounded contiguous attempt sequence")
        if [d.call_id for d in self.budget_debits] != self.call_ids:
            raise ValueError("every dispatched attempt needs its own matching debit")
        if self.llm_call_id != (self.call_ids[-1] if self.call_ids else None):
            raise ValueError("llm_call_id must identify the terminal attempt, if any")
        if self.error_kind == "REPLAY_DIVERGED":
            raise ValueError("replay divergence cannot be committed")
        if self.policy_id == "rule-based-v0" and self.call_ids:
            raise ValueError("rule-primary decisions cannot call a provider")
        if self.status == "ok":
            if (
                self.error_kind is not None
                or self.detail_code is not None
                or self.substituted
                or self.effective_policy_id != self.policy_id
                or self.fallback_error is not None
            ):
                raise ValueError("successful record must describe its accepted primary policy")
            if self.policy_id == "llm-v0" and not self.call_ids:
                raise ValueError("successful LLM output requires a recorded call")
        elif (
            not self.substituted or self.error_kind is None or self.effective_policy_id == "llm-v0"
        ):
            raise ValueError("failed primary requires a classified rule/wait substitute")
        if self.effective_policy_id != "llm-v0":
            if self.accepted_delta.goal_change.operation != "continue":
                raise ValueError("rule/wait output cannot rewrite a goal")
            if (
                self.effective_policy_id == "rule-based-v0"
                and self.policy_private_after.mode != "fallback"
            ):
                raise ValueError("accepted rule output requires fallback mode")
            # A malformed rule result preserves the entire prior private state;
            # a wait substitute may therefore retain either mode (decision spec section 5).
        elif self.policy_private_after.mode != "llm":
            raise ValueError("accepted LLM output requires llm mode")
        if (self.fallback_error is not None) != (self.effective_policy_id == "sim-fallback-wait"):
            raise ValueError("malformed rule output is the only wait substitution")
        if self.effective_policy_id == "sim-fallback-wait":
            if len(self.plan.intents) != 1:
                raise ValueError("wait substitute must contain exactly one intent")
            intent = self.plan.intents[0]
            if intent.action_type != "wait" or intent.reason is not None:
                raise ValueError("wait substitute is an unadorned wait intent")
        return self


class ContextRecordP3(P3Model):
    context_record_version: Literal["0.1"]
    run_id: str
    decision_id: str
    request: DecisionRequestP3
    assembly: ContextAssembly
    provider_request: ProviderRequest | None

    @model_validator(mode="after")
    def _record(self) -> ContextRecordP3:
        r = self.request
        if self.decision_id != build_decision_id(self.run_id, r.actor_id, r.decision_ordinal):
            raise ValueError("context decision identity mismatch")
        if r.context != self.assembly.context:
            raise ValueError("request/assembly contexts disagree")
        return self


class AttemptDispatch(P3Model):
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

    @model_validator(mode="after")
    def _dispatch(self) -> AttemptDispatch:
        if self.decision_id != build_decision_id(self.run_id, self.actor_id, self.decision_ordinal):
            raise ValueError("dispatch decision ID mismatch")
        if self.attempt_index >= 2 or self.call_id != build_call_id(
            self.decision_id, self.attempt_index
        ):
            raise ValueError("dispatch call ID/index mismatch")
        if self.provider_request_sha256 != canonical_sha256(self.provider_request):
            raise ValueError("dispatch provider request hash mismatch")
        wire = decode_base64(self.wire_request.body_base64)
        if self.wire_body_sha256 != hashlib.sha256(wire).hexdigest():
            raise ValueError("dispatch wire body hash mismatch")
        if len(wire) > 131072 or len(canonical_bytes(self.provider_request)) > 131072:
            raise ValueError("a dispatch cannot exceed the request byte bound")
        if self.input_reserved > 32768 or self.output_reserved != 2048:
            raise ValueError("dispatch reservation violates the admitted token bounds")
        if (
            self.model_id != self.provider_request.model_id
            or self.prompt_version != PROMPT_VERSION
            or self.action_schema_version != ACTION_SCHEMA_VERSION
        ):
            raise ValueError("dispatch must identify its exact request/prompt/action contract")
        return self


class LLMCallRecordP3(P3Model):
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

    @model_validator(mode="after")
    def _call(self) -> LLMCallRecordP3:
        if self.decision_id != build_decision_id(self.run_id, self.actor_id, self.decision_ordinal):
            raise ValueError("terminal call decision ID mismatch")
        if (
            self.attempt_index >= 2
            or self.call_id != build_call_id(self.decision_id, self.attempt_index)
            or self.debit.call_id != self.call_id
        ):
            raise ValueError("terminal call/debit identity mismatch")
        return self


CONTEXT_PROFILES: dict[str, RetrievalProfileId] = {
    "p3-context-v0": "recent-relevant-v0",
    "p3-context-recent-only-fixture-v0": "recent-only-fixture-v0",
}
MANDATORY_FIELDS = (
    "identity",
    "goals",
    "owned_intents",
    "perception.schema_version",
    "perception.actor_id",
    "perception.tick",
    "perception.own_condition",
    "perception.own_position",
    "perception.own_inventory",
    "perception.visible_tiles",
    "perception.visible_entities",
    "perception.transient_sightings",
    "perception.environmental_cues",
    "perception.heard_utterances",
    "perception.last_action_feedback",
)


def check_goal_owner(goals: GoalState, actor_id: str) -> None:
    current = goals.current
    if current is not None:
        if current.goal_id != build_goal_id(actor_id, goals.next_goal_sequence - 1):
            raise ValueError("current goal must use this actor's latest allocated ID")
        if (
            current.evidence is not None
            and current.evidence.owned_intent.intent.actor_id != actor_id
        ):
            raise ValueError("foreign goal evidence")


def check_context_owner(
    actor_id: str,
    tick: int,
    identity: ResidentIdentity,
    goals: GoalState,
    recalled: list[ExperienceRecord],
    refs: list[OwnedIntentRef],
) -> None:
    if identity.actor_id != actor_id:
        raise ValueError("foreign identity in context")
    check_goal_scope(goals, actor_id, tick, recalled, refs)
    if len(recalled) > 16 or len({r.experience_id for r in recalled}) != len(recalled):
        raise ValueError("recall must be bounded and unique")
    if any(r.owner_id != actor_id or r.observed_tick > tick for r in recalled):
        raise ValueError("foreign or future experience in context")
    if any(r.intent.actor_id != actor_id or r.committed_tick > tick for r in refs):
        raise ValueError("foreign or future intent reference")


def decode_base64(value: str) -> bytes:
    """Decode a retained byte string without accepting noncanonical alternative spellings."""
    try:
        body = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("invalid retained base64") from exc
    if base64.b64encode(body).decode("ascii") != value:
        raise ValueError("retained base64 must use canonical padding")
    return body


def check_goal_scope(
    goals: GoalState,
    actor_id: str,
    tick: int,
    records: list[ExperienceRecord],
    refs: list[OwnedIntentRef],
) -> None:
    """Reject future goals and mismatches with every available own-source run witness.

    The runtime additionally checks the external run identity when no source remains.
    The pure cognitive DTO intentionally has no separate invented run field.
    """
    check_goal_owner(goals, actor_id)
    current = goals.current
    runs = {r.source.run_id for r in records}
    for ref in refs:
        suffix = f":d:{actor_id}:{ref.decision_ordinal:06d}"
        if not ref.decision_id.endswith(suffix):
            raise ValueError("intent source is not this actor's decision")
        runs.add(ref.decision_id[: -len(suffix)])
    if len(runs) > 1:
        raise ValueError("context cannot mix source runs")
    if current is None:
        return
    if current.created_at_tick > tick:
        raise ValueError("current goal cannot come from a future boundary")
    evidence = current.evidence
    if evidence is not None:
        if evidence.observed_tick > tick:
            raise ValueError("goal evidence cannot come from a future boundary")
        for run in runs:
            if evidence.delivery_id != format_delivery_id(run, evidence.observed_tick, actor_id):
                raise ValueError("goal evidence must match the known own source run")
