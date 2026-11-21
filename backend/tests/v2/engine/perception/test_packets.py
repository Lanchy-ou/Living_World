"""Assert resident-visible packets published by the real world boundary."""

from copy import deepcopy

import pytest

A, B, C, D = "res_a", "res_b", "res_c", "res_d"

SLEEP_RULE = """
[[rule]]
id = "packet_sleep"
trigger = "verb:sleep"
work_ticks = { param = "duration_ticks" }
"""
BODY = """
enabled_verbs = ["sleep"]
enabled_needs = ["health", "satiety", "hydration", "mental_fatigue"]

[physiology]
replace = true
stamina_awake_decay_per_tick = 0
stamina_move_extra_cost_per_tick = 0
satiety_awake_decay_per_tick = 1
satiety_asleep_decay_per_tick = 1
health_recovery_min_satiety = 10
hydration_awake_decay_per_tick = 1
hydration_asleep_decay_per_tick = 1
health_recovery_min_hydration = 10
health_loss_per_tick_if_deprived = 1
health_recovery_sleep_per_tick = 0
awake_per_tick = 1
per_utterance_heard = 0
per_first_sighting = 0
recovery_per_tick_asleep = 1
faint_ticks = 3

[timing]
replace = true
invalid_attempt_ticks = 1
give_ticks = 3
pick_up_ticks = 1
drop_ticks = 1
wait_ticks = 1
inspect_ticks = 1

[timing.attempt_ticks]
build = 1
combine = 1
fill = 1
gather = 1
rest = 1
strike = 1
sleep = 1

[needs.health]
min = 0
max = 10
initial = 10
band_cutoffs = [2, 4, 6, 8]
max_gain_per_tick = 0
max_loss_per_tick = 1

[needs.satiety]
min = 0
max = 10
initial = 10
band_cutoffs = [2, 4, 6, 8]
max_gain_per_tick = 0
max_loss_per_tick = 1
thresholds = [{ id = "urgent", at = 3, wakes = true }]

[needs.hydration]
min = 0
max = 10
initial = 10
band_cutoffs = [2, 4, 6, 8]
max_gain_per_tick = 0
max_loss_per_tick = 1

[needs.mental_fatigue]
min = 0
max = 100
initial = 0
band_cutoffs = [20, 40, 60, 80]
max_gain_per_tick = 0
max_loss_per_tick = 1
"""


def packet(world, actor=A):
    return world.state.pending_deliveries[actor]


def step(world, *turns):
    return world.step(
        turns,
        acknowledged={
            key: value.delivery_id for key, value in world.state.pending_deliveries.items()
        },
    )


def turn(world, actor, action, *, speech=None, **fields):
    identity = f"{actor}:t{world.state.turn_ordinals[actor]:06d}"
    return {
        "schema_version": "wap/0.1",
        "actor_id": actor,
        "turn_id": identity,
        "observed_tick": world.state.tick,
        "utterance": speech,
        "action": {
            "kind": "intent",
            "intent": {
                "intent_id": f"{identity}:a",
                "turn_id": identity,
                "actor_id": actor,
                "action": action,
                "verb": None,
                "target": None,
                "params": {},
                "instruments": [],
                "inputs": [],
                "reason": None,
                **fields,
            },
        },
    }


def entity(key, kind="entity"):
    return {"kind": kind, "id": key}


def tile(x, y):
    return {"kind": "tile", "position": {"x": x, "y": y}}


def statement(addressee=None):
    return {
        "addressee_id": addressee,
        "speech_act": "statement",
        "text": "Water nearby.",
        "terms": None,
        "in_reply_to": None,
    }


def sleep(world, actor, duration=6):
    return turn(world, actor, "act", verb="sleep", params={"duration_ticks": duration})


def report_rows(delivery):
    return [(r.kind, r.subject_id, r.addressed, r.band, r.threshold_id) for r in delivery.reports]


def report(kind, subject=None, *, addressed=None, band=None, threshold=None):
    return kind, subject, addressed, band, threshold


def looks(item):
    return {row.property_id: row.value for row in item.descriptors}


def events(result, kind):
    return [event for event in result.events if event.type == kind]


def test_wap05_replacement_feedback_is_delivered_once(make_world):
    world = make_world(
        [(A, 3, 1), (B, 2, 1)],
        rules="""
[[rule]]
id = "packet_gather"
trigger = "verb:gather"
work_ticks = 4
target = { where = { archetype = "arch_b" } }
inputs = [{ slot = "kit", where = { archetype = "arch_a" }, qty = 1 }]
on_interrupt = { partial = [{ archetype = "arch_a", quantity = 1, at = "actor" }] }
conditions = [
  { id = "ready", kind = "state", of = "target", field = "store.count", op = ">", value = 0 },
]
effects = [{ op = "move", from = "target.store", to = "actor", quantity = 1 }]
""",
        instances="""
[[instance]]
id = "gather_kit"
archetype = "arch_a"
at = { holder = "res_a" }
quantity = 2
""",
    )
    initial = packet(world)
    assert initial.delivery_id.endswith(f":perception:0000000000:{A}")
    assert initial.reports == initial.perception.action_feedback == []
    step(
        world,
        turn(
            world,
            A,
            "act",
            verb="gather",
            target=entity("inst_b"),
            inputs=[{"item": {"kind": "item", "id": "gather_kit"}, "quantity": 1}],
        ),
    )
    running = packet(world).perception.running_action
    assert running.progress == "started"
    result = step(world, turn(world, A, "wait"))
    old, new = result.actions
    assert (old.tick_finished, new.tick_started, new.tick_finished) == (1, 1, 2)
    assert old.stop.by == "actor"
    assert events(result, "entity_consumed")[0].intent_id == old.intent_id
    assert events(result, "entity_created")[0].intent_id == old.intent_id
    assert packet(world).perception.inventory[0].quantity == 2
    assert packet(world).perception.action_feedback == [old.visible_feedback, new.visible_feedback]
    assert report_rows(packet(world)) == [
        report("action_ended", old.intent_id),
        report("action_ended", new.intent_id),
    ]
    assert [
        (watch.phase, watch.tick)
        for watch in packet(world, B).perception.observed_actions
        if watch.intent_id == old.intent_id
    ] == [("stop", 1)]
    step(world)
    assert report_rows(packet(world)) == []
    assert packet(world).perception.action_feedback == []


def test_wap07_and_wap17_appearance_inspection_and_completion_range(make_world):
    world = make_world(
        [(A, 1, 1), (B, 3, 1)],
        seed=2,
        settings="""
[timing]
replace = true
invalid_attempt_ticks = 1
give_ticks = 3
pick_up_ticks = 1
drop_ticks = 1
wait_ticks = 1
inspect_ticks = 2
[timing.attempt_ticks]
build = 1
combine = 1
fill = 1
gather = 1
rest = 1
strike = 1
""",
    )
    first, other = [
        next(v for v in packet(world, who).perception.visible_entities if v.entity_id == "inst_a")
        for who in (A, B)
    ]
    assert first == other
    assert first.material_id == "mat_a"
    assert looks(first)["hardness"] == "soft"
    assert looks(first)["strength"] == "sturdy"
    assert "weight" not in looks(first)
    key = entity("inst_a")
    step(world, turn(world, A, "inspect", target=key))
    step(world)
    (feedback,) = packet(world).perception.action_feedback
    assert looks(feedback.inspected)["hardness"] == "soft"
    assert looks(feedback.inspected)["weight"] == "light"
    assert "edible" not in looks(feedback.inspected)
    assert first == next(
        v for v in packet(world).perception.visible_entities if v.entity_id == "inst_a"
    )
    step(world, turn(world, A, "inspect", target=entity("inst_b")))
    assert packet(world).perception.action_feedback[0].failure_code == "OUT_OF_REACH"

    step(world, turn(world, A, "inspect", target=key))
    step(world, turn(world, B, "pick_up", target=key, params={"quantity": 2}))
    assert packet(world).perception.action_feedback[0].failure_code == "OUT_OF_REACH"
    assert packet(world).perception.action_feedback[0].inspected is None


def test_wap07_inspect_completion_of_removed_target(make_world):
    world = make_world(
        [(A, 1, 1), (B, 3, 1)],
        seed=2,
        rules="""
[[rule]]
id = "packet_remove_target"
trigger = "verb:strike"
work_ticks = 1
target = { where = { archetype = "arch_a" } }
effects = [{ op = "consume", of = "target" }]
""",
    )
    key = entity("inst_a")
    result = step(
        world,
        turn(world, A, "inspect", target=key),
        turn(world, B, "act", verb="strike", target=key),
    )
    assert events(result, "entity_consumed")[0].target_id == "inst_a"
    (failed,) = packet(world).perception.action_feedback
    assert failed.failure_code == "INVALID_TARGET"
    assert failed.inspected is None
    assert failed.start_target.id == "inst_a"


def test_wap17_use_does_not_change_the_worlds_apparent_projection(make_world):
    world = make_world(
        [(A, 1, 1), (B, 3, 1)],
        rules="""
[[rule]]
id = "packet_use_true_material"
trigger = "verb:strike"
work_ticks = 1
target = { where = { archetype = "arch_a", hardness_min = 4 } }
phenomena = { success = ["snaps"] }
""",
    )
    key = entity("inst_a")
    result = step(world, turn(world, A, "act", verb="strike", target=key))
    assert result.actions[0].settlement.kind == "applied"
    assert result.actions[0].visible_feedback.phenomena == ["snaps"]
    step(world, *(turn(world, actor, "inspect", target=key) for actor in (A, B)))
    experienced, novice = (
        packet(world, actor).perception.action_feedback[0].inspected for actor in (A, B)
    )
    assert experienced == novice
    assert novice.material_id == "mat_a" and looks(novice)["hardness"] == "soft"


def test_round3_consumption_sight_and_actor_death(make_world):
    world = make_world(
        [(A, 3, 2), (B, 5, 4), (C, 0, 2)],
        opaque=[(4, 3)],
        radius=3,
        settings=BODY,
        rules="""
[[rule]]
id = "packet_strike"
trigger = "verb:strike"
work_ticks = 1
target = { where = { archetype = "arch_c" } }
inputs = [{ slot = "cord", where = { archetype = "arch_a" }, qty = 1 }]
outputs = [{ archetype = "arch_a", quantity = 1, at = "actor" }]
phenomena = { success = ["snaps", "tastes_good"] }
""",
        instances="""
[[instance]]
id = "occluded_target"
archetype = "arch_c"
at = { tile = [4, 2] }

[[instance]]
id = "cord"
archetype = "arch_a"
at = { holder = "res_a" }
properties = { strength = 2 }
apparent = { hardness = 1 }
tell = ["strength"]
""",
    )
    world.state.needs[A].update(health=1, satiety=1)
    assert A not in {v.entity_id for v in packet(world, B).perception.visible_entities}
    assert A in {v.entity_id for v in packet(world, C).perception.visible_entities}
    ordered = (
        turn(
            world,
            A,
            "act",
            verb="strike",
            target=entity("occluded_target"),
            inputs=[{"item": {"kind": "item", "id": "cord"}, "quantity": 1}],
        ),
        turn(world, B, "move_to", target=tile(4, 4)),
        turn(world, C, "move_to", target=tile(0, 1)),
    )
    copy = deepcopy(world)
    result = step(world, *ordered)
    assert result == step(copy, *reversed(ordered))
    assert {k: v.model_dump_json() for k, v in world.state.pending_deliveries.items()} == {
        k: v.model_dump_json() for k, v in copy.state.pending_deliveries.items()
    }
    assert not world.state.residents[A].alive
    assert A not in world.state.pending_deliveries
    intent_id = ordered[0]["action"]["intent"]["intent_id"]
    start, settle = [
        phase
        for phase in packet(world, B).perception.observed_actions
        if phase.intent_id == intent_id
    ]
    assert [start.phase, settle.phase] == ["start", "settle"]
    assert start.target == start.start_target == settle.target == settle.start_target is None
    (cord,) = start.visible_items
    assert (cord.entity_id, cord.role, cord.quantity, cord.material_id) == (
        "cord",
        "input",
        1,
        "mat_a",
    )
    assert looks(cord)["hardness"] == "soft"
    actor_result = next(action for action in result.actions if action.intent_id == intent_id)
    assert actor_result.visible_feedback.start_target.id == "occluded_target"
    assert cord == actor_result.visible_feedback.items_used[-1]
    assert "weight" not in looks(cord)
    assert settle.phenomena == ["snaps"]
    assert [(item.role, item.quantity) for item in settle.visible_items] == [("output", 1)]
    assert settle.visible_items[0].entity_id != "cord"
    assert not any(
        phase.intent_id == intent_id for phase in packet(world, C).perception.observed_actions
    )
    assert {"cord", "occluded_target"}.isdisjoint(
        world.state.exposure_receipts_by_resident[B].entities
    )
    assert [
        row.subject_id for row in packet(world, B).reports if row.kind == "action_observed"
    ].count(intent_id) == 1
    step(world, turn(world, B, "inspect", target=entity("cord")))
    assert packet(world, B).perception.action_feedback[0].failure_code == "INVALID_TARGET"


GIFT_STACKS = """
[[instance]]
id = "gift_source"
archetype = "arch_a"
at = { holder = "res_a" }
quantity = 2

[[instance]]
id = "gift_survivor"
archetype = "arch_a"
at = { holder = "res_b" }
"""


@pytest.mark.parametrize("wakes", [True, False])
def test_round3_gift_settles_before_wake(make_world, wakes):
    world = make_world(
        [(A, 2, 1), (B, 3, 1), (C, 3, 2)],
        settings=BODY,
        rules=SLEEP_RULE,
        instances=GIFT_STACKS,
    )
    step(world, sleep(world, B, 6 if wakes else 7))
    step(world)
    step(world)
    give = turn(
        world,
        A,
        "give",
        target=entity(B, "resident"),
        params={
            "item": {"kind": "held", "archetype_id": "arch_a"},
            "quantity": 1,
        },
    )
    step(world, give)
    step(world)
    assert packet(world, B).perception.awareness == "asleep"
    result = step(world)
    (transfer,) = events(result, "item_transferred")
    (merged,) = events(result, "stack_merged")
    assert transfer.payload["item_id"] != "gift_source"
    assert merged.target_id == "gift_survivor"
    intent = give["action"]["intent"]["intent_id"]
    expected = [
        phase for phase in packet(world, C).perception.observed_actions if phase.intent_id == intent
    ]
    assert len(expected) == 1 and expected[0].phase == "settle"
    assert expected[0].received_items == []
    assert "gift_source" not in world.state.exposure_receipts_by_resident[C].entities
    view = packet(world, B).perception
    assert [(item.entity_id, item.quantity) for item in view.inventory] == [("gift_survivor", 2)]
    assert "gift_source" not in world.state.exposure_receipts_by_resident[B].entities
    if wakes:
        (observed,) = view.observed_actions
        assert observed.actor_id == A and observed.intent_id == intent
        assert observed.target.model_dump() == entity(B, "resident")
        (received,) = observed.received_items
        assert (received.role, received.entity_id, received.quantity) == ("item", "gift_source", 1)
        assert received == packet(world).perception.action_feedback[0].items_used[0]
        assert view.awareness == "awake"
        assert report_rows(packet(world, B)) == [
            report("action_ended", f"{B}:t000000:a"),
            report("action_observed", intent),
            report("woke"),
        ]
    else:
        assert view.awareness == "asleep"
        assert view.observed_actions == view.visible_entities == view.visible_tiles == []
        assert report_rows(packet(world, B)) == []


@pytest.mark.parametrize("fails", [True, False])
def test_wap37_failed_give_has_no_portions_and_blind_recipient_cannot_watch(make_world, fails):
    world = make_world(
        [(A, 2, 1), (B, 3, 1)],
        radius=3,
        night=0,
        start=1170,
        instances=GIFT_STACKS,
    )
    give = turn(
        world,
        A,
        "give",
        target=entity(B, "resident"),
        params={
            "item": {"kind": "item", "id": "gift_source"},
            "quantity": 1,
        },
    )
    step(world, give)
    step(world)
    if fails:
        # Keep sight in the failure control so it witnesses the failed settlement.
        from dataclasses import replace

        world.state.senses = replace(world.state.senses, night_radius=3)
        result = step(world, turn(world, B, "move_to", target=tile(4, 1)))
        assert result.actions[0].visible_feedback.failure_code == "OUT_OF_REACH"
        (seen,) = packet(world, B).perception.observed_actions
        assert seen.phase == "settle" and seen.received_items == []
        assert packet(world, B).perception.inventory[0].quantity == 1
    else:
        result = step(world)
        assert result.actions[0].outcome == "success"
        assert packet(world, B).perception.inventory[0].quantity == 2
        assert packet(world, B).perception.observed_actions == []


@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("early", [False, True])
def test_en25_final_sleep_tick_never_hears_even_when_sleep_settles_first(make_world, seed, early):
    world = make_world(
        [(A, 2, 1), (B, 3, 1)],
        settings=BODY,
        rules=SLEEP_RULE,
        seed=seed,
    )
    step(world, sleep(world, A, 6))
    if early:
        world.state.needs[A]["satiety"] = 4
    else:
        for _ in range(4):
            step(world)
    result = step(world, turn(world, B, "wait", speech=statement(A)))
    (spoken,) = events(result, "utterance_spoken")
    (woke,) = events(result, "resident_woke")
    assert woke.payload["early"] == early
    if not early:
        (settled,) = events(result, "act_settled")
        assert (result.events.index(settled) < result.events.index(spoken)) == (seed == 1)
    assert packet(world).perception.awareness == "awake"
    assert packet(world).perception.heard_utterances == []
    assert "utterance_heard" not in [r.kind for r in packet(world).reports]
    assert packet(world).reports[-1].kind == "woke"
    step(world)
    assert packet(world).perception.heard_utterances == []
    assert "woke" not in [r.kind for r in packet(world).reports]


@pytest.mark.parametrize("keep_sight", [True, False])
def test_wap14_wap32_sleep_sight_at_dawn_and_first_corpse_receipt(make_world, keep_sight):
    world = make_world(
        [(A, 2, 1), (B, 3, 1), (C, 2, 2)],
        settings=f"sight_while_asleep = {str(keep_sight).lower()}\n" + BODY,
        rules=SLEEP_RULE,
        start=340,
        night=1,
        radius=4,
        instances=GIFT_STACKS,
    )
    step(world, sleep(world, A))
    before_dawn = packet(world).perception
    assert before_dawn.awareness == "asleep"
    world.state.needs[B].update(health=1, satiety=1)
    result = step(world, turn(world, C, "wait", speech=statement(A)))
    (corpse,) = events(result, "corpse_created")
    corpse_id = corpse.target_id
    dawn = packet(world).perception
    assert dawn.heard_utterances == dawn.observed_actions == []
    assert dawn.own_position == before_dawn.own_position
    assert dawn.inventory == before_dawn.inventory
    assert dawn.running_action.intent_id == before_dawn.running_action.intent_id
    assert dawn.needs
    assert dawn.action_feedback == []
    assert (corpse_id in world.state.exposure_receipts_by_resident[A].entities) == keep_sight
    if keep_sight:
        assert len(dawn.explored_static_tiles) > len(before_dawn.explored_static_tiles)
        assert any(v.entity_id == corpse_id for v in dawn.visible_entities)
        assert report("entity_first_seen", corpse_id) in report_rows(packet(world))
    else:
        assert dawn.explored_static_tiles == before_dawn.explored_static_tiles
        assert (
            dawn.visible_tiles
            == dawn.visible_entities
            == dawn.transient_sightings
            == dawn.environmental_cues
            == []
        )
    for _ in range(4):
        step(world)
    assert packet(world).perception.awareness == "awake"
    assert any(v.entity_id == corpse_id for v in packet(world).perception.visible_entities)
    assert (report("entity_first_seen", corpse_id) in report_rows(packet(world))) != keep_sight


def test_wap14_unconscious_never_has_senses_even_with_sleep_sight(make_world):
    world = make_world(
        [(A, 2, 1), (B, 3, 1)],
        settings="sight_while_asleep = true\n" + BODY,
        rules=SLEEP_RULE,
        instances=GIFT_STACKS,
        cues=(("water", 2, 2),),
    )
    initial = packet(world).perception
    world.state.needs[A]["mental_fatigue"] = 99
    result = step(world, turn(world, B, "wait", speech=statement(A)))
    assert events(result, "utterance_heard")
    view = packet(world).perception
    assert view.awareness == "unconscious"
    assert view.needs and view.inventory == initial.inventory
    assert view.explored_static_tiles == initial.explored_static_tiles
    for field in (
        "visible_tiles",
        "visible_entities",
        "transient_sightings",
        "environmental_cues",
        "heard_utterances",
        "observed_actions",
    ):
        assert getattr(view, field) == []
    assert "utterance_heard" not in [r.kind for r in packet(world).reports]


def test_en06_addressed_listener_and_excluded_audiences_in_real_packets(make_world):
    world = make_world([(A, 1, 1), (B, 2, 1), (C, 2, 2), (D, 5, 1)])
    world.state.residents[C].alive = False
    result = step(world, turn(world, A, "wait", speech=statement(B)))
    (spoken,) = events(result, "utterance_spoken")
    (heard,) = packet(world, B).perception.heard_utterances
    assert (heard.utterance_id, heard.speaker_id, heard.addressee_id) == (spoken.event_id, A, B)
    assert report_rows(packet(world, B)) == [
        report("utterance_heard", spoken.event_id, addressed=True),
        report("action_observed", f"{A}:t000000:a"),
    ]
    assert C not in world.state.pending_deliveries
    assert packet(world, D).perception.heard_utterances == []
    assert all(row.kind != "utterance_heard" for row in packet(world, D).reports)
    assert packet(world).perception.last_utterance_feedback.utterance_id == spoken.event_id
    step(world)
    assert packet(world, B).perception.heard_utterances == []
    assert packet(world).perception.last_utterance_feedback is None


def test_wap19_exact_mixed_report_order_and_no_repeat(make_world):
    world = make_world(
        [(A, 1, 1), (B, 3, 1), (C, 1, 1)],
        tick_minutes=240,
        night=0,
        cues=(("water", 3, 1),),
        settings="""
[needs.stamina]
replace = true
min = 0
max = 10000
initial = 6000
band_cutoffs = [2000, 4000, 6000, 8000]
max_gain_per_tick = 4
max_loss_per_tick = 4
thresholds = [{id = "z_high", at = 5999}, {id = "a_low", at = 5998}]
""",
        rules="""
[[rule]]
id = "packet_rest"
trigger = "verb:rest"
work_ticks = 2
effects = [{ op = "need", need = "stamina", delta = -4, timing = "completion" }]

[[rule]]
id = "packet_spawn"
trigger = "every:6"
subject = { archetype = "arch_b" }
conservation = "source"
outputs = [{ archetype = "arch_a", quantity = 1, at = "subject.tile", source = "src_a" }]
""",
    )
    assert report_rows(packet(world)) == []
    assert packet(world).perception.environmental_cues[0].detail_level == "distant"
    for _ in range(3):
        step(world)
    step(world, turn(world, A, "move_to", target=tile(2, 1)))
    assert packet(world).perception.environmental_cues == []
    step(world, turn(world, A, "act", verb="rest"))
    assert report_rows(packet(world)) == [report("progress_step", f"{A}:t000001:a")]
    result = step(
        world,
        turn(world, C, "wait", speech=statement(B)),
        turn(world, B, "wait", speech=statement(A)),
    )
    (created,) = events(result, "entity_created")
    messages = sorted((e.event_id, e.actor_id == B) for e in events(result, "utterance_spoken"))
    assert len(messages) == 2
    assert packet(world).perception.environmental_cues[0].detail_level == "near"
    assert report_rows(packet(world)) == [
        report("action_ended", f"{A}:t000001:a"),
        report("need_band_changed", "stamina", band="moderate"),
        report("need_threshold_crossed", "stamina", threshold="a_low"),
        report("need_threshold_crossed", "stamina", threshold="z_high"),
        *(
            report("utterance_heard", identity, addressed=addressed)
            for identity, addressed in messages
        ),
        report("entity_first_seen", created.target_id),
        report("entity_first_seen", "water"),
        report("action_observed", f"{B}:t000000:a"),
        report("action_observed", f"{C}:t000000:a"),
        report("progress_step", f"{A}:t000001:a"),
    ]
    step(world)
    assert report_rows(packet(world)) == []


def test_transient_last_step_and_cue_upgrade_are_delivered_once(make_world):
    world = make_world([(A, 1, 1), (B, 0, 1)], radius=2, cues=(("water", 2, 0),))
    (cue,) = packet(world).perception.environmental_cues
    assert cue.detail_level == "distant" and cue.direction is None
    assert world.state.exposure_receipts_by_resident[A].cue_detail_seen == {"water": "distant"}
    step(world, turn(world, A, "move_to", target=tile(3, 1)))
    view = packet(world).perception
    (transient,) = [v for v in view.transient_sightings if v.entity_id == B]
    assert transient.seen_at_step == 1
    assert B not in {v.entity_id for v in view.visible_entities}
    (near,) = view.environmental_cues
    assert (near.detail_level, near.physical_description, near.direction) == (
        "near",
        "Water",
        "east",
    )
    assert world.state.exposure_receipts_by_resident[A].cue_detail_seen == {"water": "near"}
    reports = report_rows(packet(world))
    assert reports.count(report("entity_first_seen", "water")) == 1
    assert reports[0] == report("action_ended", f"{A}:t000000:a")
    step(world)
    assert packet(world).perception.transient_sightings == []
    assert report_rows(packet(world)) == []


def test_wap31_running_feedback_and_watch_share_by_kind_stack_looks(make_world):
    world = make_world(
        [(A, 2, 1), (B, 3, 1), (C, 8, 5)],
        rules="""
[[rule]]
id = "packet_uses"
trigger = "verb:strike"
work_ticks = 2
target = { where = { archetype = "arch_c" } }
instruments = [{ slot = "tool", where = { archetype = "arch_d" }, qty = 1 }]
inputs = [{ slot = "cord", where = { archetype = "arch_a" }, qty = 2 }]
outputs = [{ archetype = "arch_a", quantity = 1, at = "actor" }]
phenomena = { success = ["snaps", "tastes_good"] }
""",
        instances="""
[[instance]]
id = "cord_a"
archetype = "arch_a"
at = { holder = "res_a" }
properties = { strength = 2 }
apparent = { hardness = 1 }
tell = ["strength"]

[[instance]]
id = "cord_b"
archetype = "arch_a"
at = { holder = "res_a" }

[[instance]]
id = "tool"
archetype = "arch_d"
at = { holder = "res_a" }
""",
    )
    step(
        world,
        turn(
            world,
            A,
            "act",
            verb="strike",
            target=entity("inst_c"),
            instruments=[{"kind": "item", "id": "tool"}],
            inputs=[{"item": {"kind": "held", "archetype_id": "arch_a"}, "quantity": 2}],
        ),
    )
    own = packet(world).perception.running_action
    (starting,) = packet(world, B).perception.observed_actions
    assert starting.phase == "start"
    assert starting.start_target == own.start_target
    assert starting.target.model_dump() == entity("inst_c")
    assert starting.visible_items == own.items
    assert [(v.role, v.entity_id, v.quantity) for v in own.items] == [
        ("target", "inst_c", 1),
        ("instrument", "tool", 1),
        ("input", "cord_a", 1),
        ("input", "cord_b", 1),
    ]
    assert [looks(item)["hardness"] for item in own.items[-2:]] == ["soft", "hard"]
    assert packet(world, C).perception.observed_actions == []
    result = step(world)
    (feedback,) = packet(world).perception.action_feedback
    assert feedback.items_used == own.items
    assert feedback.phenomena == ["snaps", "tastes_good"]
    (ending,) = packet(world, B).perception.observed_actions
    assert ending.phase == "settle" and ending.phenomena == ["snaps"]
    (output,) = events(result, "entity_created")
    assert [(v.role, v.entity_id, v.quantity) for v in ending.visible_items] == [
        ("target", "inst_c", 1),
        ("instrument", "tool", 1),
        ("output", output.target_id, 1),
    ]
    assert output.target_id in {v.entity_id for v in packet(world).perception.inventory}
    assert {"cord_a", "cord_b", "tool", output.target_id}.isdisjoint(
        world.state.exposure_receipts_by_resident[B].entities
    )


def test_process_progress_and_container_visibility(make_world):
    world = make_world(
        [(A, 2, 2), (B, 3, 3)],
        instances="""
[[instance]]
id = "open_part"
archetype = "arch_a"
at = { holder = "inst_e" }

[[instance]]
id = "sealed_part"
archetype = "arch_a"
at = { holder = "inst_c" }
""",
    )
    visible = {view.entity_id: view for view in packet(world).perception.visible_entities}
    assert "open_part" in visible and "sealed_part" not in visible
    assert looks(visible["inst_e"])["progress"] == "started"
    step(world, *(turn(world, actor, "contribute", target=entity("inst_e")) for actor in (A, B)))
    for actor, other in ((A, B), (B, A)):
        delivery = packet(world, actor)
        assert delivery.perception.running_action.progress == "halfway"
        site = next(v for v in delivery.perception.visible_entities if v.entity_id == "inst_e")
        assert looks(site)["progress"] == "halfway"
        assert report_rows(delivery) == [
            report("action_observed", f"{other}:t000000:a"),
            report("progress_step", "inst_e"),
        ]
    step(world)
    assert packet(world).perception.running_action is None
    assert packet(world).reports[-1].model_dump() == {
        "kind": "progress_step",
        "subject_id": "inst_e",
        "addressed": None,
        "band": None,
        "threshold_id": None,
    }


def test_wap08_visible_walker_keeps_hidden_destination_private(make_world):
    world = make_world([(A, 5, 1), (B, 6, 1)], radius=3)
    step(world, turn(world, A, "move_to", target=tile(2, 1)))
    assert packet(world).perception.running_action.start_target.position.x == 2
    (seen,) = packet(world, B).perception.observed_actions
    assert (seen.actor_id, seen.action, seen.phase) == (A, "move_to", "start")
    assert seen.target is seen.start_target is None
    step(world)
    assert packet(world, B).perception.observed_actions == []


def test_store_materialized_output_has_a_held_watch_look(make_world):
    world = make_world([(A, 3, 1), (B, 2, 1)])
    result = step(world, turn(world, A, "act", verb="gather", target=entity("inst_b")))
    output = events(result, "matter_moved")[0].payload["entity_id"]
    start, settle = packet(world, B).perception.observed_actions
    assert start.visible_items == []
    (item,) = settle.visible_items
    assert (item.role, item.entity_id, item.quantity) == ("output", output, 1)
    assert item.entity_id not in world.state.exposure_receipts_by_resident[B].entities
