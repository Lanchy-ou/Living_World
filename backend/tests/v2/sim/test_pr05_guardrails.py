"""Real-world regressions for turn and callback boundaries."""

from dataclasses import replace

import pytest
from test_runner import wait_choice


def test_runner_rejects_swapped_callback_answers_before_world_step(
    real_world, tmp_path, monkeypatch
):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.sim.v2.runner import Runner
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import InvalidTurn

    world = real_world
    before = encode_snapshot(world)
    a, b = world.pending_packets()
    for_a = TurnRequest(a, 0, ("start",)).bind(wait_choice())
    for_b = TurnRequest(b, 0, ("start",)).bind(wait_choice())
    calls = []
    original_step = world.step

    def observe_step(*args, **kwargs):
        calls.append((args, kwargs))
        return original_step(*args, **kwargs)

    monkeypatch.setattr(world, "step", observe_step)

    swap = True

    def decide(request):
        if swap:
            if request.delivery.actor_id == a.actor_id:
                return FallbackTurn(for_b, "wrong actor", "scripted")
            return for_a
        return request.bind(wait_choice())

    runner = Runner(
        world, decide, deliver=lambda _: False, journal=PacketJournal(tmp_path, world.run_id)
    )
    with pytest.raises(InvalidTurn):
        runner.advance()
    assert calls == []
    assert encode_snapshot(world) == before
    assert world.state.turn_ordinals == {a.actor_id: 0, b.actor_id: 0}
    assert runner.manifest.boundaries == []
    assert len(runner.manifest.refusals) == 1

    swap = False
    runner.advance()
    assert len(calls) == 1
    assert world.state.turn_ordinals == {a.actor_id: 1, b.actor_id: 1}


@pytest.mark.parametrize("kind", ["orphan", "stale", "duplicate"])
def test_world_refuses_fallback_metadata_without_one_matching_committed_turn(real_world, kind):
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.engine.tick import FallbackFact
    from living_island.world.v2.protocol import InvalidTurn

    world = real_world
    before = encode_snapshot(world)
    a, b = world.pending_packets()
    submission = TurnRequest(a, 0, ("start",)).bind(wait_choice())
    valid = FallbackFact(a.actor_id, submission.turn_id, "timeout", "scripted")
    facts = {
        "orphan": (FallbackFact(b.actor_id, f"{b.actor_id}:t000000", "timeout", "scripted"),),
        "stale": (FallbackFact(a.actor_id, f"{a.actor_id}:t000001", "timeout", "scripted"),),
        "duplicate": (valid, valid),
    }[kind]
    ids = {p.actor_id: p.delivery_id for p in (a, b)}
    stored = []
    proposal = {
        "id": "extra_rest",
        "trigger": "verb:rest",
        "work_ticks": 1,
        "provenance": {
            "kind": "proposed",
            "llm_call_id": "call_a",
            "approved_by": a.actor_id,
            "approved_at_tick": 0,
        },
    }
    with pytest.raises(InvalidTurn):
        world.step(
            [submission],
            acknowledged=ids,
            fallbacks=facts,
            rule_additions=[proposal],
            store_rule=lambda digest, raw: stored.append((digest, raw)),
        )
    assert stored == []
    assert encode_snapshot(world) == before


def test_receiver_cannot_remove_action_ended_from_coordinator(real_world, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.runner import Runner

    world = real_world
    journal = PacketJournal(tmp_path, world.run_id)
    ticks = []

    def deliver(packet):
        journaled = {p.actor_id: p for p in journal.read(packet.observed_tick)}
        assert packet == journaled[packet.actor_id]
        packet.reports.clear()
        return False

    def decide(request):
        ticks.append((request.delivery.observed_tick, request.delivery.actor_id))
        return request.bind(wait_choice())

    runner = Runner(world, decide, deliver=deliver, journal=journal)
    runner.advance()
    assert all(any(r.kind == "action_ended" for r in p.reports) for p in world.pending_packets())
    runner.advance()
    assert ticks == [(0, "res_a"), (0, "res_b"), (1, "res_a"), (1, "res_b")]


@pytest.mark.parametrize("fallback", [False, True])
def test_committed_submission_does_not_alias_callback_output(real_world, pack, tmp_path, fallback):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RuleStore, replay
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine.snapshot import encode_snapshot

    world = real_world
    journal = PacketJournal(tmp_path, world.run_id)
    start = encode_snapshot(world)
    pinned = RunManifest.capture(world.run_id, pack)
    returned = []

    def decide(request):
        submission = request.bind(wait_choice())
        returned.append(submission)
        return FallbackTurn(submission, "timeout", "scripted") if fallback else submission

    runner = Runner(world, decide, deliver=lambda _: False, journal=journal)
    runner.advance()
    end = encode_snapshot(world)
    submitted_bytes = [s.model_dump_json() for s in runner.manifest.boundaries[0].submissions]
    returned[0].action.intent.params["injected"] = 1
    [boundary] = runner.manifest.boundaries
    assert [s.model_dump_json() for s in boundary.submissions] == submitted_bytes
    if fallback:
        assert boundary.fallback_turns[0].submission.model_dump_json() == submitted_bytes[0]
    else:
        assert boundary.fallback_turns == ()
    [regenerated] = replay(
        start, pinned, pack, journal, RuleStore(tmp_path), [boundary.for_replay()]
    )
    assert regenerated.snapshot == end


def test_terminal_witness_does_not_alias_callback_output(real_world, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import TerminalStop
    from living_island.sim.v2.runner import Runner

    world = real_world
    data = {"call_kind": "recall", "counts": {"floor": 90, "candidates": ["fact"]}}
    stop = TerminalStop("stopped_unfit", data)
    runner = Runner(
        world,
        lambda _: stop,
        deliver=lambda _: False,
        journal=PacketJournal(tmp_path, world.run_id),
    )
    assert runner.advance() is None
    data["counts"]["floor"] = 1
    data["counts"]["candidates"].clear()
    assert runner.manifest.stop.stop.witness == {
        "call_kind": "recall",
        "counts": {"floor": 90, "candidates": ["fact"]},
    }


def test_replay_rejects_self_consistent_fallback_tag_for_an_unsubmitted_actor(
    real_world, pack, tmp_path
):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RecordedBoundary, RuleStore, replay
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.engine.tick import FallbackFact
    from living_island.world.v2.protocol import InvalidTurn, encode_event_line

    world = real_world
    start = encode_snapshot(world)
    manifest = RunManifest.capture(world.run_id, pack)
    journal = PacketJournal(tmp_path, world.run_id)
    store = RuleStore(tmp_path)
    a, b = world.pending_packets()
    a_turn = TurnRequest(a, 0, ("start",)).bind(wait_choice())
    valid = FallbackFact(a.actor_id, a_turn.turn_id, "timeout", "test-policy")
    output = world.step([a_turn], acknowledged=journal.ingest(world), fallbacks=(valid,))
    *events, tag = output.events
    original = RecordedBoundary(
        (a_turn,), b"".join(map(encode_event_line, output.events)), (valid,)
    )
    [control] = replay(start, manifest, pack, journal, store, [original])
    assert control.event_lines == original.event_lines
    assert control.snapshot == encode_snapshot(world)

    orphan = replace(valid, actor_id=b.actor_id, turn_id=f"{b.actor_id}:t000000")
    revised = tag.model_copy(
        update={
            "actor_id": orphan.actor_id,
            "payload": {**tag.payload, "resident_id": orphan.actor_id, "turn_id": orphan.turn_id},
        }
    )
    forged = replace(
        original,
        event_lines=b"".join(map(encode_event_line, [*events, revised])),
        fallbacks=(orphan,),
    )
    with pytest.raises(InvalidTurn):
        tuple(replay(start, manifest, pack, journal, store, [forged]))


def test_delivery_retry_preserves_an_earlier_successful_callback(real_world, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine.snapshot import encode_snapshot

    world = real_world
    before = encode_snapshot(world)
    journal = PacketJournal(tmp_path, world.run_id)
    seen = []
    decisions = []
    will_raise = True

    def deliver(packet):
        nonlocal will_raise
        seen.append(packet.actor_id)
        if packet.actor_id == "res_b" and will_raise:
            will_raise = False
            raise OSError("receiver failed before ingesting res_b")
        return False

    def decide(request):
        decisions.append(request.delivery.actor_id)
        return request.bind(wait_choice())

    runner = Runner(world, decide, deliver=deliver, journal=journal)
    with pytest.raises(OSError, match="receiver failed"):
        runner.advance()
    assert decisions == []
    assert runner.manifest.boundaries == []
    assert encode_snapshot(world) == before
    assert journal.read(0) == world.pending_packets()
    runner.advance()
    assert decisions == ["res_a", "res_b"]
    assert seen == ["res_a", "res_b", "res_b"]


def test_mutating_old_fallback_answer_cannot_break_replay(real_world, pack, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RuleStore, replay
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine.snapshot import encode_snapshot

    world = real_world
    start = encode_snapshot(world)
    manifest = RunManifest.capture(world.run_id, pack)
    journal = PacketJournal(tmp_path, world.run_id)
    store = RuleStore(tmp_path)
    old = []

    def decide(request):
        submission = request.bind(wait_choice())
        old.append(submission)
        return FallbackTurn(submission, "timeout", "test-policy")

    runner = Runner(world, decide, deliver=lambda _: False, journal=journal)
    runner.advance()
    end = encode_snapshot(world)
    [boundary] = runner.manifest.boundaries
    [control] = replay(start, manifest, pack, journal, store, [boundary.for_replay()])
    assert control.snapshot == end

    old[0].action.intent.params["injected"] = 1
    [regenerated] = replay(start, manifest, pack, journal, store, [boundary.for_replay()])
    assert regenerated.snapshot == end


@pytest.mark.parametrize(
    ("nested", "field", "value"),
    [
        (False, "turn_id", "res_a:t000001"),
        (True, "actor_id", "res_b"),
        (True, "turn_id", "res_a:t000001"),
        (True, "intent_id", "res_a:t000001:a"),
    ],
)
def test_runner_refuses_mismatched_turn_identity(
    real_world, tmp_path, monkeypatch, nested, field, value
):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import InvalidTurn

    world = real_world
    before = encode_snapshot(world)

    def unexpected_step(*args, **kwargs):
        pytest.fail("invalid callback answer reached the world port")

    monkeypatch.setattr(world, "step", unexpected_step)

    def decide(request):
        turn = request.bind(wait_choice())
        if nested:
            intent = turn.action.intent.model_copy(update={field: value})
            return turn.model_copy(
                update={"action": turn.action.model_copy(update={"intent": intent})}
            )
        return turn.model_copy(update={field: value})

    runner = Runner(
        world, decide, deliver=lambda _: False, journal=PacketJournal(tmp_path, world.run_id)
    )
    with pytest.raises(InvalidTurn):
        runner.advance()
    assert encode_snapshot(world) == before
    assert world.state.turn_ordinals == {"res_a": 0, "res_b": 0}
    assert not runner.manifest.boundaries
    assert len(runner.manifest.refusals) == 1


def test_decision_retry_preserves_packet_and_owns_refused_answer(real_world, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import InvalidTurn

    world = real_world
    journal = PacketJournal(tmp_path, world.run_id)
    returned = []
    decisions = []

    def decide(request):
        packet = request.delivery
        decisions.append((packet.observed_tick, packet.actor_id, request.reasons))
        if packet.observed_tick == 1:
            assert any(report.kind == "action_ended" for report in packet.reports)
            packet.reports.clear()
            if not returned:
                wrong = request.bind(wait_choice()).model_copy(update={"observed_tick": 0})
                returned.append(wrong)
                return wrong
        return request.bind(wait_choice())

    runner = Runner(world, decide, deliver=lambda _: False, journal=journal)
    runner.advance()
    before = encode_snapshot(world)
    with pytest.raises(InvalidTurn):
        runner.advance()
    assert encode_snapshot(world) == before
    returned[0].action.intent.params["injected"] = 1
    [refusal] = runner.manifest.refusals
    assert refusal.submissions[0].action.intent.params == {}
    assert journal.read(1) == world.pending_packets()

    runner.advance()
    assert decisions[2:] == [
        (1, "res_a", ("action_ended",)),
        (1, "res_a", ("action_ended",)),
        (1, "res_b", ("action_ended",)),
    ]
    assert world.state.turn_ordinals == {"res_a": 2, "res_b": 2}
