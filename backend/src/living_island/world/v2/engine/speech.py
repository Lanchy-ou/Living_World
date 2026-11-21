"""Two-phase utterance validation, dialogue bookkeeping and objective speech events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..protocol import HeardUtterance, UtteranceFeedback
from .events import json_object
from .kernel import distance, exposed
from .physiology import hearing_awake
from .state import Agreement, DialogueSession, Proposal
from .terms import valid_terms

if TYPE_CHECKING:
    from ..protocol import FailureCode, IntegerJson
    from .events import EventType
    from .state import DialogueLimits
    from .tick import SpeechAttempt, TickContext


def dialogue_pair(speaker_id: str, addressee_id: str) -> tuple[str, str]:
    return (speaker_id, addressee_id) if speaker_id < addressee_id else (addressee_id, speaker_id)


def check_utterance(
    ctx: TickContext, attempt: SpeechAttempt, *, emission: bool
) -> FailureCode | None:
    state = ctx.state
    utterance = attempt.utterance
    speaker_id = attempt.actor_id
    addressee_id = utterance.addressee_id
    if addressee_id is None:
        return None  # The turn DTO permits only a statement here.

    if addressee_id == speaker_id or not exposed(state, speaker_id, addressee_id):
        return "INVALID_TARGET"
    recipient = state.residents.get(addressee_id)
    if recipient is None or not recipient.alive:
        return "INVALID_TARGET"
    if (
        distance(state.residents[speaker_id].position, recipient.position)
        > state.senses.hearing_radius
    ):
        return "OUT_OF_HEARING"

    reply_id = utterance.in_reply_to
    if reply_id is not None:
        proposal = state.proposals.get(reply_id)
        if (
            proposal is None
            or proposal.speaker_id != addressee_id
            or proposal.addressee_id != speaker_id
            or proposal.answer is not None
        ):
            return "INVALID_REPLY"

    if utterance.terms is not None and not valid_terms(
        state,
        ctx.pack,
        speaker_id,
        addressee_id,
        utterance.terms,
        ctx.tick if emission else state.tick,
    ):
        return "INVALID_TERMS"

    if emission:
        session = state.dialogue_sessions.get(dialogue_pair(speaker_id, addressee_id))
        if state.dialogue_limits.max_turns == 0 or (
            session is not None and ctx.tick < session.cooldown_until_tick
        ):
            return "DIALOGUE_LIMIT"
    return None


def check_start(ctx: TickContext, attempt: SpeechAttempt) -> None:
    """Check an utterance before its actor starts or progresses."""
    attempt.failure = check_utterance(ctx, attempt, emission=False)


def advance_session(
    pair: tuple[str, str], previous: DialogueSession | None, limits: DialogueLimits, tick: int
) -> DialogueSession:
    turn_count = 1
    if (
        previous is not None
        and previous.turn_count < limits.max_turns
        and tick - previous.last_utterance_tick <= limits.gap_ticks
    ):
        turn_count += previous.turn_count
    cooldown_until = tick + limits.cooldown_ticks if turn_count == limits.max_turns else 0
    return DialogueSession(pair, turn_count, tick, cooldown_until)


def emit_speech_event(
    ctx: TickContext,
    attempt: SpeechAttempt,
    kind: EventType,
    payload: dict[str, IntegerJson],
    *,
    actor_id: str,
    target_id: str | None,
    causes: tuple[str, ...] = (),
    identity_field: str | None = None,
) -> str:
    """Use the tick's event cursor while retaining the speech-specific actors and targets."""
    event = ctx.writer.emit(kind, payload, actor_id=actor_id, target_id=target_id, caused_by=causes)
    if identity_field is not None:
        event.payload[identity_field] = event.event_id
    if attempt.intent_id is not None:
        # The listener and addressee can differ from the companion action's actors.
        ctx.writer.events[-1] = event.model_copy(update={"intent_id": attempt.intent_id})
        ctx.started_actions[attempt.intent_id].event_ids.append(event.event_id)
    return event.event_id


def settle_utterance(ctx: TickContext, attempt: SpeechAttempt) -> None:
    """Apply the second check and publish speech in settlement order."""
    speaker_id = attempt.actor_id
    failure = attempt.failure
    if failure is None:
        failure = check_utterance(ctx, attempt, emission=True)
    if failure is not None:
        ctx.utterances[speaker_id] = UtteranceFeedback.model_construct(
            utterance_id=None, failure_code=failure
        )
        return

    state = ctx.state
    utterance = attempt.utterance
    addressee_id = utterance.addressee_id
    reply_id = utterance.in_reply_to
    utterance_id = emit_speech_event(
        ctx,
        attempt,
        "utterance_spoken",
        json_object(utterance.model_dump(mode="json")),
        actor_id=speaker_id,
        target_id=addressee_id,
        causes=() if reply_id is None else (reply_id,),
        identity_field="utterance_id",
    )
    heard = HeardUtterance.model_construct(
        utterance_id=utterance_id,
        speaker_id=speaker_id,
        addressee_id=addressee_id,
        speech_act=utterance.speech_act,
        text=utterance.text,
        terms=utterance.terms,
        in_reply_to=reply_id,
        heard_at_tick=ctx.tick,
    )
    speaker_position = state.residents[speaker_id].position
    for listener_id, listener in sorted(state.residents.items()):
        if (
            listener_id != speaker_id
            and listener.alive
            and distance(speaker_position, listener.position) <= state.senses.hearing_radius
            and hearing_awake(ctx, listener_id)
        ):
            emit_speech_event(
                ctx,
                attempt,
                "utterance_heard",
                {"utterance_id": utterance_id, "listener_id": listener_id},
                actor_id=listener_id,
                target_id=speaker_id,
                causes=(utterance_id,),
            )
            ctx.heard.setdefault(listener_id, []).append(heard)

    if addressee_id is not None:
        pair = dialogue_pair(speaker_id, addressee_id)
        state.dialogue_sessions[pair] = advance_session(
            pair, state.dialogue_sessions.get(pair), state.dialogue_limits, ctx.tick
        )
        if utterance.terms is not None:
            state.proposals[utterance_id] = Proposal(
                utterance_id, speaker_id, addressee_id, utterance.terms, pair
            )

    if reply_id is not None:
        proposal = state.proposals[reply_id]
        if utterance.speech_act == "accept":
            proposal.answer = "accept"
            agreement_id = emit_speech_event(
                ctx,
                attempt,
                "agreement_accepted",
                {
                    "proposal_id": reply_id,
                    "acceptance_id": utterance_id,
                    "terms": json_object(proposal.terms.model_dump(mode="json")),
                },
                actor_id=speaker_id,
                target_id=addressee_id,
                causes=(reply_id, utterance_id),
                identity_field="agreement_id",
            )
            state.agreements[agreement_id] = Agreement(
                agreement_id, reply_id, utterance_id, proposal.terms, ctx.tick
            )
        else:
            proposal.answer = "refuse"

    ctx.utterances[speaker_id] = UtteranceFeedback.model_construct(
        utterance_id=utterance_id, failure_code=None
    )
