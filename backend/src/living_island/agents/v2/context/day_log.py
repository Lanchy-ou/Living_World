"""Append-only working memory built from a resident's own deliveries."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from living_island.agents.v2.calls.journal import Journal
from living_island.memory.v2.projections import ProjectedRevision, RevisionRef
from living_island.world.v2 import protocol as wap

from .delivery import FilteredDelivery
from .dialogue import terms_words
from .entries import (
    CueRef,
    DayEntry,
    DeliberateRecall,
    EntityRef,
    EntryRef,
    EntryType,
    FeedbackRef,
    HeardRef,
    InspectionRef,
    LocalRecall,
    ObservedRef,
    ReportRef,
    TurnRef,
    UtteranceFeedbackRef,
)
from .state import look_words

type Awareness = Literal["awake", "asleep", "unconscious"]
type LookSignature = tuple[tuple[str, str], ...]


def _bounded(text: str) -> str:
    if len(text) <= 1000:
        return text
    # A complete word ending at offset 999 still fits beside the ellipsis.
    head = text[:999]
    if not text[999].isspace():
        head = head[: max((i + 1 for i, char in enumerate(head) if char.isspace()), default=0)]
    return head.rstrip() + "…"


def _place(position: wap.Coord) -> str:
    return f"{position.x},{position.y}"


def _look_keys(entity: wap.InspectView) -> set[str]:
    keys = {f"entity:{entity.entity_id}"}
    if entity.archetype_id is not None:
        keys.add(f"archetype:{entity.archetype_id}")
    if entity.material_id is not None:
        keys.add(f"material:{entity.material_id}")
    return keys


def _items(items: Iterable[wap.ItemUse], keys: set[str]) -> str:
    portions = []
    for item in items:
        keys.update(_look_keys(item))
        portions.append(f"{item.quantity} × {look_words(item)} ({item.role})")
    return ", ".join(portions)


def _target(look: wap.StartTarget | None, target: wap.Target | None, keys: set[str]) -> str:
    if look is not None:
        if isinstance(look, wap.TileStartTarget):
            place = _place(look.position)
            keys.add(f"place:{place}")
            return f"{look.terrain} at {place}"
        keys.add(f"{look.kind}:{look.id}")
        if look.archetype_id is not None:
            keys.add(f"archetype:{look.archetype_id}")
        if look.material_id is not None:
            keys.add(f"material:{look.material_id}")
        return " ".join(
            word
            for word in (
                look.id,
                look.archetype_id,
                look.material_id,
                *(d.value for d in look.descriptors),
            )
            if word
        )
    if target is None:
        return ""
    if target.kind == "tile":
        place = _place(target.position)
        keys.add(f"place:{place}")
        return place
    keys.add(f"{target.kind}:{target.id}")
    return target.id


@dataclass(frozen=True)
class _Note:
    """Entry content before allocating its period-local ordinal."""

    type: EntryType
    text: str
    ref: EntryRef
    paths: tuple[str, ...]
    keys: Iterable[str] = ()
    tick: int | None = None
    speech: wap.HeardUtterance | None = None


class DayLog:
    def __init__(
        self,
        period_id: str,
        journal: Journal,
        *,
        phenomena: Mapping[str, str],
        prior_awareness: Awareness = "awake",
    ) -> None:
        self.period_id = period_id
        self._journal = journal
        self._phenomena = phenomena
        self._awareness = prior_awareness
        self._looks: dict[str, LookSignature] = {}
        self._entries: list[DayEntry] = []

    @property
    def entries(self) -> tuple[DayEntry, ...]:
        """An immutable snapshot, including while the live log receives sleep packets."""
        return tuple(self._entries)

    def _store(
        self,
        ordinal: int,
        tick: int,
        note: _Note,
        delivery_id: str | None,
        retrieved: RevisionRef | None = None,
    ) -> DayEntry:
        entry = DayEntry(
            id=f"d:{self.period_id}:{ordinal}",
            type=note.type,
            tick=tick if note.tick is None else note.tick,
            text=_bounded(note.text)
            if delivery_id is not None and note.speech is None
            else note.text,
            ref=note.ref,
            about=tuple(sorted(set(note.keys))),
            member_paths=note.paths,
            verbatim=note.speech,
            delivery_id=delivery_id,
            retrieved=retrieved,
        )
        self._journal.blob(entry.canonical)
        self._journal.blob(entry.part.text.encode())
        return entry

    def _append(self, tick: int, note: _Note, retrieved: RevisionRef | None = None) -> DayEntry:
        entry = self._store(len(self._entries) + 1, tick, note, None, retrieved)
        self._entries.append(entry)
        return entry

    def response(self, tick: int, turn_id: str, adopted_raw: str | None) -> DayEntry | None:
        """Sim supplies the exact adopted response text, or None on fallback/non-adoption."""
        if adopted_raw is None:
            return None
        return self._append(tick, _Note("own_response", adopted_raw, TurnRef(turn_id=turn_id), ()))

    def recall(
        self, tick: int, ref: DeliberateRecall | LocalRecall, revision: ProjectedRevision
    ) -> DayEntry:
        record = revision.record
        words = f"You remember: [{record.id}] {record.gist}"
        if record.text:
            words += " " + record.text
        return self._append(tick, _Note("recall", words, ref, ()), revision.ref)

    def empty_recall(self, tick: int, turn_id: str, ordinal: int) -> DayEntry:
        ref = LocalRecall(mode="off_empty", turn_id=turn_id, ordinal=ordinal)
        return self._append(
            tick, _Note("recall", "You cannot remember anything about that.", ref, ())
        )

    def _watched(self, action: wap.ObservedAction, paths: tuple[str, ...]) -> _Note:
        verb = action.verb or action.action
        keys = {f"verb:{verb}", f"resident:{action.actor_id}"}
        phase = {"start": "starts", "settle": "finishes", "stop": "stops"}[action.phase]
        words = f"{action.actor_id} {phase} {verb.replace('_', ' ')}"
        target = _target(action.start_target, action.target, keys)
        if target:
            words += " at " + target
        if action.visible_items:
            words += " with " + _items(action.visible_items, keys)
        if action.phenomena:
            words += ". " + " ".join(self._phenomena[key] for key in action.phenomena)
            keys.update(f"phenomenon:{key}" for key in action.phenomena)
        if action.received_items:
            words += ". You received " + _items(action.received_items, keys)
        return _Note(
            "observation",
            words,
            ObservedRef(intent_id=action.intent_id, phase=action.phase),
            paths,
            keys,
            tick=action.tick,
        )

    def _result(
        self, feedback: wap.ActionFeedback, verb: str, paths: tuple[str, ...]
    ) -> Iterable[_Note]:
        keys = {f"verb:{verb}", *(f"phenomenon:{key}" for key in feedback.phenomena)}
        words = f"Your {verb.replace('_', ' ')} ended: {feedback.status}"
        reason = feedback.failure_code or feedback.stop_reason
        if reason:
            words += ", " + reason.replace("_", " ").lower()
        if feedback.items_used:
            words += ", using " + _items(feedback.items_used, keys)
        target = _target(feedback.start_target, None, keys)
        if target:
            words += " at " + target
        words += "."
        if feedback.phenomena:
            words += " " + " ".join(self._phenomena[key] for key in feedback.phenomena)
        yield _Note("action_result", words, FeedbackRef(intent_id=feedback.intent_id), paths, keys)
        if (inspected := feedback.inspected) is not None:
            yield _Note(
                "inspection",
                f"Looking closely at {look_words(inspected)}",
                InspectionRef(intent_id=feedback.intent_id),
                (paths[0] + ".inspected",),
                _look_keys(inspected),
            )

    def _notes(
        self, delivery: FilteredDelivery, looks: dict[str, LookSignature]
    ) -> Iterable[_Note]:
        packet = delivery.packet
        view = packet.perception
        # Original slots remain resolvable even when sim removed an earlier member.
        reports = {
            (r.kind, r.subject_id): delivery.report_path(index)
            for index, r in enumerate(packet.reports)
        }
        running = view.running_action
        if running is not None and view.awareness == "asleep" and self._awareness != "asleep":
            # Chosen sleep is confirmed by the still-running intent. WAP's
            # identity binding gives its turn ID without fabricating a report.
            yield _Note(
                "sleep",
                "You fall asleep.",
                TurnRef(turn_id=running.intent_id.removesuffix(":a")),
                ("perception.awareness", "perception.running_action.intent_id"),
            )
        sightings = {
            r.subject_id: reports[r.kind, r.subject_id]
            for r in packet.reports
            if r.kind == "entity_first_seen"
        }
        cues = {cue.cue_id for cue in view.environmental_cues}
        seen_fields: tuple[tuple[str, Sequence[wap.ItemView | wap.EntityView]], ...] = (
            ("inventory", view.inventory),
            ("visible_entities", view.visible_entities),
            ("transient_sightings", view.transient_sightings),
        )
        for field, items in seen_fields:
            for index, item in enumerate(items):
                identity = item.entity_id
                if identity in cues:
                    continue  # A transient cue also has its richer cue member.
                signature = tuple((d.property_id, d.value) for d in item.descriptors)
                first = sightings.pop(identity, None)
                if first is None and (
                    field != "visible_entities" or looks.get(identity) == signature
                ):
                    continue
                looks[identity] = signature
                paths = (f"perception.{field}[{index}]",) + ((first,) if first else ())
                keys = _look_keys(item)
                words = look_words(item)
                if isinstance(item, wap.EntityView):
                    place = _place(item.position)
                    words += " at " + place
                    keys.add(f"place:{place}")
                    if item.kind == "resident":
                        keys.add(f"resident:{identity}")
                    if item.observable_signs:
                        words += " (" + ", ".join(item.observable_signs) + ")"
                if item.quantity is not None:
                    words += f" × {item.quantity}"
                yield _Note(
                    "observation", "You see " + words, EntityRef(entity_id=identity), paths, keys
                )
        for index, cue in enumerate(view.environmental_cues):
            if cue.cue_id in sightings:
                place = _place(cue.position)
                where = place + (f", {cue.direction}" if cue.direction else "")
                yield _Note(
                    "observation",
                    f"You notice {cue.physical_description} at {where}",
                    CueRef(cue_id=cue.cue_id),
                    (f"perception.environmental_cues[{index}]", sightings[cue.cue_id]),
                    (f"place:{place}",),
                )

        for index, heard in enumerate(view.heard_utterances):
            target = (
                "you" if heard.addressee_id == view.actor_id else heard.addressee_id or "everyone"
            )
            words = f'{heard.speaker_id} said to {target}: "{heard.text}"'
            words += f" [{heard.speech_act} {heard.utterance_id}]"
            if heard.in_reply_to is not None:
                words += f" in reply to {heard.in_reply_to}"
            speech_keys = [f"resident:{heard.speaker_id}"]
            if heard.addressee_id is not None:
                speech_keys.append(f"resident:{heard.addressee_id}")
            if heard.terms is not None:
                words += " " + terms_words(heard.terms)
                # The closed proposal describes these subjects as heard words.
                # A heard_speech entry remains ineligible as an observed source.
                term = heard.terms.what
                if term.kind == "be_at":
                    speech_keys.append(f"place:{_place(term.position)}")
                elif term.kind == "return_item":
                    speech_keys.append(f"entity:{term.item_id}")
                elif term.kind == "contribute":
                    speech_keys.append(f"entity:{term.process_id}")
                elif isinstance(term.item, wap.ExactItemSpec):
                    speech_keys.append(f"entity:{term.item.item_id}")
                else:
                    speech_keys.append(f"archetype:{term.item.archetype_id}")
            yield _Note(
                "heard_speech",
                words,
                HeardRef(utterance_id=heard.utterance_id, speaker_id=heard.speaker_id),
                (
                    f"perception.heard_utterances[{index}]",
                    reports["utterance_heard", heard.utterance_id],
                ),
                speech_keys,
                heard.heard_at_tick,
                heard,
            )
        for index, watched in enumerate(view.observed_actions):
            yield self._watched(
                watched,
                (
                    f"perception.observed_actions[{index}]",
                    reports["action_observed", watched.intent_id],
                ),
            )
        for feedback in view.action_feedback:
            source = delivery.feedback_sources[feedback.intent_id]
            paths = (
                f"perception.action_feedback[{source.position}]",
                reports["action_ended", feedback.intent_id],
            )
            yield from self._result(feedback, source.action, paths)
        if delivery.own_speech is not None:
            feedback_s = delivery.own_speech.feedback
            spoken = delivery.own_speech.utterance
            to = spoken.addressee_id or "everyone"
            own_keys: tuple[str, ...]
            if feedback_s.failure_code is None:
                words = f'You said to {to}: "{spoken.text}" [{feedback_s.utterance_id}]'
                own_keys = (f"spoke:{feedback_s.utterance_id}",)
            else:
                reason = feedback_s.failure_code.replace("_", " ").lower()
                words = f"Your words to {to} were not said: {reason}"
                own_keys = ()
            yield _Note(
                "utterance_result",
                words,
                UtteranceFeedbackRef(utterance_id=feedback_s.utterance_id),
                ("perception.last_utterance_feedback",),
                own_keys,
            )
        for index, report in enumerate(packet.reports):
            paths = (delivery.report_path(index),)
            ref = ReportRef(report_kind=report.kind, subject_id=report.subject_id)
            if report.kind in ("need_band_changed", "need_threshold_crossed"):
                level = report.band or report.threshold_id
                words = f"You feel {report.subject_id}: {level}."
                yield _Note("body_change", words, ref, paths, (f"need:{report.subject_id}",))
            elif report.kind == "progress_step":
                subject_id = str(report.subject_id)
                progress_keys: tuple[str, ...]
                running_action = view.running_action
                if running_action and running_action.intent_id == subject_id:
                    name = running_action.verb or running_action.action
                    progress = running_action.progress
                    paths += ("perception.running_action",)
                    progress_keys = (f"verb:{name}",)
                elif subject_id in delivery.feedback_sources:
                    # Progress may cross a band on the same tick the action ends.
                    # There is then no running descriptor in the packet.
                    ended = delivery.feedback_sources[subject_id]
                    name = ended.action
                    progress = None
                    paths += (f"perception.action_feedback[{ended.position}]",)
                    progress_keys = (f"verb:{name}",)
                else:
                    name = subject_id
                    progress = None
                    progress_keys = ()
                    for i, entity in enumerate(view.visible_entities):
                        if entity.entity_id == name:
                            progress_keys = (f"entity:{name}",)
                            progress = next(
                                (
                                    d.value
                                    for d in entity.descriptors
                                    if d.property_id == "progress"
                                ),
                                None,
                            )
                            paths += (f"perception.visible_entities[{i}]",)
                            break
                words = (
                    f"Your {name} is {progress.replace('_', ' ')}."
                    if progress
                    else f"Your {name} progressed."
                )
                yield _Note("progress", words, ref, paths, progress_keys)
            elif report.kind == "woke":
                yield _Note("sleep", "You wake.", ref, paths)

    def deliver(self, delivery: FilteredDelivery) -> tuple[DayEntry, ...]:
        """Journal resident senses in packet order, independent of muting and turn scheduling."""
        packet = delivery.packet
        # Blob writes are content-addressed. Commit the log and its change
        # detector together only after every blob in the delivery is durable.
        looks = self._looks.copy()
        entries = tuple(
            self._store(ordinal, packet.observed_tick, note, packet.delivery_id)
            for ordinal, note in enumerate(self._notes(delivery, looks), len(self._entries) + 1)
        )
        self._entries.extend(entries)
        self._looks = looks
        self._awareness = packet.perception.awareness
        return entries
