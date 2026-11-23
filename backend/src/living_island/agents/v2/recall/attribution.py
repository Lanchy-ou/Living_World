"""Attribute citations and memory use to fragments of an actual dispatch."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from living_island.agents.v2.calls.contracts import ActStep
from living_island.agents.v2.calls.guard import Call, Manifest, Ref
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.agents.v2.calls.provider import Dispatch, Returned
from living_island.agents.v2.context.entries import DayEntry
from living_island.memory.v2.projections import RevisionRef
from living_island.memory.v2.store import DecisionDispatch, MemoryStore, StoreWrite

type Credit = Callable[[DecisionDispatch, Callable[[StoreWrite], None]], StoreWrite | None]


def store_credit(store: MemoryStore) -> Credit:
    """Create the coordinator's write capability for its single-writer resident store."""

    def apply(batch: DecisionDispatch, publish: Callable[[StoreWrite], None]) -> StoreWrite | None:
        staged = MemoryStore.from_snapshot(store.snapshot, store.registry)
        write = staged.credit_dispatch(batch)
        if write is not None:
            # Journal the deterministic delta first. A failed write leaves the
            # live store at the previous snapshot, ready for the same dispatch.
            publish(write)
            store.credit_dispatch(batch)
        return write

    return apply


class SentFragment(Fact):
    source: Ref
    sha256: str
    memory_revision: RevisionRef | None


class Citation(Fact):
    id: str
    fragments: tuple[SentFragment, ...]


class ActCitations(Fact):
    turn_id: str
    call_id: str
    attempt: int
    request_sha256: str
    valid: tuple[Citation, ...]
    invalid: tuple[str, ...]


def _turn_id(call: Call) -> str:
    if call.turn_id is None:
        raise ValueError("decision dispatch requires a turn ID")
    return call.turn_id


def _sent_fragments(
    manifest: Manifest, entries: tuple[DayEntry, ...]
) -> Iterator[tuple[str, SentFragment]]:
    # A day ID can denote different content in two candidate histories. Join by
    # its immutable source ref, including the canonical entry revision.
    day = {entry.part.source: entry for entry in entries}
    for section in manifest.sections:
        for item in section.entries:
            source = item.source
            memory: RevisionRef | None
            match source:
                case Ref(kind="day_log"):
                    memory = day[source].retrieved
                case Ref(kind="memory", version=str(stamp)):
                    # Decode the revision written by context.prefix.memory_ref.
                    version, content_hash = stamp.split(":", 1)
                    memory = RevisionRef(source.id, int(version), content_hash)
                case _:
                    continue
            yield (
                section.section,
                SentFragment(source=source, sha256=item.sha256, memory_revision=memory),
            )


def bind_adopted_act(
    returned: Returned, entries: tuple[DayEntry, ...], journal: Journal
) -> ActCitations:
    """The host calls this upon adoption. The reply and its dispatch travel together."""
    act = returned.parsed
    if not isinstance(act, ActStep):
        raise ValueError("only a returned act can supply citations")
    dispatch = returned.dispatch
    by_id: dict[str, list[SentFragment]] = {}
    for _, fragment in _sent_fragments(dispatch.sent.manifest, entries):
        by_id.setdefault(fragment.source.id, []).append(fragment)
        # The same line can be cited by its day entry or by the recalled memory.
        if fragment.source.kind == "day_log" and fragment.memory_revision is not None:
            by_id.setdefault(fragment.memory_revision.id, []).append(fragment)
    result = ActCitations(
        turn_id=_turn_id(dispatch.call),
        call_id=dispatch.call.call_id,
        attempt=dispatch.n,
        request_sha256=dispatch.request_sha256,
        valid=tuple(
            Citation(id=id_, fragments=tuple(by_id[id_])) for id_ in act.cite if id_ in by_id
        ),
        invalid=tuple(id_ for id_ in act.cite if id_ not in by_id),
    )
    journal.fact(result.call_id, f"{dispatch.n}.citations", result)
    return result


class UseCredit(Fact):
    turn_id: str
    call_id: str
    dispatch_cursor: str
    credited: tuple[RevisionRef, ...]
    before_version: int
    after_version: int
    store_hash: str


def credit_dispatch(
    dispatch: Dispatch, entries: tuple[DayEntry, ...], credit: Credit, journal: Journal
) -> StoreWrite | None:
    """Apply one store batch using only the prefix and recall entries actually sent."""
    manifest = dispatch.sent.manifest
    stage = manifest.call_kind
    if stage != "decision" and stage != "decision_after_recall":
        return None
    revisions = tuple(
        fragment.memory_revision
        for section, fragment in _sent_fragments(manifest, entries)
        if section != "current_state" and fragment.memory_revision is not None
    )
    call = dispatch.call
    batch = DecisionDispatch(stage, _turn_id(call), call.call_id, call.tick, revisions)

    def publish(write: StoreWrite) -> None:
        receipt = UseCredit(
            turn_id=batch.turn_id,
            call_id=batch.call_id,
            dispatch_cursor=Journal.cursor(call.call_id, f"{dispatch.n}.dispatch"),
            credited=write.credited,
            before_version=write.before_version,
            after_version=write.after_version,
            store_hash=write.store_hash,
        )
        journal.fact(call.call_id, f"{dispatch.n}.use", receipt)

    return credit(batch, publish)


@dataclass(frozen=True)
class _CreditingJournal(Journal):
    entries: tuple[DayEntry, ...]
    credit: Credit

    def fact(self, call_id: str, slot: str, fact: Fact, *, exclusive: bool = False) -> str:
        cursor = super().fact(call_id, slot, fact, exclusive=exclusive)
        if isinstance(fact, Dispatch):
            credit_dispatch(fact, self.entries, self.credit, self)
        return cursor


def crediting_journal(journal: Journal, entries: tuple[DayEntry, ...], credit: Credit) -> Journal:
    """Observe DL-01's exclusive dispatch fact before its transport exchange."""
    return _CreditingJournal(journal.keep, journal.create, entries, credit)
