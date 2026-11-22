"""Exercise scheduling, binding and replay against the actual v2 world."""

import pytest
from test_runner import wait_choice

A, B = "res_a", "res_b"


def acknowledgements(world):
    return {packet.actor_id: packet.delivery_id for packet in world.pending_packets()}


def test_wap02_runner_identity_and_fallback_commit_once(real_world, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import InvalidTurn

    world = real_world
    initial = encode_snapshot(world)
    first = world.pending_packets()
    journal = PacketJournal(tmp_path, world.run_id)
    received = []
    refuse = True

    def deliver(packet):
        received.append(packet)
        return False

    def decide(request):
        assert request.delivery.observed_tick == world.tick
        assert request.ordinal == world.state.turn_ordinals[request.delivery.actor_id]
        submission = request.bind(wait_choice())
        if submission.actor_id == A:
            if refuse:
                return submission.model_copy(update={"observed_tick": 1})
            return FallbackTurn(submission, "test refusal", "scripted")
        return submission

    runner = Runner(world, decide, deliver=deliver, journal=journal)
    with pytest.raises(InvalidTurn):
        runner.advance()
    assert encode_snapshot(world) == initial
    assert not runner.manifest.boundaries
    [rejected] = runner.manifest.refusals
    assert rejected.tick == 0
    assert rejected.submissions[0].observed_tick == 1

    refuse = False
    advanced = runner.advance()
    assert [row.actor_id for row in advanced.actions] == [A, B]
    assert received == list(first)
    assert journal.read(0) == first
    [boundary] = runner.manifest.boundaries
    assert [turn.turn_id for turn in boundary.submissions] == [f"{A}:t000000", f"{B}:t000000"]
    [fallback] = boundary.fallback_turns
    assert fallback.submission == boundary.submissions[0]
    assert world.tick == 1
    assert world.state.turn_ordinals == {A: 1, B: 1}
    assert all(packet.observed_tick == 1 for packet in world.pending_packets())

    committed = encode_snapshot(world)
    with pytest.raises(InvalidTurn):
        world.step((fallback.submission,), acknowledged=acknowledgements(world))
    assert encode_snapshot(world) == committed

    runner.advance()
    assert [turn.turn_id for turn in runner.manifest.boundaries[-1].submissions] == [
        f"{A}:t000001",
        f"{B}:t000001",
    ]
    assert world.state.turn_ordinals == {A: 2, B: 2}


@pytest.mark.parametrize(
    "invalid", ["continue", "nested_actor", "nested_turn", "stale_tick", "intent_id", "utterance"]
)
def test_wap02_real_world_refuses_invalid_bindings_atomically(real_world, invalid):
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import InvalidTurn

    world = real_world
    world.step(acknowledged=acknowledgements(world))
    packet = world.pending_packets()[0]
    raw = TurnRequest(packet, 0, ()).bind(wait_choice()).model_dump(mode="json")
    match invalid:
        case "continue":
            raw["action"] = {"kind": "continue"}
        case "nested_actor":
            raw["action"]["intent"]["actor_id"] = B
        case "nested_turn":
            raw["action"]["intent"]["turn_id"] = f"{A}:t000001"
        case "stale_tick":
            raw["observed_tick"] = 0
        case "intent_id":
            raw["action"]["intent"]["intent_id"] = "bad"
        case "utterance":
            raw["utterance"] = {"text": "missing required fields"}

    before = encode_snapshot(world)
    with pytest.raises(InvalidTurn) as error:
        world.step((raw,), acknowledged=acknowledgements(world))
    assert error.value.code == "INVALID_TURN"
    assert encode_snapshot(world) == before


def test_wap12_settlement_is_policy_neutral(real_world, pack, setup, tmp_path):
    from living_island.agents.v2.scripted import ScriptedAgent
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.sim.v2.runner import Runner
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.protocol import TurnSubmission

    world = real_world
    normal = initialize(pack, setup)
    scripted = ScriptedAgent(
        {
            packet.actor_id: [TurnRequest(packet, 0, ("start",)).bind(wait_choice())]
            for packet in world.pending_packets()
        }
    )

    def scripted_fallback(request):
        return FallbackTurn(scripted.submit(request.delivery), "test timeout", "scripted")

    plain_runner = Runner(
        normal,
        lambda request: request.bind(wait_choice()),
        deliver=lambda _: False,
        journal=PacketJournal(tmp_path / "normal", normal.run_id),
    )
    fallback_runner = Runner(
        world,
        scripted_fallback,
        deliver=lambda _: False,
        journal=PacketJournal(tmp_path / "fallback", world.run_id),
    )
    expected = plain_runner.advance()
    actual = fallback_runner.advance()
    plain = plain_runner.manifest.boundaries[0]
    tagged = fallback_runner.manifest.boundaries[0]
    assert set(TurnSubmission.model_fields) == {
        "schema_version",
        "turn_id",
        "actor_id",
        "observed_tick",
        "action",
        "utterance",
    }
    assert plain.submissions == tagged.submissions
    assert actual.actions == expected.actions
    assert actual.utterances == expected.utterances
    assert (
        tuple(event for event in actual.events if event.type != "agent_fallback_used")
        == expected.events
    )
    assert world.pending_packets() == normal.pending_packets()
    assert world.state.turn_ordinals == normal.state.turn_ordinals


def test_wap16_real_notification_continue_and_fallback_replay(real_world, pack, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RuleStore, replay
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import (
        ContinueAction,
        Coord,
        IntentShape,
        ModelIntentAction,
        ModelTurn,
        TileTarget,
        Utterance,
    )

    world = real_world
    journal = PacketJournal(tmp_path / "packets", world.run_id)
    start = encode_snapshot(world)
    pinned = RunManifest.capture(world.run_id, pack)
    received = []
    turns = []

    def deliver(packet):
        received.append(packet)
        return any(
            report.kind == "utterance_heard" and report.addressed for report in packet.reports
        )

    def decide(request):
        packet = request.delivery
        actor = packet.actor_id
        turns.append((packet.observed_tick, actor, request.reasons))
        if packet.observed_tick == 0 and actor == A:
            choice = ModelTurn(
                action=ModelIntentAction(
                    kind="intent",
                    intent=IntentShape(
                        action="move_to",
                        verb=None,
                        target=TileTarget(kind="tile", position=Coord(x=5, y=1)),
                        instruments=[],
                        inputs=[],
                        params={},
                        reason=None,
                    ),
                ),
                utterance=None,
            )
            return request.bind(choice)
        if packet.observed_tick == 0 and actor == B:
            choice = wait_choice().model_copy(
                update={
                    "utterance": Utterance(
                        addressee_id=A,
                        speech_act="statement",
                        text="Hello.",
                        terms=None,
                        in_reply_to=None,
                    )
                }
            )
            return request.bind(choice)
        if packet.observed_tick == 1 and actor == A:
            assert packet.perception.running_action.intent_id == f"{A}:t000000:a"
            choice = ModelTurn(action=ContinueAction(kind="continue"), utterance=None)
            return FallbackTurn(request.bind(choice), "fixture timeout", "scripted")
        submission = request.bind(wait_choice())
        if packet.observed_tick == 2 and actor == B:
            return FallbackTurn(submission, "fixture timeout", "scripted")
        return submission

    runner = Runner(world, decide, deliver=deliver, journal=journal)
    snapshots = []
    original_events = []
    actions = []
    for tick in range(3):
        before = world.pending_packets()
        result = runner.advance()
        assert journal.read(tick) == before
        original_events.append(result.events)
        actions.append(result.actions)
        snapshots.append(encode_snapshot(world))

    assert [entry for entry in turns if entry[1] == A] == [
        (0, A, ("start",)),
        (1, A, ("notification",)),
        (2, A, ("action_ended",)),
    ]
    assert [
        (row.intent_id, row.tick_started, row.tick_finished)
        for row in actions[1]
        if row.actor_id == A
    ] == [(f"{A}:t000000:a", 0, 2)]
    assert world.state.turn_ordinals == {A: 3, B: 3}
    assert [
        (event.tick, event.actor_id, event.payload["turn_id"])
        for batch in original_events
        for event in batch
        if event.type == "agent_fallback_used"
    ] == [(2, A, f"{A}:t000001"), (3, B, f"{B}:t000002")]
    records = tuple(boundary.for_replay() for boundary in runner.manifest.boundaries)
    prior_calls = tuple(turns)
    prior_deliveries = tuple(received)
    regenerated = list(replay(start, pinned, pack, journal, RuleStore(tmp_path), records))
    assert [item.snapshot for item in regenerated] == snapshots
    assert [item.event_lines for item in regenerated] == [item.event_lines for item in records]
    assert tuple(turns) == prior_calls
    assert tuple(received) == prior_deliveries


def test_real_terminal_stop_keeps_pending_boundary(real_world, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import FallbackTurn, StopRecord, TerminalStop
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine.snapshot import encode_snapshot

    world = real_world
    before = encode_snapshot(world)
    pending = world.pending_packets()
    journal = PacketJournal(tmp_path, world.run_id)
    witness = TerminalStop("stopped_unfit", {"call_kind": "recall", "floor": 90, "window": 80})

    def decide(request):
        if request.delivery.actor_id == A:
            return FallbackTurn(request.bind(wait_choice()), "fixture timeout", "scripted")
        return witness

    runner = Runner(world, decide, deliver=lambda _: False, journal=journal)
    assert runner.advance() is None
    assert runner.advance() is None
    assert encode_snapshot(world) == before
    assert journal.read(0) == pending
    assert runner.manifest.boundaries == []
    assert runner.manifest.refusals == []
    assert runner.manifest.stop == StopRecord(0, B, f"{B}:t000000", witness)
