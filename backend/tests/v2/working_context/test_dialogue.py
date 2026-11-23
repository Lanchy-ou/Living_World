"""DL-15. A relationship between heard words and successful replies lasts for one session."""

import json


def test_dl_15_dialogue_opens_answers_and_releases_on_gap_or_period_end(packet, audit):
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.guard import Assembly, Call, prepare
    from living_island.agents.v2.context.delivery import FilteredDelivery, OwnSpeech
    from living_island.agents.v2.context.dialogue import DialogueState
    from living_island.agents.v2.context.state import render_current_state
    from living_island.world.v2.protocol import HeardUtterance, Utterance

    dialogue = DialogueState("ella", gap_ticks=3)

    def spoken(to, act="statement", text="Hello.", *, terms=None, reply=None):
        return Utterance(addressee_id=to, speech_act=act, text=text, terms=terms, in_reply_to=reply)

    def heard(key, tick, words, speaker="ryan"):
        return HeardUtterance(
            utterance_id=key, heard_at_tick=tick, speaker_id=speaker, **words.model_dump()
        )

    def receive(tick, *heard_words, own=None, own_id=None):
        feedback = None
        if own is not None:
            feedback = {
                "utterance_id": own_id,
                "failure_code": None if own_id is not None else "OUT_OF_HEARING",
            }
        current = packet(
            tick=tick, heard_utterances=list(heard_words), last_utterance_feedback=feedback
        )
        joined = None if own is None else OwnSpeech(current.perception.last_utterance_feedback, own)
        dialogue.receive(FilteredDelivery(current, own_speech=joined))
        return current

    def request(current):
        state = render_current_state(
            current, reasons=("notification",), time_of_day="morning", dialogue=dialogue.sessions
        )
        call = Call(
            call_id=f"turn-{current.observed_tick}",
            tick=current.observed_tick,
            resident_id="ella",
            period_id="one",
        )
        assembly = Assembly.decision(
            state.parts, prefix_memories=(), day_log=(), pressure_at=state.pressure_at
        )
        admitted = prepare(call, Contract("decision"), assembly, audit).admitted
        return json.loads(admitted.wire.body)["input"][1]["content"]

    terms = {
        "promisor_id": "ella",
        "promisee_id": "ryan",
        "what": {"kind": "give_item", "item": {"archetype_id": "fruit", "quantity": 2}},
        "due_tick": 22,
    }
    proposal = spoken("ella", "propose", "Will you bring fruit?", terms=terms)
    receive(
        1,
        heard("broadcast", 1, spoken(None)),
        heard("other-pair", 1, spoken("kai")),
        own=spoken(None),
        own_id="my-broadcast",
    )
    assert dialogue.sessions == ()
    current = receive(2, heard("heard-id", 2, proposal))
    (session,) = dialogue.sessions
    assert (session.resident_id, session.counterpart_id, session.last_tick) == ("ella", "ryan", 2)
    assert session.reply_due == ("ella",)
    assert [p.utterance_id for p in session.unanswered] == ["heard-id"]
    visible = request(current)
    assert "Talking with ryan" in visible
    assert 'heard-id: "Will you bring fruit?"' in visible
    assert "ella would give 2 fruit for ryan by tick 22" in visible

    reply = spoken("ryan", "refuse", "I cannot.", reply="heard-id")
    receive(3, own=reply)
    assert dialogue.sessions == (session,)
    receive(4, own=reply, own_id="spoken-reply")
    assert dialogue.sessions[0].unanswered == ()
    assert dialogue.sessions[0].reply_due == ()
    receive(5, own=spoken("ryan", "propose", "Carry the fruit?", terms=terms), own_id="my-proposal")
    assert dialogue.sessions[0].reply_due == ("ryan",)
    receive(6, heard("their-reply", 6, spoken("ella", "accept", "Yes.", reply="my-proposal")))
    assert dialogue.sessions[0].reply_due == ()
    receive(9, heard("broadcast-again", 9, spoken(None)))
    assert dialogue.sessions[0].last_tick == 6
    at_gap = receive(10)
    assert dialogue.sessions == () and "Talking with" not in request(at_gap)

    receive(
        11,
        heard("another-offer", 11, proposal),
        heard("other-peer", 11, spoken("ella"), "kai"),
    )
    assert [s.counterpart_id for s in dialogue.sessions] == ["kai", "ryan"]
    dialogue.end_period()
    receive(12)
    assert dialogue.sessions == ()
    later = receive(13, heard("new-hello", 13, spoken("ella")))
    assert dialogue.sessions[0].unanswered == ()
    visible = request(later)
    assert "Talking with ryan" in visible and "another-offer" not in visible

    receive(14, heard("quiet-offer", 14, proposal))
    receive(17)
    receive(18, heard("later-session", 18, spoken("ella")))
    assert dialogue.sessions[0].last_tick == 18 and dialogue.sessions[0].unanswered == ()
