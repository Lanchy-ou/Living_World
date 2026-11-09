"""Talk preconditions, unordered sessions, and speech payloads."""

from collections.abc import Mapping

from living_island.world.actions import distance
from living_island.world.content import EffectiveConfig
from living_island.world.facts import UtteranceRequest, UtteranceSpokenPayload
from living_island.world.protocol import ActionIntent, FailureCode, ResidentTarget, TalkParameters
from living_island.world.state import DialogueSessionState, ResidentPhysicalState, WorldState


def _session(
    state: WorldState,
    pair: list[str],
) -> DialogueSessionState | None:
    return next((session for session in state.dialogue_sessions if session.pair_ids == pair), None)


def validate_talk(
    config: EffectiveConfig,
    state: WorldState,
    actor: ResidentPhysicalState,
    intent: ActionIntent,
    tick: int,
    requests: Mapping[str, tuple[str, str]],
) -> FailureCode | None:
    # The engine has already checked the exposure receipt.
    target = intent.target
    params = intent.parameters
    assert isinstance(target, ResidentTarget) and isinstance(params, TalkParameters)
    recipient = next((r for r in state.residents if r.id == target.id), None)
    if recipient is None or not recipient.alive or recipient.id == actor.id:
        return "INVALID_TARGET"
    if distance(actor.position, recipient.position) > config.perception.hearing_radius_tiles:
        return "OUT_OF_HEARING"
    if params.in_reply_to is not None and requests.get(params.in_reply_to) != (
        recipient.id,
        actor.id,
    ):
        return "INVALID_REPLY"
    session = _session(state, sorted([actor.id, recipient.id]))
    if config.social.max_dialogue_turns == 0 or (session and tick < session.cooldown_until_tick):
        return "DIALOGUE_LIMIT"
    return None


def count_turn(
    config: EffectiveConfig, state: WorldState, speaker: str, addressee: str, tick: int
) -> None:
    pair = sorted([speaker, addressee])
    previous = _session(state, pair)
    turns = 1
    if (
        previous is not None
        and previous.turn_count < config.social.max_dialogue_turns
        and tick - previous.last_utterance_tick <= config.social.dialogue_gap_ticks
    ):
        turns += previous.turn_count
    cooldown = (
        tick + config.social.dialogue_cooldown_ticks
        if (turns == config.social.max_dialogue_turns)
        else 0
    )
    session = DialogueSessionState(
        pair_ids=pair,
        turn_count=turns,
        last_utterance_tick=tick,
        cooldown_until_tick=cooldown,
    )
    state.dialogue_sessions = sorted(
        [s for s in state.dialogue_sessions if s.pair_ids != pair] + [session],
        key=lambda s: s.pair_ids,
    )


def speech_payload(intent: ActionIntent, utterance_id: str) -> UtteranceSpokenPayload:
    target = intent.target
    params = intent.parameters
    assert isinstance(target, ResidentTarget) and isinstance(params, TalkParameters)
    return UtteranceSpokenPayload(
        utterance_id=utterance_id,
        addressee_id=target.id,
        speech_act=params.speech_act,
        text=params.text,
        request=(
            UtteranceRequest(item_type=params.request.item_type, quantity=params.request.quantity)
            if params.request is not None
            else None
        ),
        in_reply_to=params.in_reply_to,
    )
