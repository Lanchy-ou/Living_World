"""Closed wire views shared by the offline v2 exporter, analysis and inspector."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, NonNegativeInt

from living_island.agents.v2.calls.contracts import ActStep, CallKind, Selection
from living_island.agents.v2.calls.guard import Call, Manifest, Part, PreparedRecord, Ref
from living_island.agents.v2.calls.provider import Dispatch, Terminal
from living_island.agents.v2.context.entries import DayEntry
from living_island.agents.v2.context.prefix import MorningReceipt
from living_island.agents.v2.recall.attribution import ActCitations
from living_island.agents.v2.recall.sequence import RecallReceipt
from living_island.memory.v2.projections import RevisionRef as RevisionRef
from living_island.memory.v2.provenance import RelabelFlag, SourceBinding
from living_island.memory.v2.records import (
    Belief,
    Commitment,
    Episodic,
    Intention,
    MemoryRecord,
    Personality,
    Skill,
    Social,
)
from living_island.world.v2.protocol import BoundaryDelivery as BoundaryDelivery
from living_island.world.v2.protocol import TurnSubmission as TurnSubmission
from living_island.world.v2.protocol import WorldEvent as WorldEvent

type Digest = Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
type Arm = Literal["on", "off"]
type Family = Literal[
    "decisions",
    "consolidations",
    "stores",
    "deliveries",
    "revisions",
    "evidence_writes",
    "calls",
    "metrics",
    "cost",
    "time_use",
    "attempts",
]


class View(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, serialize_by_alias=True)


class Resident(View):
    resident_id: str
    profile_id: str


class PackPin(View):
    pack_id: str
    sha256: Digest


class FilePart(View):
    name: Annotated[str, Field(pattern=r"^[0-9a-f]{64}\.[0-9]+\.json$")]
    sha256: Digest
    size: Annotated[int, Field(gt=0, le=8388608)]


class ShardRef(View):
    family: Family
    id: str
    sha256: Digest
    parts: Annotated[list[FilePart], Field(min_length=1)]


class TurnRef(View):
    resident_id: str
    tick: NonNegativeInt
    turn_id: str
    shard: ShardRef


class PeriodRef(View):
    resident_id: str
    period_id: str
    boundary_tick: NonNegativeInt
    shard: ShardRef


class StoreRef(PeriodRef):
    store_version: NonNegativeInt


class CallRef(View):
    call_id: str
    call_kind: CallKind
    resident_id: str
    turn_id: str | None
    period_id: str
    tick: NonNegativeInt
    shard: ShardRef


class InspectionIndex(View):
    inspection_schema_version: Literal["ia/0.1"]
    run_id: str
    manifest_sha256: Digest
    replay_sha256: Digest
    arm: Arm
    pack_ids: list[PackPin]
    final_tick: NonNegativeInt
    residents: list[Resident]
    decisions: list[TurnRef]
    consolidations: list[PeriodRef]
    stores: list[StoreRef]
    deliveries: list[ShardRef]
    revisions: list[ShardRef]
    evidence_writes: list[ShardRef]
    calls: list[CallRef]
    metrics: ShardRef
    cost: ShardRef
    time_use: ShardRef
    attempts: ShardRef


class StoredPart(View):
    sha256: Digest
    text: str


class Attempt(View):
    dispatch: Dispatch
    terminal: Terminal | None
    raw_output_base64: str | None
    parsed_output: JsonValue
    missing_usage_reason: str | None


class Disposition(View):
    record_schema: Literal["cr/0.1"]
    authorized_cursor: str
    prepared_cursor: str | None
    attempts: list[tuple[str, str | None]]
    outcome: Literal["adopted", "abandoned", "failed", "stopped_unfit"]
    ignored: list[str]


class CallInspection(View):
    family: Literal["calls"] = "calls"
    record_schema: Literal["cr/0.1"] = "cr/0.1"
    call: Call
    call_kind: CallKind
    authorized_parts: list[Part]
    prepared: PreparedRecord | None
    full_manifest: Manifest | None
    sent_manifest: Manifest | None
    disposition: Disposition | None
    outcome: Literal["adopted", "not_adopted", "failed", "abandoned", "stopped_unfit"]
    attempts: list[Attempt]
    parts: list[StoredPart]
    requests: list[StoredPart]
    morning: MorningReceipt | None
    deliberate_recall: RecallReceipt | None
    adopted_citations: list[ActCitations]


class Stage(View):
    call_id: str
    full_tokens: int
    pressure_band: str
    pressure_text: str
    omitted: list[Ref]


class Telemetry(View):
    delivery_id: str
    awake_ticks: int
    fatigue_band: str | None
    stages: list[Stage]


class Used(View):
    record_id: str
    revision: RevisionRef
    call_id: str
    before_version: int
    after_version: int


class Citation(View):
    id: str
    act_call_id: str
    sent_part_sha256: Digest
    revision: str | None


class Fallback(View):
    used: bool
    reason: str | None
    policy_id: str | None


class DecisionRecord(View):
    record_schema: Literal["dr/0.1"]
    turn_id: str
    resident_id: str
    tick: int
    period_id: str
    reasons: list[str]
    call_ids: list[str]
    prepared_cursors: list[str]
    new_entries: list[str]
    output: ActStep | None
    valid_cites: list[str]
    invalid_cites: list[str]
    cited_parts: list[Citation]
    telemetry: Telemetry
    use_updates: list[Used]
    origin: Literal["model", "fallback"] | None
    fallback: Fallback
    submission: TurnSubmission | None
    used_memories: list[str]


class DecisionInspection(View):
    family: Literal["decisions"] = "decisions"
    record: DecisionRecord
    parts: list[StoredPart]
    calls: list[CallInspection]
    entries: list[DayEntry]
    outcome_event_ids: list[str]
    outcomes: list[WorldEvent]


class Record(MemoryRecord):
    content: Episodic | Belief | Social | Skill | Commitment | Intention | Personality


class Head(View):
    content_hash: Digest
    last_used_tick: int | None
    use_count: int


class Change(View):
    id: str
    before: Head | None
    after: Head | None


class Credit(View):
    stage: Literal["decision", "decision_after_recall"]
    turn_id: str
    call_id: str
    tick: int
    revisions: list[RevisionRef]


class Write(View):
    owner_id: str
    kind: Literal["mechanical", "change_set", "use"]
    before_version: int
    after_version: int
    store_hash: Digest
    changes: list[Change]
    blobs: dict[str, Record]
    dispatch: Credit | None
    credited: list[RevisionRef]


class Effect(View):
    op_id: str
    edits: list[Record | str]
    produced_id: str | None
    evictions: list[str]
    carried_from: list[RevisionRef]
    bindings: list[SourceBinding]


class Verdict(View):
    op_id: str | None
    result: Literal["committed", "dropped"]
    reason: str | None
    depends_on: list[str | None]


class Pending(View):
    period_id: str
    state: Literal["included", "omitted", "retained", "evicted"]


class ConsolidationRecord(View):
    record_schema: Literal["mf/0.1"]
    resident_id: str
    period_id: str
    arm: Arm
    s_tick: int
    started_tick: int
    confirming_delivery: str
    boundary_tick: int
    outcome: Literal["committed", "failed", "abandoned", "off_arm"]
    reason: str | None
    base_version: int
    result_version: int | None
    store_hash: Digest
    selection_call_id: str | None
    change_set_call_id: str | None
    selection: Selection | None
    change_set: dict[str, JsonValue] | None
    verdicts: list[Verdict]
    relabel_flags: list[RelabelFlag]
    pending: list[Pending]
    pending_after: list[str]
    closed_context: Digest | None
    effects: list[Effect]
    episodic_created: int
    write: Write | None


class ConsolidationInspection(View):
    family: Literal["consolidations"] = "consolidations"
    record: ConsolidationRecord
    parts: list[StoredPart]
    calls: list[CallInspection]


class Revision(View):
    ref: RevisionRef
    record: Record


class Revisions(View):
    family: Literal["revisions"] = "revisions"
    resident_id: str
    store_version: int
    records: list[Revision]


class StoreInspection(View):
    family: Literal["stores"] = "stores"
    resident_id: str
    period_id: str
    store_version: int
    records: list[Record]
    index_lines: list[str]
    relabel_flags: list[RelabelFlag]


class Member(View):
    delivery_id: str
    path: str
    entry_id: str | None
    entry_revision: str | None
    related_paths: list[str]


class SkillEvidence(View):
    hypothesis: RevisionRef
    intent_id: str
    actor_id: str
    delta: dict[str, int]


class Evidence(View):
    family: Literal["evidence_writes"] = "evidence_writes"
    write: Write
    members: list[Member]
    skill: SkillEvidence | None
    agreement: dict[str, JsonValue] | None


class JoinedEntry(View):
    entry: DayEntry
    event_ids: list[str]
    members: list[JsonValue]
    missing_reason: str | None


class Delivery(View):
    family: Literal["deliveries"] = "deliveries"
    packet: BoundaryDelivery
    period_id: str | None
    entries: list[JoinedEntry]


class CheckRecord(View):
    instance_id: str
    ids: list[str]
    checker: str
    date: str
    note: str


class SpeechCheck(CheckRecord):
    check: Literal["hop", "told_event"]
    verdict: Literal["carries", "different"]


class ChoiceCheck(CheckRecord):
    check: Literal["choice_link"]
    verdict: Literal["relevant", "not_relevant"]
    sent_fragment_sha256: list[Digest] = Field(min_length=1)
    source_revision_ids: list[str]
    member_ids: list[str]
    antecedent_event_ids: list[str]
    chosen_outcome_ids: list[str]


class ContradictionCheck(CheckRecord):
    check: Literal["contradiction"]
    verdict: Literal["contradicts", "consistent"]


type ContentCheck = SpeechCheck | ChoiceCheck | ContradictionCheck


class Metric(View):
    instance_id: str
    metric: str
    trace: list[str]
    value: int | float | None
    reason: str | None


class Metrics(View):
    family: Literal["metrics"] = "metrics"
    instances: list[Metric]
    content_checks: list[ContentCheck]
    checked_parts: list[StoredPart]


class Charge(View):
    call_id: str
    n: int
    input: int | None
    output: int | None
    cache_hit: int | None
    cache_miss: int | None
    latency_ms: int | None
    missing_usage_reason: str | None


class Cost(View):
    family: Literal["cost"] = "cost"
    attempts: list[Charge]


class Interval(View):
    resident_id: str
    intent_id: str
    start_tick: int
    end_tick: int | None
    event_ids: list[str]


class TimeUse(View):
    family: Literal["time_use"] = "time_use"
    intervals: list[Interval]


class Attempts(View):
    family: Literal["attempts"] = "attempts"
    events: list[WorldEvent]
    submissions: list[TurnSubmission]


type Shard = (
    DecisionInspection
    | ConsolidationInspection
    | StoreInspection
    | Revisions
    | CallInspection
    | Delivery
    | Evidence
    | Metrics
    | Cost
    | TimeUse
    | Attempts
)
