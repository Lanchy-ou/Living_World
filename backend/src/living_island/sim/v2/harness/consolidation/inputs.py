"""Build both consolidation requests from the resident's confirmed, frozen input."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import cast

from living_island.agents.v2.calls.contracts import digest
from living_island.agents.v2.calls.guard import Assembly, Call, Manifest, Part, Ref
from living_island.agents.v2.context.entries import DayEntry, HeardRef
from living_island.agents.v2.context.prefix import render_memory
from living_island.agents.v2.context.working import FrozenPeriod
from living_island.memory.v2.pending import PendingPeriod
from living_island.memory.v2.projections import ResidentView
from living_island.memory.v2.provenance import HeardSpeechEntry, PerceptionEntry, SentInput


@dataclass(frozen=True)
class Choice:
    selected: tuple[str, ...]
    ignored: tuple[str, ...]


def _pending_part(period: PendingPeriod[FrozenPeriod]) -> Part:
    # A pending context is an indivisible guard candidate. The published part
    # contains precisely its resident-facing lines; typed evidence stays local.
    text = "\n".join(
        [f"Pending period {period.period_id}", *(part.text for part in period.context.parts)]
    )
    source = Ref(kind="pending_period", id=period.period_id, version=digest(text.encode()))
    return Part("pending_periods", source, text)


def _witnesses(
    owner: str, entries: Sequence[DayEntry]
) -> Iterator[HeardSpeechEntry | PerceptionEntry]:
    for entry in entries:
        if entry.type == "own_response" or entry.type == "recall":
            continue
        # All other DL-02 entry types are written by DayLog.deliver.
        delivery = cast(str, entry.delivery_id)
        if entry.type == "heard_speech":
            heard = cast(HeardRef, entry.ref)
            yield HeardSpeechEntry(
                owner, entry.id, delivery, entry.member_paths, heard.utterance_id, heard.speaker_id
            )
        else:
            yield PerceptionEntry(
                owner, entry.id, delivery, entry.member_paths, entry.type, frozenset(entry.about)
            )


@dataclass(frozen=True)
class FixedInput:
    period: FrozenPeriod
    pending: tuple[PendingPeriod[FrozenPeriod], ...]
    view: ResidentView
    base_version: int
    mechanical_ids: frozenset[str]

    def select(self, read: Sequence[str]) -> Choice:
        indexed = {revision.ref.id for revision in self.view.records}
        selected: dict[str, None] = {}
        ignored = []
        for position, key in enumerate(read):
            if position < 60 and key in indexed and key not in selected:
                selected[key] = None
            else:
                ignored.append(key)
        return Choice(tuple(selected), tuple(ignored))

    def assembly(self, choice: Choice | None = None) -> Assembly:
        """None builds selection. An empty successful choice still adds mechanical inputs."""
        parts = list(self.period.parts)
        days = [i for i, part in enumerate(parts) if part.source.kind == "day_log"]
        pending_start = len(parts)
        parts.extend(_pending_part(period) for period in self.pending)
        pending = range(pending_start, len(parts))

        version = str(self.base_version)
        parts.append(
            Part(
                "index_header",
                Ref(kind="index", id=self.period.prefix.period_id, version=version),
                "Memory index:",
            )
        )
        indexed = {r.ref.id: r for r in self.view.records}
        parts.extend(
            Part("index", Ref(kind="index", id=r.ref.id, version=version), r.index_line)
            for r in self.view.records
        )

        # The fixed morning prefix can already carry a full base revision.
        # An older revision of the same ID still needs its current projection.
        shown = {memory.revision for memory in self.period.prefix.memories}
        for revision in self.view.records:
            mechanical = choice is not None and revision.ref.id in self.mechanical_ids
            open_commitment = revision.record.kind == "commitment" and "open" in revision.flags
            if revision.ref not in shown and (
                mechanical or open_commitment or revision.record.needs_review
            ):
                shown.add(revision.ref)
                fragment = render_memory(revision).part
                source = fragment.source
                if mechanical:
                    source = source.model_copy(update={"kind": "mechanical_record"})
                parts.append(Part("required_records", source, fragment.text))

        optional_start = len(parts)
        if choice is not None:
            for key in choice.selected:
                if indexed[key].ref not in shown:
                    fragment = render_memory(indexed[key]).part
                    parts.append(Part("selected_records", fragment.source, fragment.text))
        order = (*reversed(range(optional_start, len(parts))), *pending, *days)
        return Assembly(tuple(parts), order, frozenset(range(len(parts))).difference(order))

    @staticmethod
    def sent_pending(manifest: Manifest) -> tuple[str, ...]:
        return tuple(e.source.id for e in manifest.entries if e.source.kind == "pending_period")

    def sent(self, call: Call, manifest: Manifest) -> SentInput:
        """The validator receives authorizations from the dispatched change set only."""
        indexed = {r.ref.id: r.ref for r in self.view.records}
        full = tuple(
            memory.revision
            for memory in self.period.prefix.memories
            if indexed.get(memory.revision.id) == memory.revision
        ) + tuple(
            indexed[e.source.id]
            for section in manifest.sections
            if section.section in ("required_records", "selected_records")
            for e in section.entries
        )
        sent_index = tuple(
            indexed[e.source.id]
            for section in manifest.sections
            if section.section == "index"
            for e in section.entries
        )
        day_ids = {e.source.id for e in manifest.entries if e.source.kind == "day_log"}
        entries = [entry for entry in self.period.entries if entry.id in day_ids]
        pending = self.sent_pending(manifest)
        for period in self.pending:
            if period.period_id in pending:
                entries.extend(period.context.entries)
        return SentInput(
            call.resident_id,
            call.call_id,
            full,
            sent_index,
            tuple(_witnesses(call.resident_id, entries)),
        )
