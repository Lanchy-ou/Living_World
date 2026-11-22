"""Production-path regressions from the independent PR-06 review."""

from dataclasses import replace

import pytest
from test_scripted import _wait_choice, hosts_for, load_case, seeded_world
from test_scripted import archive as archive


def _packets(world):
    return {packet.actor_id: packet for packet in world.pending_packets()}


@pytest.mark.parametrize("mode", ("bridge", "visible"))
def test_fallback_controls_after_restore(archive, tmp_path, mode):
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import action
    from living_island.sim.v2.compat.policy_host import PolicySession, UseFallback, restore_policies
    from living_island.world.v2 import protocol as v2

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-gather-empty-at-start")
    case = replace(case, plans={("ella", 1): (action("rest"),)})
    world = seeded_world(bound, content, case)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    received = []
    requested = []

    def deliver(packet):
        if packet.actor_id == "ella":
            received.append(packet)
            return packet.observed_tick == 2 or any(
                report.kind == "progress_step" for report in packet.reports
            )
        return False

    def choose(packet):
        if packet.actor_id == "ella":
            requested.append(packet)
            if packet.observed_tick == 1:
                return UseFallback("offline probe")
            if packet.perception.running_action is not None:
                return v2.ModelTurn(action=v2.ContinueAction(kind="continue"), utterance=None)
        return _wait_choice()

    session = PolicySession(
        world, hosts_for(bound, content, case, mode), journal, model=choose, model_delivery=deliver
    )
    session.advance()
    session.advance()
    running = _packets(world)["ella"].perception.running_action
    assert running is not None and running.verb == "rest"
    path = tmp_path / "restore.json"
    save_checkpoint(path, world, journal, session.checkpoint())
    restored = load_checkpoint(path, bound.pack, journal)
    session = PolicySession(
        restored.world,
        hosts_for(bound, content, case, mode, restore_policies(restored.sim_checkpoint)),
        journal,
        model=choose,
        model_delivery=deliver,
    )
    session.advance()
    assert requested[-1].observed_tick == received[-1].observed_tick == 2
    assert _packets(restored.world)["ella"].perception.running_action.intent_id == running.intent_id
    for public in (requested[-1], received[-1]):
        assert public.perception.running_action == running
        assert not public.perception.action_feedback

    while restored.world.tick < 6:
        raw = _packets(restored.world)["ella"]
        session.advance()
        if any(report.kind == "progress_step" for report in raw.reports):
            for public in (requested[-1], received[-1]):
                assert public.observed_tick == raw.observed_tick
                assert (
                    public.perception.running_action.progress
                    == raw.perception.running_action.progress
                )
                assert [r for r in public.reports if r.kind == "progress_step"] == [
                    r for r in raw.reports if r.kind == "progress_step"
                ]
            break
    else:
        pytest.fail("rest did not reach a progress notification")


@pytest.mark.parametrize("mode", ("bridge", "visible"))
def test_fallback_end_signal_and_no_private_feedback(archive, tmp_path, mode):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.compat.policy_host import PolicySession, UseFallback

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-gather-empty-at-start")
    case = replace(case, plans={("ella", 1): case.plans["ella", 0]})
    world = seeded_world(bound, content, case)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    seen = []
    memory = []

    def deliver(packet):
        if packet.actor_id == "ella":
            memory.append(packet)
        return False

    def choose(packet):
        if packet.actor_id == "ella":
            seen.append(packet)
            if packet.observed_tick == 1:
                return UseFallback("offline probe")
        return _wait_choice()

    session = PolicySession(
        world, hosts_for(bound, content, case, mode), journal, model=choose, model_delivery=deliver
    )
    session.advance()
    session.advance()
    raw = _packets(world)["ella"]
    [end] = [report for report in raw.reports if report.kind == "action_ended"]
    assert raw.perception.action_feedback[0].phenomena == ["finds_nothing"]
    session.advance()
    assert next(packet for packet in journal.read(2) if packet.actor_id == "ella") == raw
    for public in (seen[-1], memory[-1]):
        assert public.observed_tick == 2 and not public.perception.action_feedback
        [signal] = [report for report in public.reports if report.kind == "action_ended"]
        assert signal.subject_id is None
        assert end.subject_id not in public.model_dump_json()
        assert "finds_nothing" not in public.model_dump_json()


@pytest.mark.parametrize("mode", ("bridge", "visible"))
def test_real_fallback_exact_tag_and_world_replay(archive, tmp_path, mode):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RuleStore, replay
    from living_island.sim.v2.compat.policy_host import PolicySession, UseFallback
    from living_island.world.v2.engine.snapshot import encode_snapshot

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-gather-empty-at-start")
    case = replace(case, plans={("ella", 1): case.plans["ella", 0]})
    world = seeded_world(bound, content, case)
    opening = encode_snapshot(world)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    hosts = hosts_for(bound, content, case, mode)
    calls = []

    def choose(packet):
        calls.append((packet.actor_id, packet.observed_tick))
        if (packet.actor_id, packet.observed_tick) == ("ella", 1):
            return UseFallback("offline probe reason")
        return _wait_choice()

    session = PolicySession(world, hosts, journal, model=choose)
    snapshots = []
    for _ in range(3):
        result = session.advance()
        if world.tick == 2:
            [event] = [entry for entry in result.events if entry.type == "agent_fallback_used"]
            [fallback] = session.runner.manifest.boundaries[-1].fallback_turns
            assert event.actor_id == "ella"
            assert event.payload == {
                "resident_id": "ella",
                "turn_id": fallback.submission.turn_id,
                "reason": "offline probe reason",
                "fallback_policy_id": hosts["ella"].config.policy_id,
            }
        snapshots.append(encode_snapshot(world))
    calls_before = list(calls)
    recorded = [boundary.for_replay() for boundary in session.runner.manifest.boundaries]
    replayed = list(
        replay(
            opening,
            RunManifest.capture(world.run_id, bound.pack),
            bound.pack,
            journal,
            RuleStore(tmp_path),
            recorded,
        )
    )
    assert [entry.snapshot for entry in replayed] == snapshots
    assert [item.event_lines for item in replayed] == [item.event_lines for item in recorded]
    assert calls == calls_before


@pytest.mark.parametrize(
    ("due_tick", "expected"),
    [(20, ("statement", None, None)), (None, ("request", "fruit", 1))],
)
def test_native_timed_proposal_is_not_a_v1_request(due_tick, expected):
    from living_island.sim.v2.compat.adapters import legacy_speech
    from living_island.world.v2 import protocol as v2

    terms = v2.Terms(
        promisor_id="ella",
        promisee_id="ryan",
        due_tick=due_tick,
        what=v2.GiveItemTerm(
            kind="give_item", item=v2.KindItemSpec(archetype_id="fruit", quantity=1)
        ),
    )
    speech = v2.Utterance(
        addressee_id="ella",
        speech_act="propose",
        text="Bring a fruit later.",
        terms=terms,
        in_reply_to=None,
    )
    assert legacy_speech("ryan", speech) == expected


def test_cue_does_not_hide_independently_visible_entity_receipt(archive, tmp_path):
    from living_island.world.v2.engine.perception import build_deliveries
    from living_island.world.v2.engine.tick import EventWriter, TickContext
    from living_island.world.v2.engine.validate import CueSetup

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-gather-empty-at-start")
    world = seeded_world(bound, content, case)
    state = world.state
    tree = state.entities["fruit_01"]
    cue = CueSetup(
        id=tree.entity_id,
        kind="damp_moss",
        position=tree.place.position,
        visible_description="Distant moss",
        near_description="Near moss",
        direction=None,
    )
    from living_island.world.v2.engine.state import Cue

    state.cues = (
        Cue(
            cue.id,
            cue.kind,
            cue.position,
            cue.visible_description,
            cue.near_description,
            cue.direction,
        ),
    )
    receipt = state.exposure_receipts_by_resident["ella"]
    receipt.entities.pop(tree.entity_id)
    build_deliveries(TickContext(state, world.pack, EventWriter(state, 0)))
    packet = _packets(world)["ella"]
    assert tree.entity_id in {value.entity_id for value in packet.perception.visible_entities}
    assert tree.entity_id in {value.cue_id for value in packet.perception.environmental_cues}
    assert tree.entity_id in receipt.entities


@pytest.mark.parametrize("mode", ("bridge", "visible"))
def test_legacy_only_interrupt_does_not_override_model_mute(archive, tmp_path, mode):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import move, seeded
    from living_island.sim.v2.compat.policy_host import PolicySession, UseFallback

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-ct15-refused-profiles")
    case = replace(
        case, plans={("ella", 1): (move(21, 32),)}, setup=seeded(positions={"ella": (12, 32)})
    )
    world = seeded_world(bound, content, case)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    hosts = hosts_for(bound, content, case, mode)
    requests = []

    def choose(packet):
        if packet.actor_id == "ella":
            requests.append(packet.observed_tick)
            if packet.observed_tick == 1:
                return UseFallback("offline probe")
        return _wait_choice()

    session = PolicySession(world, hosts, journal, model=choose, model_delivery=lambda _: False)
    session.advance()
    session.advance()
    packet = _packets(world)["ella"]
    assert packet.perception.running_action is not None
    assert packet.perception.environmental_cues[0].detail_level == "near"
    assert all(report.kind not in ("action_ended", "woke") for report in packet.reports)
    session.advance()
    assert requests == [0, 1]
    assert _packets(world)["ella"].perception.running_action is None


@pytest.mark.parametrize("mode", ("bridge", "visible"))
def test_private_feedback_carrier_and_native_schedule_marker(archive, tmp_path, monkeypatch, mode):
    from living_island.agents.runtime import Runtime
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import FixturePolicy
    from living_island.sim.v2.compat.adapters import project_perception
    from living_island.sim.v2.compat.policy_host import PolicySession, UseFallback

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-gather-empty-at-start")
    case = replace(case, plans={("ella", 1): case.plans["ella", 0]})
    world = seeded_world(bound, content, case)
    hosts = hosts_for(bound, content, case, mode)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    legacy_ingestions = []
    planner_requests = []
    model_inputs = []
    memory_inputs = []
    original_ingest = Runtime.ingest
    original_decide = FixturePolicy.decide

    def inspect(runtime, delivery):
        if delivery.actor_id == "ella":
            legacy_ingestions.append(delivery.model_copy(deep=True))
        original_ingest(runtime, delivery)

    def decide(policy, request):
        if request.actor_id == "ella":
            planner_requests.append(request.model_copy(deep=True))
        return original_decide(policy, request)

    def choose(packet):
        model_inputs.append(packet)
        if (packet.actor_id, packet.observed_tick) == ("ella", 1):
            return UseFallback("offline probe")
        return _wait_choice()

    def deliver(packet):
        memory_inputs.append(packet)
        return False

    monkeypatch.setattr(Runtime, "ingest", inspect)
    monkeypatch.setattr(FixturePolicy, "decide", decide)
    session = PolicySession(world, hosts, journal, model=choose, model_delivery=deliver)
    session.advance()
    session.advance()
    fallback_opening = hosts["ella"].checkpoint()
    session.advance()
    assert [delivery.observed_tick for delivery in legacy_ingestions] == [1, 2]
    assert all(not delivery.decision_triggers for delivery in legacy_ingestions)
    assert all(delivery.perception.last_action_feedback is None for delivery in legacy_ingestions)
    assert fallback_opening.boundary_triggers == ()
    scheduling, feedback = planner_requests
    assert (scheduling.tick, scheduling.triggers) == (1, ["PLAN_FINISHED"])
    assert scheduling.context.perception.last_action_feedback is None
    assert (feedback.tick, feedback.triggers) == (2, ["ACTION_FAILED"])
    private = feedback.context.perception.last_action_feedback
    assert private.failure_code == "RESOURCE_TAKEN"
    assert private.intent_id == "ella:p000000:i0"
    opening, resumed = hosts["ella"].decision_trace
    assert opening.scheduling_marker == "native_fallback"
    assert resumed.scheduling_marker is None
    assert opening.record.triggers == scheduling.triggers
    [backoff] = hosts["ella"].checkpoint().policy_state.failed_targets
    assert (backoff.code, backoff.retry_after_tick) == ("RESOURCE_TAKEN", 38)
    for packet in (*journal.read(1), *journal.read(2), *model_inputs, *memory_inputs):
        serialized = packet.model_dump_json()
        assert all(
            token not in serialized
            for token in ("PLAN_FINISHED", "RESOURCE_TAKEN", "ACTION_FAILED", "ella:p000000:i0")
        )
        assert project_perception(packet.perception).last_action_feedback is None


def test_world_setup_accepts_same_named_cue_and_entity(archive, tmp_path, monkeypatch):
    from living_island.world.v2 import engine
    from living_island.world.v2.engine.validate import CueSetup, WorldSetup

    original = engine.initialize
    bound, content, case, _ = load_case(archive, tmp_path, "wap23-gather-empty-at-start")
    seen = []

    def initialize(pack, setup):
        cue = CueSetup(
            id="fruit_01",
            kind="damp_moss",
            position=setup.cues[0].position,
            visible_description="Distant moss",
            near_description="Near moss",
            direction=None,
        )
        altered = WorldSetup.model_validate({**setup.model_dump(), "cues": (cue,)})
        world = original(pack, altered)
        seen.append(world)
        return world

    monkeypatch.setattr(engine, "initialize", initialize)
    world = seeded_world(bound, content, case)
    assert seen == [world]
    packet = _packets(world)["ella"]
    assert "fruit_01" in {value.entity_id for value in packet.perception.visible_entities}
    assert "fruit_01" in {value.cue_id for value in packet.perception.environmental_cues}
    assert "fruit_01" in world.state.exposure_receipts_by_resident["ella"].entities


def test_both_same_named_sightings_survive_a_real_move(archive, tmp_path, monkeypatch):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import move, seeded
    from living_island.sim.v2.compat.adapters import project_perception
    from living_island.sim.v2.compat.policy_host import PolicySession
    from living_island.world.v2 import engine
    from living_island.world.v2.engine.validate import WorldSetup

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-gather-empty-at-start")
    case = replace(
        case,
        plans={("ella", 0): (move(10, 2),)},
        setup=seeded(positions={"ella": (1, 2)}, known_route=True),
    )
    original = engine.initialize

    def initialize(pack, setup):
        data = setup.model_dump()
        data["cues"][0]["id"] = "fruit_01"
        data["clock"]["start_minute"] = 1200
        return original(pack, WorldSetup.model_validate(data))

    monkeypatch.setattr(engine, "initialize", initialize)
    world = seeded_world(bound, content, case)
    hosts = hosts_for(bound, content, case, "visible")
    session = PolicySession(world, hosts, PacketJournal(tmp_path / "journal", world.run_id))
    session.advance()
    packet = _packets(world)["ella"]
    assert packet.perception.own_position.x == 8
    assert not any(view.entity_id == "fruit_01" for view in packet.perception.visible_entities)
    assert {
        (view.archetype_id, view.position.x, view.position.y, view.seen_at_step)
        for view in packet.perception.transient_sightings
        if view.entity_id == "fruit_01"
    } == {("fruit_tree", 3, 2, 5), (None, 3, 1, 4)}
    [cue] = packet.perception.environmental_cues
    assert (cue.cue_id, cue.detail_level) == ("fruit_01", "near")
    receipt = world.state.exposure_receipts_by_resident["ella"]
    assert receipt.entities["fruit_01"].archetype_id == "fruit_tree"
    assert receipt.cue_detail_seen["fruit_01"] == "near"

    legacy = project_perception(packet.perception)
    [tree] = [view for view in legacy.transient_sightings if view.entity_id == "fruit_01"]
    assert tree.entity_type == "fruit_tree" and tree.seen_at_step == 5
    assert legacy.environmental_cues[0].cue_id == "fruit_01"
    hosts["ella"].ingest(packet)
    assert {
        (entry.entity_type, entry.x, entry.y)
        for entry in hosts["ella"].checkpoint().receipts.entities
        if entry.entity_id == "fruit_01"
    } == {("fruit_tree", 3, 2), ("cue", 3, 1)}


@pytest.mark.parametrize("mode", ("bridge", "visible"))
@pytest.mark.parametrize("handback", ("continue", "replace"))
def test_model_handback_resolves_real_stop_only(archive, tmp_path, mode, handback):
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import action, move, seeded
    from living_island.sim.v2.compat.policy_host import PolicySession, UseFallback, restore_policies
    from living_island.world.v2 import protocol as v2

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-ct15-refused-profiles")
    case = replace(
        case,
        plans={("ella", 1): (move(21, 32), action("wait"))},
        setup=seeded(positions={"ella": (12, 32)}),
    )
    world = seeded_world(bound, content, case)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    hosts = hosts_for(bound, content, case, mode)
    model_inputs = []
    memory_inputs = []

    def deliver(packet):
        if packet.actor_id == "ella":
            memory_inputs.append(packet)
        return packet.actor_id == "ella" and packet.observed_tick == 2

    def choose(packet):
        if packet.actor_id == "ella":
            model_inputs.append(packet)
            if packet.observed_tick == 1:
                return UseFallback("offline probe")
            if packet.observed_tick == 2 and handback == "continue":
                return v2.ModelTurn(action=v2.ContinueAction(kind="continue"), utterance=None)
        return _wait_choice()

    session = PolicySession(world, hosts, journal, model=choose, model_delivery=deliver)
    session.advance()
    session.advance()
    active = _packets(world)["ella"].perception.running_action
    queue = hosts["ella"].checkpoint().queue
    assert [intent.action_type for intent in queue] == ["wait"]
    advanced = session.advance()
    if handback == "continue":
        [outcome] = [result for result in advanced.actions if result.intent_id == active.intent_id]
        assert outcome.outcome == "success"
        assert hosts["ella"].checkpoint().boundary_results == ()
        assert hosts["ella"].checkpoint().queue == queue
        assert "NEW_SIGHT" in hosts["ella"].checkpoint().deferred
        session.advance()
        [result] = hosts["ella"].checkpoint().boundary_results
        assert result.status == "success" and result.tick_finished == 3
        return
    pending = _packets(world)["ella"]
    assert any(
        f.intent_id == active.intent_id and f.stop_reason == "own_choice"
        for f in pending.perception.action_feedback
    )
    assert hosts["ella"].checkpoint().queue == ()
    assert hosts["ella"].checkpoint().handled_stops == (active.intent_id,)
    assert hosts["ella"].checkpoint().boundary_results == ()
    path = tmp_path / "restore.json"
    save_checkpoint(path, world, journal, session.checkpoint())
    restored = load_checkpoint(path, bound.pack, journal)
    hosts = hosts_for(bound, content, case, mode, restore_policies(restored.sim_checkpoint))
    session = PolicySession(restored.world, hosts, journal, model=choose, model_delivery=deliver)
    session.advance()
    assert model_inputs[-1].observed_tick == memory_inputs[-1].observed_tick == 3
    assert active.intent_id not in model_inputs[-1].model_dump_json()
    assert active.intent_id not in memory_inputs[-1].model_dump_json()
    for public in (model_inputs[-1], memory_inputs[-1]):
        assert any(r.kind == "action_ended" and r.subject_id is None for r in public.reports)
        [feedback] = public.perception.action_feedback
        assert feedback.intent_id != active.intent_id and feedback.status == "done"
    assert not hosts["ella"].checkpoint().handled_stops
    assert not hosts["ella"].checkpoint().boundary_results
