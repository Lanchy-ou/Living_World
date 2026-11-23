"""Measure and retain full, candidate and floor requests before any dispatch."""

from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter
from typing import Literal, Self

from living_island.agents.llm import provider as p3

from .contracts import CallKind, Contract, digest
from .journal import Fact, Journal
from .wire import (
    FRAMING_VERSION,
    MODEL_WINDOW,
    NOTICE,
    RESERVE,
    WINDOW,
    WORDING_VERSION,
    Wire,
    frame,
    part_tokens,
)


class Call(Fact):
    call_id: str
    resident_id: str
    tick: int
    period_id: str
    turn_id: str | None = None
    consolidation_period: str | None = None


class Ref(Fact):
    kind: Literal[
        "template",
        "schema",
        "memory",
        "day_log",
        "current_state",
        "pending_period",
        "index",
        "query",
        "notice",
        "pressure",
        "mechanical_record",
    ]
    id: str
    version: str | None
    member_path: str | None = None


@dataclass(frozen=True)
class Part:
    section: str
    source: Ref
    text: str


@dataclass(frozen=True)
class Assembly:
    """Indices address the ordered user parts, including revisions of the same ID.
    The pressure slot is a gap between parts (before part i, or after the last).
    Omission order and protected positions form a partition supplied by the assembler.
    """

    parts: tuple[Part, ...]
    omission_order: tuple[int, ...]
    protected: frozenset[int]
    pressure_at: int | None = None

    def __post_init__(self) -> None:
        positions = (*self.omission_order, *self.protected)
        if sorted(positions) != list(range(len(self.parts))):
            raise ValueError("omission order and floor must partition the parts")
        if self.pressure_at is not None and not 0 <= self.pressure_at <= len(self.parts):
            raise ValueError("pressure slot is outside the assembly")

    @classmethod
    def decision(
        cls,
        parts: tuple[Part, ...],
        *,
        prefix_memories: tuple[int, ...],
        day_log: tuple[int, ...],
        pressure_at: int,
        recall_entries: frozenset[int] = frozenset(),
    ) -> Self:
        """The assembler identifies log and selection positions in their original order.
        This turn's deliberate/empty recall remains protected even in a long log.
        """
        order = tuple(i for i in day_log[:-20] if i not in recall_entries) + prefix_memories[::-1]
        return cls(parts, order, frozenset(range(len(parts))).difference(order), pressure_at)


class Entry(Fact):
    source: Ref
    sha256: str
    tokens: int


class Section(Fact):
    section: str
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class Rendered:
    section: str
    entry: Entry
    text: str


class Pressure(Fact):
    kind: Literal["pressure"] = "pressure"
    counter_id: str = p3.COUNTER_ID
    counter_version: str = p3.COUNTER_VERSION
    wording_version: str = WORDING_VERSION
    counted: int
    window: int = WINDOW
    band: str
    text: str


def pressure(counted: int) -> Pressure:
    for limit, band, words in (
        (5, "clear", "clear"),
        (15, "busy", "busy"),
        (30, "crowded", "crowded"),
        (50, "heavy", "heavy and crowded"),
    ):
        if 100 * counted < limit * WINDOW:
            return Pressure(counted=counted, band=band, text=f"Your thoughts feel {words}.")
    return Pressure(counted=counted, band="overloaded", text="Your thoughts feel overloaded.")


class Manifest(Fact):
    manifest_schema: Literal["cm/0.1"] = "cm/0.1"
    call_kind: CallKind
    resident_id: str
    tick: int
    period_id: str
    sections: tuple[Section, ...]
    derived: tuple[Pressure, ...]
    tokens_total: int

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(entry for section in self.sections for entry in section.entries)


class Candidate(Fact):
    manifest: Manifest
    wire_sha256: str
    omitted: tuple[Ref, ...]


class Settings(Fact):
    provider: str = "deepseek-responses"
    model: str = p3.MODEL_ID
    model_version: str = p3.COUNTER_MODEL_VERSION
    endpoint: str = "https://api.deepseek.com/responses"
    prompt_version: str
    prompt_sha256: str
    schema_sha256: str
    wire_adapter_version: str = FRAMING_VERSION
    max_output_tokens: int = RESERVE
    temperature: None = None  # Provider default, omitted in the pinned Responses mapping.
    model_window: int = MODEL_WINDOW
    counter_id: str = p3.COUNTER_ID
    counter_version: str = p3.COUNTER_VERSION
    counter_source_sha256: str = "fdaf256a6f4558bf8722af2e744e10a816f312248768d3278b988820a36146bc"
    tokenizer_sha256: str = p3.COUNTER_TOKENIZER_SHA256


class PreparedRecord(Fact):
    call: Call
    settings: Settings
    candidates: tuple[Candidate, ...]  # Index zero is full. No sent fact until dispatch.
    floor_candidate: int
    admitted_candidate: int | None
    omission_order: tuple[int, ...]
    pressure_at: int | None
    reason: Literal["stopped_unfit"] | None


@dataclass(frozen=True)
class Admitted:
    candidate: Candidate
    wire: Wire


@dataclass(frozen=True)
class Prepared:
    record: PreparedRecord
    cursor: str
    contract: Contract
    admitted: Admitted | None


def _render(part: Part, journal: Journal) -> Rendered:
    entry = Entry(
        source=part.source, sha256=journal.blob(part.text.encode()), tokens=part_tokens(part.text)
    )
    return Rendered(part.section, entry, part.text)


def prepare(call: Call, contract: Contract, assembly: Assembly, journal: Journal) -> Prepared:
    with_pressure = contract.kind in ("decision", "decision_after_recall", "morning")
    if with_pressure != (assembly.pressure_at is not None):
        raise ValueError("pressure slot does not match this call kind")
    if contract.kind in ("morning", "recall") and assembly.omission_order:
        raise ValueError("the whole index request is protected")
    parts = assembly.parts
    settings = Settings(
        prompt_version=contract.prompt_version,
        prompt_sha256=digest(contract.instructions.encode()),
        schema_sha256=digest(contract.schema),
    )
    system = _render(
        Part(
            "system",
            Ref(kind="template", id=contract.kind, version=contract.prompt_version),
            contract.instructions,
        ),
        journal,
    )
    schema = _render(
        Part(
            "schema",
            Ref(kind="schema", id=contract.kind, version=settings.schema_sha256),
            contract.schema.decode(),
        ),
        journal,
    )
    derived: tuple[Pressure, ...] = ()
    rendered = [(i, _render(part, journal)) for i, part in enumerate(parts)]
    if assembly.pressure_at is not None:
        bare = frame(
            contract.kind,
            contract.instructions,
            contract.schema,
            "\n".join(part.text for part in parts),
        )
        cue = pressure(bare.counted)
        derived = (cue,)
        line = Part(
            "current_state", Ref(kind="pressure", id="pressure", version=WORDING_VERSION), cue.text
        )
        rendered.insert(assembly.pressure_at, (-1, _render(line, journal)))
    candidates: list[Candidate] = []
    admitted: Admitted | None = None
    admitted_index = None
    order = assembly.omission_order
    notice_part = Part("notice", Ref(kind="notice", id="omission", version="notice/0.1"), NOTICE)
    notice = [_render(notice_part, journal)] if order else []
    removed: set[int] = set()
    count = 0
    while True:
        visible = notice.copy() if count else []
        visible.extend(part for index, part in rendered if index not in removed)
        wire = frame(
            contract.kind,
            contract.instructions,
            contract.schema,
            "\n".join(part.text for part in visible),
        )
        manifest = Manifest(
            call_kind=contract.kind,
            resident_id=call.resident_id,
            tick=call.tick,
            period_id=call.period_id,
            sections=tuple(
                Section(section=section, entries=tuple(part.entry for part in group))
                for section, group in groupby((system, *visible, schema), attrgetter("section"))
            ),
            derived=derived,
            tokens_total=wire.counted,
        )
        candidate = Candidate(
            manifest=manifest,
            wire_sha256=journal.blob(wire.body),
            omitted=tuple(parts[index].source for index in order[:count]),
        )
        candidates.append(candidate)
        if admitted is None and wire.counted <= WINDOW:
            admitted = Admitted(candidate, wire)
            admitted_index = len(candidates) - 1
        if count == len(order):
            break
        # Even if the full/first fitting candidate is admitted, measure the floor.
        if admitted is not None:
            removed.update(order[count:])
            count = len(order)
        else:
            removed.add(order[count])
            count += 1
    if candidates[-1].manifest.tokens_total > WINDOW:
        admitted = None
        admitted_index = None
    record = PreparedRecord(
        call=call,
        settings=settings,
        candidates=tuple(candidates),
        floor_candidate=len(candidates) - 1,
        admitted_candidate=admitted_index,
        omission_order=order,
        pressure_at=assembly.pressure_at,
        reason="stopped_unfit" if admitted is None else None,
    )
    return Prepared(record, journal.fact(call.call_id, "prepared", record), contract, admitted)


def rebuild(candidate: Candidate, settings: Settings, resolved_parts: tuple[bytes, ...]) -> Wire:
    """Replay from this manifest's parts, resolved in order by the audit owner."""
    if (settings.counter_id, settings.counter_version) != (p3.COUNTER_ID, p3.COUNTER_VERSION):
        raise p3.InputCounterUnavailable
    manifest = candidate.manifest
    entries = manifest.entries
    for entry, raw in zip(entries, resolved_parts, strict=True):
        if digest(raw) != entry.sha256 or part_tokens(raw.decode()) != entry.tokens:
            raise ValueError("rendered part differs")
    instructions_bytes, *user, shape = resolved_parts
    instructions = instructions_bytes.decode()
    expected = Settings(
        prompt_version=f"{manifest.call_kind}/0.1",
        prompt_sha256=digest(instructions_bytes),
        schema_sha256=digest(shape),
    )
    if expected != settings:
        raise ValueError("request settings differ")
    texts = [
        (entry.source.kind, data.decode()) for entry, data in zip(entries[1:-1], user, strict=True)
    ]
    if (
        manifest.call_kind in ("decision", "decision_after_recall", "morning")
        and not candidate.omitted
    ):
        bare = "\n".join(text for kind, text in texts if kind != "pressure")
        cue = pressure(frame(manifest.call_kind, instructions, shape, bare).counted)
        if manifest.derived != (cue,) or [text for kind, text in texts if kind == "pressure"] != [
            cue.text
        ]:
            raise ValueError("full request pressure differs")
    wire = frame(manifest.call_kind, instructions, shape, "\n".join(text for _, text in texts))
    if digest(wire.body) != candidate.wire_sha256 or wire.counted != manifest.tokens_total:
        raise ValueError("rebuilt request differs")
    return wire
