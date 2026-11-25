"""Change-set wire vocabulary. Store authority and per-operation verdicts belong to MF."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel
from pydantic.json_schema import SkipJsonSchema


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Observed(Output):
    kind: Literal["observed"]
    entry_id: str = Field(
        description="ID of a sent perception entry that directly witnesses the record's subject.",
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


class NewRecord(Output):
    kind: str = Field(
        description="Add episodic, belief or skill records. Merge only episodic or belief records.",
        examples=["episodic", "belief", "skill"],
    )
    gist: Gist
    text: str | None = Field(default=None, description="Optional text, at most 2000 characters.")
    content: dict[str, JsonValue] = Field(
        description=(
            "Use the exact fields for the record kind. Episodic: participants (resident IDs) "
            "and place (x/y coordinate or null). Belief: subject {kind, ref}, stance and topics. "
            "Subject kind is place, entity, resident, kind_of_thing or general. Place refs are "
            "strings like 38,30; general has null ref. Stance is stable, dated or guess. Topics "
            "are food, water, shelter, tools, materials, people, danger or other. Skill: "
            "hypothesis {verb, target, instruments, inputs, circumstances, expected} and status "
            "(active, doubtful or refuted). Target is a Look, {terrain}, or null. Instruments "
            "are Looks; inputs have look and quantity. A Look has nullable archetype_id and "
            "material_id and descriptors [{property_id, word}]. Circumstances is text or "
            "null and expected lists phenomenon IDs. Code fills skill evidence."
        ),
        examples=[
            {"participants": [], "place": {"x": 38, "y": 30}},
            {"subject": {"kind": "place", "ref": "38,30"}, "stance": "stable", "topics": ["water"]},
            {
                "hypothesis": {
                    "verb": "drink",
                    "target": None,
                    "instruments": [],
                    "inputs": [],
                    "circumstances": "beside a spring",
                    "expected": ["drinks"],
                },
                "status": "active",
            },
        ],
    )
    about_tick: AboutTick | None = Field(
        default=None,
        description=(
            "Inclusive tick range. Required for episodic and dated beliefs; omit for skills."
        ),
        examples=[{"from": 20, "to": 21}],
    )
    sources: list[Source] = Field(
        description="Use observed, told or inferred evidence from this request."
    )
    confidence: int = Field(
        description=(
            "Integer 0–4, within the source confidence caps; speech-derived records cap at 3."
        ),
        examples=[2],
    )


class Operation(Output):
    op_id: str = Field(description="Operation ID unique within this change set.")


class Add(Operation):
    op: Literal["add"]
    ref: NewRef
    record: NewRecord


class Merge(Operation):
    op: Literal["merge"]
    ids: list[str]
    ref: NewRef
    record: NewRecord


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
    about_tick: AboutTick | None = None
    add_sources: list[Source] = Field(default_factory=list)


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


type KnownOperation = Annotated[
    Add | Merge | Update | Supersede | Confidence | ReviewDone | Forget | CommitmentStatus | Trait,
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
            KnownOperation | SkipJsonSchema[InvalidOperation], Field(union_mode="left_to_right")
        ]
    ] = Field(description="Operations in application order. The harness supplies base_version.")
