"""Stage each consolidation operation atomically against a single frozen resident snapshot."""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from living_island.memory.v2.capacity import plan_capacity
from living_island.memory.v2.kinds import KindRegistry
from living_island.memory.v2.projections import RevisionRef
from living_island.memory.v2.provenance import (
    BoundRevision,
    RelabelFlag,
    SentInput,
    SourceBinding,
    bind_sources,
    confidence_allowed,
    relabel_flags,
)
from living_island.memory.v2.records import (
    Belief,
    Commitment,
    Content,
    Inferred,
    MemoryRecord,
    Personality,
    Social,
    Source,
    TraitChange,
)
from living_island.memory.v2.store import MemoryStore, Snapshot, StoreWrite
from living_island.memory.v2.validation import (
    Add,
    ChangeSet,
    CommitmentStatus,
    Confidence,
    Forget,
    Inference,
    InvalidOp,
    Merge,
    ReviewDone,
    SubmittedOp,
    TraitOp,
    Update,
    WireSource,
    allowed_kind,
    new_content,
    trait_value,
    update_content,
)

type Edit = MemoryRecord | str
type Reason = Literal[
    "depends_on", "format", "authority", "reference", "provenance", "source_kind", "capacity"
]
_PRECEDENCE: tuple[Reason, ...] = (
    "depends_on",
    "format",
    "authority",
    "reference",
    "provenance",
    "source_kind",
    "capacity",
)


@dataclass(frozen=True)
class Verdict:
    op_id: str | None
    result: Literal["committed", "dropped"]
    reason: Reason | None
    depends_on: tuple[str | None, ...]


@dataclass(frozen=True)
class OperationEffects:
    """The ordered edits include intermediate revisions cited later in this transaction."""

    op_id: str
    edits: tuple[Edit, ...]
    produced_id: str | None
    evictions: tuple[str, ...]
    carried_from: tuple[RevisionRef, ...]
    bindings: tuple[SourceBinding, ...]


@dataclass(frozen=True)
class CommittedChangeSet:
    write: StoreWrite
    relabel_flags: tuple[RelabelFlag, ...]


@dataclass(frozen=True)
class StagedChangeSet:
    base: Snapshot
    change_set: ChangeSet
    sent: SentInput
    tick: int
    verdicts: tuple[Verdict, ...]
    effects: tuple[OperationEffects, ...]

    @property
    def evictions(self) -> tuple[str, ...]:
        return tuple(key for effect in self.effects for key in effect.evictions)

    def commit(self, store: MemoryStore) -> CommittedChangeSet:
        """Publish on the original base. MF-03 rebases the recorded effects for a newer store."""
        if store.snapshot is not self.base and store.snapshot.store_hash != self.base.store_hash:
            raise ValueError("change set requires its original base or a mechanical rebase")
        edits = (edit for effect in self.effects for edit in effect.edits)
        write = store.apply(self.base.version, "change_set", edits)
        created = (effect.produced_id for effect in self.effects if effect.produced_id is not None)
        return CommittedChangeSet(write, relabel_flags(store.snapshot, created, self.sent.call_id))


@dataclass
class _Candidate:
    writes: set[str]
    errors: set[Reason] = field(default_factory=set)
    revised: dict[str, MemoryRecord] = field(default_factory=dict)
    removals: list[str] = field(default_factory=list)
    victims: list[str] = field(default_factory=list)
    bindings: tuple[SourceBinding, ...] = ()
    carried: tuple[RevisionRef, ...] = ()
    ancestry: set[str] = field(default_factory=set)
    trust_changed: bool = False


def _inferences(record: MemoryRecord) -> Iterable[str]:
    for source in record.sources:
        if isinstance(source, Inferred):
            yield from source.memory_ids


class _Transaction:
    def __init__(
        self, store: MemoryStore, change_set: ChangeSet, sent: SentInput, tick: int
    ) -> None:
        self.base = store.snapshot
        self.registry: KindRegistry = store.registry
        self.sent = sent
        self.tick = tick
        self.records = {r.id: r for r in self.base.records()}
        self.sent_revisions = {
            ref.id: BoundRevision(ref, self.base.read(ref))
            for ref in (*sent.index, *sent.full)
            if ref.id in self.records
        }
        self.full = {ref.id for ref in sent.full if ref.id in self.sent_revisions}
        self.personality_id = next(
            (r.id for r in self.records.values() if r.kind == "personality"), None
        )
        self.base_sources = {key: tuple(_inferences(r)) for key, r in self.records.items()}
        self.added_ancestry: dict[str, set[str]] = {}
        self.refs: dict[str, str] = {}
        self.count_ids = Counter(op.op_id for op in change_set.ops)
        self.count_refs = Counter(op.ref for op in change_set.ops if op.ref is not None)
        self.protected = {key for op in change_set.ops for key in self.targets(op)}
        self.written: set[str] = set()
        self.changed_traits: set[str] = set()
        self.changed_trust: set[str] = set()
        self.dropped: list[tuple[int, set[str], set[int]]] = []
        self.verdicts: list[Verdict] = []
        self.effects: list[OperationEffects] = []

    def targets(self, proposal: SubmittedOp) -> tuple[str, ...]:
        if proposal.name == "trait" and self.personality_id is not None:
            return (self.personality_id,)
        return tuple(self.refs.get(key, key) for key in proposal.operands)

    def revision(self, key: str) -> RevisionRef:
        if key in self.written:
            return RevisionRef(key, self.base.version + 1, self.records[key].content_hash())
        return self.base.ref(key)

    def ancestry(self, key: str, *, staged: bool) -> set[str]:
        # Follow the frozen input graph for a sent revision. An earlier staged citation
        # contributes exactly the ancestry it captured when its own sources were bound.
        result = {key}
        pending = [key]
        while pending:
            for parent in self.base_sources.get(pending.pop(), ()):
                if parent not in result:
                    result.add(parent)
                    pending.append(parent)
        if staged and key in self.added_ancestry:
            result.update(self.added_ancestry[key])
        return result

    def sources(
        self,
        c: _Candidate,
        target: str,
        content: Content | None,
        inherited: Sequence[Source],
        proposed: Sequence[WireSource],
    ) -> tuple[list[Source], bool]:
        added: list[Source] = []
        cited: dict[str, BoundRevision] = {}
        for wire in proposed:
            if isinstance(wire, Inference):
                named = [(name, self.refs.get(name, name)) for name in wire.memory_ids]
                canonical = sorted(key for _, key in named)
                if any(
                    isinstance(source, Inferred)
                    and source.call_id == wire.call_id
                    and source.memory_ids == canonical
                    for source in inherited
                ):
                    continue
                ids: list[str] = []
                for name, key in named:
                    if key not in self.records:
                        c.errors.add("reference")
                        continue
                    ids.append(key)
                    if name in self.refs:
                        cited[key] = BoundRevision(self.revision(key), self.records[key])
                    elif name in self.sent_revisions:
                        cited[key] = self.sent_revisions[name]
                    else:
                        c.errors.add("provenance")
                        continue
                    c.ancestry.update(self.ancestry(key, staged=name in self.refs))
                if not ids:
                    continue
                source: Source = Inferred(memory_ids=ids, call_id=wire.call_id)
            else:
                source = wire
            if source not in inherited and source not in added:
                added.append(source)
        if target in c.ancestry:
            c.errors.add("reference")
        trust = {
            r.content.about: r.content.trust
            for r in self.records.values()
            if isinstance(r.content, Social)
        }
        evidence = bind_sources(added, content, self.sent, cited, trust)
        c.bindings = evidence.bindings
        if evidence.provenance_error:
            c.errors.add("provenance")
        if evidence.source_kind_error:
            c.errors.add("source_kind")
        return [*inherited, *added], evidence.speech_derived

    def structure(
        self,
        c: _Candidate,
        proposal: SubmittedOp,
        targets: tuple[str, ...],
        produced: str,
    ) -> None:
        """Discover backlinks, review flags and capacity victims even if a later check fails."""
        name = proposal.name
        if name not in ("add", "merge", "supersede"):
            return
        old_ids: tuple[str, ...] = ()
        successor: str | None = produced
        if name == "merge":
            old_ids = targets
        elif name == "supersede":
            old_ids = targets[:1]
            successor = targets[1] if len(targets) == 2 else None
        resolved = all(key in self.records for key in targets)
        if name == "merge" and (len(set(targets)) != len(targets) or len(targets) < 2):
            c.errors.add("reference")
        if old_ids and successor is not None:
            for key in old_ids:
                old = self.records.get(key)
                if old is None:
                    continue
                if old.superseded_by is not None or key == successor:
                    c.errors.add("reference")
                c.revised[key] = old.model_copy(
                    update={"superseded_by": successor, "updated_tick": self.tick}
                )
            predecessors = set(old_ids)
            for r in self.records.values():
                if predecessors.intersection(_inferences(r)):
                    c.writes.add(r.id)
                    record = c.revised.get(r.id, r)
                    c.revised[r.id] = record.model_copy(
                        update={"needs_review": True, "updated_tick": self.tick}
                    )
        if name == "supersede" and successor is not None and successor in self.records and old_ids:
            by = self.records[successor]
            if by.supersedes is not None or any(
                r.superseded_by == successor for r in self.records.values()
            ):
                c.errors.add("reference")
            if old_ids[0] in self.records and self.records[old_ids[0]].kind != by.kind:
                c.errors.add("reference")
            seen = set(old_ids)
            cursor: str | None = successor
            while cursor is not None and cursor in self.records:
                if cursor in seen:
                    c.errors.add("reference")
                    break
                seen.add(cursor)
                cursor = self.records[cursor].superseded_by
            c.revised[successor] = c.revised.get(successor, by).model_copy(
                update={"supersedes": old_ids[0], "updated_tick": self.tick}
            )
        if (
            not resolved
            or proposal.unresolved_operands
            or any(self.refs.get(key, key) not in self.records for key in proposal.inferred_ids)
        ):
            return
        kinds = {self.records[key].kind for key in old_ids}
        if proposal.new_kind is not None:
            kinds.add(proposal.new_kind)
        population = self.records | c.revised
        for kind in sorted(kinds):
            try:
                capacity = plan_capacity(
                    kind,
                    population.values(),
                    self.registry,
                    self.protected | self.written,
                    added_live=int(kind == proposal.new_kind),
                )
            except KeyError:  # Unknown model-proposed destination kind.
                c.errors.add("format")
                continue
            c.victims.extend(capacity.victims)
            c.writes.update(capacity.victims)
            if not capacity.fits:
                c.errors.add("capacity")

    def create(
        self,
        c: _Candidate,
        op: Add | Merge,
        targets: tuple[str, ...],
        produced: str,
    ) -> None:
        new = op.record
        content = None
        if allowed_kind(self.registry, op.op, new.kind):
            try:
                content = new_content(self.registry, new)
            except InvalidOp as exc:
                c.errors.add(exc.reason)
        else:
            c.errors.add("authority")
        members = [self.records[k] for k in dict.fromkeys(targets) if k in self.records]
        inherited: list[Source] = []
        for member in members:
            for source in member.sources:
                if source not in inherited:
                    inherited.append(source)
        sources, speech = self.sources(c, produced, content, inherited, new.sources)
        speech |= any(r.speech_derived for r in members)
        c.carried = tuple(self.revision(r.id) for r in members)
        for member in members:
            c.ancestry.update(self.ancestry(member.id, staged=True))
        if not confidence_allowed(new.confidence, sources, speech):
            c.errors.add("format")
        if content is None:
            return
        if not sources and (new.sources or len(members) < len(targets)):
            # An unresolved citation/member has no typed source yet. Its absence
            # here does not turn a well-formed submission into an empty source list.
            return
        if (
            isinstance(content, Belief)
            and content.stance == "guess"
            and not any(s.kind == "inferred" for s in (*sources, *new.sources))
        ):
            c.errors.add("format")
        c.revised[produced] = MemoryRecord(
            id=produced,
            owner_id=self.base.owner_id,
            kind=new.kind,
            created_tick=self.tick,
            updated_tick=self.tick,
            about_tick=new.about_tick,
            sources=sources,
            confidence=new.confidence,
            speech_derived=speech,
            last_used_tick=None,
            use_count=0,
            supersedes=None,
            superseded_by=None,
            needs_review=False,
            gist=new.gist,
            text=new.text,
            content=content,
        )

    def update(self, c: _Candidate, op: Update, old: MemoryRecord, *, allowed: bool) -> None:
        content = old.content
        if allowed:
            try:
                content = update_content(self.registry, old, op)
            except InvalidOp as exc:
                c.errors.add(exc.reason)
        sources, speech = self.sources(c, old.id, content, old.sources, op.add_sources)
        speech |= old.speech_derived
        if not confidence_allowed(old.confidence, sources, speech):
            c.errors.add("format")
        if (
            isinstance(content, Belief)
            and content.stance == "guess"
            and not any(s.kind == "inferred" for s in (*sources, *op.add_sources))
        ):
            c.errors.add("format")
        if isinstance(content, Social) and isinstance(old.content, Social):
            c.trust_changed = content.trust != old.content.trust
            if c.trust_changed and old.id in self.changed_trust:
                c.errors.add("authority")
        fields = dict(old)
        fields.update(
            gist=op.gist,
            content=content,
            sources=sources,
            speech_derived=speech,
            updated_tick=self.tick,
        )
        for key in ("text", "about_tick"):
            if key in op.model_fields_set:
                fields[key] = getattr(op, key)
        c.revised[old.id] = MemoryRecord.model_validate(fields)
        c.carried = (self.revision(old.id),)

    def modify(
        self, c: _Candidate, proposal: SubmittedOp, targets: tuple[str, ...], new: str
    ) -> None:
        op = proposal.operation
        if op is None:
            return
        allowed = all(
            allowed_kind(self.registry, op.op, self.records[key].kind)
            for key in targets
            if key in self.records
        )
        if not allowed:
            c.errors.add("authority")
        if isinstance(op, Add | Merge):
            self.create(c, op, targets, new)
            return
        if not targets or targets[0] not in self.records:
            c.errors.add("reference")
            return
        old = self.records[targets[0]]
        if isinstance(op, Confidence):
            if not confidence_allowed(op.to, old.sources, old.speech_derived):
                c.errors.add("format")
            c.revised[old.id] = old.model_copy(
                update={"confidence": op.to, "updated_tick": self.tick}
            )
        elif isinstance(op, Update):
            self.update(c, op, old, allowed=allowed)
        elif isinstance(op, ReviewDone):
            c.revised[old.id] = old.model_copy(
                update={"needs_review": False, "updated_tick": self.tick}
            )
        elif isinstance(op, Forget):
            c.removals.append(old.id)
        elif isinstance(op, CommitmentStatus) and isinstance(old.content, Commitment):
            content = old.content.model_copy(update={"status": op.status, "status_note": op.note})
            c.revised[old.id] = old.model_copy(
                update={"content": content, "updated_tick": self.tick}
            )
        elif isinstance(op, TraitOp) and isinstance(old.content, Personality):
            value = trait_value(old.content, op)
            if op.trait_id in self.changed_traits:
                c.errors.add("authority")
            sources, _ = self.sources(c, old.id, old.content, (), op.sources)
            if sources:
                traits = []
                for trait in old.content.traits:
                    if trait.trait_id == op.trait_id:
                        change = TraitChange(
                            tick=self.tick, **{"from": trait.value, "to": value}, sources=sources
                        )
                        trait = trait.model_copy(
                            update={"value": value, "changes": [*trait.changes, change]}
                        )
                    traits.append(trait)
                c.revised[old.id] = old.model_copy(
                    update={
                        "content": old.content.model_copy(update={"traits": traits}),
                        "updated_tick": self.tick,
                    }
                )

    def stage(self, proposal: SubmittedOp) -> None:
        targets = self.targets(proposal)
        c = _Candidate(set(targets))
        if proposal.problem:
            c.errors.add(proposal.problem)
        if self.count_ids[proposal.op_id] > 1 or (
            proposal.ref and self.count_refs[proposal.ref] > 1
        ):
            c.errors.add("format")
        if any(key not in self.records for key in targets):
            c.errors.add("reference")
        if any(
            name not in self.refs and name not in self.full
            for name in ((self.personality_id,) if proposal.name == "trait" else proposal.operands)
        ):
            c.errors.add("provenance")
        produced = self.base.next_id(len(self.refs))
        self.structure(c, proposal, targets, produced)
        try:
            self.modify(c, proposal, targets, produced)
        except InvalidOp as exc:
            c.errors.add(exc.reason)
        except ValidationError:
            c.errors.add("format")

        reads = {self.refs.get(key, key) for key in proposal.inferred_ids}
        dependencies: set[int] = set()
        for position, writes, prior in self.dropped:
            if writes.intersection(c.writes | reads):
                dependencies.update((position, *prior))
        if dependencies:
            c.errors.add("depends_on")
        reason = next((reason for reason in _PRECEDENCE if reason in c.errors), None)
        if reason is not None:
            if proposal.ref is not None:
                c.writes.add(proposal.ref)
            self.dropped.append((len(self.verdicts), c.writes, dependencies))
            depends_on = tuple(self.verdicts[i].op_id for i in sorted(dependencies))
            self.verdicts.append(Verdict(proposal.op_id, "dropped", reason, depends_on))
            return

        op = proposal.operation
        assert op is not None
        if proposal.ref is not None:
            self.refs[proposal.ref] = produced
            self.added_ancestry[produced] = c.ancestry
        elif isinstance(op, Update):
            self.added_ancestry.setdefault(targets[0], set()).update(c.ancestry)
        if c.trust_changed:
            self.changed_trust.add(targets[0])
        if isinstance(op, TraitOp):
            self.changed_traits.add(op.trait_id)
        self.records.update(c.revised)
        for key in (*c.removals, *c.victims):
            del self.records[key]
        self.written.update(c.writes | c.revised.keys())
        self.effects.append(
            OperationEffects(
                op.op_id,
                (*c.revised.values(), *c.removals, *c.victims),
                produced if proposal.ref is not None else None,
                tuple(c.victims),
                c.carried,
                c.bindings,
            )
        )
        self.verdicts.append(Verdict(op.op_id, "committed", None, ()))


def stage_change_set(
    store: MemoryStore,
    change_set: ChangeSet,
    sent: SentInput,
    tick: int,
) -> StagedChangeSet:
    """Validate the accepted prefix of model operations without changing the caller's store."""
    if (
        change_set.base_version != store.snapshot.version
        or sent.owner_id != store.snapshot.owner_id
    ):
        raise ValueError("change set must use its resident's frozen base")
    transaction = _Transaction(store, change_set, sent, tick)
    for proposal in change_set.ops:
        transaction.stage(proposal)
    return StagedChangeSet(
        transaction.base,
        change_set,
        sent,
        tick,
        tuple(transaction.verdicts),
        tuple(transaction.effects),
    )
