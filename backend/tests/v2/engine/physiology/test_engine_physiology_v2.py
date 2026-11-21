"""Synthetic-pack physiology and hard-stop acceptance tests."""

from dataclasses import replace

import pytest

A, B = "res_a", "res_b"


@pytest.fixture
def physiology_pack(pack, tmp_path):
    from living_island.world.v2.rules import load_pack

    path = tmp_path / pack.pack_id / "pack.toml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "[physiology]",
        """
enabled_needs = ["health", "hydration", "mental_fatigue", "satiety", "stamina"]
enabled_verbs = ["sleep"]

[physiology]
satiety_awake_decay_per_tick = 40
satiety_asleep_decay_per_tick = 25
hydration_awake_decay_per_tick = 150
hydration_asleep_decay_per_tick = 100
health_loss_per_tick_if_deprived = 70
health_recovery_sleep_per_tick = 15
health_recovery_min_satiety = 2500
health_recovery_min_hydration = 2500
awake_per_tick = 50
per_utterance_heard = 20
per_first_sighting = 30
recovery_per_tick_asleep = 150
faint_ticks = 35""",
    )
    text = (
        text.replace("strike = 1", "strike = 1\nsleep = 1")
        .replace("stamina_awake_decay_per_tick = 0", "stamina_awake_decay_per_tick = 2")
        .replace("stamina_move_extra_cost_per_tick = 0", "stamina_move_extra_cost_per_tick = 4")
    )
    for key in ("health", "hydration", "mental_fatigue", "satiety"):
        initial = 0 if key == "mental_fatigue" else 9000
        text += f"""
[needs.{key}]
min = 0
max = 10000
initial = {initial}
band_cutoffs = [2000, 4000, 6000, 8000]
max_gain_per_tick = 0
max_loss_per_tick = {26 if key == "satiety" else 0}
"""
        if key in ("satiety", "hydration"):
            text += 'thresholds = [{id = "urgent", at = 3000, wakes = true}]\n'
        elif key == "mental_fatigue":
            text += 'thresholds = [{id = "tired", at = 1000}]\n'
    path.write_text(text, encoding="utf-8")
    (path.parent / "unmatched.toml").write_text(
        '[unmatched.sleep]\nentries = []\ndefault = ["nothing_happens"]\n',
        encoding="utf-8",
    )
    (path.parent / "rules.toml").write_text(
        """
[[rule]]
id = "test_sleep"
trigger = "verb:sleep"
work_ticks = { param = "duration_ticks" }
conditions = [{ id = "has_satiety", kind = "need", need = "satiety", op = ">", value = 0 }]
""",
        encoding="utf-8",
    )
    return load_pack(path.parent, pack.vocabulary)


@pytest.fixture
def body(world, physiology_pack):
    from living_island.world.v2.engine import perception
    from living_island.world.v2.engine.events import EventWriter
    from living_island.world.v2.engine.tick import TickContext
    from living_island.world.v2.engine.validate import EnginePack

    world.pack = EnginePack.from_pack(physiology_pack)
    world.state.needs = {
        actor: {key: spec.initial for key, spec in world.pack.needs.items()}
        for actor in world.state.residents
    }
    perception.build_deliveries(TickContext(world.state, world.pack, EventWriter(world.state, 0)))
    return world


def _set_tick(body, tick):
    state = body.state
    state.tick = tick
    for actor_id, packet in state.pending_deliveries.items():
        state.pending_deliveries[actor_id] = packet.model_copy(
            update={
                "observed_tick": tick,
                "delivery_id": f"{state.run_id}:perception:{tick:010d}:{actor_id}",
                "perception": packet.perception.model_copy(update={"tick": tick}),
            }
        )


NONNEGATIVE_PHYSIOLOGY_KEYS = (
    "satiety_awake_decay_per_tick",
    "satiety_asleep_decay_per_tick",
    "hydration_awake_decay_per_tick",
    "hydration_asleep_decay_per_tick",
    "stamina_awake_decay_per_tick",
    "stamina_move_extra_cost_per_tick",
    "health_loss_per_tick_if_deprived",
    "health_recovery_sleep_per_tick",
    "awake_per_tick",
    "per_utterance_heard",
    "per_first_sighting",
    "recovery_per_tick_asleep",
)
REQUIRED_PHYSIOLOGY_KEYS = (
    *NONNEGATIVE_PHYSIOLOGY_KEYS,
    "health_recovery_min_satiety",
    "health_recovery_min_hydration",
    "faint_ticks",
)


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        *(
            pytest.param(key, None, "lacks engine setting", id=f"{key}-missing")
            for key in REQUIRED_PHYSIOLOGY_KEYS
        ),
        *(
            pytest.param(key, "0", "expected an integer", id=f"{key}-wrong-type")
            for key in REQUIRED_PHYSIOLOGY_KEYS
        ),
        *(
            pytest.param(key, -1, "outside bounds", id=f"{key}-negative")
            for key in NONNEGATIVE_PHYSIOLOGY_KEYS
        ),
        pytest.param("faint_ticks", 0, "outside bounds", id="faint_ticks-zero"),
        pytest.param("faint_ticks", True, "expected an integer", id="faint_ticks-boolean"),
    ],
)
def test_initialization_refuses_missing_or_invalid_physiology(
    physiology_pack, setup, key, value, error
):
    from living_island.world.v2.engine import initialize

    settings = dict(physiology_pack.data["physiology"])
    if value is None:
        del settings[key]
    else:
        settings[key] = value
    candidate = replace(physiology_pack, data={**physiology_pack.data, "physiology": settings})

    with pytest.raises(ValueError, match=rf"(?=.*physiology\.{key})(?=.*{error})"):
        initialize(candidate, setup)


def _turn(world, actor, action, *, target=None, verb=None, params=None):
    identity = f"{actor}:t{world.state.turn_ordinals[actor]:06d}"
    return {
        "schema_version": "wap/0.1",
        "actor_id": actor,
        "turn_id": identity,
        "observed_tick": world.state.tick,
        "action": {
            "kind": "intent",
            "intent": {
                "intent_id": f"{identity}:a",
                "turn_id": identity,
                "actor_id": actor,
                "action": action,
                "target": target,
                "params": params or {},
                "verb": verb,
                "instruments": [],
                "inputs": [],
                "reason": None,
            },
        },
        "utterance": None,
    }


def _sleep(world, duration):
    return _turn(world, A, "act", verb="sleep", params={"duration_ticks": duration})


def _proposed_rule(world, rule_id, verb, **fields):
    return {
        "id": rule_id,
        "trigger": f"verb:{verb}",
        "provenance": {
            "kind": "proposed",
            "llm_call_id": "call_a",
            "approved_by": A,
            "approved_at_tick": world.state.tick,
        },
        **fields,
    }


def _events(result, kind, actor=A):
    return [event for event in result.events if event.type == kind and event.actor_id == actor]


@pytest.mark.parametrize(
    ("satiety", "hydration", "health"),
    [
        (2525, 2600, 9000),
        (2525, 2601, 9000),
        (2526, 2600, 9000),
        (2526, 2601, 9015),
        (25, 100, 8930),
        (9000, 9000, 9015),
    ],
)
def test_en12_recovery_strict_after_decay(body, satiety, hydration, health):
    body.state.needs[A].update(satiety=satiety, hydration=hydration)
    result = body.step([_sleep(body, 6)])
    needs = body.state.needs[A]
    assert (needs["satiety"], needs["hydration"], needs["health"]) == (
        satiety - 25,
        hydration - 100,
        health,
    )
    assert body.state.needs[B]["satiety"] == 8960
    assert body.state.needs[B]["hydration"] == 8850
    assert needs["stamina"] == 6000
    assert body.state.needs[B]["stamina"] == 5998
    assert len(_events(result, "needs_changed")) == 1


def test_en24_first_and_final_sleep_tick(body, monkeypatch):
    from living_island.world.v2.engine import perception, physiology

    phase_flags = []
    build = perception.build_deliveries

    def capture(ctx):
        phase_flags.append((ctx.tick, physiology.hearing_awake(ctx, A)))
        build(ctx)

    monkeypatch.setattr(perception, "build_deliveries", capture)
    _set_tick(body, 100)
    assert body.state.awareness[A].kind == "awake"
    first = body.step([_sleep(body, 36)])
    (fell_asleep,) = _events(first, "resident_fell_asleep")
    assert fell_asleep.tick == body.state.tick == 101
    assert body.state.awareness[A].kind == "asleep"
    for _ in range(34):
        body.step()
    body.state.needs[A].update(satiety=3025, hydration=9000, health=9000)
    last = body.step()
    assert body.state.tick == 136
    assert body.state.awareness[A].kind == "awake"
    assert last.actions[0].outcome == "settled"
    assert last.actions[0].settlement.kind == "applied"
    assert last.actions[0].settlement.rule_id == "test_sleep"
    assert _events(last, "resident_woke")[0].payload == {"resident_id": A, "early": False}
    assert body.state.needs[A]["health"] == 9015
    assert phase_flags == [(tick, False) for tick in range(101, 137)]


def test_wap18_early_waking_and_already_critical(body, monkeypatch):
    from living_island.world.v2.engine import perception, physiology

    can_hear = []
    monkeypatch.setattr(
        perception,
        "build_deliveries",
        lambda ctx: can_hear.append(physiology.hearing_awake(ctx, A)),
    )
    body.state.needs[A]["satiety"] = 3001
    result = body.step([_sleep(body, 6)])
    assert body.state.awareness[A].kind == "awake"
    assert result.actions[0].visible_feedback.stop_reason == "WOKEN"
    assert _events(result, "resident_woke")[0].payload == {"resident_id": A, "early": True}
    assert can_hear == [False]
    result = body.step([_sleep(body, 6)])
    assert not result.actions
    assert not _events(result, "resident_woke")
    assert body.state.awareness[A].kind == "asleep"


@pytest.mark.parametrize("duration", [5, 6, 54, 55])
def test_wap18_duration_bounds(body, duration):
    from living_island.world.v2.protocol import InvalidTurn

    if duration in (5, 55):
        with pytest.raises(InvalidTurn):
            body.step([_sleep(body, duration)])
        assert body.state.tick == 0
    else:
        result = body.step([_sleep(body, duration)])
        assert _events(result, "resident_fell_asleep")[0].payload["duration_ticks"] == duration
        assert body.state.active_actions[A].due_tick == duration


def test_en24_unmet_sleep_stays_awake(body):
    body.state.needs[A]["satiety"] = 0
    result = body.step([_sleep(body, 6)])
    assert result.actions[0].outcome == "settled"
    assert result.actions[0].settlement.kind == "unmet"
    assert result.actions[0].settlement.failed_check == "has_satiety"
    assert not _events(result, "resident_fell_asleep")
    assert body.state.awareness[A].kind == "awake"


def test_en14_faint_and_unconscious_boundary(body, monkeypatch):
    from living_island.world.v2.engine import perception, physiology
    from living_island.world.v2.engine.reports import report

    flags = []
    build = perception.build_deliveries

    def capture(ctx):
        flags.append(physiology.hearing_awake(ctx, A))
        build(ctx)

    monkeypatch.setattr(perception, "build_deliveries", capture)
    _set_tick(body, 100)
    body.state.needs[A].update(mental_fatigue=9879, satiety=3060)
    packet = body.state.pending_deliveries[A]
    body.state.pending_deliveries[A] = packet.model_copy(
        update={
            "reports": [
                report("utterance_heard", "one", addressed=True),
                report("utterance_heard", "two", addressed=False),
                report("entity_first_seen", "item"),
            ]
        }
    )
    body.step()
    assert body.state.needs[A]["mental_fatigue"] == 9999
    assert body.state.awareness[A].kind == "awake"
    _set_tick(body, 100)
    movement = _turn(body, A, "move_to", target={"kind": "tile", "position": {"x": 5, "y": 1}})
    body.state.explored_tiles_by_resident[A] = set(range(35))
    # Exhaustion at the same check loses to fainting.
    body.state.needs[A]["stamina"] = 1
    result = body.step([movement])
    assert _events(result, "resident_fainted")[0].tick == 101
    assert body.state.awareness[A].unconscious_until == 136
    assert result.actions[0].visible_feedback.stop_reason == "FAINTED"
    assert flags == [True, True]
    crossed = body.step()
    assert not _events(crossed, "resident_woke")
    assert body.state.awareness[A].kind == "unconscious"
    assert body.state.needs[A]["mental_fatigue"] == 9850
    for _ in range(33):
        body.step()
    result = body.step()
    assert _events(result, "resident_woke")[0].tick == 136
    assert body.state.awareness[A].kind == "awake"
    assert flags[-1] is False


def test_rr16_polarity_and_wap24_crossings(body):
    from living_island.world.v2.engine.physiology import condition_value, need_band, need_crossings

    pack = body.pack
    assert condition_value(pack, "mental_fatigue", 9500) == 500
    assert need_band(pack, "mental_fatigue", 9500) == "critical"
    assert [
        need_band(pack, "mental_fatigue", value) for value in (10000, 8000, 6000, 4000, 2000)
    ] == ["critical", "low", "moderate", "good", "strong"]
    tired = need_crossings(pack, {"mental_fatigue": 8900}, {"mental_fatigue": 9000})
    assert [(crossing.threshold_id, crossing.wakes) for crossing in tired] == [("tired", False)]
    assert need_band(pack, "satiety", 3001) == need_band(pack, "satiety", 3000)
    values = [3001, 3000, 2999, 3001, 2998]
    assert [
        len(need_crossings(pack, {"satiety": before}, {"satiety": after}))
        for before, after in zip(values, values[1:], strict=False)
    ] == [1, 0, 0, 1]


def test_wap24_boundary_opening_includes_phase2_and_earlier_events(body):
    from living_island.world.v2.engine.events import EventWriter, json_object
    from living_island.world.v2.engine.physiology import (
        ProgressNeeds,
        apply_physiology,
        boundary_crossings,
    )
    from living_island.world.v2.engine.state import TickActivity
    from living_island.world.v2.engine.tick import TickContext

    state = body.state
    assert not boundary_crossings(TickContext(state, body.pack, EventWriter(state, 0)), {})
    ctx = TickContext(state, body.pack, EventWriter(state, 1))
    ctx.activity = {actor: TickActivity(None, 0) for actor in state.residents}
    ctx.writer.emit(
        "needs_changed",
        json_object(
            {
                "resident_id": A,
                "changes": [{"need_id": "satiety", "before": 2999, "after": 2980}],
                "causes": ["completion_rule"],
            }
        ),
        actor_id=A,
    )
    state.needs[A]["satiety"] = 2980
    progress = {A: ProgressNeeds({"satiety": 3001}, ("progress_rule",))}
    apply_physiology(ctx, progress)
    (crossing,) = boundary_crossings(ctx, progress)[A]
    assert (crossing.need_id, crossing.threshold_id, crossing.wakes) == ("satiety", "urgent", True)
    assert ctx.writer.events[1].payload["causes"] == ["physiology", "progress_rule"]


@pytest.mark.parametrize("sleep_sight", [False, True])
def test_en_awareness_flags(body, sleep_sight):
    from living_island.world.v2.engine.physiology import sight_enabled

    pack = replace(body.pack, sight_while_asleep=sleep_sight)
    assert sight_enabled(pack, "awake")
    assert sight_enabled(pack, "asleep") is sleep_sight
    assert not sight_enabled(pack, "unconscious")


@pytest.mark.parametrize("dies", [False, True])
def test_wap33_exhaustion_boundary_and_completion_rng(body, dies):
    body.state.explored_tiles_by_resident[A] = set(range(35))
    body.state.needs[A]["stamina"] = 1
    if dies:
        body.state.needs[A].update(health=1, satiety=0, mental_fatigue=9999)
    initial_rng = body.state.resolution_rng_state_uint32
    movement = _turn(body, A, "move_to", target={"kind": "tile", "position": {"x": 5, "y": 1}})
    result = body.step([movement])
    assert len(_events(result, "resident_moved")) == 2
    assert result.actions[0].visible_feedback.stop_reason == ("DEATH" if dies else "EXHAUSTED")
    assert result.actions[0].tick_finished == 1
    assert A not in body.state.active_actions
    result = body.step([_turn(body, B, "wait")])
    assert [action.actor_id for action in result.actions] == [B]
    assert body.state.resolution_rng_state_uint32 == initial_rng


@pytest.mark.parametrize("reason", ["PATH_BLOCKED", "EXHAUSTED", None])
def test_en16_phase2_stop_or_completion_survives_death(body, reason):
    from living_island.world.v2.engine.state import ActiveAction, Move, Route
    from living_island.world.v2.protocol import Coord, Intent

    target = Coord(x=0, y=1) if reason == "PATH_BLOCKED" else Coord(x=2, y=1)
    movement = _turn(body, A, "move_to", target={"kind": "tile", "position": target.model_dump()})
    action = ActiveAction(
        Intent.model_validate(movement["action"]["intent"]),
        Move(target),
        0,
        route=Route((target,)),
    )
    body.state.active_actions[A] = action
    body.state.needs[A].update(health=1, satiety=0, stamina=0 if reason == "EXHAUSTED" else 100)
    result = body.step()
    (finished,) = result.actions
    assert finished.visible_feedback.stop_reason == reason
    assert finished.outcome == ("stopped" if reason else "success")
    assert not body.state.residents[A].alive


@pytest.mark.parametrize("target_state", ["gone", "out_of_reach", "reachable"])
def test_en16_process_target(body, target_state):
    from living_island.world.v2.engine.state import ActiveAction, Contribute, OnTile
    from living_island.world.v2.protocol import Coord, Intent

    process = body.state.entities["inst_a"]
    process.components["process"] = {"work_done": 0, "work_required": 4}
    process.place = OnTile(Coord(x=1 if target_state == "reachable" else 5, y=1))
    if target_state == "gone":
        body.state.entities.pop(process.entity_id)
    turn = _turn(body, A, "contribute", target={"kind": "entity", "id": process.entity_id})
    action = ActiveAction(
        Intent.model_validate(turn["action"]["intent"]), Contribute(process.entity_id), 0
    )
    body.state.active_actions[A] = action
    result = body.step()
    if target_state == "reachable":
        assert not result.actions
    else:
        assert result.actions[0].visible_feedback.stop_reason == "TARGET_GONE"


@pytest.mark.parametrize("reason", ["EXHAUSTED", "FAINTED", "DEATH"])
def test_en16_interrupt_delegates_chosen_rule(body, monkeypatch, reason):
    from living_island.world.v2.engine import settle
    from living_island.world.v2.engine.state import Act, ActiveAction
    from living_island.world.v2.protocol import Intent

    rule_id, rule = next(iter(body.pack.source.rules.items()))
    body.pack.source.rules[rule_id] = replace(rule, data={**rule.data, "exhaustion_stops": True})
    turn = _turn(body, A, "act", verb="gather")
    intent = Intent.model_validate(turn["action"]["intent"])
    body.state.active_actions[A] = ActiveAction(intent, Act("gather", {}), 0, rule_id=rule_id)
    body.state.needs[A]["stamina"] = 1
    if reason == "FAINTED":
        body.state.needs[A]["mental_fatigue"] = 9999
    if reason == "DEATH":
        body.state.needs[A].update(health=1, hydration=0)
    calls = []
    monkeypatch.setattr(
        settle, "interrupt", lambda ctx, action: calls.append(action.intent.intent_id)
    )
    result = body.step()
    assert calls == [intent.intent_id]
    assert result.actions[0].visible_feedback.stop_reason == reason


def test_death_drops_at_limit_and_merges(body):
    from living_island.world.v2.engine.items import entities_at
    from living_island.world.v2.engine.limits import entity_units
    from living_island.world.v2.engine.state import Held, OnTile

    at = OnTile(body.state.residents[A].position)
    ground = body.state.entities["inst_a"]
    ground.place = at
    held = replace(ground, entity_id="held_a", place=Held(A), owner_id=A)
    body.state.entities[held.entity_id] = held
    total = entity_units(body.state)
    body.pack = replace(
        body.pack, limits=replace(body.pack.limits, max_entity_units_world=total + 2)
    )
    body.state.needs[A].update(health=1, satiety=0, hydration=0)
    result = body.step()
    relevant = [
        event.type for event in result.events if event.actor_id == A or event.type == "stack_merged"
    ]
    assert relevant == [
        "needs_changed",
        "resident_died",
        "corpse_created",
        "item_transferred",
        "stack_merged",
    ]
    assert body.state.entities["corpse@res_a"].death_tick == 1
    assert entity_units(body.state) == total + 1
    assert body.state.entities["inst_a"].quantity == held.quantity * 2
    assert all(item.place == at for item in entities_at(body.state, at))


def test_en13_movement_charge_once_for_two_tiles(body):
    movement = _turn(body, A, "move_to", target={"kind": "tile", "position": {"x": 5, "y": 1}})
    result = body.step([movement])
    assert len(_events(result, "resident_moved")) == 2
    assert body.state.needs[A]["stamina"] == 6000 - 2 - 4
    assert body.state.needs[B]["stamina"] == 6000 - 2


@pytest.mark.parametrize("higher_stop", ["DEATH", "EXHAUSTED", None])
def test_wap04_waking_priority_and_interrupt(body, monkeypatch, higher_stop):
    from living_island.world.v2.engine import settle

    rule_id = "sleep_with_exhaustion"
    rule = _proposed_rule(
        body,
        rule_id,
        "sleep",
        work_ticks={"param": "duration_ticks"},
        exhaustion_stops=True,
        conditions=[
            {"id": "has_satiety", "kind": "need", "need": "satiety", "op": ">", "value": 0},
            {"id": "has_room", "kind": "free_slots", "op": ">=", "value": 1},
        ],
        effects=[{"op": "need", "need": "stamina", "delta": -1, "timing": "per_tick"}],
    )
    interrupt = settle.interrupt
    calls = []

    def record_interrupt(ctx, action):
        calls.append(action.rule_id)
        interrupt(ctx, action)

    monkeypatch.setattr(settle, "interrupt", record_interrupt)
    body.state.needs[A]["satiety"] = 3025
    if higher_stop == "DEATH":
        body.state.needs[A].update(hydration=0, health=1)
    if higher_stop == "EXHAUSTED":
        body.state.needs[A]["stamina"] = 1

    result = body.step([_sleep(body, 6)], rule_additions=[rule])
    assert result.actions[0].visible_feedback.stop_reason == (higher_stop or "WOKEN")
    assert calls == [rule_id]
    woke = _events(result, "resident_woke")
    if higher_stop == "DEATH":
        assert not woke
    else:
        assert woke[0].payload["early"] is (higher_stop is None)


def test_en12_tick_combines_rule_and_metabolism_changes(body):
    rule = _proposed_rule(
        body,
        "rest_with_gain",
        "rest",
        work_ticks=2,
        effects=[{"op": "need", "need": "stamina", "delta": 3, "timing": "per_tick"}],
    )

    result = body.step([_turn(body, A, "act", verb="rest")], rule_additions=[rule])

    (changed,) = _events(result, "needs_changed")
    assert changed.payload["causes"] == ["physiology", "rest_with_gain"]
    assert {"need_id": "stamina", "before": 6000, "after": 6001} in changed.payload["changes"]
    assert body.state.needs[A]["stamina"] == 6001


def test_wap24_tick_rule_band_crossing_wakes_sleeper(body):
    from copy import deepcopy

    from living_island.world.v2.engine.physiology import need_band

    satiety = body.pack.needs["satiety"]
    # The waking threshold is the first value in the critical band.
    satiety = replace(satiety, band_cutoffs=(3001, *satiety.band_cutoffs[1:]))
    body.pack = replace(body.pack, needs={**body.pack.needs, "satiety": satiety})
    body.state.needs[A]["satiety"] = 3026
    control = deepcopy(body)
    rule = _proposed_rule(
        body,
        "sleep_with_hunger",
        "sleep",
        work_ticks={"param": "duration_ticks"},
        conditions=[
            {"id": "has_stamina", "kind": "need", "need": "stamina", "op": ">", "value": 0},
            {"id": "has_room", "kind": "free_slots", "op": ">=", "value": 1},
        ],
        effects=[{"op": "need", "need": "satiety", "delta": -26, "timing": "per_tick"}],
    )

    assert not control.step([_sleep(control, 6)]).actions
    assert control.state.needs[A]["satiety"] == 3001
    assert need_band(control.pack, "satiety", 3001) == "low"
    assert control.state.awareness[A].kind == "asleep"

    result = body.step([_sleep(body, 6)], rule_additions=[rule])
    (stopped,) = result.actions
    assert body.state.needs[A]["satiety"] == 2975
    assert need_band(body.pack, "satiety", 2975) == "critical"
    assert stopped.visible_feedback.stop_reason == "WOKEN"
    assert stopped.tick_finished == 1
    (woke,) = _events(result, "resident_woke")
    assert woke.payload == {"resident_id": A, "early": True}
    assert body.state.awareness[A].kind == "awake"


def test_en24_sleep_start_has_one_transition_at_next_boundary(body):
    boundary = body.state.tick
    assert body.state.awareness[A].kind == "awake"

    result = body.step([_sleep(body, 6)])

    assert not result.actions
    (fell_asleep,) = _events(result, "resident_fell_asleep")
    assert fell_asleep.tick == body.state.tick == boundary + 1
    assert fell_asleep.payload == {"resident_id": A, "duration_ticks": 6}
    assert body.state.awareness[A].kind == "asleep"
    assert body.state.active_actions[A].rule_id == "test_sleep"
    assert not _events(body.step(), "resident_fell_asleep")
