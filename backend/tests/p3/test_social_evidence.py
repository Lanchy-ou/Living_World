"""P3-06 engine-backed hearing, commitment, and transfer evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_engine_actions import content_with, failures, intent
from test_engine_movement import tick
from test_experience import heard, packet

from living_island.agents.p3.cognition import (
    advance_goal_evidence,
    apply_goal_change,
    initial_goal_state,
)
from living_island.agents.p3.types import GoalChange
from living_island.agents.types import build_intent_id, build_plan_id
from living_island.memory.experience import (
    capture_accepted_decision,
    ingest_experience,
    initial_experience,
)
from living_island.memory.p3_types import (
    MAX_EXPERIENCE_BYTES,
    FeedbackData,
    RetrievalQuery,
    build_decision_id,
    canonical_bytes,
)
from living_island.memory.retrieval import retrieve
from living_island.world.ports import create_engine
from living_island.world.protocol import ActionPlan

FIXTURE = Path(__file__).parents[1] / "fixtures/p3/three_residents/social_oracles.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def world_for(name, **sections):
    positions = {actor: tuple(position) for actor, position in CASES[name]["positions"].items()}
    return content_with(positions, **sections)


def delivery(commit, actor):
    return next(packet for packet in commit.pending_deliveries if packet.actor_id == actor)


def heard_records(state):
    return [record for record in state.records if record.kind == "heard_speech"]


def query(owner):
    return RetrievalQuery(query_schema_version="0.1", owner_id=owner, entity_ids=[], positions=[])


def test_one_world_utterance_is_captured_independently_by_two_hearers():
    case = CASES["shared_hearing"]
    content = world_for("shared_hearing")
    run_id = content.config.meta.run_id
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    states = {
        actor: ingest_experience(initial_experience(actor), delivery(initial, actor), run_id=run_id)
        for actor in case["positions"]
    }
    spoken = tick(
        engine,
        intent(
            "talk",
            target={"kind": "resident", "id": case["addressee"]},
            speech_act="statement",
            text=case["text"],
        ),
    )
    utterance = next(event for event in spoken.events if event.type == "utterance_spoken")
    for actor in states:
        states[actor] = ingest_experience(states[actor], delivery(spoken, actor), run_id=run_id)
    assert heard_records(states[case["speaker"]]) == []
    for actor in (case["addressee"], case["bystander"]):
        records = heard_records(states[actor])
        assert len(records) == 1
        assert records[0].payload.data.utterance_id == utterance.event_id
        assert records[0].payload.data.text == case["text"]
        assert records[0].owner_id == records[0].experience_id.split(":e")[0] == actor
        assert records[0].source.delivery_id == delivery(spoken, actor).delivery_id
        assert records[0].payload.information_kind == "delivered"
        assert records[0].payload.confidence is None
    assert states[case["addressee"]] is not states[case["bystander"]]
    assert canonical_bytes(states[case["addressee"]]) != canonical_bytes(states[case["bystander"]])


def test_non_hearer_has_no_speech_or_cross_owner_retrieval():
    case = CASES["private_hearing"]
    content = world_for("private_hearing")
    run_id = content.config.meta.run_id
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    result = tick(
        engine,
        intent(
            "talk",
            target={"kind": "resident", "id": "ryan"},
            speech_act="statement",
            text=case["text"],
        ),
    )
    states = {
        actor: ingest_experience(
            ingest_experience(initial_experience(actor), delivery(initial, actor), run_id=run_id),
            delivery(result, actor),
            run_id=run_id,
        )
        for actor in case["positions"]
    }
    non_hearer = case["non_hearer"]
    assert delivery(result, non_hearer).perception.heard_utterances == []
    assert heard_records(states[non_hearer]) == []
    assert len(heard_records(states["ryan"])) == 1
    assert all(
        record.owner_id == non_hearer
        for record in retrieve(
            states[non_hearer], query(non_hearer), "recent-relevant-v0"
        ).selected_records
    )
    with pytest.raises(ValueError, match="owner"):
        retrieve(states["ryan"], query(non_hearer), "recent-relevant-v0")
    with pytest.raises(ValueError, match="owner"):
        ingest_experience(states[non_hearer], delivery(result, "ryan"), run_id=run_id)


def test_engine_delivers_conflicting_claims_to_different_private_histories():
    case = CASES["conflicting_knowledge"]
    content = world_for("conflicting_knowledge")
    run_id = content.config.meta.run_id
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    states = {
        actor: ingest_experience(initial_experience(actor), delivery(initial, actor), run_id=run_id)
        for actor in case["positions"]
    }
    west = tick(
        engine,
        intent(
            "talk",
            "ryan",
            target={"kind": "resident", "id": "ella"},
            speech_act="statement",
            text=case["ella_claim"],
        ),
    )
    moved = tick(
        engine,
        intent(
            "move_to",
            "ryan",
            target={
                "kind": "tile",
                "position": {
                    "x": case["speaker_target_position"][0],
                    "y": case["speaker_target_position"][1],
                },
            },
        ),
    )
    east = tick(
        engine,
        intent(
            "talk",
            "ryan",
            id="ryan:east-claim",
            target={"kind": "resident", "id": "mia"},
            speech_act="statement",
            text=case["mia_claim"],
        ),
    )
    for commit in (west, moved, east):
        for actor in states:
            states[actor] = ingest_experience(states[actor], delivery(commit, actor), run_id=run_id)
    assert [record.payload.data.text for record in heard_records(states["ella"])] == [
        case["ella_claim"]
    ]
    assert [record.payload.data.text for record in heard_records(states["mia"])] == [
        case["mia_claim"]
    ]
    assert heard_records(states["ryan"]) == []
    for actor, claim, foreign in (
        ("ella", case["ella_claim"], case["mia_claim"]),
        ("mia", case["mia_claim"], case["ella_claim"]),
    ):
        recalled = retrieve(states[actor], query(actor), "recent-relevant-v0").selected_records
        assert any(
            record.kind == "heard_speech" and record.payload.data.text == claim
            for record in recalled
        )
        assert all(record.owner_id == actor for record in recalled)
        assert not any(
            record.kind == "heard_speech" and record.payload.data.text == foreign
            for record in recalled
        )
    assert all(commit.snapshot.unique_canteen.holder_id == "ella" for commit in (west, moved, east))


@pytest.mark.parametrize("reply_act", ["accept", "refuse"])
def test_request_reply_and_promise_words_do_not_transfer_an_item(reply_act):
    engine = create_engine(world_for("shared_hearing"), None)
    initial = engine.initial_commit()
    assert initial.snapshot.unique_canteen.holder_id == "ella"
    asked = tick(
        engine,
        intent(
            "talk",
            target={"kind": "resident", "id": "ryan"},
            speech_act="request",
            text="Will you take my canteen?",
            request={"item_type": "canteen", "quantity": 1},
        ),
    )
    request_id = next(event.event_id for event in asked.events if event.type == "utterance_spoken")
    replied = tick(
        engine,
        intent(
            "talk",
            "ryan",
            target={"kind": "resident", "id": "ella"},
            speech_act=reply_act,
            text="I promise to receive it." if reply_act == "accept" else "I refuse it.",
            in_reply_to=request_id,
        ),
    )
    assert not failures(asked) and not failures(replied)
    assert [u.speech_act for u in delivery(replied, "ella").perception.heard_utterances] == [
        reply_act
    ]
    assert replied.snapshot.unique_canteen.holder_id == "ella"
    assert not any(
        event.type == "item_given" for commit in (asked, replied) for event in commit.events
    )
    assert delivery(replied, "ryan").perception.last_action_feedback.status == "success"
    assert delivery(replied, "ella").perception.last_action_feedback is None


def test_completed_give_has_sender_verdict_and_receiver_inventory_without_attribution():
    content = world_for("shared_hearing")
    run_id = content.config.meta.run_id
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    sender = ingest_experience(initial_experience("ella"), delivery(initial, "ella"), run_id=run_id)
    plan_id = build_plan_id("ella", 0)
    give = intent(
        "give",
        target={"kind": "resident", "id": "ryan"},
        item_type="canteen",
        quantity=1,
    ).model_copy(update={"plan_id": plan_id, "intent_id": build_intent_id(plan_id, 0)})
    accepted = ActionPlan(plan_id=plan_id, actor_id="ella", created_at_tick=0, intents=[give])
    sender = capture_accepted_decision(
        sender,
        run_id,
        build_decision_id(run_id, "ella", 0),
        0,
        accepted,
        None,
        max_plan_actions=5,
    )
    settled = tick(engine, give)
    assert settled.snapshot.unique_canteen.holder_id == "ryan"
    transfers = [event for event in settled.events if event.type == "item_given"]
    assert len(transfers) == 1
    assert transfers[0].intent_id == give.intent_id
    sender = ingest_experience(sender, delivery(settled, "ella"), run_id=run_id)
    feedback = sender.records[-1].payload.data
    assert isinstance(feedback, FeedbackData)
    assert feedback.feedback.status == "success"
    assert feedback.feedback.visible_effects == ["item_given"]
    assert feedback.owned_intent.intent == give
    assert feedback.owned_intent.decision_id == build_decision_id(run_id, "ella", 0)
    receiver = delivery(settled, "ryan").perception
    assert receiver.own_inventory.canteen_id == "canteen_01"
    assert receiver.last_action_feedback is None
    assert receiver.heard_utterances == []


def test_social_agreement_and_receiver_inventory_cannot_complete_an_own_give_goal():
    content = world_for("shared_hearing")
    run_id = content.config.meta.run_id
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    memories = {
        actor: ingest_experience(initial_experience(actor), delivery(initial, actor), run_id=run_id)
        for actor in ("ella", "ryan")
    }
    goals = {
        "ella": apply_goal_change(
            initial_goal_state(),
            GoalChange.model_validate(
                {
                    "operation": "revise",
                    "expected_goal_id": None,
                    "proposal": {
                        "text": "Give Ryan my canteen.",
                        "completion": {
                            "kind": "own_action_success",
                            "action_type": "give",
                            "target": {"kind": "resident", "id": "ryan"},
                            "parameters": {"item_type": "canteen", "quantity": 1},
                        },
                    },
                }
            ),
            actor_id="ella",
            tick=0,
        ),
        "ryan": apply_goal_change(
            initial_goal_state(),
            GoalChange.model_validate(
                {
                    "operation": "revise",
                    "expected_goal_id": None,
                    "proposal": {
                        "text": "Receive Ella's canteen.",
                        "completion": {"kind": "unverifiable"},
                    },
                }
            ),
            actor_id="ryan",
            tick=0,
        ),
    }

    def accepted(actor, ordinal, action):
        plan_id = build_plan_id(actor, ordinal)
        issued = action.model_copy(
            update={
                "plan_id": plan_id,
                "intent_id": build_intent_id(plan_id, 0),
            }
        )
        plan = ActionPlan(
            plan_id=plan_id,
            actor_id=actor,
            created_at_tick=memories[actor].last_ingested_tick,
            intents=[issued],
        )
        memories[actor] = capture_accepted_decision(
            memories[actor],
            run_id,
            build_decision_id(run_id, actor, ordinal),
            ordinal,
            plan,
            goals[actor].current.goal_id,
            max_plan_actions=5,
        )
        return issued

    def observe(commit):
        for actor in memories:
            packet_for_actor = delivery(commit, actor)
            goals[actor] = advance_goal_evidence(
                packet_for_actor, memories[actor].intent_refs, goals[actor], run_id=run_id
            )
            memories[actor] = ingest_experience(memories[actor], packet_for_actor, run_id=run_id)

    ask = accepted(
        "ella",
        0,
        intent(
            "talk",
            target={"kind": "resident", "id": "ryan"},
            speech_act="request",
            text="Will you take my canteen?",
            request={"item_type": "canteen", "quantity": 1},
        ),
    )
    asked = tick(engine, ask)
    observe(asked)
    request_id = next(event.event_id for event in asked.events if event.type == "utterance_spoken")
    assert goals["ella"].current.status == "attempted"
    assert asked.snapshot.unique_canteen.holder_id == "ella"

    answer = accepted(
        "ryan",
        0,
        intent(
            "talk",
            "ryan",
            target={"kind": "resident", "id": "ella"},
            speech_act="accept",
            text="I promise to take it.",
            in_reply_to=request_id,
        ),
    )
    agreed = tick(engine, answer)
    observe(agreed)
    assert delivery(agreed, "ella").perception.heard_utterances[0].speech_act == "accept"
    assert goals["ella"].current.status == goals["ryan"].current.status == "attempted"
    assert agreed.snapshot.unique_canteen.holder_id == "ella"
    assert not any(
        event.type == "item_given" for commit in (asked, agreed) for event in commit.events
    )

    moved = tick(
        engine,
        intent(
            "move_to",
            "ryan",
            id="ryan:away",
            target={"kind": "tile", "position": {"x": 5, "y": 3}},
        ),
    )
    observe(moved)
    failed_intent = accepted(
        "ella",
        1,
        intent(
            "give",
            target={"kind": "resident", "id": "ryan"},
            item_type="canteen",
            quantity=1,
        ),
    )
    failed = tick(engine, failed_intent)
    observe(failed)
    assert failures(failed) == ["OUT_OF_REACH"]
    assert goals["ella"].current.status == "attempted"
    assert goals["ella"].current.evidence.owned_intent.intent == failed_intent
    assert failed.snapshot.unique_canteen.holder_id == "ella"

    returned = tick(
        engine,
        intent(
            "move_to",
            "ryan",
            id="ryan:back",
            target={"kind": "tile", "position": {"x": 3, "y": 3}},
        ),
    )
    observe(returned)
    success_intent = accepted(
        "ella",
        2,
        intent(
            "give",
            target={"kind": "resident", "id": "ryan"},
            item_type="canteen",
            quantity=1,
        ),
    )
    completed = tick(engine, success_intent)
    observe(completed)
    own = goals["ella"].current
    receiver = goals["ryan"].current
    assert own.status == "observed_complete"
    assert own.evidence.owned_intent.intent == success_intent
    assert own.evidence.feedback.status == "success"
    assert own.evidence.feedback.visible_effects == ["item_given"]
    assert receiver.status == "attempted"
    assert delivery(completed, "ryan").perception.last_action_feedback is None
    assert delivery(completed, "ryan").perception.own_inventory.canteen_id == "canteen_01"
    assert completed.snapshot.unique_canteen.holder_id == "ryan"

    # Synthetic capacity input isolates eviction after the engine supplied the verdict.
    retained_evidence = canonical_bytes(goals["ella"])
    refs = canonical_bytes([ref.model_dump(mode="json") for ref in memories["ella"].intent_refs])
    evicted = ingest_experience(
        memories["ella"],
        packet(
            completed.snapshot.tick + 1,
            actor="ella",
            run=run_id,
            speech=[heard("x" * (MAX_EXPERIENCE_BYTES + 1), tick=completed.snapshot.tick + 1)],
        ),
        run_id=run_id,
    )
    assert evicted.records == []
    assert canonical_bytes([ref.model_dump(mode="json") for ref in evicted.intent_refs]) == refs
    assert canonical_bytes(goals["ella"]) == retained_evidence
    assert own.evidence.feedback.intent_id == success_intent.intent_id


def test_target_moves_after_promise_then_give_fails_and_replanning_keeps_feedback():
    case = CASES["moved_target"]
    content = world_for("moved_target")
    run_id = content.config.meta.run_id
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    ella = ingest_experience(initial_experience("ella"), delivery(initial, "ella"), run_id=run_id)
    promised = tick(
        engine,
        intent(
            "talk",
            target={"kind": "resident", "id": "mia"},
            speech_act="statement",
            text=case["promise_text"],
        ),
    )
    assert delivery(promised, "mia").perception.heard_utterances[0].text == case["promise_text"]
    ella = ingest_experience(ella, delivery(promised, "ella"), run_id=run_id)
    moved = tick(
        engine,
        intent(
            "move_to",
            "mia",
            target={
                "kind": "tile",
                "position": {
                    "x": case["target_position"][0],
                    "y": case["target_position"][1],
                },
            },
        ),
    )
    assert (
        next(resident for resident in moved.snapshot.residents if resident.id == "mia").position.x
        == case["target_position"][0]
    )
    ella = ingest_experience(ella, delivery(moved, "ella"), run_id=run_id)
    plan_id = build_plan_id("ella", 0)
    give = intent(
        "give",
        target={"kind": "resident", "id": "mia"},
        item_type="canteen",
        quantity=1,
    ).model_copy(update={"plan_id": plan_id, "intent_id": build_intent_id(plan_id, 0)})
    plan = ActionPlan(
        plan_id=plan_id, actor_id="ella", created_at_tick=moved.snapshot.tick, intents=[give]
    )
    ella = capture_accepted_decision(
        ella, run_id, build_decision_id(run_id, "ella", 0), 0, plan, None, max_plan_actions=5
    )
    failed = tick(engine, give)
    assert failures(failed) == ["OUT_OF_REACH"]
    assert failed.snapshot.unique_canteen.holder_id == "ella"
    ella = ingest_experience(ella, delivery(failed, "ella"), run_id=run_id)
    evidence = ella.records[-1]
    assert evidence.kind == "action_feedback"
    data = evidence.payload.data
    assert isinstance(data, FeedbackData)
    assert data.feedback.status == "failure" and data.feedback.visible_effects == []
    assert data.owned_intent.intent == give
    next_plan_id = build_plan_id("ella", 1)
    next_plan = ActionPlan(
        plan_id=next_plan_id,
        actor_id="ella",
        created_at_tick=failed.snapshot.tick,
        intents=[
            intent("wait").model_copy(
                update={"plan_id": next_plan_id, "intent_id": build_intent_id(next_plan_id, 0)}
            )
        ],
    )
    replanned = capture_accepted_decision(
        ella, run_id, build_decision_id(run_id, "ella", 1), 1, next_plan, None, max_plan_actions=5
    )
    assert replanned.intent_refs[0].intent.action_type == "wait"
    assert replanned.records[-2] == evidence
    assert replanned.records[-2].payload.data.owned_intent.decision_ordinal == 0
    # A typed capacity packet is deliberately synthetic; no world speech could be this large.
    # Capture still advances at a boundary with no decision, and current refs survive eviction.
    refs = canonical_bytes([ref.model_dump(mode="json") for ref in replanned.intent_refs])
    oversized = packet(
        failed.snapshot.tick + 1,
        actor="ella",
        run=run_id,
        speech=[heard("x" * (MAX_EXPERIENCE_BYTES + 1), tick=failed.snapshot.tick + 1)],
    )
    evicted = ingest_experience(replanned, oversized, run_id=run_id)
    assert evicted.records == []
    assert evicted.next_sequence == replanned.next_sequence + 2
    assert canonical_bytes([ref.model_dump(mode="json") for ref in evicted.intent_refs]) == refs
    assert retrieve(evicted, query("ella"), "recent-relevant-v0").selected_records == []
    no_decision = ingest_experience(
        evicted, packet(failed.snapshot.tick + 2, actor="ella", run=run_id), run_id=run_id
    )
    assert [record.kind for record in no_decision.records] == ["own_state"]
    assert canonical_bytes([ref.model_dump(mode="json") for ref in no_decision.intent_refs]) == refs


def test_direct_speech_interrupts_promised_travel_without_transfer():
    content = world_for("moved_target", map={"walk_cost_budget_per_tick": 2})
    engine = create_engine(content, None)
    engine.initial_commit()
    promised = tick(
        engine,
        intent(
            "talk",
            target={"kind": "resident", "id": "mia"},
            speech_act="statement",
            text=CASES["moved_target"]["promise_text"],
        ),
    )
    assert any(event.type == "utterance_spoken" for event in promised.events)
    interrupted = tick(
        engine,
        intent("move_to", target={"kind": "tile", "position": {"x": 7, "y": 3}}),
        intent(
            "talk",
            "mia",
            target={"kind": "resident", "id": "ella"},
            speech_act="statement",
            text="Please stop and listen.",
        ),
    )
    feedback = delivery(interrupted, "ella").perception.last_action_feedback
    assert feedback.status == "interrupted"
    assert feedback.interruption_reason == "DIRECT_SPEECH"
    assert "item_given" not in feedback.visible_effects
    assert interrupted.snapshot.unique_canteen.holder_id == "ella"
    assert not any(event.type == "item_given" for event in interrupted.events)


def test_two_givers_contend_for_one_receiver_slot_and_only_one_gets_success():
    case = CASES["contention"]
    content = world_for("contention", inventory={"slot_capacity": case["receiver_slot_capacity"]})
    initial = create_engine(content, None).initial_commit()
    snapshot = initial.snapshot
    for actor in ("ella", "ryan"):
        next(resident for resident in snapshot.residents if resident.id == actor).fruit_count = 1
    engine = create_engine(content, snapshot, initial.events)
    given = tick(
        engine,
        *(
            intent(
                "give",
                actor,
                target={"kind": "resident", "id": case["receiver"]},
                item_type=case["item_type"],
                quantity=case["quantity"],
            )
            for actor in ("ella", "ryan")
        ),
    )
    assert failures(given) == ["INVENTORY_FULL"]
    transfers = [event for event in given.events if event.type == "item_given"]
    assert len(transfers) == 1 and transfers[0].actor_id == "ella"
    assert (
        next(resident for resident in given.snapshot.residents if resident.id == "mia").fruit_count
        == 1
    )
    assert delivery(given, "ella").perception.last_action_feedback.status == "success"
    loser = delivery(given, "ryan").perception.last_action_feedback
    assert (loser.status, loser.failure_code, loser.visible_effects) == (
        "failure",
        "INVENTORY_FULL",
        [],
    )
    receiver = delivery(given, "mia").perception
    assert receiver.last_action_feedback is None
    assert receiver.own_inventory.fruit_count == 1
    assert receiver.heard_utterances == []
