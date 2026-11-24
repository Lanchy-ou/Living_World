"""Attribute first successes and score hypotheses from immutable resident evidence."""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

from living_island.agents.v2.context.entries import DayEntry
from living_island.analysis.v2.continuity import (
    History,
    continuity,
    link,
    revision_link,
    row_fields,
)
from living_island.contract import inspection_v2 as ia

type Flag = Literal["own_failures", "watched", "told", "earlier_period", "prior_knowledge"]


class _Part(BaseModel):
    model_config = ConfigDict(strict=True)
    archetype_id: str


class _Slot(BaseModel):
    parts: list[_Part]


_slots = TypeAdapter(list[_Slot])


@dataclass
class Attempt:
    event: ia.WorldEvent
    intent: str
    rule: str | None
    verb: str
    applied: bool
    items: set[str] | None
    items_event: str | None
    decision: ia.DecisionRecord | None

    def related(self, success: "Attempt") -> bool:
        return self.verb == success.verb and (
            self.rule == success.rule
            or bool(self.items and success.items and self.items & success.items)
        )


type Appearance = frozenset[tuple[str, str]]


def appearance(
    archetype: str | None, material: str | None, words: Iterable[tuple[str, str]]
) -> Appearance:
    fields = {("word:" + key, word) for key, word in words}
    if archetype is not None:
        fields.add(("archetype", archetype))
    if material is not None:
        fields.add(("material", material))
    return frozenset(fields)


def fits_groups(
    required: list[tuple[Appearance, int]], actual: list[tuple[Appearance, int]]
) -> bool:
    if len(required) != len(actual):
        return False
    assigned: dict[int, int] = {}

    def assign(slot: int, visited: set[int]) -> bool:
        look, count = required[slot]
        for i, (visible, quantity) in enumerate(actual):
            if i in visited or quantity != count or not look.issubset(visible):
                continue
            visited.add(i)
            if i not in assigned or assign(assigned[i], visited):
                assigned[i] = slot
                return True
        return False

    return all(assign(slot, set()) for slot in range(len(required)))


def predicts(
    skill: ia.Skill,
    success: Attempt,
    delivery: ia.Delivery,
    submitted: ia.TurnSubmission,
) -> bool:
    """A frozen prefix can retain a hypothesis after its live record was superseded."""
    hypothesis = skill.hypothesis
    feedback = next(
        f for f in delivery.packet.perception.action_feedback if f.intent_id == success.intent
    )
    if hypothesis.verb != success.verb or not set(hypothesis.expected).issubset(feedback.phenomena):
        return False
    seen_inputs: Counter[Appearance] = Counter()
    seen_instruments = []
    seen_target = None
    target = feedback.start_target
    if target and target.kind != "tile":
        seen_target = appearance(
            target.archetype_id,
            target.material_id,
            ((d.property_id, d.value) for d in target.descriptors),
        )
    for item in feedback.items_used:
        seen = appearance(
            item.archetype_id,
            item.material_id,
            ((d.property_id, d.value) for d in item.descriptors),
        )
        if item.role == "input":
            seen_inputs[seen] += item.quantity
        elif item.role == "instrument":
            seen_instruments.append((seen, 1))
        else:
            seen_target = seen
    required = hypothesis.target
    if required is None:
        if submitted.action.kind != "intent" or submitted.action.intent.target is not None:
            return False
    elif hasattr(required, "terrain"):
        if not target or target.kind != "tile" or target.terrain != required.terrain:
            return False
    elif seen_target is None or not appearance(
        required.archetype_id,
        required.material_id,
        ((d.property_id, d.word) for d in required.descriptors),
    ).issubset(seen_target):
        return False
    inputs = [
        (
            appearance(
                i.look.archetype_id,
                i.look.material_id,
                ((d.property_id, d.word) for d in i.look.descriptors),
            ),
            i.quantity,
        )
        for i in hypothesis.inputs
    ]
    instruments = [
        (
            appearance(
                i.archetype_id, i.material_id, ((d.property_id, d.word) for d in i.descriptors)
            ),
            1,
        )
        for i in hypothesis.instruments
    ]
    return fits_groups(inputs, list(seen_inputs.items())) and fits_groups(
        instruments, seen_instruments
    )


def attempts(
    events: Sequence[ia.WorldEvent], decisions: Sequence[ia.DecisionRecord]
) -> dict[str, Attempt]:
    choices = {
        d.submission.action.intent.intent_id: d
        for d in decisions
        if d.submission and d.submission.action.kind == "intent"
    }
    items = {e.intent_id: e for e in events if e.type == "act_items"}
    settled = {e.intent_id for e in events if e.type == "act_settled"}
    result = {}
    for event in events:
        failed_act = (
            event.type in ("action_failed", "action_stopped")
            and event.payload.get("action") == "act"
            and event.intent_id not in settled
        )
        if (event.type != "act_settled" and not failed_act) or event.intent_id is None:
            continue
        item = items.get(event.intent_id)
        kinds = (
            {
                p.archetype_id
                for slot in _slots.validate_python(item.payload["slots"])
                for p in slot.parts
            }
            if item
            else None
        )
        rule = (
            event.payload.get("rule_id")
            if not failed_act
            else item.payload.get("rule_id")
            if item
            else None
        )
        result[event.intent_id] = Attempt(
            event,
            event.intent_id,
            str(rule) if rule is not None else None,
            str(event.payload["verb"]),
            event.payload.get("kind") == "applied",
            kinds,
            item.event_id if item else None,
            choices.get(event.intent_id),
        )
    return result


@dataclass
class Proof:
    flags: set[Flag] = field(default_factory=set)
    trace: set[str] = field(default_factory=set)
    links: list[ia.AnalysisLink] = field(default_factory=list)
    unchecked: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)

    def entry(self, joined: ia.JoinedEntry) -> None:
        entry = joined.entry
        self.trace.update([entry.id, entry.revision, *joined.event_ids])
        if entry.delivery_id:
            self.trace.add(entry.delivery_id)
            self.links.append(link("deliveries", entry.delivery_id, "Delivered " + entry.id))

    def attempt(self, a: Attempt) -> None:
        self.trace.update([a.intent, a.event.event_id])
        if a.items_event:
            self.trace.add(a.items_event)
        self.links.append(
            link("attempts", "attempts", "Settlement " + a.event.event_id, a.event.event_id)
        )
        if a.decision:
            self.links.append(
                link("decisions", a.decision.turn_id, "Decision " + a.decision.turn_id)
            )
            self.trace.add(a.decision.turn_id)


class Learning:
    def __init__(
        self,
        history: History,
        events: Sequence[ia.WorldEvent],
        decisions: Sequence[ia.DecisionRecord],
        checks: Sequence[ia.ContentCheck],
        entries: dict[str, DayEntry],
    ) -> None:
        self.history = history
        self.attempts = attempts(events, decisions)
        self.entries = entries
        self.checks = [
            c for c in checks if isinstance(c, ia.SpeechCheck) and c.check == "told_event"
        ]
        self.watches = {
            (actor, j.entry.ref.intent_id, j.entry.ref.phase): j
            for (actor, _), j in history.entries.items()
            if j.entry.ref.kind == "observed_action" and j.event_ids
        }
        self.heard = {
            (actor, j.entry.ref.utterance_id): j
            for (actor, _), j in history.entries.items()
            if j.entry.ref.kind == "utterance" and j.event_ids
        }
        self.writes: defaultdict[str, list[tuple[str, ia.SkillEvidence]]] = defaultdict(list)
        for key, w in history.evidence.items():
            if w.skill:
                self.writes[w.skill.hypothesis.id].append((key, w.skill))

    def told(self, proof: Proof, actor: str, utterance: str, success: Attempt, tick: int) -> None:
        heard = self.heard.get((actor, utterance))
        if heard is None or heard.entry.tick > tick:
            return
        proof.entry(heard)
        targets = {
            a.event.event_id
            for a in self.attempts.values()
            if a.rule == success.rule and a.event.tick <= tick
        }
        targets.update([str(success.rule), success.event.event_id])
        matches = [c for c in self.checks if utterance in c.ids and targets.intersection(c.ids)]
        if not matches:
            proof.unchecked.add(utterance)
        for check in matches:
            proof.trace.update([utterance, check.instance_id, *check.ids])
            if check.verdict == "carries":
                proof.flags.add("told")

    def earlier(
        self, ref: ia.RevisionRef, decision: ia.DecisionRecord, success: Attempt, proof: Proof
    ) -> None:
        root = self.history.records.get(ref)
        if root is None:
            proof.missing.add("missing sent memory revision")
            return
        origin = self.history.created_period(root)
        if origin is None:
            proof.missing.add("missing creation period")
            return
        if origin == decision.period_id:
            return
        delivery = self.history.feedback.get((decision.resident_id, success.intent))
        if (
            isinstance(root.content, ia.Skill)
            and delivery
            and decision.submission
            and predicts(root.content, success, delivery, decision.submission)
        ):
            key = delivery.packet.delivery_id
            proof.flags.add("earlier_period")
            proof.trace.update([origin, key, ref.content_hash])
            proof.links.append(link("deliveries", key, "Delivered prediction outcome " + key))
        # A mechanical match ties the delivered slot looks AND expected phenomena to
        # this attempt. Compare prediction bodies since evidence updates change hashes.
        for ancestor, record in self.history.ancestors(ref):
            for key, skill in self.writes[record.id]:
                a = self.attempts.get(skill.intent_id)
                if a is None or skill.hypothesis not in self.history.records:
                    continue
                predicted = (
                    ancestor == ref
                    and a.intent == success.intent
                    and skill.delta.get("matched_expected")
                )
                earlier_write = (
                    self.history.evidence[key].write.after_version <= ancestor.store_version
                    and a.intent != success.intent
                    and a.event.tick <= decision.tick
                    and a.related(success)
                    and (
                        skill.delta.get("watched") or (a.decision and a.decision.origin == "model")
                    )
                )
                if predicted or earlier_write:
                    proof.flags.add("earlier_period")
                    proof.trace.update(
                        [origin, key, ancestor.content_hash, skill.hypothesis.content_hash]
                    )
                    proof.attempt(a)
                    proof.links.extend(
                        [
                            link("evidence_writes", key, "Hypothesis evidence " + key),
                            revision_link(decision.resident_id, skill.hypothesis),
                        ]
                    )
            for source in record.sources:
                if source.kind != "observed":
                    continue
                entry = self.history.entries.get((decision.resident_id, source.entry_id))
                if (
                    not entry
                    or not entry.event_ids
                    or entry.entry.ref.kind not in ("observed_action", "feedback")
                ):
                    continue
                a = self.attempts.get(entry.entry.ref.intent_id)
                if (
                    a
                    and a.event.tick <= decision.tick
                    and a.intent != success.intent
                    and a.related(success)
                    and (
                        a.event.actor_id != decision.resident_id
                        or (a.decision and a.decision.origin == "model")
                    )
                ):
                    proof.flags.add("earlier_period")
                    proof.trace.add(origin)
                    proof.entry(entry)
                    proof.attempt(a)
                    proof.trace.update(
                        [ancestor.id, str(ancestor.store_version), ancestor.content_hash]
                    )
                    proof.links.append(revision_link(decision.resident_id, ancestor))

    def day_source(
        self, joined: ia.JoinedEntry, success: Attempt, decision: ia.DecisionRecord, proof: Proof
    ) -> None:
        ref = joined.entry.ref
        if ref.kind not in ("feedback", "observed_action"):
            return
        a = self.attempts.get(ref.intent_id)
        if a is None or a.event.tick > decision.tick or a.intent == success.intent:
            return
        actor = decision.resident_id
        if (
            ref.kind == "feedback"
            and a.event.actor_id == actor
            and a.decision
            and a.decision.origin == "model"
            and a.related(success)
            and not (a.applied and a.rule == success.rule)
            and a.event.event_id in joined.event_ids
        ):
            proof.flags.add("own_failures")
            proof.attempt(a)
            proof.entry(joined)
        if (
            ref.kind == "observed_action"
            and a.event.actor_id != actor
            and a.applied
            and a.rule == success.rule
        ):
            phases = [self.watches.get((actor, a.intent, phase)) for phase in ("start", "settle")]
            if all(j and j.entry.tick <= decision.tick for j in phases):
                proof.flags.add("watched")
                proof.attempt(a)
                for phase in phases:
                    if phase:
                        proof.entry(phase)

    def path(
        self, success: Attempt, d: ia.DecisionRecord, call: ia.CallInspection
    ) -> ia.LearningPath:
        proof = Proof()
        proof.attempt(success)
        proof.trace.update([d.turn_id, d.period_id, call.call.call_id])
        proof.links.append(link("calls", call.call.call_id, "Adopted call " + call.call.call_id))
        dispatched = {(a.dispatch.n, a.dispatch.request_sha256) for a in call.attempts}
        cited = {
            (f.source, f.sha256)
            for binding in call.adopted_citations
            if binding.turn_id == d.turn_id
            and binding.call_id == call.call.call_id
            and (binding.attempt, binding.request_sha256) in dispatched
            for citation in binding.valid
            for f in citation.fragments
        }
        manifest = call.sent_manifest
        if manifest is None:
            proof.missing.add("missing adopted dispatch")
        for part in manifest.entries if manifest else ():
            source = part.source
            valid_citation = (source, part.sha256) in cited
            memory = None
            if source.kind == "day_log":
                entry = self.entries.get(source.version or "")
                if entry is None:
                    proof.missing.add("missing sent entry revision")
                    continue
                joined = self.history.by_revision.get(entry.revision)
                if joined and entry.tick <= d.tick:
                    self.day_source(joined, success, d, proof)
                    if entry.ref.kind == "utterance" and valid_citation:
                        self.told(proof, d.resident_id, entry.ref.utterance_id, success, d.tick)
                memory = entry.retrieved
            elif source.kind == "memory" and source.version:
                version, digest = source.version.split(":", 1)
                memory = ia.RevisionRef(source.id, int(version), digest)
            if memory:
                proof.links.append(revision_link(d.resident_id, memory))
                proof.trace.update(
                    [memory.id, str(memory.store_version), memory.content_hash, part.sha256]
                )
                self.earlier(memory, d, success, proof)
                body = self.history.records.get(memory)
                if body and valid_citation:
                    for src in body.sources:
                        if src.kind == "told":
                            self.told(proof, d.resident_id, src.utterance_id, success, d.tick)
            if valid_citation:
                proof.trace.add(part.sha256)
        prior_related = any(
            a.intent != success.intent
            and a.event.actor_id == d.resident_id
            and a.event.tick <= d.tick
            and a.decision
            and a.decision.origin == "model"
            and a.related(success)
            for a in self.attempts.values()
        )
        if not (proof.flags or proof.unchecked or proof.missing or prior_related):
            proof.flags.add("prior_knowledge")
        reason = "; ".join(sorted(proof.missing)) or None
        if not proof.flags and not reason:
            reason = (
                "unchecked told evidence"
                if proof.unchecked
                else "earlier related attempt outside sent context"
            )
        base = row_fields(d.resident_id, "first_success", proof.trace, proof.links)
        return ia.LearningPath(
            **base.model_dump(),
            period_id=d.period_id,
            turn_id=d.turn_id,
            rule_id=str(success.rule),
            flags=sorted(proof.flags),
            unchecked_utterances=sorted(proof.unchecked),
            reason=reason,
        )

    def paths(self, calls: dict[str, ia.CallInspection]) -> list[ia.LearningPath]:
        found = set()
        rows = []
        for a in self.attempts.values():
            d = a.decision
            key = (a.event.actor_id, a.rule)
            if a.applied and a.rule and d and d.origin == "model" and key not in found:
                found.add(key)
                rows.append(self.path(a, d, calls[d.call_ids[-1]]))
        return rows

    def scores(self) -> list[ia.SkillScore]:
        scores = []
        for first in self.history.first.values():
            record = self.history.records[first]
            if not isinstance(record.content, ia.Skill):
                continue
            creator = self.history.creation.get(record.id)
            proof = Proof()
            proof.links.append(revision_link(record.owner_id, first))
            proof.trace.update([record.id, str(first.store_version), first.content_hash])
            creator_call = creator.change_set_call_id if creator else None
            if creator_call:
                proof.links.append(
                    link("calls", creator_call, "Hypothesis creator " + creator_call)
                )
                proof.trace.add(creator_call)
            sources = [s.model_dump_json() for s in record.sources]
            for ancestor, body in self.history.ancestors(first):
                if ancestor != first:
                    proof.links.append(revision_link(record.owner_id, ancestor))
                    proof.trace.add(ancestor.content_hash)
                for src in body.sources:
                    entry = (
                        self.history.entries.get((record.owner_id, src.entry_id))
                        if src.kind == "observed"
                        else self.heard.get((record.owner_id, src.utterance_id))
                        if src.kind == "told"
                        else None
                    )
                    if entry:
                        proof.entry(entry)
            count = matched = fallback = watched = 0
            supplied = record.content.evidence.attempts
            latest = self.history.latest.get(record.id, record).content
            writes = self.writes[record.id]
            if isinstance(latest, ia.Skill) and (
                latest.evidence.attempts
                != supplied + sum(s.delta.get("attempts", 0) for _, s in writes)
                or latest.evidence.matched_expected
                != record.content.evidence.matched_expected
                + sum(s.delta.get("matched_expected", 0) for _, s in writes)
            ):
                proof.missing.add("incomplete evidence writes for recorded skill counters")
            for key, skill in writes:
                proof.links.extend(
                    [
                        link("evidence_writes", key, "Evidence write " + key),
                        revision_link(record.owner_id, skill.hypothesis),
                    ]
                )
                proof.trace.update(
                    [
                        key,
                        skill.intent_id,
                        str(skill.hypothesis.store_version),
                        skill.hypothesis.content_hash,
                    ]
                )
                a = self.attempts.get(skill.intent_id)
                if a:
                    proof.attempt(a)
                if (
                    not a
                    or skill.hypothesis not in self.history.records
                    or a.event.actor_id != skill.actor_id
                ):
                    proof.missing.add("missing settlement or immutable hypothesis")
                elif skill.delta.get("watched"):
                    watched += skill.delta["watched"]
                elif not a.decision:
                    proof.missing.add("missing originating decision")
                elif a.decision.origin == "fallback":
                    fallback += skill.delta.get("attempts", 0)
                elif a.decision.origin == "model":
                    count += skill.delta.get("attempts", 0)
                    matched += skill.delta.get("matched_expected", 0)
            base = row_fields(record.owner_id, "skill_accuracy", proof.trace, proof.links)
            scores.append(
                ia.SkillScore(
                    **base.model_dump(),
                    revision=first,
                    prediction=record.content.hypothesis.model_dump_json(),
                    sources=sources,
                    creator_call=creator_call,
                    origin="self_found" if creator_call else "supplied",
                    attempts=None if proof.missing else count,
                    matched_expected=None if proof.missing else matched,
                    watched=watched,
                    supplied_attempts=supplied,
                    fallback_attempts=fallback,
                    accuracy=str(Fraction(matched, count)) if count and not proof.missing else None,
                    reason="; ".join(sorted(proof.missing))
                    or ("no qualifying observations" if not count else None),
                )
            )
        return scores


def resident_analysis(
    history: History,
    decisions: list[ia.DecisionRecord],
    calls: dict[str, ia.CallInspection],
    events: list[ia.WorldEvent],
    checks: list[ia.ContentCheck],
    entries: dict[str, DayEntry],
    residents: list[ia.Resident],
    packs: list[ia.PackPin],
) -> ia.ResidentAnalysis:
    view = Learning(history, events, decisions, checks, entries)
    skills = view.scores()
    activity = continuity(history, decisions, calls, entries)
    summary = []
    for resident in residents:
        actor = resident.resident_id
        own = [s for s in skills if s.resident_id == actor and s.origin == "self_found"]
        uses = [u for u in activity.uses if u.resident_id == actor]
        summary.append(
            ia.ResidentSummary(
                resident_id=actor,
                self_found_skills=len(own),
                accuracy_distribution=sorted(
                    (s.accuracy for s in own if s.accuracy is not None), key=Fraction
                ),
                later_period_uses=sum(
                    u.created_period is not None and u.created_period != u.period_id for u in uses
                ),
                prior_day_uses=sum(
                    u.created_day is not None and u.created_day < u.day for u in uses
                ),
                unknown_use_origins=sum(u.created_period is None for u in uses),
            )
        )
    return ia.ResidentAnalysis(
        packs=[p.pack_id for p in packs],
        residents=summary,
        learning=view.paths(calls),
        skills=skills,
        uses=activity.uses,
        periods=activity.periods,
        consolidations=activity.consolidations,
    )
