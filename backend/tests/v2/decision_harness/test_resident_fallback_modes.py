"""Visible feedback and calibration of the two private adapters used by the roster."""

import gzip
import json
from pathlib import Path


def _intent(template):
    from living_island.world.protocol import ActionIntent

    return ActionIntent(
        **template.model_dump(),
        intent_id="ella:p000000:i0",
        plan_id="ella:p000000",
        actor_id="ella",
    )


def _feedback(*, word=None, status="done", code=None, stop=None):
    from living_island.world.v2.protocol import ActionFeedback

    return ActionFeedback(
        intent_id="ella:t000000:a",
        status=status,
        failure_code=code,
        stop_reason=stop,
        phenomena=[word] if word else [],
        inspected=None,
        start_target=None,
        items_used=[],
    )


def test_dl13_visible_feedback_rows():
    from living_island.sim.equivalence.v1_extract import action, talk, target
    from living_island.sim.v2.compat.bridge import visible_result
    from living_island.world.v2.protocol import UtteranceFeedback

    tree = target("entity", "fruit_01")
    for template, words in [
        (
            action("gather", tree),
            [
                ("picks_fruit", None),
                ("too_tired", "EXHAUSTED"),
                ("hands_full", "INVENTORY_FULL"),
                ("finds_nothing", "RESOURCE_TAKEN"),
                ("nothing_happens", "OUT_OF_REACH"),
            ],
        ),
        (
            action("eat"),
            [("tastes_good", None), ("not_hungry", "NO_NEED"), ("nothing_happens", "NO_ITEM")],
        ),
        (
            action("drink", source="spring"),
            [("drinks", None), ("not_thirsty", "NO_NEED"), ("no_water_here", "OUT_OF_REACH")],
        ),
        (
            action("drink", source="canteen"),
            [
                ("drinks", None),
                ("not_thirsty", "NO_NEED"),
                ("no_water_here", "NO_WATER"),
                ("nothing_happens", "NO_ITEM"),
            ],
        ),
        (
            action("fill_canteen", tree),
            [
                ("fills_up", None),
                ("no_water_here", "OUT_OF_REACH"),
                ("already_full", "ALREADY_FULL"),
                ("nothing_happens", "NO_ITEM"),
            ],
        ),
        (action("rest"), [("rests", None), ("nothing_happens", "INVALID_TARGET")]),
        (action("sleep"), [("sleeps", None)]),
        (action("wait"), [(None, None)]),
    ]:
        for word, expected in words:
            assert (
                visible_result(_intent(template), 0, 1, _feedback(word=word), None).failure_code
                == expected
            )
    intent = _intent(talk("ryan", "statement"))
    for code in (None, "OUT_OF_REACH"):
        speech = UtteranceFeedback(utterance_id=None, failure_code=code)
        assert visible_result(intent, 0, 1, _feedback(), speech).failure_code == code
    for stop, expected in [
        ("EXHAUSTED", "EXHAUSTED"),
        ("PATH_BLOCKED", "PATH_BLOCKED"),
        ("WOKEN", "URGENT_NEED"),
        ("DEATH", "DEATH"),
        ("own_choice", None),
        ("FAINTED", None),
        ("TARGET_GONE", None),
    ]:
        result = visible_result(intent, 0, 1, _feedback(status="stopped", stop=stop), None)
        assert (result.failure_code or result.interruption_reason if result else None) == expected


def test_dl25_private_policy_calibration(island, run):
    from functools import partial

    from living_island.sim.equivalence.v1_extract import FixturePolicy, action, give, target
    from living_island.sim.v2.compat.bridge import LegacyBridge, visible_result
    from living_island.sim.v2.compat.policy_host import PolicyHost
    from living_island.world.v2.protocol import ActionResult, WorldStop

    bound, _ = island
    bridge = LegacyBridge(bound)
    archive = Path(__file__).resolve().parents[2] / "fixtures/v1_projection/scripted"
    for name, template, stop in [
        (
            "wap23-wap33-en23-gather-exhaustion",
            action("gather", target("entity", "fruit_01")),
            "EXHAUSTED",
        ),
        ("wap23-wap32-early-wake-no-speech", action("sleep"), "WOKEN"),
        ("wap23-give-too-few-items", give("ryan"), None),
    ]:
        frames = json.loads(gzip.decompress((archive / f"{name}.json.gz").read_bytes()))["frames"]
        oracle = next(o for f in frames for o in f["outcomes"] if o["actor_id"] == "ella")
        feedback = _feedback(
            status="stopped" if stop else "failed", stop=stop, code=None if stop else "NO_ITEM"
        )
        physical = ActionResult(
            intent_id=feedback.intent_id,
            actor_id="ella",
            tick_started=0,
            tick_finished=oracle["tick_finished"],
            outcome="stopped" if stop else "failure",
            failure_code=feedback.failure_code,
            stop=WorldStop(by="world", reason=stop) if stop else None,
            settlement=None,
            state_delta=[],
            visible_feedback=feedback,
            event_ids=[],
        )
        intent = _intent(template)
        private = bridge.translate(intent, physical, None)
        assert private == visible_result(intent, 0, physical.tick_finished, feedback, None)
        assert (private.status, private.failure_code or private.interruption_reason) == (
            oracle["status"],
            oracle["code"],
        )

    # A restored visible-mode adapter keeps both a previously deferred novelty
    # and new urgent input when FAINTED discards its dependent tail.
    session, _, _, settings = run(["{}", "{}"])
    host = session.model_host
    host._factory = partial(
        FixturePolicy, overrides={("ella", 0): (action("rest"), action("wait"))}, observed=""
    )
    session.advance()
    checkpoint = host.checkpoint()
    assert len(checkpoint.queue) == 1
    packet = next(p for p in session.world.pending_packets() if p.actor_id == "ella")
    visible = PolicyHost(
        settings["config"],
        settings["profiles"]["ella"],
        settings["sleep_ticks"],
        restored=checkpoint,
    )
    from v2.decision_harness.resident_vectors import report

    stranger = next(
        e for e in packet.perception.visible_entities if e.kind == "resident"
    ).model_copy(update={"entity_id": "arrival"})
    sight = packet.perception.model_copy(update={"visible_entities": [stranger]})
    visible.ingest(packet.model_copy(update={"perception": sight}))
    assert "NEW_SIGHT" in visible.checkpoint().deferred
    resumed = PolicyHost(
        settings["config"],
        settings["profiles"]["ella"],
        settings["sleep_ticks"],
        restored=visible.checkpoint(),
    )
    view = sight.model_copy(
        update={
            "awareness": "unconscious",
            "tick": 2,
            "running_action": None,
            "action_feedback": [_feedback(status="stopped", stop="FAINTED")],
        }
    )
    resumed.ingest(
        packet.model_copy(
            update={
                "observed_tick": 2,
                "perception": view,
                "reports": [report("need_threshold_crossed", "satiety", threshold_id="urgent")],
            }
        )
    )
    end = resumed.checkpoint()
    assert not end.queue and not end.issued
    assert {"NEW_SIGHT", "URGENT_NEED", "ACTION_INTERRUPTED"} <= set(end.deferred)
