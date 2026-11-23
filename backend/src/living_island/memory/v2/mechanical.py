"""Mechanical writes from one resident's delivered evidence, in boundary order."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from living_island.memory.v2.projections import RevisionRef
from living_island.memory.v2.records import (
    Commitment,
    Look,
    MemoryRecord,
    Observed,
    Skill,
    Social,
    SocialFacts,
    Source,
    TerrainTarget,
    Told,
    Transfer,
)
from living_island.memory.v2.store import MemoryStore, StoreWrite
from living_island.world.v2.protocol import (
    ActionFeedback,
    ItemUse,
    ObservedAction,
    StartTarget,
    SubjectStartTarget,
    Terms,
    TileStartTarget,
)


@dataclass(frozen=True)
class AgreementFact:
    agreement_id: str
    role: Literal["promisor", "promisee"]
    counterpart_id: str
    terms: Terms
    due_tick: int | None
    accepted_tick: int
    proposal_id: str
    acceptance_id: str


@dataclass(frozen=True)
class Member:
    delivery_id: str
    path: str
    entry_id: str | None = None
    entry_revision: str | None = None
    related_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sight:
    resident_id: str
    member: Member


@dataclass(frozen=True)
class Speech:
    utterance_id: str
    source: Observed | Told
    member: Member
    tick: int
    agreement_speech: bool


@dataclass(frozen=True)
class Watch:
    action: ObservedAction
    member: Member


@dataclass(frozen=True)
class OwnResult:
    feedback: ActionFeedback
    action: str
    verb: str | None
    target_absent: bool
    recipient: str | None
    member: Member


@dataclass(frozen=True)
class MechanicalDelivery:
    owner_id: str
    tick: int
    sights: tuple[Sight, ...]
    speech: tuple[Speech, ...]
    watches: tuple[Watch, ...]
    results: tuple[OwnResult, ...]


@dataclass(frozen=True)
class SkillTrace:
    hypothesis: RevisionRef
    intent_id: str
    actor_id: str
    delta: dict[str, int]


@dataclass(frozen=True)
class MechanicalWrite:
    write: StoreWrite
    members: tuple[Member, ...]
    skill: SkillTrace | None = None
    agreement: AgreementFact | None = None


@dataclass(frozen=True)
class WriterCheckpoint:
    """Keep the cursor, unpaired starts and delivered agreement speech beside the store."""

    owner_id: str
    tick: int = -1
    starts: tuple[Watch, ...] = ()
    speech: tuple[Speech, ...] = ()


def _new_record(
    store: MemoryStore,
    tick: int,
    content: Commitment | Social,
    sources: list[Source],
    trust: int,
) -> MemoryRecord:
    told = any(source.kind == "told" for source in sources)
    confidence = (0, 1, 1, 2, 3)[trust] if told and all(s.kind == "told" for s in sources) else 3
    return MemoryRecord(
        owner_id=store.snapshot.owner_id,
        id=store.snapshot.next_id(),
        kind=content.kind,
        created_tick=tick,
        updated_tick=tick,
        sources=sources,
        confidence=confidence,
        speech_derived=told,
        about_tick=None,
        last_used_tick=None,
        use_count=0,
        supersedes=None,
        superseded_by=None,
        needs_review=False,
        gist="",  # MemoryStore applies the registered hard-fact template.
        text=None,
        content=content,
    )


def _transfers(previous: Sequence[Transfer], items: Sequence[ItemUse]) -> list[Transfer]:
    counts = Counter({part.archetype_id: part.quantity for part in previous})
    for item in items:
        if item.role == "item" and item.archetype_id is not None:
            counts[item.archetype_id] += item.quantity
    return [Transfer(archetype_id=key, quantity=counts[key]) for key in sorted(counts)]


class _Boundary:
    """Write one packet in category order. The store may have changed since the last packet."""

    def __init__(self, store: MemoryStore, tick: int) -> None:
        self.store = store
        self.tick = tick
        self.writes: list[MechanicalWrite] = []
        self.socials: dict[str, tuple[MemoryRecord, Social]] = {}
        self.skills: dict[str, tuple[MemoryRecord, Skill]] = {}
        self.agreements: dict[str, list[str]] = {}
        for record in store.snapshot.records():
            content = record.content
            if isinstance(content, Social):
                self.socials[content.about] = record, content
            elif isinstance(content, Skill) and not record.history:
                self.skills[record.id] = record, content
            elif isinstance(content, Commitment):
                self.agreements.setdefault(content.counterpart_id, []).append(content.agreement_id)

    def put(
        self,
        record: MemoryRecord,
        members: tuple[Member, ...],
        *,
        skill: SkillTrace | None = None,
        agreement: AgreementFact | None = None,
    ) -> None:
        write = self.store.apply(self.store.snapshot.version, "mechanical", [record])
        self.writes.append(MechanicalWrite(write, members, skill, agreement))

    def attempt(
        self,
        actor_id: str,
        intent_id: str,
        verb: str | None,
        items: Sequence[ItemUse],
        target: StartTarget | None,
        absent: bool,
        phenomena: Sequence[str],
        members: tuple[Member, ...],
        *,
        watched: bool,
    ) -> None:
        base = self.store.snapshot
        for record_id, (record, skill) in self.skills.items():
            hypothesis = base.ref(record_id)
            update = _skill_update(
                skill,
                verb=verb,
                items=items,
                start_target=target,
                known_absent_target=absent,
                phenomena=phenomena,
                watched=watched,
                tick=self.tick,
            )
            if update is not None:
                content, delta = update
                updated = record.model_copy(update={"updated_tick": self.tick, "content": content})
                trace = SkillTrace(hypothesis, intent_id, actor_id, delta)
                self.put(updated, members, skill=trace)
                self.skills[record_id] = updated, content

    def social(
        self,
        counterpart: str,
        members: tuple[Member, ...],
        sources: list[Source],
        *,
        seen: bool = False,
        heard: int | None = None,
        given: Sequence[ItemUse] = (),
        received: Sequence[ItemUse] = (),
        agreement: AgreementFact | None = None,
    ) -> None:
        prior = self.socials.get(counterpart)
        if prior is None:
            # A social record begins with the first delivered evidence for this resident.
            # A commitment alone can exist with no speech or sighting at all.
            if not sources:
                return
            facts = SocialFacts(
                given=[],
                received=[],
                agreements=self.agreements.get(counterpart, []),
                last_seen_tick=None,
                last_heard_tick=None,
            )
            content = Social(about=counterpart, trust=2, impression="", facts=facts)
        else:
            _, content = prior
            facts = content.facts
        changes = facts.model_copy(
            update={
                "last_seen_tick": self.tick if seen else facts.last_seen_tick,
                "last_heard_tick": heard if heard is not None else facts.last_heard_tick,
                "given": _transfers(facts.given, given) if given else facts.given,
                "received": _transfers(facts.received, received) if received else facts.received,
                "agreements": [*facts.agreements, agreement.agreement_id]
                if agreement
                else facts.agreements,
            }
        )
        if prior is not None and changes == facts:
            return
        content = content.model_copy(update={"facts": changes})
        if prior is None:
            record = _new_record(self.store, self.tick, content, sources, content.trust)
        else:
            record = prior[0].model_copy(update={"updated_tick": self.tick, "content": content})
        self.put(record, members, agreement=agreement)
        self.socials[counterpart] = record, content

    def commitment(self, fact: AgreementFact, speech: Sequence[Speech]) -> None:
        sources: list[Source] = [s.source for s in speech]
        content = Commitment(
            role=fact.role,
            counterpart_id=fact.counterpart_id,
            terms=fact.terms,
            due_tick=fact.due_tick,
            heard_counterpart=any(source.kind == "told" for source in sources),
            status="open",
            status_note=None,
            agreement_id=fact.agreement_id,
        )
        social = self.socials.get(fact.counterpart_id)
        record = _new_record(
            self.store, self.tick, content, sources, social[1].trust if social else 2
        )
        self.put(record, tuple(s.member for s in speech), agreement=fact)


def _observed(member: Member) -> list[Source]:
    return [Observed(entry_id=member.entry_id)] if member.entry_id is not None else []


class MechanicalWriter:
    """Apply the already logged, origin-filtered packet to its resident's store, in either arm."""

    def __init__(self, store: MemoryStore, *, restored: WriterCheckpoint | None = None) -> None:
        self.store = store
        state = restored or WriterCheckpoint(store.snapshot.owner_id)
        if state.owner_id != store.snapshot.owner_id:
            raise ValueError("writer checkpoint belongs to another resident")
        self._tick = state.tick
        self._starts = {s.action.intent_id: s for s in state.starts}
        self._speech = {s.utterance_id: s for s in state.speech}

    def checkpoint(self) -> WriterCheckpoint:
        return WriterCheckpoint(
            self.store.snapshot.owner_id,
            self._tick,
            tuple(self._starts.values()),
            tuple(self._speech.values()),
        )

    def deliver(
        self, packet: MechanicalDelivery, *, agreements: Sequence[AgreementFact] = ()
    ) -> tuple[MechanicalWrite, ...]:
        """Deliver once per verified boundary, after DL-02 appended its day entries."""
        if packet.owner_id != self.store.snapshot.owner_id:
            raise ValueError("mechanical delivery belongs to another resident")
        if packet.tick <= self._tick:
            return ()
        for fact in agreements:
            party = fact.terms.promisor_id if fact.role == "promisor" else fact.terms.promisee_id
            if party != packet.owner_id:
                raise ValueError("agreement fact is routed to the wrong party")
        boundary = _Boundary(self.store, packet.tick)
        for watch in packet.watches:
            action = watch.action
            if action.action != "act":
                continue
            if action.phase == "start":
                self._starts[action.intent_id] = watch
            else:
                start = self._starts.pop(action.intent_id, None)
                if action.phase == "settle" and start is not None:
                    boundary.attempt(
                        action.actor_id,
                        action.intent_id,
                        start.action.verb,
                        start.action.visible_items,
                        start.action.start_target,
                        False,
                        action.phenomena,
                        (start.member, watch.member),
                        watched=True,
                    )
        for result in packet.results:
            if result.action == "act":
                feedback = result.feedback
                boundary.attempt(
                    packet.owner_id,
                    feedback.intent_id,
                    result.verb,
                    feedback.items_used,
                    feedback.start_target,
                    result.target_absent,
                    feedback.phenomena,
                    (result.member,),
                    watched=False,
                )

        for sight in packet.sights:
            boundary.social(sight.resident_id, (sight.member,), _observed(sight.member), seen=True)
        for speech in packet.speech:
            if speech.agreement_speech:
                self._speech[speech.utterance_id] = speech
            if isinstance(speech.source, Told):
                boundary.social(
                    speech.source.speaker_id, (speech.member,), [speech.source], heard=speech.tick
                )
        for watch in packet.watches:
            action = watch.action
            target = action.target
            recipient = (
                action.action == "give"
                and action.phase == "settle"
                and target is not None
                and target.kind == "resident"
                and target.id == packet.owner_id
            )
            boundary.social(
                action.actor_id,
                (watch.member,),
                _observed(watch.member),
                seen=True,
                received=action.received_items if recipient else (),
            )
        for result in packet.results:
            if result.recipient is not None:
                boundary.social(
                    result.recipient,
                    (result.member,),
                    _observed(result.member),
                    given=result.feedback.items_used,
                )
        party_speech = []
        for fact in agreements:
            evidence = [
                delivered
                for key in (fact.proposal_id, fact.acceptance_id)
                if (delivered := self._speech.pop(key, None)) is not None
                and (
                    isinstance(delivered.source, Observed)
                    or delivered.source.speaker_id == fact.counterpart_id
                )
            ]
            boundary.social(
                fact.counterpart_id,
                tuple(s.member for s in evidence),
                [s.source for s in evidence],
                agreement=fact,
            )
            party_speech.append((fact, evidence))
        for fact, evidence in party_speech:
            boundary.commitment(fact, evidence)
        self._tick = packet.tick
        return tuple(boundary.writes)


def _look_fits(required: Look, seen: ItemUse | SubjectStartTarget) -> bool:
    words = {(descriptor.property_id, descriptor.value) for descriptor in seen.descriptors}
    return (
        (required.archetype_id is None or required.archetype_id == seen.archetype_id)
        and (required.material_id is None or required.material_id == seen.material_id)
        and all((word.property_id, word.word) in words for word in required.descriptors)
    )


def _slots_fit(slots: Sequence[tuple[Look, int]], items: Sequence[tuple[ItemUse, int]]) -> bool:
    if len(slots) != len(items):
        return False
    candidates = [
        [
            index
            for index, (item, quantity) in enumerate(items)
            if quantity == required_quantity and _look_fits(look, item)
        ]
        for look, required_quantity in slots
    ]
    # Only existence of a full assignment affects evidence. Try delivered
    # positions in order and move a previous match when a narrower slot needs it.
    assigned = [-1] * len(items)

    def assign(slot: int, tried: set[int]) -> bool:
        for index in candidates[slot]:
            if index in tried:
                continue
            tried.add(index)
            if assigned[index] == -1 or assign(assigned[index], tried):
                assigned[index] = slot
                return True
        return False

    return all(assign(slot, set()) for slot in range(len(slots)))


type _Appearance = tuple[str | None, str | None, tuple[tuple[str, str], ...]]


def _group_inputs(items: Sequence[ItemUse]) -> list[tuple[ItemUse, int]]:
    groups: dict[_Appearance, tuple[ItemUse, int]] = {}
    for item in items:
        if item.role == "input":
            words = tuple((d.property_id, d.value) for d in item.descriptors)
            key = (item.archetype_id, item.material_id, words)
            first, quantity = groups.get(key, (item, 0))
            groups[key] = (first, quantity + item.quantity)
    return list(groups.values())


def _target_fits(
    required: Look | TerrainTarget | None,
    items: Sequence[ItemUse],
    start_target: StartTarget | None,
    known_absent: bool,
) -> bool:
    if required is None:
        return known_absent
    if isinstance(required, TerrainTarget):
        return (
            isinstance(start_target, TileStartTarget) and start_target.terrain == required.terrain
        )
    # An item target has a role-specific apparent view. Non-item subjects
    # carry their apparent fields in the typed start target.
    target_item = next((item for item in items if item.role == "target"), None)
    if target_item is not None:
        return _look_fits(required, target_item)
    return isinstance(start_target, SubjectStartTarget) and _look_fits(required, start_target)


def _skill_update(
    skill: Skill,
    *,
    verb: str | None,
    items: Sequence[ItemUse],
    start_target: StartTarget | None,
    known_absent_target: bool,
    phenomena: Sequence[str],
    watched: bool,
    tick: int,
) -> tuple[Skill, dict[str, int]] | None:
    recipe = skill.hypothesis
    if skill.status == "refuted" or recipe.verb != verb:
        return None
    if not _target_fits(recipe.target, items, start_target, known_absent_target):
        return None
    if not _slots_fit(
        [(look, 1) for look in recipe.instruments],
        [(item, 1) for item in items if item.role == "instrument"],
    ):
        return None
    if not _slots_fit([(slot.look, slot.quantity) for slot in recipe.inputs], _group_inputs(items)):
        return None

    matched = set(recipe.expected).issubset(phenomena)
    if watched:
        delta = {"watched": 1}
        if matched:
            delta["watched_matched"] = 1
    else:
        delta = {"attempts": 1, "matched_expected" if matched else "other_outcomes": 1}
    updates = {field: getattr(skill.evidence, field) + value for field, value in delta.items()}
    if not watched:
        updates["last_attempt_tick"] = delta["last_attempt_tick"] = tick
    evidence = skill.evidence.model_copy(update=updates)
    return skill.model_copy(update={"evidence": evidence}), delta
