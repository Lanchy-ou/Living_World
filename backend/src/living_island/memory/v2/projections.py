"""Resident readers receive only these detached values, including for index and recall."""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import SerializeAsAny

from .records import Envelope, MemoryRecord, Model


@dataclass(frozen=True)
class RevisionRef:
    id: str
    store_version: int
    content_hash: str


class ResidentRecord(Envelope):
    content: SerializeAsAny[Model]


@dataclass(frozen=True)
class ProjectedRevision:
    ref: RevisionRef
    record: ResidentRecord
    flags: tuple[str, ...]

    @property
    def index_line(self) -> str:
        record = self.record
        flags = ",".join(self.flags) or "-"
        return f"{record.id} | {record.kind} | c{record.confidence} | {flags} | {record.gist}"


def _project(ref: RevisionRef, record: MemoryRecord, links: Mapping[str, str]) -> ProjectedRevision:
    gist, content = record.content.resident_fields(record.gist, links)
    fields = {name: getattr(record, name) for name in Envelope.model_fields}
    fields["gist"] = gist
    visible = ResidentRecord.model_construct(**fields, content=content)
    flags = list(record.content.flags())
    if record.needs_review:
        flags.append("needs_review")
    if record.history:
        flags.append("superseded")
    return ProjectedRevision(ref, visible.model_copy(deep=True), tuple(sorted(flags)))


@dataclass(frozen=True)
class ResidentView:
    """ID-ordered records for prefix/recall/consolidation and the separate working intention."""

    records: tuple[ProjectedRevision, ...]
    current_intention: ProjectedRevision | None

    def index(self) -> tuple[str, ...]:
        return tuple(revision.index_line for revision in self.records)

    def live(self) -> tuple[ProjectedRevision, ...]:
        return tuple(revision for revision in self.records if "superseded" not in revision.flags)

    def history(self) -> tuple[ProjectedRevision, ...]:
        return tuple(revision for revision in self.records if "superseded" in revision.flags)
