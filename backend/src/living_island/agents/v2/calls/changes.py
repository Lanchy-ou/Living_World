"""Change-set wire vocabulary. Store authority and per-operation verdicts belong to MF."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel
from pydantic.json_schema import SkipJsonSchema


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Observed(Output):
    kind: Literal["observed"]
    entry_id: str


class Told(Output):
    kind: Literal["told"]
    utterance_id: str
    speaker_id: str


class Inferred(Output):
    kind: Literal["inferred"]
    memory_ids: list[str]
    call_id: str


class Innate(Output):
    kind: Literal["innate"]


type Source = Observed | Told | Inferred | Innate


class AboutTick(Output):
    start: int = Field(alias="from")
    to: int


class NewRecord(Output):
    kind: str
    gist: str
    text: str | None = None
    content: dict[str, JsonValue]
    about_tick: AboutTick | None = None
    sources: list[Source]
    confidence: int


class Operation(Output):
    op_id: str


class Add(Operation):
    op: Literal["add"]
    ref: str
    record: NewRecord


class Merge(Operation):
    op: Literal["merge"]
    ids: list[str]
    ref: str
    record: NewRecord


class Update(Operation):
    op: Literal["update"]
    id: str
    gist: str
    text: str | None = None
    content: dict[str, JsonValue] | None = None
    about_tick: AboutTick | None = None
    add_sources: list[Source] = Field(default_factory=list)


class Supersede(Operation):
    op: Literal["supersede"]
    id: str
    by: str


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
    trait_id: str
    delta: int
    sources: list[Source]


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
    ]
