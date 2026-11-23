"""A resident's working conversations, derived from delivered speech and feedback."""

from dataclasses import dataclass

from living_island.world.v2 import protocol as wap

from .delivery import FilteredDelivery


def terms_words(terms: wap.Terms) -> str:
    what = terms.what
    if what.kind == "give_item":
        item = what.item
        detail = (
            item.item_id
            if isinstance(item, wap.ExactItemSpec)
            else f"{item.quantity} {item.archetype_id}"
        )
        action = f"give {detail}"
    elif what.kind == "return_item":
        action = f"return {what.item_id}"
    elif what.kind == "be_at":
        action = f"be at ({what.position.x},{what.position.y})"
    else:
        action = f"contribute {what.work_ticks} ticks to {what.process_id}"
    due = "" if terms.due_tick is None else f" by tick {terms.due_tick}"
    return f"{terms.promisor_id} would {action} for {terms.promisee_id}{due}"


@dataclass(frozen=True)
class Proposal:
    utterance_id: str
    text: str
    terms: wap.Terms


@dataclass(frozen=True)
class DialogueSession:
    resident_id: str
    counterpart_id: str
    last_tick: int
    unanswered: tuple[Proposal, ...]
    awaiting_counterpart: tuple[str, ...]

    @property
    def reply_due(self) -> tuple[str, ...]:
        people = []
        if self.unanswered:
            people.append(self.resident_id)
        if self.awaiting_counterpart:
            people.append(self.counterpart_id)
        return tuple(people)

    def words(self) -> str:
        lines = [f"Talking with {self.counterpart_id} (last spoke at tick {self.last_tick})."]
        for proposal in self.unanswered:
            lines.append(
                f'Unanswered proposal {proposal.utterance_id}: "{proposal.text}" '
                f"({terms_words(proposal.terms)})."
            )
        if self.reply_due:
            lines.append(f"Reply due from {', '.join(self.reply_due)}.")
        return "\n".join(lines)


class DialogueState:
    def __init__(self, resident_id: str, gap_ticks: int) -> None:
        self.resident_id = resident_id
        self.gap_ticks = gap_ticks
        self._sessions: dict[str, DialogueSession] = {}

    @classmethod
    def restore(
        cls, resident_id: str, gap_ticks: int, sessions: tuple[DialogueSession, ...]
    ) -> "DialogueState":
        state = cls(resident_id, gap_ticks)
        state._sessions = {session.counterpart_id: session for session in sessions}
        return state

    @property
    def sessions(self) -> tuple[DialogueSession, ...]:
        return tuple(self._sessions[key] for key in sorted(self._sessions))

    def end_period(self) -> None:
        self._sessions.clear()

    def receive(self, delivery: FilteredDelivery) -> None:
        packet = delivery.packet
        speech: list[tuple[int, str, str, wap.Utterance]] = [
            (heard.heard_at_tick, heard.utterance_id, heard.speaker_id, heard)
            for heard in packet.perception.heard_utterances
            if heard.addressee_id == self.resident_id
        ]
        own = delivery.own_speech
        if own is not None and own.feedback.utterance_id is not None:
            speech.append(
                (packet.observed_tick, own.feedback.utterance_id, self.resident_id, own.utterance)
            )
        for tick, utterance_id, speaker, utterance in sorted(speech, key=lambda item: item[:2]):
            self._addressed(tick, utterance_id, speaker, utterance)
        self._sessions = {
            peer: session
            for peer, session in self._sessions.items()
            if packet.observed_tick - session.last_tick <= self.gap_ticks
        }

    def _addressed(self, tick: int, utterance_id: str, speaker: str, words: wap.Utterance) -> None:
        if words.addressee_id is None:
            return
        own = speaker == self.resident_id
        peer = words.addressee_id if own else speaker
        last = self._sessions.get(peer)
        if last is None or tick - last.last_tick > self.gap_ticks:
            last = DialogueSession(self.resident_id, peer, tick, (), ())
        unanswered = last.unanswered
        awaiting = last.awaiting_counterpart
        if words.terms is not None:
            if own:
                awaiting += (utterance_id,)
            else:
                unanswered += (Proposal(utterance_id, words.text, words.terms),)
        elif words.in_reply_to is not None:
            if own:
                unanswered = tuple(p for p in unanswered if p.utterance_id != words.in_reply_to)
            else:
                awaiting = tuple(key for key in awaiting if key != words.in_reply_to)
        self._sessions[peer] = DialogueSession(self.resident_id, peer, tick, unanswered, awaiting)
