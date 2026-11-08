"""Canonical objective facts: the ``WorldEvent`` envelope and every event payload.

Interface Contract §3. World owns these models and the event-ID format (amendment A1);
``living_island.events`` only re-exports and projects them. Pure: no IO.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from living_island.world.protocol import (
    ActionType,
    Coord,
    DrinkSource,
    FailureCode,
    InterruptionReason,
    ItemType,
    NonNegInt,
    PosInt,
    ProtocolModel,
    SpeechAct,
)

EventType = Literal[
    "world_initialized",
    "config_changed",
    "action_started",
    "action_progressed",
    "resident_moved",
    "action_succeeded",
    "action_failed",
    "action_interrupted",
    "fruit_gathered",
    "fruit_consumed",
    "water_drank",
    "canteen_filled",
    "stamina_action_cost_applied",
    "fruit_regrew",
    "condition_updated",
    "utterance_spoken",
    "utterance_heard",
    "item_given",
    "item_picked_up",
    "resident_died",
    "corpse_created",
    "item_dropped",
    "exploration_updated",
    "agent_fallback_used",
    "god_intervention_recorded",
]


def format_event_id(run_id: str, tick: int, seq_in_tick: int) -> str:
    """``<run_id>:<10-digit tick>:<6-digit seq>``; padded, never truncated."""
    if tick < 0 or seq_in_tick < 0:
        raise ValueError("tick and seq_in_tick must be nonnegative")
    return f"{run_id}:{tick:010d}:{seq_in_tick:06d}"


# ---------------------------------------------------------------------------
# Payloads (Interface Contract §3.2)
# ---------------------------------------------------------------------------


class WorldInitializedPayload(ProtocolModel):
    config_hash: str
    map_hash: str
    initial_snapshot_hash: str


class ConfigChangedPayload(ProtocolModel):
    parameter: str
    old_value: int
    new_value: int
    effective_tick: NonNegInt


class ActionStartedPayload(ProtocolModel):
    action_type: ActionType
    plan_id: str
    duration_ticks: NonNegInt | None


class ActionProgressedPayload(ProtocolModel):
    action_type: ActionType
    elapsed_ticks: NonNegInt
    remaining_ticks: NonNegInt | None
    route_cursor: NonNegInt | None


class ResidentMovedPayload(ProtocolModel):
    from_: Coord = Field(alias="from")
    to: Coord
    step_cost_units: PosInt

    # The contract field is ``from`` (a Python keyword); serialize under that name.
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


class ActionSucceededPayload(ProtocolModel):
    action_type: ActionType
    result_code: Literal["OK"]


class ActionFailedPayload(ProtocolModel):
    action_type: ActionType
    failure_code: FailureCode


class ActionInterruptedPayload(ProtocolModel):
    action_type: ActionType
    reason: InterruptionReason


class FruitGatheredPayload(ProtocolModel):
    tree_id: str
    quantity: PosInt
    stock_before: NonNegInt
    stock_after: NonNegInt


class FruitConsumedPayload(ProtocolModel):
    quantity: PosInt
    satiety_before: NonNegInt
    satiety_after: NonNegInt


class WaterDrankPayload(ProtocolModel):
    source: DrinkSource
    servings: PosInt
    hydration_before: NonNegInt
    hydration_after: NonNegInt
    canteen_servings_after: NonNegInt | None


class CanteenFilledPayload(ProtocolModel):
    canteen_id: str
    servings_before: NonNegInt
    servings_after: NonNegInt


class StaminaActionCostAppliedPayload(ProtocolModel):
    amount: NonNegInt
    reason: Literal["gather", "move"]


class FruitRegrewPayload(ProtocolModel):
    tree_id: str
    quantity: PosInt
    stock_before: NonNegInt
    stock_after: NonNegInt


class ConditionUpdatedPayload(ProtocolModel):
    resident_id: str
    satiety_before: NonNegInt
    satiety_after: NonNegInt
    hydration_before: NonNegInt
    hydration_after: NonNegInt
    stamina_before: NonNegInt
    stamina_after: NonNegInt
    health_before: NonNegInt
    health_after: NonNegInt


class UtteranceRequest(ProtocolModel):
    item_type: str
    quantity: PosInt


class UtteranceSpokenPayload(ProtocolModel):
    utterance_id: str
    addressee_id: str
    speech_act: SpeechAct
    text: str
    request: UtteranceRequest | None
    in_reply_to: str | None


class UtteranceHeardPayload(ProtocolModel):
    utterance_id: str
    listener_id: str


class ItemGivenPayload(ProtocolModel):
    from_id: str
    to_id: str
    item_type: ItemType
    quantity: PosInt
    canteen_id: str | None


class ItemPickedUpPayload(ProtocolModel):
    resident_id: str
    position: Coord
    item_type: ItemType
    quantity: PosInt
    canteen_id: str | None


class ResidentDiedPayload(ProtocolModel):
    resident_id: str
    position: Coord
    cause: Literal["DEPRIVATION"]


class CorpseCreatedPayload(ProtocolModel):
    corpse_id: str
    resident_id: str
    position: Coord


class ItemDroppedPayload(ProtocolModel):
    resident_id: str
    position: Coord
    item_type: ItemType
    quantity: PosInt
    canteen_id: str | None
    canteen_servings: NonNegInt | None


class ExplorationUpdatedPayload(ProtocolModel):
    resident_id: str
    newly_seen_tile_indices: list[NonNegInt]

    @model_validator(mode="after")
    def _sorted(self) -> ExplorationUpdatedPayload:
        idx = self.newly_seen_tile_indices
        if any(a >= b for a, b in zip(idx, idx[1:], strict=False)):
            raise ValueError("newly_seen_tile_indices must be ascending and duplicate-free")
        return self


class AgentFallbackUsedPayload(ProtocolModel):
    resident_id: str
    reason: Literal["TIMEOUT", "PARSE_ERROR", "BUDGET", "PROVIDER_ERROR"]
    fallback_policy_id: str


class GodInterventionRecordedPayload(ProtocolModel):
    intervention_id: str
    recipient_id: str
    kind: Literal["dream", "faint_thought"]
    transcript_retained: bool


TypedEventPayload = (
    WorldInitializedPayload
    | ConfigChangedPayload
    | ActionStartedPayload
    | ActionProgressedPayload
    | ResidentMovedPayload
    | ActionSucceededPayload
    | ActionFailedPayload
    | ActionInterruptedPayload
    | FruitGatheredPayload
    | FruitConsumedPayload
    | WaterDrankPayload
    | CanteenFilledPayload
    | StaminaActionCostAppliedPayload
    | FruitRegrewPayload
    | ConditionUpdatedPayload
    | UtteranceSpokenPayload
    | UtteranceHeardPayload
    | ItemGivenPayload
    | ItemPickedUpPayload
    | ResidentDiedPayload
    | CorpseCreatedPayload
    | ItemDroppedPayload
    | ExplorationUpdatedPayload
    | AgentFallbackUsedPayload
    | GodInterventionRecordedPayload
)

PAYLOAD_MODEL_BY_TYPE: dict[EventType, type[ProtocolModel]] = {
    "world_initialized": WorldInitializedPayload,
    "config_changed": ConfigChangedPayload,
    "action_started": ActionStartedPayload,
    "action_progressed": ActionProgressedPayload,
    "resident_moved": ResidentMovedPayload,
    "action_succeeded": ActionSucceededPayload,
    "action_failed": ActionFailedPayload,
    "action_interrupted": ActionInterruptedPayload,
    "fruit_gathered": FruitGatheredPayload,
    "fruit_consumed": FruitConsumedPayload,
    "water_drank": WaterDrankPayload,
    "canteen_filled": CanteenFilledPayload,
    "stamina_action_cost_applied": StaminaActionCostAppliedPayload,
    "fruit_regrew": FruitRegrewPayload,
    "condition_updated": ConditionUpdatedPayload,
    "utterance_spoken": UtteranceSpokenPayload,
    "utterance_heard": UtteranceHeardPayload,
    "item_given": ItemGivenPayload,
    "item_picked_up": ItemPickedUpPayload,
    "resident_died": ResidentDiedPayload,
    "corpse_created": CorpseCreatedPayload,
    "item_dropped": ItemDroppedPayload,
    "exploration_updated": ExplorationUpdatedPayload,
    "agent_fallback_used": AgentFallbackUsedPayload,
    "god_intervention_recorded": GodInterventionRecordedPayload,
}


class WorldEvent(ProtocolModel):
    """Objective event envelope (Interface Contract §3.1) with a typed payload."""

    schema_version: str
    run_id: str
    event_id: str
    tick: NonNegInt
    seq_in_tick: NonNegInt
    type: EventType
    actor_id: str | None
    target_id: str | None
    intent_id: str | None
    llm_call_id: str | None
    caused_by_event_ids: list[str]
    payload: Annotated[TypedEventPayload, Field(union_mode="left_to_right")]

    @model_validator(mode="before")
    @classmethod
    def _parse_payload_by_type(cls, data: Any) -> Any:
        # Parse a raw payload with the model the event type names, not by union guessing.
        if isinstance(data, dict):
            event_type = data.get("type")
            payload = data.get("payload")
            if event_type in PAYLOAD_MODEL_BY_TYPE and isinstance(payload, dict):
                model = PAYLOAD_MODEL_BY_TYPE[event_type]
                return {**data, "payload": model.model_validate(payload)}
        return data

    @model_validator(mode="after")
    def _consistent(self) -> WorldEvent:
        if type(self.payload) is not PAYLOAD_MODEL_BY_TYPE[self.type]:
            raise ValueError(f"payload does not match event type {self.type}")
        if self.event_id != format_event_id(self.run_id, self.tick, self.seq_in_tick):
            raise ValueError("event_id must equal format_event_id(run_id, tick, seq_in_tick)")
        if self.event_id in self.caused_by_event_ids:
            raise ValueError("an event cannot cause itself")
        return self
