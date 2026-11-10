"""Agent-side schemas, policy configuration and shared ID builders.

Agent Interface Spec §2-§6. Imports world types only through ``living_island.world.protocol``;
never imports ``contract``, ``persistence``, ``world.state`` or ``world.facts``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import (
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from living_island.world.protocol import (
    ActionParameters,
    ActionPlan,
    ActionTarget,
    ActionType,
    Coord,
    CursorTick,
    DecisionTrigger,
    EmptyParameters,
    EntityTarget,
    NeedBand,
    NonNegInt,
    Perception,
    PosInt,
    ProtocolModel,
    ResidentTarget,
    Sha256Hex,
    TileTarget,
    check_action_shape,
    is_canonical_trigger_order,
    require_sorted_unique,
)

SCHEMA_VERSION_0_1 = "0.1"
SIM_FALLBACK_WAIT_POLICY_ID = "sim-fallback-wait"

PolicyId = Literal["random-v0", "scripted-v0", "recorded-v0", "rule-based-v0"]

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


def require_initial_or_triggered(tick: int, ordinal: int, triggers: list[DecisionTrigger]) -> None:
    """AI §2.2: empty triggers only for the tick-zero initial request (ordinal 0)."""
    if not triggers and (tick, ordinal) != (0, 0):
        raise ValueError("empty triggers are allowed only for the tick-zero initial request")


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
        require_initial_or_triggered(self.tick, self.decision_ordinal, self.triggers)
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
        require_initial_or_triggered(self.tick, self.decision_ordinal, self.triggers)
        if self.error_kind == "REPLAY_DIVERGED":
            raise ValueError("REPLAY_DIVERGED stops before commitment; never in a record")
        if self.llm_call_id is not None:
            raise ValueError("P1 decision records have llm_call_id null (AI §5)")
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


class RuleParams(ProtocolModel):
    rule_params_version: Literal["0.1"]
    canteen_use: Literal["enabled", "restricted"]
    cue_use: Literal["enabled", "ignored"]
    fruit_carry_target: PosInt
    failed_target_retry_ticks: PosInt


class PolicyConfig(ProtocolModel):
    policy_id: PolicyId
    seed: Annotated[int, Field(ge=1, le=0xFFFFFFFF)]
    max_plan_actions: PosInt
    map_width: PosInt
    map_height: PosInt
    script_sha256: Sha256Hex | None
    source_trace_sha256: Sha256Hex | None
    rule_params: RuleParams | None = None

    @model_validator(mode="before")
    @classmethod
    def _no_explicit_null(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "rule_params" in data and data["rule_params"] is None:
            raise ValueError("rule_params must be omitted, not null")
        return data

    @model_serializer(mode="wrap")
    def _omit_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        out: dict[str, Any] = handler(self)
        if self.rule_params is None:
            out.pop("rule_params", None)
        return out

    @model_validator(mode="after")
    def _identities(self) -> PolicyConfig:
        if (self.policy_id == "scripted-v0") != (self.script_sha256 is not None):
            raise ValueError("script_sha256 is set for, and only for, scripted-v0")
        if (self.policy_id == "recorded-v0") != (self.source_trace_sha256 is not None):
            raise ValueError("source_trace_sha256 is set for, and only for, recorded-v0")
        if (self.policy_id == "rule-based-v0") != (self.rule_params is not None):
            raise ValueError("rule_params is set for, and only for, rule-based-v0")
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


class SelfTarget(ProtocolModel):
    kind: Literal["self"]


TargetKey = Annotated[
    SelfTarget | TileTarget | EntityTarget | ResidentTarget, Field(discriminator="kind")
]
BackOffAction = ActionType | Literal["request"]


class RuleCommitment(ProtocolModel):
    goal: Literal["water", "tree", "canteen", "explore"]
    target: Coord
    set_at_tick: NonNegInt


class IssuedIntent(ProtocolModel):
    intent_id: str
    action_type: ActionType
    target: TargetKey | None


class FailedTarget(ProtocolModel):
    action: BackOffAction
    target: TargetKey
    code: str
    retry_after_tick: PosInt

    def sort_key(self) -> tuple[str, int, int, int, str]:
        match self.target:
            case SelfTarget():
                return self.action, 0, 0, 0, ""
            case TileTarget(position=position):
                return self.action, 1, position.y, position.x, ""
            case EntityTarget(id=entity_id):
                return self.action, 2, 0, 0, entity_id
            case ResidentTarget(id=resident_id):
                return self.action, 3, 0, 0, resident_id


class CueImpression(ProtocolModel):
    cue_id: str
    position: Coord
    detail_level: Literal["distant", "near"]
    direction: str | None


class RuleStateV0_1(ProtocolModel):
    rule_state_version: Literal["0.1"]
    commitment: RuleCommitment | None
    issued_intents: list[IssuedIntent]
    failed_targets: list[FailedTarget]
    cue_impressions: list[CueImpression]
    canteen_capacity: NonNegInt | None


# Rule Policy §7.1 intent references and §5 back-off cells.
_ISSUED_TARGET_KINDS: dict[ActionType, str] = {
    "move_to": "tile",
    "pick_up": "tile",
    "gather": "tile",
    "give": "resident",
    "talk": "resident",
    "fill_canteen": "entity",
}
_FAILURE_CODES: dict[tuple[BackOffAction, str], frozenset[str]] = {
    ("move_to", "tile"): frozenset({"INVALID_TARGET", "PATH_BLOCKED", "NO_PATH"}),
    ("gather", "tile"): frozenset({"OUT_OF_REACH", "RESOURCE_TAKEN", "INVALID_TARGET"}),
    ("gather", "self"): frozenset({"INVENTORY_FULL"}),
    ("pick_up", "tile"): frozenset({"ITEM_TAKEN", "OUT_OF_REACH", "INVALID_TARGET"}),
    ("pick_up", "self"): frozenset({"INVENTORY_FULL"}),
    ("give", "resident"): frozenset({"OUT_OF_REACH", "INVENTORY_FULL", "INVALID_TARGET"}),
    ("talk", "resident"): frozenset(
        {
            "INVALID_TARGET",
            "OUT_OF_HEARING",
            "INVALID_SPEECH_ACT",
            "INVALID_REPLY",
            "DIALOGUE_LIMIT",
        }
    ),
    ("fill_canteen", "entity"): frozenset({"NO_ITEM", "OUT_OF_REACH", "INVALID_TARGET"}),
}
_LOCAL_CODES: dict[tuple[BackOffAction, str], frozenset[str]] = {
    ("gather", "tile"): frozenset({"OBSERVED_EMPTY"}),
    ("request", "resident"): frozenset({"REFUSED", "REQUESTED"}),
}


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
        elif self.policy_config.policy_id == "rule-based-v0":
            self._validate_rule_state(RuleStateV0_1.model_validate(self.policy_state))
        elif self.policy_state:
            raise ValueError("random/recorded policy_state is {}")
        return self

    def _validate_rule_state(self, state: RuleStateV0_1) -> None:
        config = self.policy_config
        params = config.rule_params
        if params is None:
            raise ValueError("rule-based-v0 requires rule_params")
        keys = [entry.sort_key() for entry in state.failed_targets]
        if any(left >= right for left, right in zip(keys, keys[1:], strict=False)):
            raise ValueError("failed_targets must be sorted and unique by key")
        require_sorted_unique([cue.cue_id for cue in state.cue_impressions], "cue_impressions")
        if len(state.cue_impressions) > 1:
            raise ValueError("cue_impressions may contain at most one cue")

        self._validate_issued_intents(state.issued_intents)
        local_count = 0
        failure_count = 0
        deadline = self.latest_perception_tick + params.failed_target_retry_ticks
        for entry in state.failed_targets:
            key = (entry.action, entry.target.kind)
            if entry.code in _LOCAL_CODES.get(key, ()):
                local_count += 1
            elif entry.code in _FAILURE_CODES.get(key, ()):
                failure_count += 1
            else:
                raise ValueError("invalid failed_targets action, target kind and code")
            if entry.retry_after_tick > deadline:
                raise ValueError("failed_targets retry_after_tick exceeds the retry window")
        if local_count > 64 or failure_count > params.failed_target_retry_ticks:
            raise ValueError("failed_targets exceeds its local or failure entry limit")

        positions = [cue.position for cue in state.cue_impressions]
        targets = [ref.target for ref in state.issued_intents]
        targets.extend(entry.target for entry in state.failed_targets)
        positions.extend(target.position for target in targets if isinstance(target, TileTarget))
        if state.commitment is not None:
            positions.append(state.commitment.target)
            if state.commitment.set_at_tick > self.latest_perception_tick:
                raise ValueError("commitment.set_at_tick follows the latest perception")
        if any(p.x >= config.map_width or p.y >= config.map_height for p in positions):
            raise ValueError("rule state coordinate lies outside the grid")
        if any(
            cue.detail_level == "distant" and cue.direction is not None
            for cue in state.cue_impressions
        ):
            raise ValueError("a distant cue cannot have a direction")

    def _validate_issued_intents(self, intents: list[IssuedIntent]) -> None:
        if not intents:
            return
        if len(intents) > self.policy_config.max_plan_actions:
            raise ValueError("issued_intents exceeds the plan action limit")
        plan_id = intents[0].intent_id.rpartition(":i")[0]
        prefix = f"{self.actor_id}:p"
        ordinal = plan_id.removeprefix(prefix)
        if not plan_id.startswith(prefix) or not (ordinal.isascii() and ordinal.isdecimal()):
            raise ValueError("issued_intents must belong to a plan of this actor")
        ordinal_number = int(ordinal)
        if ordinal_number >= self.next_decision_ordinal or plan_id != build_plan_id(
            self.actor_id, ordinal_number
        ):
            raise ValueError("issued_intents must belong to a committed plan")
        for index, entry in enumerate(intents):
            if entry.intent_id != build_intent_id(plan_id, index):
                raise ValueError("issued_intents must use one plan and contiguous indices")
            target_kind = entry.target.kind if entry.target is not None else None
            if target_kind != _ISSUED_TARGET_KINDS.get(entry.action_type):
                raise ValueError("issued_intents target kind does not match its action")
