import json
from dataclasses import replace
from functools import partial

import pytest

from v2.decision_harness.resident_vectors import act, report


def test_dl01_eligible_reasons(packet):
    from living_island.sim.v2.turns import turn_reasons

    running = dict(
        intent_id="ella:t000000:a",
        action="act",
        verb="rest",
        tick_started=0,
        progress=None,
        start_target=None,
        items=[],
    )
    reasons = [report("action_ended", "ella:t000000:a"), report("woke")]
    for awareness in ("awake", "asleep", "unconscious"):
        boundary = packet(reports=reasons, running_action=running, awareness=awareness)
        assert turn_reasons(boundary, True) == (
            ("start", "woke", "action_ended", "notification") if awareness == "awake" else ()
        )


def test_dl02_reports_and_no_turn_observation(run):
    from living_island.agents.v2.decision.notifications import notifications

    for row, expected in [
        (report("progress_step", "thing"), "progress"),
        (report("utterance_heard", "u", addressed=True), "direct_speech"),
        (report("utterance_heard", "u", addressed=False), "nearby_speech"),
        (report("entity_first_seen", "thing"), "discovery"),
        (report("need_band_changed", "stamina", band="good"), "body"),
        (report("need_threshold_crossed", "hydration", threshold_id="urgent"), "body"),
        (report("action_observed", "thing"), None),
    ]:
        assert notifications([row], ()) == ({expected} if expected else set())
    session, fake, _, inputs = run(
        [act("act", verb="rest", mute=["progress", "discovery", "body"])]
    )
    session.advance()
    session.advance()
    assert len(fake.dispatches) == 1
    assert inputs["packets"].read(1)
    assert session.resident.delivery.packet.observed_tick == 1
    for _ in range(2):
        session.advance()
    assert len(fake.dispatches) == 1
    assert any(e.ref.kind == "observed_action" for e in session.resident.period.log.entries)


def test_dl03_mutes_and_critical_interrupt(run, island):
    from living_island.agents.v2.decision.notifications import notifications
    from living_island.sim.v2.cli import setup_world
    from living_island.world.v2.engine.perception import build_deliveries
    from living_island.world.v2.engine.tick import EventWriter, TickContext

    muted = ("body", "progress")
    for need in ("health", "hydration", "satiety"):
        for band in ("critical", "good"):
            assert bool(notifications([report("need_band_changed", need, band=band)], muted)) == (
                need in ("hydration", "satiety") and band == "critical"
            )
    world = setup_world(*island)
    world.state.needs["ella"].update(health=9000, hydration=9000)
    build_deliveries(TickContext(world.state, world.pack, EventWriter(world.state, 0)))
    session, _, _, _ = run(
        [act("act", verb="rest", mute=["body"]), act("continue"), act()], world=world
    )
    session.advance()
    for _ in range(8):
        session.advance()
        if len(session.records) == 2:
            break
    assert session.records[-1].submission.action.kind == "continue" and session.resident.muted == (
        "body",
    )
    for _ in range(8):
        session.advance()
        if len(session.records) == 3:
            break
    assert len(session.records) == 3 and not session.resident.muted


def test_dl04_parse_and_bind(run, monkeypatch):
    from living_island.world.v2.protocol import InvalidTurn

    raw = json.loads(act(intention={"set": "Look for water."}, actor_id="impostor"))
    raw["action"]["intent"]["intent_id"] = "foreign"
    session, fake, _, _ = run(
        [
            '{"step":"recall","query":"water"}',
            json.dumps({**raw, "intention": {"set": "a" * 501}}),
            json.dumps(raw),
        ],
        memory_on=False,
    )
    pending = session.world.pending_packets()
    original = session.runner._decide

    def wrong_companion(request):
        decision = original(request)
        if request.delivery.actor_id == "ryan":
            return decision.model_copy(update={"actor_id": "ella"})
        return decision

    with monkeypatch.context() as patch:
        patch.setattr(session.runner, "_decide", wrong_companion)
        with pytest.raises(InvalidTurn, match="does not answer"):
            session.advance()
    assert session.world.tick == 0 and session.world.pending_packets() == pending
    assert (
        not session.records and session.resident.period.store.snapshot.current_intention() is None
    )
    session.advance()
    [record] = session.records
    assert len(fake.dispatches) == 3 and fake.dispatches[1] == fake.dispatches[2]
    assert record.call_ids == (
        record.turn_id + ":decision",
        record.turn_id + ":decision_after_recall",
    )
    assert record.submission.action.intent.intent_id == record.turn_id + ":a"
    assert record.submission.actor_id == "ella"
    assert {"intention", "mute", "cite"}.isdisjoint(record.submission.model_dump())
    assert session.resident.period.store.snapshot.current_intention().text == "Look for water."


def test_dl12_retry_exhaustion(run):
    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls.fake import ScriptedReply

    for error, delays in [
        (429, [5, 10, 20, 40, 60]),
        (502, [2, 4, 8]),
        ("timeout", [2, 4, 8]),
        (200, [0]),
        (400, []),
    ]:
        session, fake, actual, _ = run([act()])
        reply = (
            TransportResponse(None, None, False, "timeout")
            if error == "timeout"
            else TransportResponse(error, b"{}", True)
        )
        fake.replies.extendleft([ScriptedReply(reply)] * (1 + len(delays)))
        session.advance()
        assert actual == [d for d in delays if d]
        assert len(set(fake.dispatches)) == 1 and len(fake.dispatches) == len(delays) + 1
        assert session.world.tick == 1 and session.records[-1].origin == "fallback"
        for _ in range(12):
            session.advance()
            if len(session.records) == 2:
                break
        assert session.records[-1].origin == "model"


def test_dl14_mixed_roster_handback_after_restore(run, island, tmp_path):
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.sim.equivalence.v1_extract import FixturePolicy, action, give, talk
    from living_island.sim.v2.compat.policy_host import restore_policies
    from living_island.sim.v2.harness.composition import compose
    from living_island.sim.v2.harness.session import ResidentContinuation

    session, fake, _, inputs = run([act(), "{}", "{}", act()])
    companion = session._hosts["ryan"]
    companion._factory = partial(
        FixturePolicy,
        overrides={("ryan", 0): (talk("ella", "statement"), action("wait"))},
        observed="",
    )
    session.model_host._factory = partial(
        FixturePolicy,
        overrides={
            ("ella", 1): (talk("ryan", "accept", in_reply_to="fixture-proposal"), give("ryan"))
        },
        observed="",
    )
    session.advance()
    assert (
        companion.checkpoint().queue and not session.runner.manifest.boundaries[-1].fallback_turns
    )
    assert next(
        s for s in session.runner.manifest.boundaries[-1].submissions if s.actor_id == "ryan"
    ).utterance
    session.advance()
    [tag] = session.runner.manifest.boundaries[-1].fallback_turns
    assert tag.submission.actor_id == "ella" and tag.submission.utterance is None
    assert (
        tag.submission.action.intent.action == "wait" and not session.model_host.checkpoint().queue
    )
    pending = session.world.pending_packets()
    path = tmp_path / "restore.json"
    save_checkpoint(path, session.world, inputs["packets"], session.checkpoint())
    restored = load_checkpoint(path, island[0].pack, inputs["packets"])
    continuation = ResidentContinuation.model_validate_json(
        session.continuation().model_dump_json()
    )
    assert [r.origin for r in session.records] == ["model", "fallback"]
    session = compose(
        restored.world, **inputs, restored=(restore_policies(restored.sim_checkpoint), continuation)
    )
    assert session.world.pending_packets() == pending
    session.advance()
    assert session.records[-1].origin == "model" and len(fake.dispatches) == 4
    assert not session.resident.delivery.packet.perception.action_feedback
    assert tag.submission.action.intent.intent_id.encode() not in fake.dispatches[-1]
    [backoff] = [
        cell
        for cell in session.model_host.checkpoint().policy_state.failed_targets
        if cell.action == "talk"
    ]
    assert (backoff.target.id, backoff.code, backoff.retry_after_tick) == (
        "ryan",
        "INVALID_SPEECH_ACT",
        38,
    )


def test_dl18_operator_stop_after_commit(run, tmp_path):
    session, fake, _, _ = run([act()])
    session.stop_file = tmp_path / "stop"
    session.stop_file.touch()
    session.advance()
    assert session.world.tick == 1 and session.incomplete.reason == "operator_stop"
    assert session.records[-1].submission in session.runner.manifest.boundaries[-1].submissions
    assert session.advance() is None and len(fake.dispatches) == 1


def test_dl24_incompatible_faint_duration(run, island):
    from living_island.sim.v2.cli import setup_world
    from living_island.world.v2.engine.validate import MentalFatigue

    world = setup_world(*island)
    world.pack = replace(
        world.pack,
        source=replace(world.pack.source, pack_id="starter-v1"),
        physiology=replace(world.pack.physiology, mental_fatigue=MentalFatigue(1, 1, 1, 1, 35)),
    )
    with pytest.raises(ValueError, match="faint_ticks 35.*K 36"):
        run([], world=world, compat=None)
    assert world.tick == 0


def test_compat_requires_registered_bridge(run):
    with pytest.raises(ValueError, match="requires the registered fallback bridge"):
        run([], compat=None)
