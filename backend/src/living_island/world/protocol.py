"""Canonical world-side protocol: the boundary between the world and its residents.

Holds ``Perception``, ``BoundaryPerceptionDelivery``, ``ActionPlan``, ``ActionIntent``,
``ActionResult`` and the public vocabularies (Interface Contract §2.2-§2.5, §4).

Agents and memory may import from ``living_island.world`` only through this module.
This module is standalone: it must not import any other ``living_island`` module,
including other ``living_island.world`` modules (implementation plan §2.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

# ---------------------------------------------------------------------------
# Base model and integer aliases
# ---------------------------------------------------------------------------


class ProtocolModel(BaseModel):
    """Base for every canonical DTO: strict types, unknown fields rejected, immutable."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


NonNegInt = Annotated[int, Field(ge=0)]
PosInt = Annotated[int, Field(ge=1)]
# Delivery cursors start at -1 before the first ingest (Interface Contract §5).
CursorTick = Annotated[int, Field(ge=-1)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

# ---------------------------------------------------------------------------
# Public vocabularies (Interface Contract §2.4, §2.5, §3.2, §4)
# ---------------------------------------------------------------------------

ActionType = Literal[
    "move_to",
    "gather",
    "eat",
    "drink",
    "fill_canteen",
    "rest",
    "sleep",
    "talk",
    "give",
    "pick_up",
    "wait",
]
ACTION_TYPES: tuple[ActionType, ...] = (
    "move_to",
    "gather",
    "eat",
    "drink",
    "fill_canteen",
    "rest",
    "sleep",
    "talk",
    "give",
    "pick_up",
    "wait",
)

Terrain = Literal[
    "sea", "beach", "grass", "woods", "rock", "spring", "cave", "fruit_tree", "damp_moss"
]
# Raw map symbol -> Terrain (Interface Contract §2.5, World Rules §1.2).
TERRAIN_BY_SYMBOL: dict[str, Terrain] = {
    "~": "sea",
    ".": "beach",
    ",": "grass",
    "W": "woods",
    "^": "rock",
    "S": "spring",
    "C": "cave",
    "F": "fruit_tree",
    "M": "damp_moss",
}

EntityType = Literal["resident", "corpse", "fruit_tree", "ground_fruit", "canteen", "cue"]
ENTITY_TYPES: tuple[EntityType, ...] = (
    "resident",
    "corpse",
    "fruit_tree",
    "ground_fruit",
    "canteen",
    "cue",
)

# Listed in precedence order.
InterruptionReason = Literal["DEATH", "URGENT_NEED", "DIRECT_SPEECH", "NEW_SIGHT"]
INTERRUPTION_REASONS: tuple[InterruptionReason, ...] = (
    "DEATH",
    "URGENT_NEED",
    "DIRECT_SPEECH",
    "NEW_SIGHT",
)

# Listed in canonical array order.
DecisionTrigger = Literal[
    "ACTION_FAILED",
    "ACTION_INTERRUPTED",
    "URGENT_NEED",
    "DIRECT_SPEECH",
    "NEW_SIGHT",
    "UTTERANCE_HEARD",
    "REPLY_REQUIRED",
    "WOKE",
    "PLAN_FINISHED",
]
DECISION_TRIGGERS: tuple[DecisionTrigger, ...] = (
    "ACTION_FAILED",
    "ACTION_INTERRUPTED",
    "URGENT_NEED",
    "DIRECT_SPEECH",
    "NEW_SIGHT",
    "UTTERANCE_HEARD",
    "REPLY_REQUIRED",
    "WOKE",
    "PLAN_FINISHED",
)

NeedBand = Literal["critical", "low", "moderate", "good", "strong"]
NEED_BANDS: tuple[NeedBand, ...] = ("critical", "low", "moderate", "good", "strong")

FruitBand = Literal["empty", "few", "many"]

# Listed in canonical array order.
VisibleSign = Literal["weak", "dehydrated", "fatigued"]
VISIBLE_SIGNS: tuple[VisibleSign, ...] = ("weak", "dehydrated", "fatigued")

SpeechAct = Literal["statement", "request", "accept", "refuse"]
ItemType = Literal["fruit", "canteen"]
DrinkSource = Literal["spring", "canteen"]
CueDetailLevel = Literal["distant", "near"]
ActionStatus = Literal["success", "failure", "interrupted"]

FailureCode = Literal[
    "DEAD",
    "EXHAUSTED",
    "INVALID_TARGET",
    "PATH_BLOCKED",
    "NO_PATH",
    "OUT_OF_REACH",
    "RESOURCE_TAKEN",
    "INVENTORY_FULL",
    "NO_ITEM",
    "NO_NEED",
    "NO_WATER",
    "ALREADY_FULL",
    "OUT_OF_HEARING",
    "INVALID_SPEECH_ACT",
    "INVALID_REPLY",
    "DIALOGUE_LIMIT",
    "ITEM_TAKEN",
]
FAILURE_CODES: tuple[FailureCode, ...] = (
    "DEAD",
    "EXHAUSTED",
    "INVALID_TARGET",
    "PATH_BLOCKED",
    "NO_PATH",
    "OUT_OF_REACH",
    "RESOURCE_TAKEN",
    "INVENTORY_FULL",
    "NO_ITEM",
    "NO_NEED",
    "NO_WATER",
    "ALREADY_FULL",
    "OUT_OF_HEARING",
    "INVALID_SPEECH_ACT",
    "INVALID_REPLY",
    "DIALOGUE_LIMIT",
    "ITEM_TAKEN",
)


def is_canonical_trigger_order(triggers: list[DecisionTrigger]) -> bool:
    """True when ``triggers`` is duplicate-free and ordered by ``DECISION_TRIGGERS``."""
    ranks = [DECISION_TRIGGERS.index(t) for t in triggers]
    return all(a < b for a, b in zip(ranks, ranks[1:], strict=False))


def is_canonical_sign_order(signs: list[VisibleSign]) -> bool:
    """True when ``signs`` is duplicate-free and ordered by ``VISIBLE_SIGNS``."""
    ranks = [VISIBLE_SIGNS.index(s) for s in signs]
    return all(a < b for a, b in zip(ranks, ranks[1:], strict=False))


def require_sorted_unique(values: list[str], what: str) -> None:
    """Raise ``ValueError`` unless ``values`` is strictly ascending."""
    if any(a >= b for a, b in zip(values, values[1:], strict=False)):
        raise ValueError(f"{what} must be sorted ascending and duplicate-free")


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------


class Coord(ProtocolModel):
    """A tile coordinate ``{x, y}``; (0,0) is top left."""

    x: NonNegInt
    y: NonNegInt


# ---------------------------------------------------------------------------
# Action targets and typed parameters (Interface Contract §2.4)
# ---------------------------------------------------------------------------


class TileTarget(ProtocolModel):
    kind: Literal["tile"]
    position: Coord


class EntityTarget(ProtocolModel):
    kind: Literal["entity"]
    id: str


class ResidentTarget(ProtocolModel):
    kind: Literal["resident"]
    id: str


ActionTarget = Annotated[TileTarget | EntityTarget | ResidentTarget, Field(discriminator="kind")]


class EmptyParameters(ProtocolModel):
    """``{}`` parameters for move_to, gather, eat, fill_canteen, rest, sleep, wait."""


class DrinkParameters(ProtocolModel):
    source: DrinkSource


class ItemRequest(ProtocolModel):
    """The ``request`` object of ``talk`` parameters."""

    item_type: ItemType
    quantity: PosInt

    @model_validator(mode="after")
    def _canteen_is_single(self) -> ItemRequest:
        if self.item_type == "canteen" and self.quantity != 1:
            raise ValueError("canteen quantity must be exactly 1")
        return self


class TalkParameters(ProtocolModel):
    """``request`` only for speech_act=request; ``in_reply_to`` only for accept/refuse."""

    speech_act: SpeechAct
    text: str
    request: ItemRequest | None = None
    in_reply_to: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _no_explicit_null(cls, data: Any) -> Any:
        # IC §2.4: optional keys are present only on their speech acts and never null.
        if isinstance(data, Mapping):
            for key in ("request", "in_reply_to"):
                if key in data and data[key] is None:
                    raise ValueError(f"{key} must be omitted, not null")
        return data

    @model_serializer(mode="wrap")
    def _omit_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        out: dict[str, Any] = handler(self)
        for key in ("request", "in_reply_to"):
            if out.get(key) is None:
                out.pop(key, None)
        return out

    @model_validator(mode="after")
    def _act_fields(self) -> TalkParameters:
        if (self.speech_act == "request") != (self.request is not None):
            raise ValueError("request is required for, and only for, speech_act=request")
        if (self.speech_act in ("accept", "refuse")) != (self.in_reply_to is not None):
            raise ValueError("in_reply_to is required for, and only for, accept/refuse")
        return self


class ItemTransferParameters(ProtocolModel):
    """Parameters for ``give`` and ``pick_up``."""

    item_type: ItemType
    quantity: PosInt

    @model_validator(mode="after")
    def _canteen_is_single(self) -> ItemTransferParameters:
        if self.item_type == "canteen" and self.quantity != 1:
            raise ValueError("canteen quantity must be exactly 1")
        return self


ActionParameters = EmptyParameters | DrinkParameters | TalkParameters | ItemTransferParameters

# action_type -> (required target kind or None, required parameter model)
ACTION_SHAPES: dict[ActionType, tuple[str | None, type[ProtocolModel]]] = {
    "move_to": ("tile", EmptyParameters),
    "gather": ("entity", EmptyParameters),
    "eat": (None, EmptyParameters),
    "drink": (None, DrinkParameters),
    "fill_canteen": ("entity", EmptyParameters),
    "rest": (None, EmptyParameters),
    "sleep": (None, EmptyParameters),
    "wait": (None, EmptyParameters),
    "talk": ("resident", TalkParameters),
    "give": ("resident", ItemTransferParameters),
    "pick_up": ("tile", ItemTransferParameters),
}


def check_action_shape(
    action_type: ActionType,
    target: TileTarget | EntityTarget | ResidentTarget | None,
    parameters: ActionParameters,
) -> None:
    """Raise ``ValueError`` unless target kind and parameter model match the action table."""
    kind, params_model = ACTION_SHAPES[action_type]
    actual_kind = None if target is None else target.kind
    if actual_kind != kind:
        raise ValueError(f"{action_type} requires target kind {kind!r}, got {actual_kind!r}")
    if type(parameters) is not params_model:
        raise ValueError(f"{action_type} requires {params_model.__name__} parameters")


# ---------------------------------------------------------------------------
# Plans, intents, results (Interface Contract §2.4)
# ---------------------------------------------------------------------------


class ActionIntent(ProtocolModel):
    intent_id: str
    plan_id: str
    actor_id: str
    action_type: ActionType
    target: ActionTarget | None
    parameters: ActionParameters
    reason: str | None

    @model_validator(mode="after")
    def _shape(self) -> ActionIntent:
        check_action_shape(self.action_type, self.target, self.parameters)
        return self


class ActionPlan(ProtocolModel):
    """1..agents.max_plan_actions intents; the configured upper bound is checked by agents."""

    plan_id: str
    actor_id: str
    created_at_tick: NonNegInt
    intents: Annotated[list[ActionIntent], Field(min_length=1)]

    @model_validator(mode="after")
    def _consistent(self) -> ActionPlan:
        for intent in self.intents:
            if intent.plan_id != self.plan_id or intent.actor_id != self.actor_id:
                raise ValueError("every intent must carry the plan's plan_id and actor_id")
        ids = [i.intent_id for i in self.intents]
        if len(set(ids)) != len(ids):
            raise ValueError("intent IDs must be unique within a plan")
        return self


DeltaValue = int | str | bool | Coord | None


class StateDelta(ProtocolModel):
    """Internal, authoritative change record; never resident-facing."""

    path: str
    before: DeltaValue
    after: DeltaValue


def _check_status_fields(
    status: ActionStatus,
    failure_code: FailureCode | None,
    interruption_reason: InterruptionReason | None,
) -> None:
    if status == "success" and (failure_code is not None or interruption_reason is not None):
        raise ValueError("success has null failure_code and interruption_reason")
    if status == "failure" and (failure_code is None or interruption_reason is not None):
        raise ValueError("failure has a failure_code and null interruption_reason")
    if status == "interrupted" and (failure_code is not None or interruption_reason is None):
        raise ValueError("interrupted has null failure_code and an interruption_reason")


class ActionFeedback(ProtocolModel):
    intent_id: str
    status: ActionStatus
    failure_code: FailureCode | None
    interruption_reason: InterruptionReason | None
    visible_effects: list[str]

    @model_validator(mode="after")
    def _status(self) -> ActionFeedback:
        _check_status_fields(self.status, self.failure_code, self.interruption_reason)
        return self


class ActionResult(ProtocolModel):
    intent_id: str
    actor_id: str
    tick_started: NonNegInt
    tick_finished: NonNegInt
    status: ActionStatus
    failure_code: FailureCode | None
    interruption_reason: InterruptionReason | None
    state_delta: list[StateDelta]
    visible_feedback: ActionFeedback
    event_ids: list[str]

    @model_validator(mode="after")
    def _consistent(self) -> ActionResult:
        _check_status_fields(self.status, self.failure_code, self.interruption_reason)
        if self.tick_finished < self.tick_started:
            raise ValueError("tick_finished must not precede tick_started")
        fb = self.visible_feedback
        if (fb.intent_id, fb.status, fb.failure_code, fb.interruption_reason) != (
            self.intent_id,
            self.status,
            self.failure_code,
            self.interruption_reason,
        ):
            raise ValueError("visible_feedback must match the result's intent and status")
        return self


# ---------------------------------------------------------------------------
# Perception (Interface Contract §2.2)
# ---------------------------------------------------------------------------


class OwnCondition(ProtocolModel):
    satiety: NeedBand
    hydration: NeedBand
    stamina: NeedBand
    health: NeedBand


class OwnInventory(ProtocolModel):
    fruit_count: NonNegInt
    canteen_id: str | None
    canteen_servings: NonNegInt | None

    @model_validator(mode="after")
    def _canteen_pair(self) -> OwnInventory:
        if (self.canteen_id is None) != (self.canteen_servings is None):
            raise ValueError("canteen_id and canteen_servings are both null or both set")
        return self


class TileView(ProtocolModel):
    """A tile and its static terrain (visible tiles and explored static tiles)."""

    position: Coord
    terrain: Terrain


def _check_descriptors(
    entity_type: EntityType,
    signs: list[VisibleSign],
    fruit_band: FruitBand | None,
    quantity: int | None,
) -> None:
    if signs and entity_type != "resident":
        raise ValueError("observable_signs apply to residents only")
    if not is_canonical_sign_order(signs):
        raise ValueError("observable_signs must be unique, ordered weak,dehydrated,fatigued")
    if (fruit_band is not None) != (entity_type == "fruit_tree"):
        raise ValueError("fruit_band is set for, and only for, fruit_tree")
    if (quantity is not None) != (entity_type == "ground_fruit"):
        raise ValueError("quantity is set for, and only for, ground_fruit")


class VisibleEntity(ProtocolModel):
    entity_id: str
    entity_type: EntityType
    position: Coord
    observable_signs: list[VisibleSign]
    fruit_band: FruitBand | None
    quantity: NonNegInt | None

    @model_validator(mode="after")
    def _descriptors(self) -> VisibleEntity:
        _check_descriptors(self.entity_type, self.observable_signs, self.fruit_band, self.quantity)
        return self


class TransientSighting(ProtocolModel):
    entity_id: str
    entity_type: EntityType
    position: Coord
    seen_at_step: PosInt
    observable_signs: list[VisibleSign]
    fruit_band: FruitBand | None
    quantity: NonNegInt | None

    @model_validator(mode="after")
    def _descriptors(self) -> TransientSighting:
        _check_descriptors(self.entity_type, self.observable_signs, self.fruit_band, self.quantity)
        return self


class EnvironmentalCue(ProtocolModel):
    cue_id: str
    position: Coord
    detail_level: CueDetailLevel
    physical_description: str
    direction: str | None


class HeardUtterance(ProtocolModel):
    utterance_id: str
    speaker_id: str
    addressee_id: str
    speech_act: SpeechAct
    text: str
    request_item_type: str | None
    request_quantity: PosInt | None
    in_reply_to: str | None
    heard_at_tick: NonNegInt


def check_physical_view_order(
    actor_id: str,
    visible_entities: list[VisibleEntity],
    transient_sightings: list[TransientSighting],
    environmental_cues: list[EnvironmentalCue],
) -> None:
    """Shared ordering/exclusion checks for Perception and observation samples."""
    require_sorted_unique([e.entity_id for e in visible_entities], "visible_entities")
    require_sorted_unique([e.entity_id for e in transient_sightings], "transient_sightings")
    require_sorted_unique([c.cue_id for c in environmental_cues], "environmental_cues")
    if any(e.entity_id == actor_id for e in visible_entities):
        raise ValueError("the observer is excluded from its own visible_entities")
    visible = {e.entity_id for e in visible_entities}
    if any(t.entity_id in visible for t in transient_sightings):
        raise ValueError("an entity visible at tick end is not a transient sighting")


class Perception(ProtocolModel):
    """What one resident physically perceives at a boundary; never full world state."""

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
    def _ordering(self) -> Perception:
        check_physical_view_order(
            self.actor_id,
            self.visible_entities,
            self.transient_sightings,
            self.environmental_cues,
        )
        return self


# ---------------------------------------------------------------------------
# Boundary delivery (Interface Contract §2.2)
# ---------------------------------------------------------------------------


def format_delivery_id(run_id: str, observed_tick: int, actor_id: str) -> str:
    """``<run_id>:perception:<10-digit observed_tick>:<actor_id>`` (padded, never truncated)."""
    if observed_tick < 0:
        raise ValueError("observed_tick must be nonnegative")
    return f"{run_id}:perception:{observed_tick:010d}:{actor_id}"


class BoundaryPerceptionDelivery(ProtocolModel):
    delivery_id: str
    actor_id: str
    observed_tick: NonNegInt
    perception: Perception
    decision_triggers: list[DecisionTrigger]

    @model_validator(mode="after")
    def _consistent(self) -> BoundaryPerceptionDelivery:
        if self.perception.actor_id != self.actor_id:
            raise ValueError("perception.actor_id must equal actor_id")
        if self.perception.tick != self.observed_tick:
            raise ValueError("perception.tick must equal observed_tick")
        suffix = f":perception:{self.observed_tick:010d}:{self.actor_id}"
        if not self.delivery_id.endswith(suffix) or len(self.delivery_id) == len(suffix):
            raise ValueError("delivery_id must be <run_id>:perception:<tick>:<actor_id>")
        if not is_canonical_trigger_order(self.decision_triggers):
            raise ValueError("decision_triggers must be unique and in canonical order")
        return self


class DeferredDecisionTriggers(ProtocolModel):
    actor_id: str
    reasons: list[DecisionTrigger]

    @model_validator(mode="after")
    def _order(self) -> DeferredDecisionTriggers:
        if not is_canonical_trigger_order(self.reasons):
            raise ValueError("reasons must be unique and in canonical order")
        return self
