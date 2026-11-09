"""Integrated boundary ordering, action results, and snapshot restore."""

import hashlib

import pytest
from test_engine_actions import RYAN, TREE, content_with, failures, intent
from test_engine_dialogue import ELLA
from test_engine_movement import movement, tick

from living_island.world.content import canonical_json_bytes
from living_island.world.engine import Engine
from living_island.world.facts import (
    AgentFallbackUsedPayload,
    GodInterventionRecordedPayload,
    WorldInitializedPayload,
    format_event_id,
)
from living_island.world.ports import WorldTickCommit, create_engine
from living_island.world.protocol import ActionIntent, Coord
from living_island.world.rng import shuffle, xorshift32
from living_island.world.state import ReceiptEntity, WorldState


def test_rng_vectors_and_rejection_sampling() -> None:
    state = 1
    for expected in [270369, 67634689, 2647435461, 307599695, 2398689233]:
        state = xorshift32(state)
        assert state == expected
    items = list("abcde")
    assert shuffle(items, 1) == 307599695
    assert items == list("cdabe")
    assert shuffle([], 42) == shuffle(["a"], 42) == 42
    # For three entries 0xffffffff lies outside the largest divisible range.
    assert xorshift32(1584200935) == 0xFFFFFFFF
    items = list("abc")
    assert shuffle(items, 1584200935) == xorshift32(253983)
    assert items == list("cba")


def packet(commit: WorldTickCommit, actor: str = "ella"):
    return next(d for d in commit.pending_deliveries if d.actor_id == actor)


def interrupt_world(urgent: bool = False, exhausted: bool = False, dying: bool = False):
    content = content_with(
        {"ella": (2, 3), "ryan": (4, 4)},
        map={"walk_cost_budget_per_tick": 2},
        perception={"day_radius_tiles": 1, "night_radius_tiles": 1},
    )
    initial = create_engine(content, None).initial_commit()
    state = initial.snapshot
    ella = state.residents[0]
    if urgent:
        ella.satiety = content.config.agents.urgent_satiety_below + 1
    if exhausted:
        ella.stamina = 1
    if dying:
        ella.hydration = 0
        ella.health = 1
    footprint = state.explored_tiles_by_resident[0]
    footprint.tile_indices = sorted(
        set(footprint.tile_indices) | {3 * content.config.map.width + x for x in range(2, 8)}
    )
    # A previous exposure gives Ryan the handle without seeding Ella's novelty baseline.
    group = state.exposure_receipts_by_resident[1]
    group.entities = sorted(
        [
            *group.entities,
            ReceiptEntity(entity_id="ella", entity_type="resident", position=ella.position),
        ],
        key=lambda e: (e.entity_id, e.position.y, e.position.x),
    )
    return content, initial


def request() -> ActionIntent:
    return intent(
        "talk",
        "ryan",
        target=ELLA,
        speech_act="request",
        text="Fruit?",
        request={"item_type": "fruit", "quantity": 1},
    )


@pytest.mark.parametrize(
    ("urgent", "speech", "reason"),
    [
        (False, False, "NEW_SIGHT"),
        (False, True, "DIRECT_SPEECH"),
        (True, False, "URGENT_NEED"),
        (True, True, "URGENT_NEED"),
    ],
)
def test_soft_priorities_keep_all_triggers(urgent: bool, speech: bool, reason: str) -> None:
    content, initial = interrupt_world(urgent=urgent)
    engine = Engine(content, initial.snapshot, initial.events)
    submitted = [movement(7, 3), *([request()] if speech else [])]
    result = tick(engine, *submitted)
    feedback = packet(result).perception.last_action_feedback
    assert feedback is not None
    assert (feedback.status, feedback.failure_code, feedback.interruption_reason) == (
        "interrupted",
        None,
        reason,
    )
    assert packet(result).decision_triggers == [
        "ACTION_INTERRUPTED",
        *(["URGENT_NEED"] if urgent else []),
        *(["DIRECT_SPEECH"] if speech else []),
        "NEW_SIGHT",
        *(["UTTERANCE_HEARD", "REPLY_REQUIRED"] if speech else []),
    ]
    assert not result.snapshot.active_actions
    assert result.snapshot.residents[0].position == Coord(x=4, y=3)
    terminal = engine._results["ella"]
    assert terminal.visible_feedback == feedback
    assert terminal.tick_started == 0 and terminal.tick_finished == 1
    assert [d.path for d in terminal.state_delta] == [
        "residents/ella/position",
        "residents/ella/stamina",
    ]
    assert terminal.state_delta[0].before == Coord(x=2, y=3)
    assert terminal.state_delta[0].after == Coord(x=4, y=3)
    assert packet(tick(engine)).perception.last_action_feedback is None


def test_exhaustion_beats_all_soft_triggers_and_death_beats_exhaustion() -> None:
    for dying in (False, True):
        content, initial = interrupt_world(urgent=True, exhausted=True, dying=dying)
        engine = Engine(content, initial.snapshot, initial.events)
        result = tick(engine, movement(7, 3), request())
        terminal = engine._results["ella"]
        if dying:
            assert terminal.interruption_reason == "DEATH"
            assert terminal.failure_code is None
            assert [d.actor_id for d in result.pending_deliveries] == ["ryan"]
        else:
            assert terminal.failure_code == "EXHAUSTED"
            assert packet(result).decision_triggers == [
                "ACTION_FAILED",
                "URGENT_NEED",
                "DIRECT_SPEECH",
                "NEW_SIGHT",
                "UTTERANCE_HEARD",
                "REPLY_REQUIRED",
            ]
        terminal_events = [
            e
            for e in result.events
            if e.intent_id == "move"
            and e.type in ("action_failed", "action_interrupted", "action_succeeded")
        ]
        assert len(terminal_events) == 1


@pytest.mark.parametrize("dying", [False, True])
def test_completion_beats_cooccurring_interrupts(dying: bool) -> None:
    content, initial = interrupt_world(urgent=True, exhausted=True, dying=dying)
    engine = Engine(content, initial.snapshot, initial.events)
    result = tick(engine, movement(4, 3), request())
    assert engine._results["ella"].status == "success"
    assert not failures(result)
    assert not any(e.type == "action_interrupted" for e in result.events)
    assert any(e.type == "resident_died" for e in result.events) == dying


@pytest.mark.parametrize("kind", ["rest", "gather"])
def test_non_movement_action_retains_sighting_without_interrupting(kind: str) -> None:
    content = content_with({"ryan": (2, 3), "ella": (3, 3)})
    engine = create_engine(content, None)
    engine.initial_commit()
    result = tick(
        engine,
        intent(kind, target=TREE if kind == "gather" else None),
        intent("give", "ryan", target=ELLA, item_type="canteen", quantity=1),
    )
    assert packet(result).decision_triggers == ["NEW_SIGHT"]
    assert packet(result).perception.last_action_feedback is None
    assert result.snapshot.active_actions[0].intent.action_type == kind


def test_sleep_urgent_crossing_wakes_and_does_not_receive_speech() -> None:
    content = content_with({"ella": (2, 3), "ryan": (3, 3)})
    initial = create_engine(content, None).initial_commit()
    state = initial.snapshot
    state.residents[0].satiety = content.config.agents.urgent_satiety_below + 1
    result = tick(create_engine(content, state, initial.events), intent("sleep"), request())
    assert packet(result).decision_triggers == ["ACTION_INTERRUPTED", "URGENT_NEED", "WOKE"]
    assert not packet(result).perception.heard_utterances


def test_allocator_tick_zero_hash_lifecycle_and_commits_detached() -> None:
    content = content_with({"ella": (2, 3)})
    engine = create_engine(content, None)
    with pytest.raises(RuntimeError, match="committed boundary"):
        engine.begin_tick()
    with pytest.raises(RuntimeError, match="begin_tick"):
        engine.start_intent(intent("wait"))
    first = engine.initial_commit()
    with pytest.raises(RuntimeError, match="once"):
        engine.initial_commit()
    init = first.events[0]
    assert isinstance(init.payload, WorldInitializedPayload)
    expected = hashlib.sha256(canonical_json_bytes(first.snapshot.model_dump(mode="json")))
    assert init.payload.initial_snapshot_hash == expected.hexdigest()
    assert (
        first.snapshot.event_log_cursor
        == first.snapshot.next_event_seq_in_tick
        == len(first.events)
    )
    assert not packet(first).decision_triggers
    first.snapshot.residents[0].fruit_count = 999
    packet(first).perception.visible_entities.clear()
    first.events.clear()
    engine.begin_tick()
    with pytest.raises(RuntimeError, match="committed boundary"):
        engine.begin_tick()
    future = format_event_id(first.snapshot.run_id, 1, 0)
    payload = AgentFallbackUsedPayload(
        resident_id="ella", reason="TIMEOUT", fallback_policy_id="rule"
    )
    with pytest.raises(ValueError, match="causal"):
        engine.append_fact("agent_fallback_used", "ella", None, None, None, [future], payload)
    causes = [init.event_id]
    appended = engine.append_fact(
        "agent_fallback_used", "ella", None, None, "call", causes, payload
    )
    causes.clear()
    appended.caused_by_event_ids.clear()
    engine.start_intent(intent("wait"))
    with pytest.raises(RuntimeError, match="already has an action"):
        engine.start_intent(intent("eat"))
    second = engine.advance_tick()
    assert second.events[0].event_id == future
    assert second.events[0].caused_by_event_ids == [init.event_id]
    assert second.events[0].llm_call_id == "call"
    assert second.snapshot.residents[0].fruit_count == 0
    assert second.snapshot.event_log_cursor == first.snapshot.event_log_cursor + len(second.events)


def test_restore_uses_serialized_active_intents_and_rng() -> None:
    content = content_with({"ella": (2, 2), "ryan": (4, 2)}, fruit={"regrow_ticks": 2})
    original = create_engine(content, None)
    initial = original.initial_commit()
    before = tick(original, intent("gather", target=TREE), intent("gather", "ryan", target=TREE))
    saved = WorldState.model_validate_json(before.snapshot.model_dump_json())
    history = (*initial.events, *before.events)
    restored = create_engine(content, saved, history)
    with pytest.raises(RuntimeError, match="fresh"):
        restored.initial_commit()
    for intents in [(), (intent("wait"),), ()]:
        next_original = tick(original, *intents)
        next_restored = tick(restored, *intents)
        assert canonical_json_bytes(next_restored.model_dump(mode="json")) == canonical_json_bytes(
            next_original.model_dump(mode="json")
        )
    saved.config_hash = "wrong"
    with pytest.raises(ValueError, match="identities"):
        create_engine(content, saved, history)


def test_restore_accepts_sim_fact_citing_pre_checkpoint_event() -> None:
    content = content_with({"ella": (2, 3)})
    engine = create_engine(content, None)
    first = engine.initial_commit()
    earlier = tick(engine, intent("wait"))
    prior = tick(engine)
    history = (*first.events, *earlier.events, *prior.events)
    restored = create_engine(content, prior.snapshot, history)
    engine.begin_tick()
    restored.begin_tick()
    payload = AgentFallbackUsedPayload(
        resident_id="ella", reason="TIMEOUT", fallback_policy_id="rule"
    )
    causes = [prior.events[0].event_id, earlier.events[-1].event_id]
    event = restored.append_fact("agent_fallback_used", "ella", None, None, None, causes, payload)
    assert event.caused_by_event_ids == list(reversed(causes))
    assert event == engine.append_fact(
        "agent_fallback_used", "ella", None, None, None, causes, payload
    )
    unknown = format_event_id(prior.snapshot.run_id, prior.snapshot.tick, len(prior.events))
    with pytest.raises(ValueError, match="causal"):
        restored.append_fact("agent_fallback_used", "ella", None, None, None, [unknown], payload)
    assert restored.advance_tick() == engine.advance_tick()


def test_restore_replies_to_pre_checkpoint_request_identically() -> None:
    content = content_with({"ella": (2, 3), "ryan": (3, 3)})
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    spoken = tick(
        engine,
        intent(
            "talk",
            target=RYAN,
            speech_act="request",
            text="Fruit?",
            request={"item_type": "fruit", "quantity": 1},
        ),
    )
    event = next(e for e in spoken.events if e.type == "utterance_spoken")
    response = intent(
        "talk",
        "ryan",
        target=ELLA,
        speech_act="accept",
        text="Sure",
        in_reply_to=event.event_id,
    )
    checkpoint = tick(engine)
    saved = WorldState.model_validate_json(checkpoint.snapshot.model_dump_json())
    history = [*initial.events, *spoken.events, *checkpoint.events]
    original_history = [e.model_dump() for e in history]
    restored = tick(create_engine(content, saved, history), response)
    assert canonical_json_bytes(restored.model_dump(mode="json")) == canonical_json_bytes(
        tick(engine, response).model_dump(mode="json")
    )
    assert [e.model_dump() for e in history] == original_history
    assert not failures(restored)
    assert next(e for e in restored.events if e.type == "utterance_spoken").caused_by_event_ids == [
        event.event_id
    ]


def test_restore_continues_a_reply_validated_before_the_checkpoint() -> None:
    content = content_with({"ella": (2, 3), "ryan": (3, 3)}, actions={"talk_ticks": 2})
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    started = tick(engine, request())
    spoken = tick(engine)
    event = next(e for e in spoken.events if e.type == "utterance_spoken")
    response = intent(
        "talk",
        target=RYAN,
        speech_act="refuse",
        text="",
        in_reply_to=event.event_id,
    )
    pending = tick(engine, response)
    assert pending.snapshot.active_actions[0].pending_failure_code is None
    saved = WorldState.model_validate_json(pending.snapshot.model_dump_json())
    history = (*initial.events, *started.events, *spoken.events, *pending.events)
    restored = tick(create_engine(content, saved, history))
    assert restored == tick(engine)
    assert not failures(restored)
    assert next(e for e in restored.events if e.type == "utterance_spoken").caused_by_event_ids == [
        event.event_id
    ]


@pytest.mark.parametrize("invalid", ["missing", "length", "run_id", "gap"])
def test_restore_rejects_invalid_event_history(invalid: str) -> None:
    content = content_with({"ella": (2, 3)})
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    latest = tick(engine, intent("wait"))
    history = [*initial.events, *latest.events]
    if invalid == "missing":
        with pytest.raises(ValueError, match="complete prefix of length"):
            create_engine(content, latest.snapshot)
        return
    if invalid == "length":
        history.pop()
        error = "complete prefix of length"
    elif invalid == "run_id":
        history[-1] = history[-1].model_copy(update={"run_id": "other"})
        error = "history run_id"
    else:
        last = history[-1]
        seq = last.seq_in_tick + 1
        history[-1] = last.model_copy(
            update={
                "seq_in_tick": seq,
                "event_id": format_event_id(last.run_id, last.tick, seq),
            }
        )
        error = "IDs must be contiguous"
    with pytest.raises(ValueError, match=error):
        create_engine(content, latest.snapshot, history)


def test_fresh_engine_rejects_event_history() -> None:
    content = content_with({"ella": (2, 3)})
    initial = create_engine(content, None).initial_commit()
    with pytest.raises(ValueError, match="fresh engine requires empty"):
        create_engine(content, None, initial.events)


def test_external_append_fact_only_accepts_sim_facts() -> None:
    content = content_with({"ella": (2, 3)})
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    engine.begin_tick()
    for fact in initial.events:
        with pytest.raises(ValueError, match="external append_fact port"):
            engine.append_fact(
                fact.type, fact.actor_id, fact.target_id, None, None, [], fact.payload
            )
    appended = engine.append_fact(
        "god_intervention_recorded",
        "ella",
        None,
        None,
        None,
        [],
        GodInterventionRecordedPayload(
            intervention_id="dream-1",
            recipient_id="ella",
            kind="dream",
            transcript_retained=False,
        ),
    )
    assert appended.seq_in_tick == 0
    engine.start_intent(movement(3, 3))
    move = next(e for e in engine.advance_tick().events if e.type == "resident_moved")
    engine.begin_tick()
    with pytest.raises(ValueError, match="external append_fact port"):
        engine.append_fact(move.type, move.actor_id, None, move.intent_id, None, [], move.payload)
    assert all(e.type != "resident_moved" for e in engine.advance_tick().events)
