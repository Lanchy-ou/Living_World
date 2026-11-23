"""Immutable day entries, resident-local evidence references and rendered fragments."""

from typing import Literal

from living_island.agents.v2.calls.contracts import digest, json_bytes
from living_island.agents.v2.calls.guard import Part, Ref
from living_island.agents.v2.calls.journal import Fact
from living_island.memory.v2.projections import RevisionRef
from living_island.world.v2.protocol import HeardUtterance, ObservationPhase, ReportKind


class FeedbackRef(Fact):
    kind: Literal["feedback"] = "feedback"
    intent_id: str


class UtteranceFeedbackRef(Fact):
    kind: Literal["utterance_feedback"] = "utterance_feedback"
    utterance_id: str | None  # Failed speech has no issued ID.


class HeardRef(Fact):
    kind: Literal["utterance"] = "utterance"
    utterance_id: str
    speaker_id: str


class ObservedRef(Fact):
    kind: Literal["observed_action"] = "observed_action"
    intent_id: str
    phase: ObservationPhase


class EntityRef(Fact):
    kind: Literal["entity"] = "entity"
    entity_id: str


class CueRef(Fact):
    kind: Literal["cue"] = "cue"
    cue_id: str


class ReportRef(Fact):
    kind: Literal["report"] = "report"
    report_kind: ReportKind
    subject_id: str | None


class InspectionRef(Fact):
    kind: Literal["inspection"] = "inspection"
    intent_id: str


class TurnRef(Fact):
    kind: Literal["turn"] = "turn"
    turn_id: str


class DeliberateRecall(Fact):
    kind: Literal["recall"] = "recall"
    mode: Literal["deliberate"] = "deliberate"
    call_id: str


class LocalRecall(Fact):
    kind: Literal["recall"] = "recall"
    mode: Literal["recipe", "off_empty"]
    turn_id: str
    ordinal: int


type EntryRef = (
    FeedbackRef
    | UtteranceFeedbackRef
    | HeardRef
    | ObservedRef
    | EntityRef
    | CueRef
    | ReportRef
    | InspectionRef
    | TurnRef
    | DeliberateRecall
    | LocalRecall
)
type EntryType = Literal[
    "own_response",
    "action_result",
    "utterance_result",
    "heard_speech",
    "observation",
    "inspection",
    "body_change",
    "progress",
    "sleep",
    "recall",
]


class DayEntry(Fact):
    id: str
    type: EntryType
    tick: int
    text: str
    delivery_id: str | None
    ref: EntryRef
    verbatim: HeardUtterance | None = None
    about: tuple[str, ...] = ()
    member_paths: tuple[str, ...] = ()
    retrieved: RevisionRef | None = None

    @property
    def canonical(self) -> bytes:
        return json_bytes(self.model_dump(mode="json"))

    @property
    def revision(self) -> str:
        return digest(self.canonical)

    @property
    def part(self) -> Part:
        # Only the published line goes into a prompt. Structured provenance
        # and original packet positions remain available by the entry revision.
        line = f"[{self.id} | tick {self.tick} | {self.type}] {self.text}"
        source = Ref(
            kind="day_log",
            id=self.id,
            version=self.revision,
            member_path=self.member_paths[0] if self.member_paths else None,
        )
        return Part("day_log", source, line)

    @property
    def fragment_sha256(self) -> str:
        return digest(self.part.text.encode())
