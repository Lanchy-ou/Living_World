"""Select resident-visible memories from the cues that triggered this turn."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

from living_island.agents.v2.context.delivery import FilteredDelivery
from living_island.agents.v2.context.entries import DayEntry, LocalRecall
from living_island.agents.v2.context.working import WorkingContext
from living_island.memory.v2.kinds import BUILTINS
from living_island.memory.v2.projections import ProjectedRevision, ResidentView
from living_island.memory.v2.records import Belief, Envelope, Look, Skill, Social, VisibleCommitment


def strength(record: Envelope, tick: int) -> int:
    last = record.created_tick if record.last_used_tick is None else record.last_used_tick
    days = (tick - last) // 144
    return 20 * record.confidence + min(40, 10 * record.use_count) + max(0, 40 - 10 * days)


@dataclass(frozen=True)
class RecipeCues:
    tick: int
    reasons: frozenset[str]
    speakers: frozenset[str] = frozenset()
    body_topics: frozenset[str] = frozenset()
    discovered_entities: frozenset[str] = frozenset()
    discovered_residents: frozenset[str] = frozenset()
    archetypes: frozenset[str] = frozenset()
    materials: frozenset[str] = frozenset()
    ended_verbs: frozenset[str] = frozenset()
    phenomena: frozenset[str] = frozenset()
    visible_residents: frozenset[str] = frozenset()

    @classmethod
    def from_delivery(
        cls,
        delivery: FilteredDelivery,
        *,
        reasons: frozenset[str],
        act_intent_ids: frozenset[str] = frozenset(),
    ) -> Self:
        """Sim supplies scheduled reason/class names and the IDs submitted as generic act."""
        packet = delivery.packet
        view = packet.perception
        reports = packet.reports
        ended = {report.subject_id for report in reports if report.kind == "action_ended"}
        # Sim retains the neutral end signal when it strips fallback outcome feedback.
        # An end report alone must not select even a registered action-ended recipe.
        feedback = [item for item in view.action_feedback if item.intent_id in ended]
        acts = [item for item in feedback if item.intent_id in act_intent_ids]
        heard_ids = {
            report.subject_id
            for report in reports
            if report.kind == "utterance_heard"
            and ("direct_speech" if report.addressed else "nearby_speech") in reasons
        }
        needs = {
            report.subject_id
            for report in reports
            if report.kind in ("need_band_changed", "need_threshold_crossed")
        }
        first_seen = {report.subject_id for report in reports if report.kind == "entity_first_seen"}
        entities = (*view.visible_entities, *view.transient_sightings)
        looks = [item for item in (*entities, *view.inventory) if item.entity_id in first_seen]
        return cls(
            tick=packet.observed_tick,
            reasons=reasons if feedback else reasons - {"action_ended"},
            speakers=frozenset(
                u.speaker_id for u in view.heard_utterances if u.utterance_id in heard_ids
            ),
            body_topics=frozenset(
                topic
                for need, topic in (("satiety", "food"), ("hydration", "water"))
                if need in needs
            ),
            discovered_entities=frozenset(item.entity_id for item in looks),
            discovered_residents=frozenset(
                e.entity_id for e in entities if e.kind == "resident" and e.entity_id in first_seen
            ),
            archetypes=frozenset(
                item.archetype_id for item in looks if item.archetype_id is not None
            ),
            materials=frozenset(item.material_id for item in looks if item.material_id is not None),
            ended_verbs=frozenset(
                delivery.feedback_sources[item.intent_id].action for item in acts
            ),
            phenomena=frozenset(key for item in acts for key in item.phenomena),
            visible_residents=frozenset(
                e.entity_id for e in view.visible_entities if e.kind == "resident"
            ),
        )


type Recipe = Callable[[RecipeCues, ProjectedRevision], bool]


def _commitment_cue(cues: RecipeCues, revision: ProjectedRevision) -> bool:
    content = revision.record.content
    return isinstance(content, VisibleCommitment) and (
        content.counterpart_id in cues.visible_residents
        or (content.due_tick is not None and 0 <= content.due_tick - cues.tick <= 24)
    )


def _speech(cues: RecipeCues, revision: ProjectedRevision) -> bool:
    match revision.record.content:
        case Social(about=who) | VisibleCommitment(counterpart_id=who):
            return who in cues.speakers
        case Belief(subject=subject):
            return subject.kind == "resident" and subject.ref in cues.speakers
    return False


def _body(cues: RecipeCues, revision: ProjectedRevision) -> bool:
    content = revision.record.content
    return isinstance(content, Belief) and not cues.body_topics.isdisjoint(content.topics)


def _action_ended(cues: RecipeCues, revision: ProjectedRevision) -> bool:
    content = revision.record.content
    return isinstance(content, Skill) and (
        content.hypothesis.verb in cues.ended_verbs
        or not cues.phenomena.isdisjoint(content.hypothesis.expected)
    )


def _discovery(cues: RecipeCues, revision: ProjectedRevision) -> bool:
    match revision.record.content:
        case Belief(subject=subject):
            return (
                (subject.kind == "entity" and subject.ref in cues.discovered_entities)
                or (subject.kind == "resident" and subject.ref in cues.discovered_residents)
                or (subject.kind == "kind_of_thing" and subject.ref in cues.archetypes)
            )
        case Skill(hypothesis=hypothesis):
            looks = [*hypothesis.instruments, *(entry.look for entry in hypothesis.inputs)]
            if isinstance(hypothesis.target, Look):
                looks.append(hypothesis.target)
            return any(
                look.archetype_id in cues.archetypes or look.material_id in cues.materials
                for look in looks
            )
    return False


class RecipeRegistry:
    """Per-harness registry. A recipe matches one projected record for a turn reason."""

    def __init__(self) -> None:
        builtins: dict[str, Recipe] = {
            "action_ended": _action_ended,
            "direct_speech": _speech,
            "nearby_speech": _speech,
            "body": _body,
            "discovery": _discovery,
        }
        self._recipes: dict[str, list[tuple[str | None, Recipe]]] = {}
        for reason, predicate in builtins.items():
            for definition in BUILTINS:
                if reason in definition.recipes:
                    self.register(reason, predicate, kind=definition.schema.kind)

    def register(self, reason: str, predicate: Recipe, *, kind: str | None = None) -> None:
        """Bind a predicate to a turn reason, optionally for one registered memory kind."""
        self._recipes.setdefault(reason, []).append((kind, predicate))

    def select(
        self, view: ResidentView, cues: RecipeCues, context: WorkingContext
    ) -> tuple[ProjectedRevision, ...]:
        seen = {fragment.revision.id for fragment in context.prefix.memories}
        seen.update(e.retrieved.id for e in context.log.entries if e.retrieved is not None)
        recipes = [
            recipe for reason in sorted(cues.reasons) for recipe in self._recipes.get(reason, ())
        ]
        ranked = []
        for revision in view.live():
            if revision.ref.id in seen or (
                revision.record.kind == "skill" and "refuted" in revision.flags
            ):
                continue
            score = strength(revision.record, cues.tick)
            priority = _commitment_cue(cues, revision)
            if priority or (
                score >= 20
                and any(
                    (kind is None or kind == revision.record.kind) and match(cues, revision)
                    for kind, match in recipes
                )
            ):
                ranked.append(((not priority, -score, revision.ref.id), revision))
        ranked.sort(key=lambda item: item[0])
        return tuple(revision for _, revision in ranked[:5])

    def append(
        self, view: ResidentView, cues: RecipeCues, context: WorkingContext, turn_id: str
    ) -> tuple[DayEntry, ...]:
        """Append at most five recipe entries for the turn, including on re-entry."""
        entries = [
            entry
            for entry in context.log.entries
            if isinstance(entry.ref, LocalRecall)
            and entry.ref.mode == "recipe"
            and entry.ref.turn_id == turn_id
        ]
        for revision in self.select(view, cues, context)[: 5 - len(entries)]:
            ref = LocalRecall(mode="recipe", turn_id=turn_id, ordinal=len(entries) + 1)
            entries.append(context.log.recall(cues.tick, ref, revision))
        return tuple(entries)
