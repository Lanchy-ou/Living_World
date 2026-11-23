"""Resident period transitions with short synthetic sequences of delivered packets."""

from v2.consolidation.conftest import sleeping
from v2.decision_harness.resident_vectors import act, report


def _wake(session, packet, tick, **view):
    from living_island.agents.v2.context.delivery import FilteredDelivery

    boundary = FilteredDelivery(packet(tick=tick, reports=[report("woke")], **view))
    session.resident.deliver(boundary, {}, ())
    return session.resident.decide(f"ella:t{tick:06d}", ("woke",), "morning", frozenset())


def test_dl17_off_arm_exact_k_and_short_sleep(run, packet):
    from functools import partial

    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.memory.v2.mechanical import AgreementFact
    from living_island.sim.equivalence.v1_extract import FixturePolicy, action
    from living_island.world.v2.protocol import Terms

    session, fake, _, _ = run(
        [
            act(intention={"set": "Return the cup."}),
            act(),
            '{"step":"recall","query":"cup"}',
            act(),
        ],
        memory_on=False,
    )
    session.advance()
    mind = session.resident
    prefix = mind.period.context.prefix
    terms = Terms.model_validate(
        dict(
            promisor_id="ella",
            promisee_id="ryan",
            due_tick=None,
            what={"kind": "return_item", "item_id": "cup"},
        )
    )
    agreement = AgreementFact(
        "private-acceptance", "promisor", "ryan", terms, None, 0, "proposal", "acceptance"
    )
    mind.dialogue.gap_ticks = 100
    utterance = dict(
        addressee_id="ella",
        speech_act="propose",
        text="Return my cup.",
        terms=terms,
        in_reply_to=None,
        utterance_id="ryan:proposal",
        speaker_id="ryan",
        heard_at_tick=1,
    )
    mind.deliver(
        FilteredDelivery(
            packet(
                tick=1,
                reports=[report("utterance_heard", "ryan:proposal", addressed=True)],
                heard_utterances=[utterance],
            )
        ),
        {},
        (agreement,),
    )
    assert mind.dialogue.sessions[0].unanswered
    short, intents = sleeping(packet, tick=3, start=2, duration=6)
    mind.deliver(short, intents, ())
    _wake(session, packet, 8)
    assert mind.period.context.prefix is prefix
    assert mind.dialogue.sessions[0].unanswered
    assert mind.period.store.snapshot.current_intention().text == "Return the cup."
    mind.publish("ella:t000008", ("woke",), None, None)
    long, intents = sleeping(packet, tick=10, start=9, duration=36)
    mind.deliver(long, intents, ())
    _wake(
        session,
        packet,
        45,
        own_position={"x": 2, "y": 0},
        explored_static_tiles=[{"position": {"x": 0, "y": 0}, "terrain": "beach"}],
    )
    assert mind.period.context.prefix.period_id != prefix.period_id
    assert mind.period.context.prefix.memories == ()
    assert not mind.dialogue.sessions and not mind.period.store.snapshot.current_intention()
    assert any(r.kind == "commitment" for r in mind.period.store.snapshot.records())
    assert b"private-acceptance" not in fake.dispatches[-1] and b"@ you" in fake.dispatches[-1]
    assert any(e.type == "recall" for e in mind.period.log.entries)

    session, _, _, _ = run(["{}", "{}"], memory_on=False)
    host = session.model_host
    host._factory = partial(
        FixturePolicy, overrides={("ella", 0): (action("sleep"), action("wait"))}, observed=""
    )
    session.advance()
    assert host.checkpoint().queue
    sleep, intents = sleeping(packet, tick=1, start=0, duration=36)
    session.resident.deliver(sleep, intents, ())
    raw = next(p for p in session.world.pending_packets() if p.actor_id == "ella")
    wake = raw.perception.model_copy(
        update={
            "tick": 36,
            "awareness": "awake",
            "observed_actions": [],
            "running_action": None,
            "action_feedback": [],
            "heard_utterances": [],
        }
    )
    session._deliver(
        raw.model_copy(
            update={
                "observed_tick": 36,
                "delivery_id": "wake-at-k",
                "reports": [report("woke")],
                "perception": wake,
            }
        )
    )
    assert session.resident.period.number == 2 and not host.checkpoint().queue
    assert host.checkpoint().policy_state is None


def test_dl26_living_k_opens_once_and_death_abandons(run, packet, island):
    from functools import partial

    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls.fake import ScriptedReply
    from living_island.sim.equivalence.v1_extract import FixturePolicy, action
    from living_island.sim.v2.cli import setup_world
    from living_island.world.v2.engine.perception import build_deliveries
    from living_island.world.v2.engine.tick import EventWriter, TickContext

    world = setup_world(*island)
    world.state.needs["ella"].update(health=9000, hydration=9000)
    build_deliveries(TickContext(world.state, world.pack, EventWriter(world.state, 0)))
    session, fake, _, _ = run([act(), "{}", "{}", act("continue"), act(), act()], world=world)
    host = session.model_host
    host._factory = partial(
        FixturePolicy, overrides={("ella", 1): (action("rest"), action("wait"))}, observed=""
    )
    session.advance()
    session.advance()
    private = session.records[-1].submission.action.intent.intent_id
    assert host.checkpoint().queue
    for _ in range(9):
        session.advance()
        if len(session.records) == 3:
            break
    assert private in host.checkpoint().issued and not host.checkpoint().queue
    assert b"Continue or replace" in fake.dispatches[-1] and b"Running rest" in fake.dispatches[-1]
    for _ in range(8):
        session.advance()
        if len(session.records) == 5:
            break
    assert len(session.records) == 5
    assert private not in session.resident.delivery.feedback_sources
    assert all(
        private not in e.ref.model_dump_json()
        for e in session.resident.period.log.entries
        if e.type in ("action_result", "recall", "inspection")
    )

    for outcome in ("committed", "failed", "dead"):
        extra = ['{"read":[]}', '{"ops":[]}'] if outcome == "committed" else []
        session, fake, _, _ = run([act(), *extra, '{"ids":[]}', act(), act()])
        session.advance()
        mind = session.resident
        sleep, intents = sleeping(packet, tick=2, start=1, duration=36)
        mind.deliver(sleep, intents, ())
        if outcome == "dead":
            assert mind.period.death(37).record.reason == "death"
            assert len(fake.dispatches) == 1 and mind.period.context is None
            continue
        if outcome == "failed":
            fake.replies.appendleft(ScriptedReply(TransportResponse(400, None, False)))
        _wake(session, packet, 37)
        first = mind.period.context.prefix
        assert first.morning.outcome == "adopted"
        assert bool(mind.period.pending.read()) == (outcome == "failed")
        mind.publish("ella:t000037", ("woke",), None, None)
        _wake(session, packet, 38)
        assert mind.period.context.prefix is first and not fake.replies
