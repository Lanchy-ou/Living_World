"""Talk settlement and listener delivery, including contested pair turns."""

import pytest
from pydantic import ValidationError
from test_engine_actions import RYAN, content_with, failures, intent
from test_engine_movement import tick

from living_island.world.facts import UtteranceSpokenPayload
from living_island.world.ports import create_engine

ELLA = {"kind": "resident", "id": "ella"}
MIA = {"kind": "resident", "id": "mia"}


def test_request_reply_and_hearing_event_order() -> None:
    content = content_with({"ella": (2, 3), "mia": (2, 4), "ryan": (3, 3)})
    engine = create_engine(content, None)
    engine.initial_commit()
    first = tick(
        engine,
        intent(
            "talk",
            target=RYAN,
            speech_act="request",
            text="Fruit?",
            request={"item_type": "fruit", "quantity": 1},
        ),
    )
    spoken = next(e for e in first.events if e.type == "utterance_spoken")
    assert isinstance(spoken.payload, UtteranceSpokenPayload)
    assert spoken.payload.utterance_id == spoken.event_id
    heard_events = first.events[spoken.seq_in_tick + 1 : spoken.seq_in_tick + 3]
    assert [(e.type, e.actor_id) for e in heard_events] == [
        ("utterance_heard", "mia"),
        ("utterance_heard", "ryan"),
    ]
    assert all(e.caused_by_event_ids == [spoken.event_id] for e in heard_events)
    heard_by_actor = {d.actor_id: d.perception.heard_utterances for d in first.pending_deliveries}
    assert not heard_by_actor["ella"]
    assert [u.utterance_id for u in heard_by_actor["mia"]] == [spoken.event_id]
    assert heard_by_actor["ryan"][0].request_quantity == 1
    second = tick(
        engine,
        intent(
            "talk",
            "ryan",
            target=ELLA,
            speech_act="accept",
            text="Sure",
            in_reply_to=spoken.event_id,
        ),
    )
    reply = next(e for e in second.events if e.type == "utterance_spoken")
    assert reply.caused_by_event_ids == [spoken.event_id]
    assert second.snapshot.dialogue_sessions[0].pair_ids == ["ella", "ryan"]
    assert second.snapshot.dialogue_sessions[0].turn_count == 2
    assert all(r.fruit_count == 0 for r in second.snapshot.residents)


def test_reply_requires_the_request_parties_and_a_request_event() -> None:
    content = content_with(
        {"ella": (2, 3), "mia": (2, 4), "ryan": (3, 3)}, perception={"hearing_radius_tiles": 2}
    )
    engine = create_engine(content, None)
    engine.initial_commit()
    result = tick(
        engine,
        intent(
            "talk",
            target=RYAN,
            speech_act="request",
            text="Fruit?",
            request={"item_type": "fruit", "quantity": 1},
        ),
    )
    request = next(e for e in result.events if e.type == "utterance_spoken")
    for actor, recipient, event_id in [
        ("mia", ELLA, request.event_id),
        ("ryan", MIA, request.event_id),
        ("ryan", ELLA, result.events[0].event_id),
    ]:
        result = tick(
            engine,
            intent(
                "talk",
                actor,
                id=f"reply-{result.snapshot.tick}",
                target=recipient,
                speech_act="refuse",
                text="",
                in_reply_to=event_id,
            ),
        )
        assert failures(result) == ["INVALID_REPLY"]


def test_out_of_hearing_and_unknown_target() -> None:
    content = content_with({"ella": (2, 3), "ryan": (5, 3)})
    engine = create_engine(content, None)
    engine.initial_commit()
    far = tick(engine, intent("talk", target=RYAN, speech_act="statement", text="Hi"))
    assert failures(far) == ["OUT_OF_HEARING"]
    unknown = tick(
        engine,
        intent(
            "talk",
            id="unknown",
            target=MIA,
            speech_act="statement",
            text="Hi",
        ),
    )
    assert failures(unknown) == ["INVALID_TARGET"]


def test_invalid_speech_act_cannot_enter_world_through_frozen_intent() -> None:
    with pytest.raises(ValidationError):
        intent("talk", target=RYAN, speech_act="invented", text="Hi")


def test_sleep_does_not_hear_even_when_it_completes_this_tick() -> None:
    content = content_with({"ella": (2, 3), "ryan": (3, 3)}, actions={"sleep_ticks": 1})
    engine = create_engine(content, None)
    engine.initial_commit()
    result = tick(
        engine,
        intent("sleep", "ryan"),
        intent("talk", target=RYAN, speech_act="statement", text="Hi"),
    )
    assert any(e.type == "utterance_spoken" for e in result.events)
    assert not any(e.type == "utterance_heard" for e in result.events)
    assert not result.pending_deliveries[1].perception.heard_utterances
    assert not tick(engine).pending_deliveries[1].perception.heard_utterances


def test_simultaneous_pair_turns_share_limit_and_cooldown() -> None:
    content = content_with(
        {"ella": (2, 3), "ryan": (3, 3)},
        social={"max_dialogue_turns": 1, "dialogue_cooldown_ticks": 2},
    )
    engine = create_engine(content, None)
    engine.initial_commit()
    first = tick(
        engine,
        intent("talk", target=RYAN, speech_act="statement", text="Hello"),
        intent("talk", "ryan", target=ELLA, speech_act="statement", text="Hi"),
    )
    assert failures(first) == ["DIALOGUE_LIMIT"]
    assert sum(e.type == "utterance_spoken" for e in first.events) == 1
    assert first.snapshot.dialogue_sessions[0].cooldown_until_tick == 3
    for boundary in (1, 2, 3):
        result = tick(
            engine,
            intent(
                "talk",
                id=f"try-{boundary}",
                target=RYAN,
                speech_act="statement",
                text="Again",
            ),
        )
        assert failures(result) == (["DIALOGUE_LIMIT"] if boundary < 3 else [])
    assert result.snapshot.dialogue_sessions[0].turn_count == 1


def test_dialogue_gap_resets_uncapped_session() -> None:
    content = content_with(
        {"ella": (2, 3), "ryan": (3, 3)},
        social={"dialogue_gap_ticks": 1},
    )
    engine = create_engine(content, None)
    engine.initial_commit()
    tick(engine, intent("talk", target=RYAN, speech_act="statement", text="First"))
    tick(engine)
    result = tick(
        engine,
        intent(
            "talk",
            id="after-gap",
            target=RYAN,
            speech_act="statement",
            text="Second",
        ),
    )
    assert result.snapshot.dialogue_sessions[0].turn_count == 1
