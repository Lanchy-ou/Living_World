"""Strict WAP 0.1 types, shape validation, and canonical wire encoding."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from hashlib import sha256
from operator import attrgetter
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    model_validator,
)
from pydantic.json_schema import models_json_schema

SCHEMA_VERSION = "wap/0.1"

Tick = Annotated[int, Field(ge=0)]
Quantity = Annotated[int, Field(gt=0)]
TurnId = Annotated[str, Field(pattern=r"^[^\r\n]+:t[0-9]{6,}$")]
IntentId = Annotated[str, Field(pattern=r"^[^\r\n]+:t[0-9]{6,}:a$")]
TargetKind = Literal["tile", "entity", "resident"]
Action = Literal["move_to", "give", "pick_up", "drop", "wait", "inspect", "contribute", "act"]
FailureCode = Literal[
    "DEAD",
    "INVALID_TARGET",
    "NO_PATH",
    "PATH_BLOCKED",
    "OUT_OF_REACH",
    "NO_ITEM",
    "ITEM_TAKEN",
    "INVENTORY_FULL",
    "CONTAINER_FULL",
    "NOT_A_PROCESS",
    "EXHAUSTED",
    "OUT_OF_HEARING",
    "INVALID_SPEECH_ACT",
    "INVALID_REPLY",
    "INVALID_TERMS",
    "DIALOGUE_LIMIT",
]
HardStop = Literal["DEATH", "FAINTED", "EXHAUSTED", "PATH_BLOCKED", "TARGET_GONE", "WOKEN"]
Terrain = Literal[
    "sea", "beach", "grass", "woods", "rock", "spring", "cave", "fruit_tree", "damp_moss"
]
VisibleSign = Literal["weak", "dehydrated", "fatigued"]
NeedBand = Literal["critical", "low", "moderate", "good", "strong"]
SpeechAct = Literal["statement", "propose", "accept", "refuse"]
DescriptorValue = str


class ProtocolModel(BaseModel):
    """Shared strict settings for messages and their embedded records."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always"
    )


class VersionedMessage(ProtocolModel):
    schema_version: Literal["wap/0.1"]


class Coord(ProtocolModel):
    x: int
    y: int


class TileTarget(ProtocolModel):
    kind: Literal["tile"]
    position: Coord


class EntityTarget(ProtocolModel):
    kind: Literal["entity"]
    id: str


class ResidentTarget(ProtocolModel):
    kind: Literal["resident"]
    id: str


Target = Annotated[TileTarget | EntityTarget | ResidentTarget, Field(discriminator="kind")]
_TARGET_TYPES: dict[TargetKind, type[ProtocolModel]] = {
    "tile": TileTarget,
    "entity": EntityTarget,
    "resident": ResidentTarget,
}


class NamedItem(ProtocolModel):
    kind: Literal["item"]
    id: str


class HeldItem(ProtocolModel):
    kind: Literal["held"]
    archetype_id: str


ItemChoice = Annotated[NamedItem | HeldItem, Field(discriminator="kind")]


class ActionInput(ProtocolModel):
    item: ItemChoice
    quantity: Quantity


class EmptyParams(ProtocolModel):
    pass


class TransferParams(ProtocolModel):
    item: ItemChoice
    quantity: Quantity


class PickupParams(ProtocolModel):
    quantity: Quantity


class TilePickupParams(PickupParams):
    archetype_id: str


# The same kernel branches drive validation and generation of the model schema.
_KERNEL_SHAPES: dict[tuple[Action, TargetKind | None], type[ProtocolModel]] = {
    ("move_to", "tile"): EmptyParams,
    ("give", "resident"): TransferParams,
    ("pick_up", "entity"): PickupParams,
    ("pick_up", "tile"): TilePickupParams,
    ("drop", "entity"): TransferParams,
    ("drop", "tile"): TransferParams,
    ("wait", None): EmptyParams,
    ("inspect", "entity"): EmptyParams,
    ("contribute", "entity"): EmptyParams,
}


class VerbParameter(ProtocolModel):
    """One required integer parameter of an enabled verb."""

    name: str
    min: int
    max: int

    @model_validator(mode="after")
    def check_bounds(self) -> Self:
        if self.min > self.max:
            raise ValueError("verb parameter minimum exceeds its maximum")
        return self


class EnabledVerb(ProtocolModel):
    """Vocabulary projection containing just the fields used by turn shapes."""

    id: str
    target_kinds: tuple[TargetKind, ...]
    params: tuple[VerbParameter, ...]

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        if len(set(self.target_kinds)) != len(self.target_kinds):
            raise ValueError("duplicate target kind")
        if len({param.name for param in self.params}) != len(self.params):
            raise ValueError("duplicate verb parameter")
        if self.id == "sleep" and (
            self.target_kinds
            or self.params != (VerbParameter(name="duration_ticks", min=6, max=54),)
        ):
            raise ValueError("sleep requires no target and duration_ticks in 6..54")
        return self


def _index_verbs(verbs: Iterable[EnabledVerb]) -> dict[str, EnabledVerb]:
    by_id: dict[str, EnabledVerb] = {}
    for verb in sorted(verbs, key=attrgetter("id")):
        if verb.id in by_id:
            raise ValueError(f"duplicate enabled verb {verb.id!r}")
        by_id[verb.id] = verb
    return by_id


class IntentShape(ProtocolModel):
    """Intent fields supplied by a policy before the harness attaches identity."""

    action: Action
    verb: str | None
    target: Target | None
    instruments: list[ItemChoice]
    inputs: list[ActionInput]
    params: dict[str, JsonValue]
    reason: str | None

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        target_kind = self.target.kind if self.target is not None else None
        if self.action == "act":
            if self.verb is None:
                raise ValueError("act requires a verb")
            if any(type(value) is not int for value in self.params.values()):
                raise ValueError("verb parameters must be integers")
            choices = [*self.instruments, *(entry.item for entry in self.inputs)]
            named = [item.id for item in choices if isinstance(item, NamedItem)]
            if len(set(named)) != len(named):
                raise ValueError("the same named item appears twice")
        else:
            if self.verb is not None or self.instruments or self.inputs:
                raise ValueError("only act accepts a verb, instruments or inputs")
            param_type = _KERNEL_SHAPES.get((self.action, target_kind))
            if param_type is None:
                raise ValueError(f"invalid target kind for {self.action}")
            param_type.model_validate(self.params)
        return self

    def _check_verb(self, verbs: dict[str, EnabledVerb]) -> None:
        if self.action != "act":
            return
        verb = verbs.get(self.verb) if self.verb is not None else None
        if verb is None:
            raise InvalidTurn(f"verb {self.verb!r} is not enabled")
        target_kind = self.target.kind if self.target is not None else None
        if target_kind not in (verb.target_kinds or (None,)):
            raise InvalidTurn(f"invalid target kind for verb {verb.id!r}")
        if self.params.keys() != {param.name for param in verb.params}:
            raise InvalidTurn(f"invalid parameters for verb {verb.id!r}")
        for param in verb.params:
            value = self.params[param.name]
            if type(value) is not int or not param.min <= value <= param.max:
                raise InvalidTurn(f"parameter {param.name!r} must be in {param.min}..{param.max}")


class Intent(IntentShape):
    intent_id: IntentId
    turn_id: TurnId
    actor_id: str


class ContinueAction(ProtocolModel):
    kind: Literal["continue"]


class IntentAction(ProtocolModel):
    kind: Literal["intent"]
    intent: Intent


class ModelIntentAction(ProtocolModel):
    kind: Literal["intent"]
    intent: IntentShape


class ExactItemSpec(ProtocolModel):
    item_id: str


class KindItemSpec(ProtocolModel):
    archetype_id: str
    quantity: Quantity


ItemSpec = ExactItemSpec | KindItemSpec


class GiveItemTerm(ProtocolModel):
    kind: Literal["give_item"]
    item: ItemSpec


class ReturnItemTerm(ProtocolModel):
    kind: Literal["return_item"]
    item_id: str


class BeAtTerm(ProtocolModel):
    kind: Literal["be_at"]
    position: Coord


class ContributeTerm(ProtocolModel):
    kind: Literal["contribute"]
    process_id: str
    work_ticks: Quantity


Term = Annotated[
    GiveItemTerm | ReturnItemTerm | BeAtTerm | ContributeTerm, Field(discriminator="kind")
]


class Terms(ProtocolModel):
    promisor_id: str
    promisee_id: str
    what: Term
    due_tick: Tick | None

    @model_validator(mode="after")
    def check_due_tick(self) -> Self:
        if self.what.kind == "be_at" and self.due_tick is None:
            raise ValueError("be_at requires a due_tick")
        return self


class Utterance(ProtocolModel):
    addressee_id: str | None
    speech_act: SpeechAct
    text: str
    terms: Terms | None
    in_reply_to: str | None

    @model_validator(mode="after")
    def check_speech_act(self) -> Self:
        if (self.speech_act == "propose") != (self.terms is not None):
            raise ValueError("only propose carries terms, and terms are required for propose")
        if (self.speech_act in ("accept", "refuse")) != (self.in_reply_to is not None):
            raise ValueError("accept and refuse require a reply ID; other speech acts forbid it")
        if self.addressee_id is None and self.speech_act != "statement":
            raise ValueError("only a statement can be unaddressed")
        return self


class HeardUtterance(Utterance):
    utterance_id: str
    speaker_id: str
    heard_at_tick: Tick


class UtteranceFeedback(ProtocolModel):
    utterance_id: str | None
    failure_code: FailureCode | None


class TurnSubmission(VersionedMessage):
    """A complete world-facing turn. Its IDs are bound by the coordinator."""

    turn_id: TurnId
    actor_id: str
    observed_tick: Tick
    action: Annotated[ContinueAction | IntentAction, Field(discriminator="kind")]
    utterance: Utterance | None


class ModelTurn(ProtocolModel):
    """The world-facing subset of the model response, before harness binding."""

    action: Annotated[ContinueAction | ModelIntentAction, Field(discriminator="kind")]
    utterance: Utterance | None


class InvalidTurn(ValueError):
    """Shape failure for a complete turn (WAP §3.4)."""

    code: Literal["INVALID_TURN"] = "INVALID_TURN"


def validate_turn_shape[T: (ModelTurn, TurnSubmission)](
    model: type[T],
    value: object,
    *,
    enabled_verbs: Iterable[EnabledVerb],
    has_running_action: bool,
) -> T:
    """Validate a model turn or a submission, including its utterance as one unit."""
    verbs = _index_verbs(enabled_verbs)
    try:
        turn = model.model_validate(value)
    except ValidationError as exc:
        raise InvalidTurn(str(exc)) from exc

    if turn.action.kind == "intent":
        turn.action.intent._check_verb(verbs)
    elif not has_running_action:
        raise InvalidTurn("continue requires a running action")
    return turn


class Descriptor(ProtocolModel):
    property_id: str
    value: DescriptorValue


def _sorted_by[T](key: Callable[[T], str | int | tuple[Any, ...]]) -> AfterValidator:
    # attrgetter and the tuple keys below all return comparable values.
    return AfterValidator(lambda values: sorted(values, key=key))


Descriptors = Annotated[list[Descriptor], _sorted_by(attrgetter("property_id"))]


class InspectView(ProtocolModel):
    entity_id: str
    archetype_id: str | None
    material_id: str | None
    descriptors: Descriptors


class ItemView(InspectView):
    archetype_id: str
    quantity: Quantity


class TileStartTarget(TileTarget):
    terrain: Terrain


class SubjectStartTarget(ProtocolModel):
    kind: Literal["entity", "resident"]
    id: str
    archetype_id: str | None
    material_id: str | None
    descriptors: Descriptors


StartTarget = Annotated[TileStartTarget | SubjectStartTarget, Field(discriminator="kind")]
ItemRole = Literal["target", "instrument", "input", "item", "output"]
_ITEM_ROLE_ORDER = get_args(ItemRole)


class ItemUse(InspectView):
    role: ItemRole
    quantity: Quantity


def _item_use_key(item: ItemUse) -> tuple[int, str]:
    return _ITEM_ROLE_ORDER.index(item.role), item.entity_id


ItemUses = Annotated[list[ItemUse], _sorted_by(_item_use_key)]
Phenomena = Annotated[list[str], AfterValidator(lambda values: sorted(set(values)))]


class ActionFeedback(ProtocolModel):
    intent_id: IntentId
    status: Literal["done", "failed", "stopped"]
    failure_code: FailureCode | None
    stop_reason: HardStop | Literal["own_choice"] | None
    phenomena: Phenomena
    inspected: InspectView | None
    start_target: StartTarget | None
    items_used: ItemUses

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if (self.status == "failed") != (self.failure_code is not None):
            raise ValueError("failure_code is required for failed feedback only")
        if (self.status == "stopped") != (self.stop_reason is not None):
            raise ValueError("stop_reason is required for stopped feedback only")
        return self


class WorldStop(ProtocolModel):
    by: Literal["world"]
    reason: HardStop


class ActorStop(ProtocolModel):
    by: Literal["actor"]


Stop = Annotated[WorldStop | ActorStop, Field(discriminator="by")]


class Settlement(ProtocolModel):
    rule_id: str | None
    kind: Literal["applied", "chance_failed", "unmet", "unmatched"]
    at: Literal["start", "completion"]
    failed_check: str | None

    @model_validator(mode="after")
    def check_kind(self) -> Self:
        if (self.kind == "unmet") != (self.failed_check is not None):
            raise ValueError("failed_check is required for unmet settlements only")
        return self


DeltaValue = int | str | bool | Coord | None


class StateDelta(ProtocolModel):
    path: str
    before: DeltaValue
    after: DeltaValue


class ActionResult(ProtocolModel):
    intent_id: IntentId
    actor_id: str
    tick_started: Tick
    tick_finished: Tick
    outcome: Literal["success", "failure", "settled", "stopped"]
    failure_code: FailureCode | None
    stop: Stop | None
    settlement: Settlement | None
    state_delta: Annotated[list[StateDelta], _sorted_by(attrgetter("path"))]
    visible_feedback: ActionFeedback
    event_ids: Annotated[list[str], AfterValidator(sorted)]

    @model_validator(mode="after")
    def check_outcome(self) -> Self:
        if (self.outcome == "failure") != (self.failure_code is not None):
            raise ValueError("failure_code is required for a failed result only")
        if (self.outcome == "stopped") != (self.stop is not None):
            raise ValueError("stop is required for a stopped result only")
        if (self.outcome == "settled") != (self.settlement is not None):
            raise ValueError("settlement is required for a settled result only")
        return self


_VISIBLE_SIGN_ORDER = get_args(VisibleSign)


class EntityView(InspectView):
    kind: Literal["resident", "corpse", "item", "structure", "process", "feature"]
    position: Coord
    quantity: Quantity | None
    observable_signs: Annotated[list[VisibleSign], _sorted_by(_VISIBLE_SIGN_ORDER.index)]


class TransientSighting(EntityView):
    seen_at_step: Tick


class RunningAction(ProtocolModel):
    intent_id: IntentId
    action: Action
    verb: str | None
    tick_started: Tick
    progress: DescriptorValue | None
    start_target: StartTarget | None
    items: ItemUses


class NeedView(ProtocolModel):
    need_id: str
    band: NeedBand


class TileView(ProtocolModel):
    position: Coord
    terrain: Terrain


def _tile_key(tile: TileView) -> tuple[int, int]:
    return tile.position.y, tile.position.x


Tiles = Annotated[list[TileView], _sorted_by(_tile_key)]


class EnvironmentalCue(ProtocolModel):
    cue_id: str
    position: Coord
    detail_level: Literal["distant", "near"]
    physical_description: str
    direction: str | None


ObservationPhase = Literal["start", "stop", "settle"]
_PHASE_ORDER = get_args(ObservationPhase)


class ObservedAction(ProtocolModel):
    actor_id: str
    intent_id: IntentId
    tick: Tick
    phase: ObservationPhase
    action: Action
    verb: str | None
    target: Target | None
    start_target: StartTarget | None
    received_items: list[ItemUse]  # Preserve committed transfer source order.
    visible_items: ItemUses
    phenomena: Phenomena


def _observation_key(observation: ObservedAction) -> tuple[int, str, str, int]:
    return (
        observation.tick,
        observation.actor_id,
        observation.intent_id,
        _PHASE_ORDER.index(observation.phase),
    )


class Perception(VersionedMessage):
    actor_id: str
    tick: Tick
    awareness: Literal["awake", "asleep", "unconscious"]
    needs: Annotated[list[NeedView], _sorted_by(attrgetter("need_id"))]
    own_position: Coord
    inventory: Annotated[list[ItemView], _sorted_by(attrgetter("entity_id"))]
    running_action: RunningAction | None
    visible_tiles: Tiles
    explored_static_tiles: Tiles
    visible_entities: Annotated[list[EntityView], _sorted_by(attrgetter("entity_id"))]
    transient_sightings: Annotated[list[TransientSighting], _sorted_by(attrgetter("entity_id"))]
    environmental_cues: Annotated[list[EnvironmentalCue], _sorted_by(attrgetter("cue_id"))]
    heard_utterances: Annotated[list[HeardUtterance], _sorted_by(attrgetter("utterance_id"))]
    observed_actions: Annotated[list[ObservedAction], _sorted_by(_observation_key)]
    # The producer orders by tick_finished then intent_id. Tick isn't in the public view.
    action_feedback: list[ActionFeedback]
    last_utterance_feedback: UtteranceFeedback | None


ReportKind = Literal[
    "action_ended",
    "need_band_changed",
    "need_threshold_crossed",
    "utterance_heard",
    "entity_first_seen",
    "action_observed",
    "progress_step",
    "woke",
]
_REPORT_ORDER = get_args(ReportKind)


class WorldReport(ProtocolModel):
    kind: ReportKind
    subject_id: str | None
    addressed: bool | None
    band: NeedBand | None
    threshold_id: str | None

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if (self.kind == "woke") != (self.subject_id is None):
            raise ValueError("subject_id is null for woke only")
        if (self.kind == "utterance_heard") != (self.addressed is not None):
            raise ValueError("addressed is required for utterance_heard only")
        if (self.kind == "need_band_changed") != (self.band is not None):
            raise ValueError("band is required for need_band_changed only")
        if (self.kind == "need_threshold_crossed") != (self.threshold_id is not None):
            raise ValueError("threshold_id is required for need_threshold_crossed only")
        return self


def _report_key(report: WorldReport) -> tuple[int, str, bool, str]:
    return (
        _REPORT_ORDER.index(report.kind),
        report.subject_id or "",
        report.threshold_id is not None,
        report.threshold_id or "",
    )


class BoundaryDelivery(ProtocolModel):
    delivery_id: str
    actor_id: str
    observed_tick: Tick
    perception: Perception
    reports: Annotated[list[WorldReport], _sorted_by(_report_key)]


def boundary_delivery_id(run_id: str, observed_tick: int, actor_id: str) -> str:
    return f"{run_id}:perception:{observed_tick:010d}:{actor_id}"


def check_delivery_identity(packet: BoundaryDelivery, run_id: str, observed_tick: int) -> None:
    """Bind a decoded packet and its perception to the expected boundary."""
    if (
        packet.observed_tick != observed_tick
        or packet.delivery_id != boundary_delivery_id(run_id, observed_tick, packet.actor_id)
        or packet.perception.actor_id != packet.actor_id
        or packet.perception.tick != observed_tick
    ):
        raise ValueError("packet identity differs from its run, resident or boundary")


def _reject_float(token: str) -> None:
    raise ValueError(f"non-integer JSON number {token!r}")


def _reject_floats(value: JsonValue) -> JsonValue:
    if isinstance(value, float):
        raise ValueError("fractional or floating-point numbers are forbidden")
    if isinstance(value, dict):
        for child in value.values():
            _reject_floats(child)
    elif isinstance(value, list):
        for child in value:
            _reject_floats(child)
    return value


IntegerJson = Annotated[JsonValue, AfterValidator(_reject_floats)]


class WorldEvent(VersionedMessage):
    """Objective event envelope. Producers own event types and payload schemas."""

    run_id: str
    event_id: str
    tick: Tick
    seq_in_tick: Tick
    type: str
    actor_id: str | None
    target_id: str | None
    intent_id: IntentId | None
    llm_call_id: str | None
    caused_by_event_ids: list[str]  # Preserve creation order.
    payload: dict[str, IntegerJson]


def _unique_fields(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    fields: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError(f"duplicate JSON field {key!r}")
        fields[key] = value
    return fields


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def canonical_bytes(value: ProtocolModel) -> bytes:
    """Canonical UTF-8 JSON without an LF record separator."""
    model = type(value).model_validate(value)
    return _json_bytes(model.model_dump(mode="json", warnings="error"))


def encode_event_line(event: WorldEvent) -> bytes:
    """Canonical objective event JSONL record, including its final LF."""
    return canonical_bytes(event) + b"\n"


def decode[T: ProtocolModel](model: type[T], data: bytes) -> T:
    """Read a wire object, refusing ambiguous JSON and non-integer numbers."""
    try:
        value = json.loads(
            data.decode("utf-8"),
            parse_float=_reject_float,
            parse_constant=_reject_float,
            object_pairs_hook=_unique_fields,
        )
        return model.model_validate(value)
    except ValueError as exc:
        if model in (TurnSubmission, ModelTurn):
            raise InvalidTurn(str(exc)) from exc
        raise


def _ref(model: type[ProtocolModel]) -> dict[str, str]:
    return {"$ref": f"#/$defs/{model.__name__}"}


def _target_schema(kinds: tuple[TargetKind, ...]) -> dict[str, Any]:
    variants = [_ref(_TARGET_TYPES[kind]) for kind in sorted(kinds)]
    if not variants:
        return {"type": "null"}
    return variants[0] if len(variants) == 1 else {"oneOf": variants}


def _verb_params_schema(verb: EnabledVerb) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            param.name: {"type": "integer", "minimum": param.min, "maximum": param.max}
            for param in sorted(verb.params, key=attrgetter("name"))
        },
        "required": sorted(param.name for param in verb.params),
    }


def _variant(base: dict[str, Any], **properties: dict[str, Any]) -> dict[str, Any]:
    return {**base, "properties": {**base["properties"], **properties}}


def model_turn_schema(enabled_verbs: Iterable[EnabledVerb]) -> dict[str, Any]:
    """Generate the closed, identity-free JSON Schema for the world part of a turn.

    Vocabulary is the only content input. Context (whether continue is allowed)
    and cross-list named item uniqueness are checked by validate_turn_shape.
    """
    verbs = _index_verbs(enabled_verbs)
    models: list[type[ProtocolModel]] = [ModelTurn, *dict.fromkeys(_KERNEL_SHAPES.values())]
    _roots, schema = models_json_schema([(model, "validation") for model in models])
    defs = schema["$defs"]
    defs.pop("JsonValue", None)  # All parameter schemas below are closed.
    base = defs["IntentShape"]
    empty_array = {"type": "array", "maxItems": 0}
    variants = [
        _variant(
            base,
            action={"const": action},
            verb={"type": "null"},
            target=_target_schema((kind,) if kind is not None else ()),
            instruments=empty_array,
            inputs=empty_array,
            params=_ref(params),
        )
        for (action, kind), params in _KERNEL_SHAPES.items()
    ]
    variants.extend(
        _variant(
            base,
            action={"const": "act"},
            verb={"const": verb.id},
            target=_target_schema(verb.target_kinds),
            params=_verb_params_schema(verb),
        )
        for verb in verbs.values()
    )
    defs["IntentShape"] = {"oneOf": variants}

    terms = defs["Terms"]
    defs["Terms"] = {
        "oneOf": [
            _variant(terms, what=_ref(BeAtTerm), due_tick={"type": "integer", "minimum": 0}),
            _variant(
                terms,
                what={"oneOf": [_ref(GiveItemTerm), _ref(ReturnItemTerm), _ref(ContributeTerm)]},
            ),
        ],
    }
    utterance = defs["Utterance"]
    defs["Utterance"] = {
        "oneOf": [
            _variant(
                utterance,
                speech_act={"const": act},
                addressee_id=utterance["properties"]["addressee_id"]
                if act == "statement"
                else {"type": "string"},
                terms=_ref(Terms) if act == "propose" else {"type": "null"},
                in_reply_to={"type": "string" if act in ("accept", "refuse") else "null"},
            )
            for act in get_args(SpeechAct)
        ],
    }
    root = defs.pop("ModelTurn")
    return {"$comment": f"World–agent protocol {SCHEMA_VERSION}", "$defs": defs, **root}


def action_schema_sha256(enabled_verbs: Iterable[EnabledVerb]) -> str:
    """SHA-256 of the generated schema's canonical JSON bytes."""
    return sha256(_json_bytes(model_turn_schema(enabled_verbs))).hexdigest()
