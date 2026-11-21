"""Agreement terms, proposal replies, and event causality."""

from copy import deepcopy
from dataclasses import replace

import pytest
from test_speech import A, B, C, speech_events, statement, turn


def propose(what, *, due_tick=None, promisor=B, promisee=A):
    return {
        **statement(B),
        "speech_act": "propose",
        "text": "Can we agree to this?",
        "terms": {
            "promisor_id": promisor,
            "promisee_id": promisee,
            "what": what,
            "due_tick": due_tick,
        },
    }


def reply(proposal_id, act="accept", addressee=A):
    return {
        **statement(addressee),
        "speech_act": act,
        "in_reply_to": proposal_id,
    }


GIVE_KIND = {"kind": "give_item", "item": {"archetype_id": "arch_a", "quantity": 2}}
GIVE_EXACT = {"kind": "give_item", "item": {"item_id": "inst_a"}}
RETURN = {"kind": "return_item", "item_id": "inst_a"}
CONTRIBUTE = {"kind": "contribute", "process_id": "inst_e", "work_ticks": 2}
BE_AT = {"kind": "be_at", "position": {"x": 2, "y": 1}}


def test_wap09_acceptance_emits_sorted_listeners_and_causal_agreement(audience, deliveries):
    terms = propose(GIVE_KIND, due_tick=8, promisor=A, promisee=B)
    first = audience.step([turn(audience, A, utterance=terms)])
    proposal_event, direct, overheard = speech_events(first)
    proposal_id = proposal_event.event_id
    assert proposal_event.payload["utterance_id"] == proposal_id
    assert direct.actor_id == B and overheard.actor_id == C
    assert audience.state.proposals[proposal_id].dialogue_session == (A, B)
    assert audience.state.proposals[proposal_id].answer is None
    assert not audience.state.agreements
    entities = deepcopy(audience.state.entities)

    accepted = audience.step([turn(audience, B, utterance=reply(proposal_id))])
    spoken, listener_a, listener_c, agreement = speech_events(accepted)
    assert [event.type for event in (spoken, listener_a, listener_c, agreement)] == [
        "utterance_spoken",
        "utterance_heard",
        "utterance_heard",
        "agreement_accepted",
    ]
    assert [event.actor_id for event in (listener_a, listener_c)] == [A, C]
    assert listener_a.target_id == listener_c.target_id == B
    assert listener_a.caused_by_event_ids == listener_c.caused_by_event_ids == [spoken.event_id]
    assert spoken.caused_by_event_ids == [proposal_id]
    assert agreement.caused_by_event_ids == [proposal_id, spoken.event_id]
    assert [event.seq_in_tick for event in (spoken, listener_a, listener_c, agreement)] == list(
        range(spoken.seq_in_tick, spoken.seq_in_tick + 4)
    )
    assert agreement.payload == {
        "agreement_id": agreement.event_id,
        "proposal_id": proposal_id,
        "acceptance_id": spoken.event_id,
        "terms": terms["terms"],
    }
    record = audience.state.agreements[agreement.event_id]
    assert record.terms.model_dump() == terms["terms"]
    assert (record.proposal_id, record.acceptance_id, record.tick) == (
        proposal_id,
        spoken.event_id,
        2,
    )
    assert audience.state.proposals[proposal_id].answer == "accept"
    assert audience.state.entities == entities
    assert deliveries[-1].utterances[B] == accepted.utterances[B]


@pytest.mark.parametrize("answer", ["accept", "refuse"])
@pytest.mark.parametrize("second_answer", ["accept", "refuse"])
def test_proposal_can_only_be_answered_once(world, answer, second_answer):
    offered = world.step([turn(world, A, utterance=propose(GIVE_KIND))])
    proposal_id = offered.utterances[A].utterance_id
    answered = world.step([turn(world, B, utterance=reply(proposal_id, answer))])
    assert answered.utterances[B].failure_code is None
    assert world.state.proposals[proposal_id].answer == answer
    assert len(world.state.agreements) == (1 if answer == "accept" else 0)
    before = deepcopy(world.state.agreements)
    result = world.step([turn(world, B, utterance=reply(proposal_id, second_answer))])
    assert result.utterances[B].failure_code == "INVALID_REPLY"
    assert not speech_events(result)
    assert world.state.agreements == before


@pytest.mark.parametrize("case", ["missing", "statement", "wrong_addressee", "wrong_speaker"])
def test_invalid_reply_is_checked_before_session_limit(audience, case):
    proposal_id = "missing_proposal"
    if case != "missing":
        initial = statement(B) if case == "statement" else propose(GIVE_KIND)
        proposal_id = (
            audience.step([turn(audience, A, utterance=initial)]).utterances[A].utterance_id
        )
    speaker = C if case == "wrong_speaker" else B
    addressee = C if case == "wrong_addressee" else A
    audience.state.dialogue_limits = replace(audience.state.dialogue_limits, max_turns=0)
    result = audience.step(
        [turn(audience, speaker, utterance=reply(proposal_id, addressee=addressee))]
    )
    assert result.utterances[speaker].failure_code == "INVALID_REPLY"
    assert not speech_events(result)
    assert not audience.state.agreements


@pytest.mark.parametrize(
    "what,due_tick",
    [(GIVE_KIND, None), (GIVE_EXACT, None), (RETURN, 8), (BE_AT, 8), (CONTRIBUTE, None)],
)
def test_wap09_well_formed_terms_are_kept_for_all_kinds(world, what, due_tick):
    initial = propose(what, due_tick=due_tick)
    result = world.step([turn(world, A, utterance=initial)])
    feedback = result.utterances[A]
    assert feedback.failure_code is None
    assert world.state.proposals[feedback.utterance_id].terms.model_dump() == initial["terms"]
    assert speech_events(result)[0].payload["terms"] == initial["terms"]


@pytest.mark.parametrize("case", ["held", "previously_exposed"])
def test_exact_reference_does_not_require_existing_inventory_on_the_promisor(world, case):
    from living_island.world.v2.engine.state import Held

    if case == "held":
        del world.state.exposure_receipts_by_resident[A].entities["inst_a"]
        world.state.entities["inst_a"].place = Held(A)
    else:
        del world.state.entities["inst_a"]
    result = world.step([turn(world, A, utterance=propose(RETURN))])
    assert result.utterances[A].failure_code is None


@pytest.mark.parametrize(
    "what,due_tick,promisor,promisee",
    [
        (GIVE_KIND, None, B, B),
        (GIVE_KIND, None, "third_party", A),
        (GIVE_EXACT, 0, B, A),
        (GIVE_EXACT, 1, B, A),
        ({"kind": "give_item", "item": {"item_id": "unexposed"}}, None, B, A),
        (
            {"kind": "give_item", "item": {"archetype_id": "unknown_kind", "quantity": 1}},
            None,
            B,
            A,
        ),
        ({"kind": "return_item", "item_id": "unexposed"}, None, B, A),
        ({"kind": "contribute", "process_id": "unexposed", "work_ticks": 1}, None, B, A),
        ({"kind": "be_at", "position": {"x": -1, "y": 1}}, 8, B, A),
    ],
)
def test_invalid_terms_precede_session_cap_and_leave_the_action_independent(
    world, what, due_tick, promisor, promisee
):
    world.state.dialogue_limits = replace(world.state.dialogue_limits, max_turns=0)
    initial = propose(what, due_tick=due_tick, promisor=promisor, promisee=promisee)
    result = world.step([turn(world, A, utterance=initial)])
    assert result.utterances[A].failure_code == "INVALID_TERMS"
    assert result.actions[0].outcome == "success"
    assert not speech_events(result)
    assert not world.state.proposals


def test_unexplored_in_bounds_position_is_invalid_terms(world):
    from living_island.world.v2.protocol import Coord

    position = Coord(x=2, y=1)
    world.state.explored_tiles_by_resident[A].discard(world.state.static_map.index(position))
    result = world.step([turn(world, A, utterance=propose(BE_AT, due_tick=8))])
    assert result.utterances[A].failure_code == "INVALID_TERMS"


def test_utterance_validation_orders_hearing_before_terms(world):
    from living_island.world.v2.protocol import Coord

    world.state.residents[B].position = Coord(x=5, y=1)
    result = world.step([turn(world, A, utterance=propose(GIVE_KIND, promisor=A, promisee=A))])
    assert result.utterances[A].failure_code == "OUT_OF_HEARING"


@pytest.mark.parametrize(
    "case", ["unknown_act", "no_reply", "no_due", "zero_quantity", "zero_work"]
)
def test_binding_rejects_invalid_utterance_shape_atomically(world, case):
    from living_island.world.v2.protocol import InvalidTurn

    match case:
        case "unknown_act":
            utterance = {**statement(B), "speech_act": "whisper"}
        case "no_reply":
            utterance = reply(None)
        case "no_due":
            utterance = propose(BE_AT)
        case "zero_quantity":
            utterance = propose(
                {"kind": "give_item", "item": {"archetype_id": "arch_a", "quantity": 0}}
            )
        case "zero_work":
            utterance = propose({"kind": "contribute", "process_id": "inst_e", "work_ticks": 0})
    before = deepcopy(world.state)
    with pytest.raises(InvalidTurn):
        world.step([turn(world, A, utterance=utterance), turn(world, B)])
    assert world.state == before


def test_deadline_is_rechecked_against_the_emission_tick(world, monkeypatch):
    from living_island.world.v2.engine import speech

    check_start = speech.check_start
    start_results = []

    def capture_start(ctx, attempt):
        check_start(ctx, attempt)
        start_results.append(attempt.failure)

    monkeypatch.setattr(speech, "check_start", capture_start)
    result = world.step([turn(world, A, utterance=propose(GIVE_KIND, due_tick=1))])
    assert start_results == [None]
    assert result.utterances[A].failure_code == "INVALID_TERMS"
    assert not speech_events(result)


def test_reply_does_not_recheck_the_proposals_deadline(world):
    proposed = world.step([turn(world, A, utterance=propose(BE_AT, due_tick=2))])
    world.step()
    result = world.step([turn(world, B, utterance=reply(proposed.utterances[A].utterance_id))])
    assert result.utterances[B].failure_code is None
    (agreement,) = world.state.agreements.values()
    assert agreement.tick == 3
    assert agreement.terms.due_tick == 2
