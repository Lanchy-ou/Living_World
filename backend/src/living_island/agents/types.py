"""Agent-side schemas, policy configuration and shared ID builders.

Agent Interface Spec §2-§6. Imports world types only through ``living_island.world.protocol``;
never imports ``contract``, ``persistence``, ``world.state`` or ``world.facts``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from living_island.world.protocol import (
    ActionParameters,
    ActionPlan,
    ActionTarget,
    ActionType,
    CursorTick,
    DecisionTrigger,
    EmptyParameters,
    NeedBand,
    NonNegInt,
    Perception,
    PosInt,
    ProtocolModel,
    Sha256Hex,
    check_action_shape,
    is_canonical_trigger_order,
    require_sorted_unique,
)

SCHEMA_VERSION_0_1 = "0.1"
SIM_FALLBACK_WAIT_POLICY_ID = "sim-fallback-wait"

PolicyId = Literal["random-v0", "scripted-v0", "recorded-v0"]

# P3 adds TIMEOUT, PARSE_ERROR, BUDGET, PROVIDER_ERROR (Agent Interface §2.2).
DecisionError = Literal["INVALID_CONTEXT", "INVALID_PLAN", "SCRIPT_EXHAUSTED", "REPLAY_DIVERGED"]

# ---------------------------------------------------------------------------
# Deterministic IDs (Agent Interface §2.2)
# ---------------------------------------------------------------------------


def build_plan_id(actor_id: str, decision_ordinal: int) -> str:
    """``<actor_id>:p<ordinal, at least 6 digits>``; never truncated."""
    if decision_ordinal < 0:
        raise ValueError("decision_ordinal must be nonnegative")
    return f"{actor_id}:p{decision_ordinal:06d}"


def build_intent_id(plan_id: str, index: int) -> str:
    """``<plan_id>:i<zero-based decimal index>``."""
    if index < 0:
        raise ValueError("intent index must be nonnegative")
    return f"{plan_id}:i{index}"


# ---------------------------------------------------------------------------
# DecisionContext (Interface Contract §2.3 as amended by A1; Agent Interface §2.3)
# ---------------------------------------------------------------------------


class PersonalityProfile(ProtocolModel):
    profile_id: str
    values: list[str]


class Goal(ProtocolModel):
    goal_id: str
    text: str
    priority: int


class RecalledEpisode(ProtocolModel):
    memory_id: str
    source: Literal["observation", "speech", "dream", "reflection"]
    summary: str
    confidence_band: NeedBand
    related_entity_ids: list[str]


class Belief(ProtocolModel):
    subject: str
    claim: str
    confidence_band: NeedBand


class DecisionContext(ProtocolModel):
    """Perception plus this resident's own private state; P1 memory fields stay empty."""

    perception: Perception
    personality_profile: PersonalityProfile
    current_goals: list[Goal]
    recalled_episodes: list[RecalledEpisode]
    beliefs: list[Belief]
    current_plan_summary: str | None


class DecisionRequest(ProtocolModel):
    actor_id: str
    tick: NonNegInt
    decision_ordinal: NonNegInt
    triggers: list[DecisionTrigger]
    context: DecisionContext

    @model_validator(mode="after")
    def _consistent(self) -> DecisionRequest:
        if not is_canonical_trigger_order(self.triggers):
            raise ValueError("triggers must be unique and in canonical order")
        p = self.context.perception
        if p.actor_id != self.actor_id or p.tick != self.tick:
            raise ValueError("context.perception must be this actor's packet for this tick")
        return self


# ---------------------------------------------------------------------------
# DecisionRecord and trace manifest (Agent Interface §5)
# ---------------------------------------------------------------------------


class DecisionRecord(ProtocolModel):
    record_schema_version: Literal["0.1"]
    run_id: str
    tick: NonNegInt
    actor_id: str
    decision_ordinal: NonNegInt
    policy_id: str
    effective_policy_id: str
    triggers: list[DecisionTrigger]
    request_sha256: Sha256Hex
    status: Literal["ok", "error"]
    error_kind: DecisionError | None
    plan: ActionPlan
    substituted: bool
    llm_call_id: str | None

    @model_validator(mode="after")
    def _consistent(self) -> DecisionRecord:
        if not is_canonical_trigger_order(self.triggers):
            raise ValueError("triggers must be unique and in canonical order")
        plan_id = build_plan_id(self.actor_id, self.decision_ordinal)
        if self.plan.actor_id != self.actor_id or self.plan.plan_id != plan_id:
            raise ValueError("plan must use this actor's deterministic plan ID")
        if self.plan.created_at_tick != self.tick:
            raise ValueError("plan.created_at_tick must equal tick")
        for i, intent in enumerate(self.plan.intents):
            if intent.intent_id != build_intent_id(plan_id, i):
                raise ValueError("intent IDs must follow the shared ID builders")
        if self.status == "ok":
            if self.error_kind is not None or self.substituted:
                raise ValueError("ok records have null error_kind and substituted=false")
            if self.policy_id != self.effective_policy_id:
                raise ValueError("ok records have matching policy_id/effective_policy_id")
        else:
            if self.error_kind is None or not self.substituted:
                raise ValueError("error records have error_kind and substituted=true")
            if self.effective_policy_id != SIM_FALLBACK_WAIT_POLICY_ID:
                raise ValueError("error records use effective_policy_id sim-fallback-wait")
            (only, *rest) = self.plan.intents
            if rest or only.action_type != "wait" or only.target is not None:
                raise ValueError("the wait substitute is a single wait intent with null target")
            if only.reason is not None or type(only.parameters) is not EmptyParameters:
                raise ValueError("the wait substitute has null reason and empty parameters")
        return self


class DecisionTraceManifest(ProtocolModel):
    trace_schema_version: Literal["0.1"]
    run_id: str
    config_hash: Sha256Hex
    map_hash: Sha256Hex
    final_tick: NonNegInt
    record_count: NonNegInt
    event_count: NonNegInt
    decisions_sha256: Sha256Hex
    events_sha256: Sha256Hex
    final_world_sha256: Sha256Hex


# ---------------------------------------------------------------------------
# DecisionOutcome (Agent Interface §2.2)
# ---------------------------------------------------------------------------


class OkOutcome(ProtocolModel):
    status: Literal["ok"]
    policy_id: str
    plan: ActionPlan


class ErrorOutcome(ProtocolModel):
    status: Literal["error"]
    policy_id: str
    error_kind: DecisionError
    detail: str


class ReplayedOutcome(ProtocolModel):
    status: Literal["replayed"]
    policy_id: Literal["recorded-v0"]
    source_record: DecisionRecord


DecisionOutcome = Annotated[
    OkOutcome | ErrorOutcome | ReplayedOutcome, Field(discriminator="status")
]

# ---------------------------------------------------------------------------
# Policy configuration and scripts (Agent Interface §2.5, §4.2)
# ---------------------------------------------------------------------------


class PolicyConfig(ProtocolModel):
    policy_id: PolicyId
    seed: Annotated[int, Field(ge=1, le=0xFFFFFFFF)]
    max_plan_actions: PosInt
    map_width: PosInt
    map_height: PosInt
    script_sha256: Sha256Hex | None
    source_trace_sha256: Sha256Hex | None

    @model_validator(mode="after")
    def _identities(self) -> PolicyConfig:
        if (self.policy_id == "scripted-v0") != (self.script_sha256 is not None):
            raise ValueError("script_sha256 is set for, and only for, scripted-v0")
        if (self.policy_id == "recorded-v0") != (self.source_trace_sha256 is not None):
            raise ValueError("source_trace_sha256 is set for, and only for, recorded-v0")
        return self


class OwnProfile(ProtocolModel):
    profile_id: str
    initial_goal: str


class IntentTemplate(ProtocolModel):
    """All fields are required, ``reason`` included."""

    action_type: ActionType
    target: ActionTarget | None
    parameters: ActionParameters
    reason: str | None

    @model_validator(mode="after")
    def _shape(self) -> IntentTemplate:
        check_action_shape(self.action_type, self.target, self.parameters)
        return self


class ActorScript(ProtocolModel):
    actor_id: str
    on_exhausted: Literal["error", "wait"]
    # Each plan has 1..max_plan_actions templates; the upper bound is config-dependent.
    plans: list[Annotated[list[IntentTemplate], Field(min_length=1)]]


class ScriptFixture(ProtocolModel):
    script_schema_version: Literal["0.1"]
    actors: list[ActorScript]

    @model_validator(mode="after")
    def _sorted(self) -> ScriptFixture:
        require_sorted_unique([a.actor_id for a in self.actors], "actors")
        return self


# ---------------------------------------------------------------------------
# Saved runtime state (Agent Interface §6)
# ---------------------------------------------------------------------------


class ResidentRuntimeState(ProtocolModel):
    actor_id: str
    policy_config: PolicyConfig
    next_decision_ordinal: NonNegInt
    policy_state: dict[str, JsonValue]
    latest_perception_tick: CursorTick

    @model_validator(mode="after")
    def _policy_state(self) -> ResidentRuntimeState:
        if self.policy_config.policy_id == "scripted-v0":
            cursor = self.policy_state.get("cursor")
            if set(self.policy_state) != {"cursor"} or not (
                isinstance(cursor, int) and not isinstance(cursor, bool) and cursor >= 0
            ):
                raise ValueError("scripted policy_state is exactly {cursor: nonnegative int}")
        elif self.policy_state:
            raise ValueError("random/recorded policy_state is {}")
        return self
