"""Decode the model-owned change-set envelope and check the authority of proposed fields."""

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from living_island.memory.v2.kinds import BUILTINS, KindRegistry, Operation
from living_island.memory.v2.records import (
    AboutTick,
    Content,
    Envelope,
    Gist,
    Innate,
    MemoryRecord,
    Model,
    Observed,
    Personality,
    Rating,
    Skill,
    SkillEvidence,
    Social,
    Text,
    Told,
    Trait,
    TraitId,
)


class Inference(Model):
    """A wire citation may name a prior producer before its local ID is bound."""

    kind: Literal["inferred"] = "inferred"
    memory_ids: Annotated[list[str], Field(min_length=1)]
    call_id: str


WireSource = Annotated[Observed | Told | Inference | Innate, Field(discriminator="kind")]
ProducerRef = Annotated[str, Field(pattern=r"^new:[0-9]+$")]
Problem = Literal["format", "authority", "source_kind"]


class _WireFields(Model):
    # Retain forbidden fields with the typed proposal for first-failure precedence.
    model_config = ConfigDict(extra="allow")


class NewRecord(_WireFields):
    kind: str
    gist: Gist
    text: Text | None = None
    content: dict[str, Any]
    about_tick: AboutTick | None = None
    sources: list[WireSource]
    confidence: Rating


class _Op(_WireFields):
    op_id: str


class Add(_Op):
    op: Literal["add"]
    ref: ProducerRef
    record: NewRecord


class Update(_Op):
    op: Literal["update"]
    id: str
    gist: Gist
    text: Text | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    about_tick: AboutTick | None = None
    add_sources: list[WireSource] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def supplied_text_is_a_string(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("a supplied update text must be a string")
        return value


class Merge(_Op):
    op: Literal["merge"]
    ids: Annotated[list[str], Field(min_length=2)]
    ref: ProducerRef
    record: NewRecord


class Supersede(_Op):
    op: Literal["supersede"]
    id: str
    by: str


class Confidence(_Op):
    op: Literal["confidence"]
    id: str
    to: Rating


class ReviewDone(_Op):
    op: Literal["review_done"]
    id: str


class Forget(_Op):
    op: Literal["forget"]
    id: str


class CommitmentStatus(_Op):
    op: Literal["commitment_status"]
    id: str
    status: Literal["kept", "broken", "expired"]
    note: str


class TraitOp(_Op):
    op: Literal["trait"]
    trait_id: TraitId
    delta: Annotated[int, Field(ge=-1, le=-1)] | Annotated[int, Field(ge=1, le=1)]
    sources: Annotated[list[WireSource], Field(min_length=1)]


Op = Annotated[
    Add
    | Update
    | Merge
    | Supersede
    | Confidence
    | ReviewDone
    | Forget
    | CommitmentStatus
    | TraitOp,
    Field(discriminator="op"),
]
_OP: TypeAdapter[Op] = TypeAdapter(Op)
_RECORD_FIELDS = (
    set(Envelope.model_fields)
    | set(Trait.model_fields)
    | {key for kind in BUILTINS for key in kind.schema.model_fields}
)


@dataclass(frozen=True)
class SubmittedOp:
    op_id: str | None
    name: str | None
    ref: str | None
    operands: tuple[str, ...]
    inferred_ids: tuple[str, ...]
    operation: Op | None
    problem: Problem | None
    new_kind: str | None
    unresolved_operands: bool = False


@dataclass(frozen=True)
class ChangeSet:
    base_version: int
    ops: tuple[SubmittedOp, ...]


class _Response(Model):
    ops: list[Any]


class ResponseFormatError(ValueError):
    """The response needs a parse retry before there are operations to stage."""


class InvalidOp(ValueError):
    def __init__(self, reason: Literal["authority", "format"]) -> None:
        self.reason = reason
        super().__init__(reason)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _identifier(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _inferred_operands(sources: object) -> tuple[str, ...]:
    if not isinstance(sources, list):
        return ()
    return tuple(
        key
        for source in sources
        if isinstance(source, dict) and source.get("kind") == "inferred"
        for key in _strings(source.get("memory_ids"))
    )


def _unresolved_inference(sources: object) -> bool:
    if not isinstance(sources, list):
        return False
    for source in sources:
        if isinstance(source, dict) and source.get("kind") == "inferred":
            ids = source.get("memory_ids")
            if not isinstance(ids, list) or not ids or len(_strings(ids)) != len(ids):
                return True
    return False


def _submitted(raw: Any) -> SubmittedOp:
    # Read the declarations even from malformed ops: earlier and later ops can depend on them.
    fields = raw if isinstance(raw, dict) else {}
    name = _identifier(fields.get("op"))
    ref = _identifier(fields.get("ref")) if name in ("add", "merge") else None
    expected = 0
    if name == "merge":
        operands = _strings(fields.get("ids"))
        members = fields.get("ids")
        expected = max(2, len(members)) if isinstance(members, list) else 2
    elif name in (
        "update",
        "confidence",
        "review_done",
        "forget",
        "commitment_status",
        "supersede",
    ):
        keys = ("id", "by") if name == "supersede" else ("id",)
        operands = tuple(fields[k] for k in keys if isinstance(fields.get(k), str))
        expected = len(keys)
    else:
        operands = ()
    new_kind = None
    if name in ("add", "merge") and isinstance(fields.get("record"), dict):
        sources = fields["record"].get("sources")
        new_kind = _identifier(fields["record"].get("kind"))
    elif name == "update":
        sources = fields.get("add_sources")
    elif name == "trait":
        sources = fields.get("sources")
    else:
        sources = None
    inferred = _inferred_operands(sources)
    try:
        operation = _OP.validate_python(raw)
    except ValidationError:
        return SubmittedOp(
            _identifier(fields.get("op_id")),
            name,
            ref,
            operands,
            inferred,
            None,
            "format",
            new_kind,
            len(operands) != expected or _unresolved_inference(sources),
        )
    extra = set(operation.model_extra or ())
    if isinstance(operation, Add | Merge):
        extra.update(operation.record.model_extra or ())
    problem: Problem | None = None
    if "speech_derived" in extra or extra - _RECORD_FIELDS:
        problem = "format"
    elif extra - {"sources"} or ("sources" in extra and name != "update"):
        problem = "authority"
    elif "sources" in extra:
        problem = "source_kind"
    return SubmittedOp(operation.op_id, name, ref, operands, inferred, operation, problem, new_kind)


def decode_change_set(raw: str | bytes, base_version: int) -> ChangeSet:
    """Parse JSON once. The caller pins the version when it freezes the request."""
    try:
        response = _Response.model_validate_json(raw)
    except ValidationError as exc:
        raise ResponseFormatError("expected a change-set response with an ops array") from exc
    return ChangeSet(base_version, tuple(_submitted(op) for op in response.ops))


def allowed_kind(registry: KindRegistry, op_name: Operation, kind: str) -> bool:
    try:
        return op_name in registry[kind].operations
    except KeyError:
        raise InvalidOp("format") from None


def _typed_content[C: Content](schema: type[C], fields: dict[str, Any]) -> C:
    try:
        return schema.model_validate(fields)
    except ValidationError:
        raise InvalidOp("format") from None


def new_content(registry: KindRegistry, record: NewRecord) -> Content:
    try:
        schema = registry[record.kind].schema
    except KeyError:
        raise InvalidOp("format") from None
    if schema is Skill:
        candidate = _typed_content(schema, {**record.content, "evidence": SkillEvidence()})
        if record.about_tick is not None or "evidence" in record.content:
            raise InvalidOp("authority")
        return candidate
    return _typed_content(schema, record.content)


def _restricted_patch[C: Content](current: C, op: Update, *, writable: set[str]) -> C:
    schema = type(current)
    mechanical = schema.model_fields.keys() - writable
    edits = {key: value for key, value in op.content.items() if key not in mechanical}
    # Unknown fields and invalid writable values are format errors, ahead of authority.
    candidate = _typed_content(schema, {**dict(current), **edits}) if edits else current
    if mechanical & op.content.keys() or {"about_tick", "add_sources"} & op.model_fields_set:
        raise InvalidOp("authority")
    return candidate


def update_content(registry: KindRegistry, current: MemoryRecord, op: Update) -> Content:
    previous = current.content
    if isinstance(previous, Social):
        social = _restricted_patch(previous, op, writable={"impression", "trust"})
        if abs(social.trust - previous.trust) > 1:
            raise InvalidOp("authority")
        return social
    if isinstance(previous, Skill):
        return _restricted_patch(previous, op, writable={"status"})
    if not op.content:
        return previous
    return _typed_content(registry[current.kind].schema, {**dict(previous), **op.content})


def trait_value(personality: Personality, op: TraitOp) -> int:
    trait = next(t for t in personality.traits if t.trait_id == op.trait_id)
    value = trait.value + op.delta
    if not trait.min <= value <= trait.max:
        raise InvalidOp("format")
    return value
