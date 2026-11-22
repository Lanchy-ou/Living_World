"""Exercise the coordinator using constructed packets at the world boundary."""

import pytest


def packet(actor_id, tick, *, awareness="awake", running=None, reports=()):
    from living_island.world.v2.protocol import BoundaryDelivery, Coord, Perception, WorldReport

    return BoundaryDelivery(
        delivery_id=f"{actor_id}/{tick}",
        actor_id=actor_id,
        observed_tick=tick,
        perception=Perception(
            schema_version="wap/0.1",
            actor_id=actor_id,
            tick=tick,
            awareness=awareness,
            needs=[],
            own_position=Coord(x=0, y=0),
            inventory=[],
            running_action=running,
            visible_tiles=[],
            explored_static_tiles=[],
            visible_entities=[],
            transient_sightings=[],
            environmental_cues=[],
            heard_utterances=[],
            observed_actions=[],
            action_feedback=[],
            last_utterance_feedback=None,
        ),
        reports=[
            WorldReport(kind=kind, subject_id=subject, addressed=None, band=None, threshold_id=None)
            for kind, subject in reports
        ],
    )


def running_wait(actor_id):
    from living_island.world.v2.protocol import RunningAction

    return RunningAction(
        intent_id=f"{actor_id}:t000000:a",
        action="wait",
        verb=None,
        tick_started=0,
        progress=None,
        start_target=None,
        items=[],
    )


def wait_choice():
    from living_island.world.v2.protocol import IntentShape, ModelIntentAction, ModelTurn

    return ModelTurn(
        action=ModelIntentAction(
            kind="intent",
            intent=IntentShape(
                action="wait",
                verb=None,
                target=None,
                params={},
                instruments=[],
                inputs=[],
                reason=None,
            ),
        ),
        utterance=None,
    )


class PacketWorld:
    """Publishes fixture packets and records calls at the World.step seam."""

    run_id = "packet-test"

    def __init__(self, *boundaries):
        from types import SimpleNamespace

        actor_ids = {packet.actor_id for boundary in boundaries for packet in boundary}
        self._boundaries = iter(boundaries)
        self.calls = []
        self.state = SimpleNamespace(
            tick=0,
            turn_ordinals=dict.fromkeys(actor_ids, 0),
            pending_deliveries={packet.actor_id: packet for packet in next(self._boundaries)},
            library=SimpleNamespace(vocabulary_hash="vocabulary", rule_library_hash="library"),
        )

    @property
    def tick(self):
        return self.state.tick

    def pending_packets(self):
        return tuple(packet for _, packet in sorted(self.state.pending_deliveries.items()))

    def step(self, submissions, *, acknowledged, fallbacks):
        from living_island.world.v2.engine import TickResult

        self.calls.append((submissions, acknowledged))
        for submission in submissions:
            self.state.turn_ordinals[submission.actor_id] += 1
        self.state.tick += 1
        self.state.pending_deliveries = {
            packet.actor_id: packet for packet in next(self._boundaries, ())
        }
        return TickResult((), (), {})


def test_turn_eligibility_delivery_order_and_continue(tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.protocol import ContinueAction, ModelTurn

    running_b = running_wait("b")
    world = PacketWorld(
        [packet("d", 0, awareness="asleep"), packet("b", 0), packet("a", 0)],
        [
            packet("d", 1, awareness="unconscious", reports=[("action_ended", "d:t000000:a")]),
            packet("c", 1, awareness="asleep", reports=[("action_ended", "c:t000000:a")]),
            packet("b", 1, running=running_b),
            packet("a", 1, reports=[("action_ended", "a:t000000:a")]),
        ],
        [
            packet("d", 2, reports=[("woke", None)]),
            packet("c", 2, reports=[("woke", None), ("action_ended", "c:t000000:a")]),
            packet("b", 2, running=running_b, reports=[("progress_step", running_b.intent_id)]),
            packet("a", 2, running=running_wait("a")),
        ],
        [packet("b", 3, running=running_b)],
    )
    received = []
    turns = []

    def deliver(delivery):
        received.append((world.state.tick, delivery.actor_id))
        return delivery.observed_tick == 2

    def decide(request):
        delivery = request.delivery
        assert delivery.observed_tick == world.state.tick
        assert len(world.calls) == world.state.tick
        assert [actor for tick, actor in received if tick == world.state.tick] == sorted(
            world.state.pending_deliveries
        )
        turns.append((world.state.tick, delivery.actor_id, request.reasons))
        if delivery.perception.running_action is not None:
            return request.bind(ModelTurn(action=ContinueAction(kind="continue"), utterance=None))
        return request.bind(wait_choice())

    runner = Runner(world, decide, deliver=deliver, journal=PacketJournal(tmp_path, world.run_id))
    for _ in range(4):
        assert runner.advance() is not None

    assert turns == [
        (0, "a", ("start",)),
        (0, "b", ("start",)),
        (1, "a", ("action_ended",)),
        (2, "a", ("notification",)),
        (2, "b", ("notification",)),
        (2, "c", ("woke", "action_ended")),
        (2, "d", ("woke",)),
    ]
    assert [tuple(turn.actor_id for turn in batch) for batch, _ in world.calls] == [
        ("a", "b"),
        ("a",),
        ("a", "b", "c", "d"),
        (),
    ]
    assert [turn.action.kind for turn in world.calls[2][0]] == [
        "continue",
        "continue",
        "intent",
        "intent",
    ]
    assert world.calls[1][1] == {actor: f"{actor}/1" for actor in "abcd"}
    assert world.calls[3][1] == {"b": "b/3"}


def test_scripted_fallback_records_only_after_the_world_commits(tmp_path):
    from living_island.agents.v2.port import AgentPort
    from living_island.agents.v2.scripted import ScriptedAgent
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.sim.v2.runner import Runner
    from living_island.sim.v2.turns import TurnRequest

    a0, b0 = packet("a", 0), packet("b", 0)
    a1 = packet("a", 1, reports=[("action_ended", "a:t000000:a")])
    world = PacketWorld([b0, a0], [a1])
    first, other, second = (
        TurnRequest(delivery, ordinal, ()).bind(wait_choice())
        for delivery, ordinal in [(a0, 0), (b0, 0), (a1, 1)]
    )
    primary: AgentPort = ScriptedAgent({"a": [second], "b": [other]})
    fallback: AgentPort = ScriptedAgent({"a": [first]})
    runner: Runner

    def decide(request):
        delivery = request.delivery
        actor = delivery.actor_id
        assert world.state.turn_ordinals[actor] == request.ordinal
        assert world.state.tick == len(runner.manifest.boundaries)
        if actor == "a" and request.ordinal == 0:
            return FallbackTurn(fallback.submit(delivery), "test failure", "scripted")
        return primary.submit(delivery)

    runner = Runner(
        world, decide, deliver=lambda _: False, journal=PacketJournal(tmp_path, world.run_id)
    )
    assert runner.advance() is not None
    assert world.calls[0][0] == (first, other)
    assert world.state.turn_ordinals == {"a": 1, "b": 1}
    assert runner.advance() is not None
    assert world.calls[1][0] == (second,)
    assert world.state.turn_ordinals == {"a": 2, "b": 1}
    assert runner.manifest.schema_version == "wap/0.1"
    assert runner.manifest.vocabulary_hash == "vocabulary"
    assert runner.manifest.rule_library_hash == "library"
    initial, later = runner.manifest.boundaries
    assert (initial.tick, initial.submissions, initial.fallback_turns) == (
        0,
        (first, other),
        (FallbackTurn(first, "test failure", "scripted"),),
    )
    assert (later.tick, later.submissions, later.fallback_turns) == (1, (second,), ())
    assert later.submissions[0].turn_id == "a:t000001"
    intent = later.submissions[0].action.intent
    assert (intent.actor_id, intent.turn_id, intent.intent_id) == (
        "a",
        "a:t000001",
        "a:t000001:a",
    )


def test_terminal_stop_keeps_the_frozen_boundary_and_witness(tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import FallbackTurn, StopRecord, TerminalStop
    from living_island.sim.v2.runner import Runner

    world = PacketWorld([packet("c", 0), packet("b", 0), packet("a", 0)])
    delivered = []
    decided = []
    stop = TerminalStop("stopped_unfit", {"call_kind": "recall", "floor": 90, "window": 80})

    def deliver(delivery):
        delivered.append(delivery.actor_id)
        return False

    def decide(request):
        actor_id = request.delivery.actor_id
        decided.append(actor_id)
        if actor_id == "a":
            return FallbackTurn(request.bind(wait_choice()), "test failure", "scripted")
        assert actor_id == "b"
        return stop

    runner = Runner(world, decide, deliver=deliver, journal=PacketJournal(tmp_path, world.run_id))
    assert runner.advance() is None
    assert runner.advance() is None
    assert delivered == ["a", "b", "c"]
    assert decided == ["a", "b"]
    assert world.calls == []
    assert world.state.tick == 0
    assert world.state.turn_ordinals == dict.fromkeys("abc", 0)
    assert set(world.state.pending_deliveries) == set("abc")
    assert runner.manifest.boundaries == []
    assert runner.manifest.stop == StopRecord(0, "b", "b:t000000", stop)


def test_invalid_submission_is_refused_before_the_world_port(monkeypatch, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.protocol import InvalidTurn

    world = PacketWorld([packet("a", 0)])
    calls = []

    original_step = world.step

    def track(*args, **kwargs):
        calls.append((args, kwargs))
        return original_step(*args, **kwargs)

    monkeypatch.setattr(world, "step", track)

    def decide(request):
        stale = request.bind(wait_choice()).model_copy(update={"observed_tick": 1})
        return FallbackTurn(stale, "test failure", "scripted")

    runner = Runner(
        world, decide, deliver=lambda _: False, journal=PacketJournal(tmp_path, world.run_id)
    )
    with pytest.raises(InvalidTurn, match="does not answer the scheduled turn"):
        runner.advance()
    assert calls == []
    assert world.state.tick == 0
    assert world.state.turn_ordinals == {"a": 0}
    assert runner.manifest.boundaries == []
    assert runner.manifest.stop is None
    [refused] = runner.manifest.refusals
    assert refused.tick == 0
    [submission] = refused.submissions
    assert submission.observed_tick == 1
