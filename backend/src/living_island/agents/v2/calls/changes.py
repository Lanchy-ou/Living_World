"""Change-set wire vocabulary. Store authority and per-operation verdicts belong to MF."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel
from pydantic.json_schema import SkipJsonSchema

from living_island.memory.v2.records import AboutTick as MemoryTickRange
from living_island.memory.v2.records import Belief, Episodic, SkillHypothesis


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Observed(Output):
    kind: Literal["observed"]
    entry_id: str = Field(
        description=(
            "ID of a sent perception entry whose displayed observed witness keys overlap the "
            "record's subject keys. A general belief has no key and cannot use this source."
        ),
        examples=["d:p:ella:1:12"],
    )


class Told(Output):
    kind: Literal["told"]
    utterance_id: str = Field(description="Utterance ID from a sent heard-speech entry.")
    speaker_id: str = Field(description="Speaker ID on that same sent entry.")


class Inferred(Output):
    kind: Literal["inferred"]
    memory_ids: list[str] = Field(
        description="One or more sent memory IDs or new refs from earlier accepted operations.",
        examples=[["m:ella:3", "new:1"]],
    )
    call_id: str = Field(
        description="Copy the exact Change-set call ID shown in this request.",
        examples=["p:ella:1:101:change_set"],
    )


class Innate(Output):
    kind: Literal["innate"]


type Source = Observed | Told | Inferred | SkipJsonSchema[Innate]

NewRef = Annotated[
    str,
    Field(
        description="Unique local ref in new:<n> format, with digits after the colon.",
        examples=["new:1"],
    ),
]
Gist = Annotated[
    str,
    Field(
        description="Single-line summary of at most 160 characters.",
        examples=["I drank beside the spring."],
    ),
]


class AboutTick(Output):
    start: int = Field(alias="from")
    to: int


class RecordFields(Output):
    gist: Gist
    text: str | None = Field(default=None, description="Optional text, at most 2000 characters.")
    sources: list[Source] = Field(
        description="Use observed, told or inferred evidence from this request."
    )
    confidence: int = Field(
        description=(
            "Integer 0–4, within the source confidence caps; speech-derived records cap at 3."
        ),
        examples=[2],
    )


class NewRecord(RecordFields):
    """Receive each operation intact so MF can assign its original verdict."""

    kind: str
    content: dict[str, JsonValue]
    about_tick: AboutTick | None = None


class EpisodicRecord(RecordFields):
    kind: Literal["episodic"]
    content: Episodic
    about_tick: MemoryTickRange = Field(
        description="Inclusive range of the episode's ticks, even for a single tick.",
        examples=[{"from": 20, "to": 20}],
    )


class BeliefRecord(RecordFields):
    kind: Literal["belief"]
    content: Belief
    about_tick: MemoryTickRange | None = Field(
        default=None, description="Required for dated beliefs. Omit or use null for stable beliefs."
    )

    # The stance is nested in content. The branches constrain the same typed
    # fields without duplicating the belief kind in the outer discriminator.
    model_config = ConfigDict(
        json_schema_extra={
            "oneOf": [
                {
                    "properties": {
                        "content": {"properties": {"stance": {"const": "dated"}}},
                        "about_tick": {"type": "object"},
                    },
                    "required": ["about_tick"],
                },
                {
                    "properties": {
                        "content": {"properties": {"stance": {"const": "stable"}}},
                        "about_tick": {"type": "null"},
                    },
                },
                {"properties": {"content": {"properties": {"stance": {"const": "guess"}}}}},
            ],
        }
    )


class SkillContent(Output):
    hypothesis: SkillHypothesis
    status: Literal["active", "doubtful", "refuted"]


class SkillRecord(RecordFields):
    kind: Literal["skill"]
    content: SkillContent = Field(description="Code supplies the skill's evidence.")


type Addition = Annotated[EpisodicRecord | BeliefRecord | SkillRecord, Field(discriminator="kind")]
type MergedRecord = Annotated[EpisodicRecord | BeliefRecord, Field(discriminator="kind")]


class Operation(Output):
    op_id: str = Field(description="Operation ID unique within this change set.")


class Add[RecordT](Operation):
    op: Literal["add"]
    ref: NewRef
    record: RecordT


class Merge[RecordT](Operation):
    op: Literal["merge"]
    ids: list[str]
    ref: NewRef
    record: RecordT


class Update(Operation):
    op: Literal["update"]
    id: str
    gist: Gist
    text: str | None = None
    content: dict[str, JsonValue] | None = Field(
        default=None,
        description=(
            "Patch only fields permitted for that kind. Social: impression and trust, "
            "with trust at most one step. Skill: status only. Intentions are read-only."
        ),
        examples=[{"impression": "Kept the promise."}, {"status": "doubtful"}],
    )
    about_tick: AboutTick | None = Field(
        default=None, description="Omit this field entirely for social or skill updates."
    )
    add_sources: list[Source] = Field(
        default_factory=list,
        description="Omit this field entirely for social or skill updates, even when empty.",
    )


class Supersede(Operation):
    op: Literal["supersede"]
    id: str
    by: str = Field(
        description="Distinct, same-kind full sent record ID or ref from an earlier accepted op.",
        examples=["m:ella:4", "new:1"],
    )


class Confidence(Operation):
    op: Literal["confidence"]
    id: str
    to: int


class ReviewDone(Operation):
    op: Literal["review_done"]
    id: str


class Forget(Operation):
    op: Literal["forget"]
    id: str


class CommitmentStatus(Operation):
    op: Literal["commitment_status"]
    id: str
    status: Literal["kept", "broken", "expired"]
    note: str


class Trait(Operation):
    op: Literal["trait"]
    trait_id: str = Field(
        description="Trait ID in the full personality record, used at most once in this set.",
        examples=["caution"],
    )
    delta: int = Field(
        description="One step (-1 or 1) within the trait's min and max.", examples=[1]
    )
    sources: list[Source] = Field(description="Evidence for the change. At least one source.")


type KnownOperation[AddT, MergeT] = Annotated[
    Add[AddT]
    | Merge[MergeT]
    | Update
    | Supersede
    | Confidence
    | ReviewDone
    | Forget
    | CommitmentStatus
    | Trait,
    Field(discriminator="op"),
]


class InvalidOperation(RootModel[dict[str, JsonValue]]):
    """An invalid operation object retained for MF's individual format verdict."""


class ChangeSetOutput(Output):
    # Only closed operations are offered on the wire. On return, a malformed
    # object cannot discard its independent siblings (MF §3.5). The harness
    # supplies base_version from the frozen store.
    ops: list[
        Annotated[
            KnownOperation[NewRecord, NewRecord] | SkipJsonSchema[InvalidOperation],
            Field(union_mode="left_to_right"),
        ]
    ] = Field(description="Operations in application order. The harness supplies base_version.")


class ChangeSetSchema(Output):
    """The output contract shown to the model. MF still validates each returned operation."""

    ops: list[KnownOperation[Addition, MergedRecord]] = Field(
        description="Operations in application order. The harness supplies base_version."
    )
