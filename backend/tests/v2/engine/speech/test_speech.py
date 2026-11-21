"""Exercise speech through the real tick, including both hearing checks."""

from copy import deepcopy
from dataclasses import replace

import pytest

A, B, C = "res_a", "res_b", "res_c"
SPEECH_EVENTS = {"utterance_spoken", "utterance_heard", "agreement_accepted"}


def statement(addressee):
    return {
        "addressee_id": addressee,
        "speech_act": "statement",
        "text": "Can you hear me?",
        "terms": None,
        "in_reply_to": None,
    }


def turn(world, actor, *, utterance=None, action="wait", target=None):
    turn_id = f"{actor}:t{world.state.turn_ordinals[actor]:06d}"
    return {
        "schema_version": "wap/0.1",
        "turn_id": turn_id,
        "actor_id": actor,
        "observed_tick": world.state.tick,
        "utterance": utterance,
        "action": {"kind": "continue"}
        if action == "continue"
        else {
            "kind": "intent",
            "intent": {
                "intent_id": f"{turn_id}:a",
                "turn_id": turn_id,
                "actor_id": actor,
                "action": action,
                "target": target,
                "params": {},
                "verb": None,
                "instruments": [],
                "inputs": [],
                "reason": None,
            },
        },
    }


def tile(x, y=1):
    return {"kind": "tile", "position": {"x": x, "y": y}}


def speech_events(result):
    return [event for event in result.events if event.type in SPEECH_EVENTS]


@pytest.mark.parametrize("speaker,mover", [(A, B), (B, A)])
@pytest.mark.parametrize("movement", ["enter", "leave", "stay"])
def test_wap29_start_and_emission_in_both_actor_orders(world, deliveries, speaker, mover, movement):
    from living_island.world.v2.protocol import Coord

    start, end = {"enter": (4, 3), "leave": (3, 4), "stay": (3, 2)}[movement]
    world.state.residents[speaker].position = Coord(x=1, y=1)
    world.state.residents[mover].position = Coord(x=start, y=1)
    result = world.step(
        [
            turn(world, speaker, utterance=statement(mover)),
            turn(world, mover, action="move_to", target=tile(end)),
        ]
    )

    moved = next(event for event in result.events if event.type == "resident_moved")
    started = next(
        event
        for event in result.events
        if event.type == "action_started" and event.actor_id == speaker
    )
    assert (moved.seq_in_tick < started.seq_in_tick) == (mover < speaker)
    assert moved.tick == started.tick == world.state.tick == 1
    assert world.state.residents[mover].position.x == end
    action = next(action for action in result.actions if action.actor_id == speaker)
    assert (action.outcome, action.tick_started, action.tick_finished) == ("success", 0, 1)
    feedback = result.utterances[speaker]
    assert deliveries[-1].utterances[speaker] == feedback

    succeeded = movement == "stay" or (movement == "enter" and mover < speaker)
    if succeeded:
        spoken, heard = speech_events(result)
        assert moved.seq_in_tick < spoken.seq_in_tick
        assert heard.actor_id == mover
        assert feedback.utterance_id == spoken.event_id
        assert feedback.failure_code is None
    else:
        assert not speech_events(result)
        assert not deliveries[-1].heard
        assert not world.state.dialogue_sessions
        assert feedback.utterance_id is None
        assert feedback.failure_code == "OUT_OF_HEARING"


def test_speaker_is_checked_before_its_own_movement(world):
    from living_island.world.v2.protocol import Coord

    world.state.residents[B].position = Coord(x=4, y=1)
    result = world.step([turn(world, A, action="move_to", target=tile(2), utterance=statement(B))])
    assert world.state.residents[A].position.x == 2
    assert result.utterances[A].failure_code == "OUT_OF_HEARING"
    assert not speech_events(result)
    assert result.actions[0].outcome == "success"


@pytest.mark.parametrize("target_case", ["unexposed", "stale", "dead", "entity", "self"])
def test_invalid_target_does_not_fail_companion_action(world, target_case):
    from living_island.world.v2.engine.state import Exposure
    from living_island.world.v2.protocol import Coord

    receipts = world.state.exposure_receipts_by_resident[A].entities
    target = B
    match target_case:
        case "unexposed":
            del receipts[B]
        case "stale":
            target = "missing"
            receipts[target] = Exposure(target, Coord(x=1, y=1))
        case "dead":
            world.state.residents[B].alive = False
        case "entity":
            target = "inst_a"
        case "self":
            target = A
    result = world.step([turn(world, A, utterance=statement(target))])
    assert result.utterances[A].failure_code == "INVALID_TARGET"
    assert result.actions[0].outcome == "success"
    assert not speech_events(result)


def test_wap03_and_en08_continue_utterance_uses_a_separate_completion(
    audience, deliveries, monkeypatch
):
    from living_island.world.v2.engine import tick

    timing = audience.pack.timing
    audience.pack = replace(
        audience.pack, timing=replace(timing, durations={**timing.durations, "wait": 3})
    )
    actual_shuffle = tick.shuffle
    completion_keys = []

    def observe_completions(completions, rng):
        completion_keys.append([(entry.actor_id, entry.key) for entry in completions])
        return actual_shuffle(completions, rng)

    monkeypatch.setattr(tick, "shuffle", observe_completions)
    first = audience.step([turn(audience, A)])
    assert not first.actions
    control = deepcopy(audience)

    second = audience.step([turn(audience, A, action="continue", utterance=statement(B))])
    control.step()
    assert not second.actions
    assert completion_keys[1] == [(A, f"{A}:t000001:u")]
    assert audience.state.active_actions[A] == control.state.active_actions[A]
    spoken, direct, overhead = speech_events(second)
    assert [direct.actor_id, overhead.actor_id] == [B, C]
    assert spoken.intent_id is None
    assert deliveries[1].utterances[A] == second.utterances[A]
    assert A not in deliveries[1].heard
    assert {
        actor: (items[0].heard_at_tick, items[0].addressee_id == actor)
        for actor, items in deliveries[1].heard.items()
    } == {B: (2, True), C: (2, False)}

    third = audience.step([turn(audience, A, action="continue", utterance=statement(B))])
    control_end = control.step()
    assert completion_keys[3] == [(A, f"{A}:t000000:a"), (A, f"{A}:t000002:u")]
    assert third.actions[0].visible_feedback == control_end.actions[0].visible_feedback
    assert third.actions[0].tick_finished == control_end.actions[0].tick_finished == 3
    assert audience.state.resolution_rng_state_uint32 != control.state.resolution_rng_state_uint32
    assert all(event.intent_id is None for event in speech_events(third))
    absent = audience.step()
    assert not absent.utterances
    assert not deliveries[-1].heard


def test_en08_attached_emission_precedes_action_settlement(world):
    result = world.step([turn(world, A, utterance=statement(B))])
    spoken, heard = speech_events(result)
    (action,) = result.actions
    completed = next(event for event in result.events if event.type == "action_succeeded")
    assert spoken.seq_in_tick < heard.seq_in_tick < completed.seq_in_tick
    assert spoken.intent_id == heard.intent_id == completed.intent_id == action.intent_id
    assert {spoken.event_id, heard.event_id} <= set(action.event_ids)
    assert result.utterances[A].utterance_id == spoken.event_id


def test_en08_speech_on_a_long_new_action_has_its_own_completion(world, monkeypatch):
    from living_island.world.v2.engine import tick

    timing = world.pack.timing
    world.pack = replace(
        world.pack, timing=replace(timing, durations={**timing.durations, "wait": 2})
    )
    keys = []
    actual_shuffle = tick.shuffle

    def observe_completions(completions, rng):
        keys.extend(entry.key for entry in completions)
        return actual_shuffle(completions, rng)

    monkeypatch.setattr(tick, "shuffle", observe_completions)
    result = world.step([turn(world, A, utterance=statement(B))])
    assert not result.actions
    assert keys == [f"{A}:t000000:u"]
    spoken, _ = speech_events(result)
    assert world.state.active_actions[A].intent.intent_id == spoken.intent_id
    assert world.step().actions[0].tick_finished == 2


def test_broadcast_reaches_awake_listeners_without_session_or_action_target(audience, deliveries):
    from living_island.world.v2.engine.state import Awareness

    audience.state.awareness[C] = Awareness("asleep")
    audience.state.dialogue_limits = replace(audience.state.dialogue_limits, max_turns=0)
    result = audience.step(
        [
            turn(
                audience,
                A,
                utterance=statement(None),
                action="inspect",
                target={"kind": "entity", "id": "inst_a"},
            )
        ]
    )
    spoken, heard = speech_events(result)
    assert spoken.target_id is None
    assert spoken.payload["addressee_id"] is None
    assert result.utterances[A].failure_code is None
    assert heard.actor_id == B
    assert list(deliveries[-1].heard) == [B]
    assert not audience.state.dialogue_sessions


def test_dialogue_cap_uses_completion_shuffle_and_cooldown_boundary(world):
    from living_island.world.v2.engine.ids import shuffle

    world.state.dialogue_limits = replace(
        world.state.dialogue_limits, max_turns=1, cooldown_ticks=2
    )
    entries = [A, B]
    expected_rng = shuffle(entries, world.state.resolution_rng_state_uint32)
    winner, loser = entries
    submissions = [turn(world, A, utterance=statement(B)), turn(world, B, utterance=statement(A))]
    replay = deepcopy(world)
    result = world.step(submissions)
    assert result == replay.step(list(reversed(submissions)))
    assert world.state == replay.state
    assert world.state.resolution_rng_state_uint32 == expected_rng
    assert result.utterances[winner].failure_code is None
    assert result.utterances[loser].failure_code == "DIALOGUE_LIMIT"
    assert speech_events(result)[0].actor_id == winner
    assert all(action.outcome == "success" for action in result.actions)

    pair = world.state.dialogue_sessions[A, B]
    assert (pair.turn_count, pair.last_utterance_tick, pair.cooldown_until_tick) == (1, 1, 3)
    blocked = world.step([turn(world, A, utterance=statement(B))])
    assert blocked.utterances[A].failure_code == "DIALOGUE_LIMIT"
    assert world.state.dialogue_sessions[A, B] == pair
    allowed = world.step([turn(world, B, utterance=statement(A))])
    assert allowed.utterances[B].failure_code is None
    pair = world.state.dialogue_sessions[A, B]
    assert (pair.turn_count, pair.last_utterance_tick, pair.cooldown_until_tick) == (1, 3, 5)


def test_dialogue_gap_keeps_unordered_pair_through_exact_boundary(world):
    world.step([turn(world, A, utterance=statement(B))])
    world.step()
    world.step([turn(world, B, utterance=statement(A))])
    assert world.state.dialogue_sessions[A, B].turn_count == 2
    for _ in range(2):
        world.step()
    world.step([turn(world, B, utterance=statement(A))])
    pair = world.state.dialogue_sessions[A, B]
    assert (pair.turn_count, pair.last_utterance_tick, pair.cooldown_until_tick) == (1, 6, 0)


def test_zero_cap_refuses_addressed_speech(world):
    world.state.dialogue_limits = replace(world.state.dialogue_limits, max_turns=0)
    result = world.step([turn(world, A, utterance=statement(B))])
    assert result.utterances[A].failure_code == "DIALOGUE_LIMIT"
    assert not speech_events(result)
    assert not world.state.dialogue_sessions


@pytest.mark.parametrize("kind", ["asleep", "unconscious"])
def test_addressed_speech_skips_unaware_recipient_at_emission(audience, deliveries, kind):
    from living_island.world.v2.engine.state import Awareness

    audience.state.awareness[B] = Awareness(kind, 6 if kind == "unconscious" else None)
    result = audience.step([turn(audience, A, utterance=statement(B))])
    spoken, heard = speech_events(result)
    assert spoken.payload["addressee_id"] == B
    assert heard.actor_id == C
    assert list(deliveries[-1].heard) == [C]
    assert result.utterances[A].failure_code is None
