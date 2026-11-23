"""Delivered witnesses, immutable source bindings and post-commit inspection flags."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass as validated_dataclass

from living_island.memory.v2.projections import RevisionRef
from living_island.memory.v2.records import (
    Belief,
    Content,
    Episodic,
    Inferred,
    Innate,
    Look,
    MemoryRecord,
    Observed,
    Skill,
    Social,
    Source,
    Told,
)
from living_island.memory.v2.store import Snapshot


@dataclass(frozen=True)
class DeliveredEntry:
    owner_id: str
    id: str
    delivery_id: str
    member_paths: Annotated[tuple[str, ...], Field(min_length=1)]


@validated_dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class PerceptionEntry(DeliveredEntry):
    type: Literal[
        "action_result",
        "utterance_result",
        "observation",
        "inspection",
        "body_change",
        "progress",
        "sleep",
    ]
    about: frozenset[str]


@validated_dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HeardSpeechEntry(DeliveredEntry):
    utterance_id: str
    speaker_id: str


@dataclass(frozen=True)
class SentInput:
    """The harness supplies refs and eligible delivered members from the actual sent bytes."""

    owner_id: str
    call_id: str
    full: tuple[RevisionRef, ...] = ()
    index: tuple[RevisionRef, ...] = ()
    entries: tuple[PerceptionEntry | HeardSpeechEntry, ...] = ()


@dataclass(frozen=True)
class BoundRevision:
    ref: RevisionRef
    record: MemoryRecord


@dataclass(frozen=True)
class SourceBinding:
    source: Source
    revisions: tuple[RevisionRef, ...] = ()
    entry_id: str | None = None
    delivery_id: str | None = None
    member_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceEvidence:
    default_confidence: int
    speech_derived: bool
    provenance_error: bool
    source_kind_error: bool
    bindings: tuple[SourceBinding, ...]


def subject_keys(content: Content) -> set[str]:
    """MF §3.5 subject keys, using only fields of the typed record."""
    match content:
        case Belief(subject=subject):
            if subject.kind == "general" or subject.ref is None:
                return set()
            prefix = "archetype" if subject.kind == "kind_of_thing" else subject.kind
            return {f"{prefix}:{subject.ref}"}
        case Episodic(participants=participants, place=place):
            keys = {f"resident:{resident}" for resident in participants}
            if place is not None:
                keys.add(f"place:{place.x},{place.y}")
            return keys
        case Skill(hypothesis=hypothesis):
            keys = {f"verb:{hypothesis.verb}"}
            looks = [*hypothesis.instruments, *(i.look for i in hypothesis.inputs)]
            if isinstance(hypothesis.target, Look):
                looks.append(hypothesis.target)
            for look in looks:
                if look.archetype_id is not None:
                    keys.add(f"archetype:{look.archetype_id}")
                if look.material_id is not None:
                    keys.add(f"material:{look.material_id}")
            return keys
        case Social(about=resident):
            return {f"resident:{resident}"}
        case _:
            return set()


def _delivery_binding(source: Source, entry: DeliveredEntry) -> SourceBinding:
    return SourceBinding(
        source, entry_id=entry.id, delivery_id=entry.delivery_id, member_paths=entry.member_paths
    )


def confidence_allowed(confidence: int, sources: Sequence[Source], speech_derived: bool) -> bool:
    return confidence < 4 or (
        not speech_derived and any(s.kind in ("observed", "innate") for s in sources)
    )


def bind_sources(
    sources: Sequence[Source],
    content: Content | None,
    sent: SentInput,
    cited: Mapping[str, BoundRevision],
    trust: Mapping[str, int],
) -> SourceEvidence:
    """Check newly written sources. The caller resolves authorized input and producer refs."""
    # A forbidden destination can still independently violate the confidence cap.
    subjects = subject_keys(content) if content is not None else set()
    perceptions = {
        e.id: e
        for e in sent.entries
        if isinstance(e, PerceptionEntry) and e.owner_id == sent.owner_id
    }
    utterances = {
        (e.utterance_id, e.speaker_id): e
        for e in sent.entries
        if isinstance(e, HeardSpeechEntry) and e.owner_id == sent.owner_id
    }
    bindings: list[SourceBinding] = []
    defaults: list[int] = []
    speech_derived = False
    provenance_error = False
    source_kind_error = False
    for source in sources:
        match source:
            case Observed(entry_id=key):
                entry = perceptions.get(key)
                if entry is None:
                    provenance_error = True
                elif entry.type == "utterance_result":
                    # An own utterance witnesses only the speaking act. No change-set
                    # subject denotes that act (mechanical commitment writes are separate).
                    source_kind_error = True
                elif subjects.isdisjoint(entry.about):
                    provenance_error = True
                else:
                    bindings.append(_delivery_binding(source, entry))
                defaults.append(3)
            case Told(utterance_id=utterance, speaker_id=speaker):
                speech_derived = True
                heard = utterances.get((utterance, speaker))
                if heard is None:
                    provenance_error = True
                else:
                    bindings.append(_delivery_binding(source, heard))
                # First contact creates a social record at neutral trust (MM §3.3).
                defaults.append((0, 1, 1, 2, 3)[trust.get(speaker, 2)])
            case Inferred(memory_ids=ids, call_id=call):
                direct = [
                    cited[key]
                    for key in ids
                    if key in cited and cited[key].record.owner_id == sent.owner_id
                ]
                speech_derived |= any(revision.record.speech_derived for revision in direct)
                if len(direct) != len(ids) or call != sent.call_id:
                    provenance_error = True
                else:
                    defaults.append(min(revision.record.confidence for revision in direct))
                    bindings.append(SourceBinding(source, tuple(r.ref for r in direct)))
            case Innate():
                # Run-start confidence is defined, but a model cannot write this source.
                defaults.append(4)
                provenance_error = True
    confidence = max(defaults, default=0)
    if not confidence_allowed(confidence, sources, speech_derived):
        confidence = 3
    return SourceEvidence(
        confidence, speech_derived, provenance_error, source_kind_error, tuple(bindings)
    )


@dataclass(frozen=True)
class RelabelFlag:
    flagged: RevisionRef
    overlaps: tuple[RevisionRef, ...]
    shared_keys: tuple[str, ...]
    store_version: int
    change_set_call_id: str


def relabel_flags(
    snapshot: Snapshot, created_ids: Iterable[str], call_id: str
) -> tuple[RelabelFlag, ...]:
    """Compute inspection sidecars from the committed store (including any rebase)."""
    created = set(created_ids)
    records = snapshot.records()  # Stable ID order; includes retained history and archived records.
    speech = [
        (record.id, subject_keys(record.content))
        for record in records
        if record.speech_derived and not record.history and not record.archived
    ]
    flags = []
    for record in records:
        if record.id not in created or record.speech_derived:
            continue
        keys = subject_keys(record.content)
        overlaps = [(key, keys & other) for key, other in speech if not keys.isdisjoint(other)]
        if overlaps:
            flags.append(
                RelabelFlag(
                    snapshot.ref(record.id),
                    tuple(snapshot.ref(key) for key, _ in overlaps),
                    tuple(sorted({key for _, common in overlaps for key in common})),
                    snapshot.version,
                    call_id,
                )
            )
    return tuple(flags)
