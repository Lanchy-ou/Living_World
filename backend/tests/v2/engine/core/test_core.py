from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.world.v2.engine import World, WorldSetup
    from living_island.world.v2.rules import Pack

A, B = "res_a", "res_b"


def tile(x: int, y: int = 1) -> dict:
    return {"kind": "tile", "position": {"x": x, "y": y}}


def subject(kind: str, id_: str) -> dict:
    return {"kind": kind, "id": id_}


def held(kind: str = "arch_a", quantity: int = 1) -> dict:
    return {"item": {"kind": "held", "archetype_id": kind}, "quantity": quantity}


def named(id_: str, quantity: int = 1) -> dict:
    return {"item": {"kind": "item", "id": id_}, "quantity": quantity}


def turn(world: World, actor: str, action: str, target=None, params=None, **extra) -> dict:
    state = world.state
    identity = f"{actor}:t{state.turn_ordinals[actor]:06d}"
    intent = {
        "intent_id": f"{identity}:a",
        "turn_id": identity,
        "actor_id": actor,
        "action": action,
        "target": target,
        "params": params or {},
        "verb": None,
        "instruments": [],
        "inputs": [],
        "reason": None,
    }
    return {
        "schema_version": "wap/0.1",
        "actor_id": actor,
        "turn_id": identity,
        "observed_tick": state.tick,
        "action": {"kind": "intent", "intent": {**intent, **extra}},
        "utterance": None,
    }


def continue_turn(world: World, actor: str) -> dict:
    return {**turn(world, actor, "wait"), "action": {"kind": "continue"}}


def give_item(world: World, actor: str = A, id_: str = "inst_a") -> None:
    from living_island.world.v2.engine.state import Held

    world.state.entities[id_].place = Held(actor)


@pytest.mark.parametrize(
    "error",
    [
        "continue",
        "actor",
        "turn",
        "tick",
        "intent",
        "utterance",
        "quantity",
        "duplicate",
        "verb",
    ],
)
def test_wap02_turn_refuses_atomically(world: World, error: str) -> None:
    from living_island.world.v2.protocol import InvalidTurn

    invalid = turn(world, B, "wait")
    intent = invalid["action"]["intent"]
    match error:
        case "continue":
            invalid = continue_turn(world, B)
        case "actor":
            intent["actor_id"] = A
        case "turn":
            intent["turn_id"] = f"{B}:t000001"
        case "tick":
            invalid["observed_tick"] = 1
        case "intent":
            intent["intent_id"] = "malformed"
        case "utterance":
            invalid["utterance"] = {"text": "hello"}
        case "quantity":
            invalid = turn(world, B, "give", subject("resident", A), held(quantity=0))
        case "duplicate":
            invalid = turn(world, A, "wait")
        case "verb":
            invalid = turn(world, B, "act", verb="unknown")
    before = deepcopy(world.state)
    with pytest.raises(InvalidTurn):
        world.step([turn(world, A, "wait"), invalid])
    assert world.state == before
    valid = turn(world, B, "wait")
    assert world.step([valid]).actions[0].outcome == "success"
    assert world.state.turn_ordinals == {A: 0, B: 1}
    with pytest.raises(InvalidTurn):
        world.step([valid])
    assert world.state.turn_ordinals[B] == 1


@pytest.mark.parametrize(
    "giver, recipient, expected",
    [
        (B, A, None),
        (A, B, "OUT_OF_REACH"),
    ],
)
def test_en02_wap27_give_start_order(
    world: World,
    giver: str,
    recipient: str,
    expected: str | None,
) -> None:
    from living_island.world.v2.engine.state import Held

    give_item(world, giver)
    gift = turn(world, giver, "give", subject("resident", recipient), held())
    walking = turn(world, recipient, "move_to", tile(2))
    boundary = world.step([gift, walking])
    starts = [event.actor_id for event in boundary.events if event.type == "action_started"]
    assert starts == [A, B]
    if expected is not None:
        assert (
            next(result for result in boundary.actions if result.actor_id == giver).failure_code
            == expected
        )
        assert world.state.entities["inst_a"].place == Held(giver)
    else:
        assert world.state.active_actions[giver].due_tick == 3
        assert world.step().actions == ()
        result = world.step()
        assert result.actions[0].tick_finished == 3
        assert result.actions[0].outcome == "success"
        assert any(entity.place == Held(recipient) for entity in world.state.entities.values())


@pytest.mark.parametrize("returns", [False, True])
def test_wap27_give_rechecks_only_on_due_tick(world: World, returns: bool) -> None:
    from living_island.world.v2.protocol import Coord

    give_item(world)
    world.state.residents[B].position = Coord(x=2, y=1)
    started = world.step(
        [
            turn(world, A, "give", subject("resident", B), held()),
            turn(world, B, "move_to", tile(4)),
        ]
    )
    assert [result.actor_id for result in started.actions] == [B]
    assert world.state.active_actions[A].elapsed_ticks == 1
    middle = world.step([turn(world, B, "move_to", tile(2))] if returns else [])
    assert all(result.actor_id != A for result in middle.actions)
    assert world.state.active_actions[A].elapsed_ticks == 2
    boundary = world.step()
    assert boundary.actions[0].failure_code == (None if returns else "OUT_OF_REACH")
    assert boundary.actions[0].tick_finished == 3


@pytest.mark.parametrize(
    "kind, command, expected",
    [
        ("move_bad", "move_to", "INVALID_TARGET"),
        ("move_blocked", "move_to", "PATH_BLOCKED"),
        ("move_empty", "move_to", "EXHAUSTED"),
        ("give_same", "give", "OUT_OF_REACH"),
        ("give_far", "give", "OUT_OF_REACH"),
        ("give_no_item", "give", "NO_ITEM"),
        ("give_missing", "give", "INVALID_TARGET"),
        ("take_far", "pick_up", "OUT_OF_REACH"),
        ("take_missing", "pick_up", "INVALID_TARGET"),
        ("take_structure", "pick_up", "INVALID_TARGET"),
        ("take_short", "pick_up", "ITEM_TAKEN"),
        ("drop_short", "drop", "NO_ITEM"),
        ("drop_far", "drop", "OUT_OF_REACH"),
        ("drop_bad_tile", "drop", "INVALID_TARGET"),
        ("drop_bad_container", "drop", "INVALID_TARGET"),
        ("inspect_far", "inspect", "OUT_OF_REACH"),
        ("inspect_missing", "inspect", "INVALID_TARGET"),
        ("contribute_wrong", "contribute", "NOT_A_PROCESS"),
    ],
)
def test_wap20_kernel_failure_codes_and_precedence(
    world: World,
    kind: str,
    command: str,
    expected: str,
) -> None:
    from living_island.world.v2.protocol import Coord

    params = {}
    target = None
    match kind:
        case "move_bad":
            target = tile(-1)
        case "move_blocked":
            target = tile(0)
        case "move_empty":
            world.state.needs[A]["stamina"] = 0
            target = tile(-1)
        case "give_same" | "give_far" | "give_no_item" | "give_missing":
            if kind == "give_same":
                world.state.residents[B].position = Coord(x=1, y=1)
            elif kind == "give_no_item":
                world.state.residents[B].position = Coord(x=2, y=1)
            target = subject("resident", "missing" if kind == "give_missing" else B)
            params = held()
        case "take_far":
            target, params = subject("entity", "inst_c"), {"quantity": 999}
        case "take_missing":
            target, params = subject("entity", "missing"), {"quantity": 1}
        case "take_structure":
            target, params = subject("entity", "inst_b"), {"quantity": 1}
        case "take_short":
            target, params = subject("entity", "inst_a"), {"quantity": 9}
        case "drop_short":
            target, params = tile(6), held()
        case "drop_far":
            give_item(world)
            target, params = tile(6), held()
        case "drop_bad_tile":
            give_item(world)
            target, params = tile(0), held()
        case "drop_bad_container":
            target, params = subject("entity", "inst_b"), held()
        case "inspect_far":
            target = subject("entity", "inst_b")
        case "inspect_missing":
            target = subject("entity", "missing")
        case "contribute_wrong":
            target = subject("entity", "inst_a")
    result = world.step([turn(world, A, command, target, params)])
    assert result.actions[0].failure_code == expected
    assert result.actions[0].tick_finished == 1
    assert [event.type for event in result.events] == ["action_started", "action_failed"]


def test_wap22_named_choices_precede_by_kind(world: World) -> None:
    from living_island.world.v2.engine.items import resolve_choices
    from living_island.world.v2.engine.state import Held, Part
    from living_island.world.v2.protocol import HeldItem, NamedItem

    give_item(world)
    source = world.state.entities["inst_a"]
    second = replace(source, entity_id="inst_z", place=Held(A), quantity=2)
    world.state.entities[second.entity_id] = second
    by_kind = HeldItem(kind="held", archetype_id="arch_a")
    exact = NamedItem(kind="item", id="inst_a")
    assert resolve_choices(world.state, A, [(by_kind, 1), (exact, 1)]) == (
        (Part("inst_z", 1),),
        (Part("inst_a", 1),),
    )
    assert resolve_choices(world.state, A, [(exact, 1), (by_kind, 1)]) == (
        (Part("inst_a", 1),),
        (Part("inst_z", 1),),
    )
    assert resolve_choices(world.state, A, [(by_kind, 3)]) == (
        (Part("inst_a", 2), Part("inst_z", 1)),
    )
    del world.state.entities[second.entity_id]
    assert resolve_choices(world.state, A, [(by_kind, 1), (exact, 1)]) is None


def test_en17_wap10_transfer_order_split_merge_and_ownership(world: World) -> None:
    from living_island.world.v2.engine.state import Held, Lineage
    from living_island.world.v2.protocol import Coord

    world.state.residents[B].position = Coord(x=2, y=1)
    pickup = world.step([turn(world, A, "pick_up", subject("entity", "inst_a"), {"quantity": 1})])
    assert [event.type for event in pickup.events] == [
        "action_started",
        "stack_split",
        "item_transferred",
        "action_succeeded",
    ]
    created = pickup.events[1].payload["new_id"]
    assert created == "e:380d791373097437"
    drop = world.step([turn(world, A, "drop", tile(2), named(created))])
    assert [event.type for event in drop.events] == [
        "action_started",
        "item_transferred",
        "stack_merged",
        "action_succeeded",
    ]
    assert drop.events[2].payload["into_id"] == "inst_a"
    assert created in world.state.entity_counter.issued

    tool = world.state.entities["inst_d"]
    tool.owner_id = B
    taken = world.step([turn(world, A, "pick_up", subject("entity", "inst_d"), {"quantity": 1})])
    assert taken.events[1].payload["owner_before"] == taken.events[1].payload["owner_after"] == B
    assert world.state.entities["inst_d"].place == Held(A)
    assert world.state.entities["inst_d"].lineage == (Lineage("inst_d", 0, 1, 4),)
    world.step([turn(world, A, "give", subject("resident", B), named("inst_d"))])
    world.step()
    moved = world.step()
    assert moved.events[0].payload["owner_before"] == moved.events[0].payload["owner_after"] == B
    assert world.state.entities["inst_d"].place == Held(B)


def test_en17_distinct_tile_stacks_and_inventory_merge(world: World) -> None:
    from living_island.world.v2.engine.state import Held, Lineage

    state = world.state
    source = state.entities["inst_a"]
    state.entities["inst_z"] = replace(
        source, entity_id="inst_z", quantity=3, apparent={}, lineage=(Lineage("inst_z", 0, 3, 7),)
    )
    state.entities["inst_h"] = replace(
        source,
        entity_id="inst_h",
        place=Held(A),
        quantity=1,
        lineage=(Lineage("inst_h", 0, 1, 8),),
    )
    result = world.step(
        [turn(world, A, "pick_up", tile(2), {"archetype_id": "arch_a", "quantity": 3})]
    )
    assert [event.type for event in result.events] == [
        "action_started",
        "item_transferred",
        "stack_merged",
        "stack_split",
        "item_transferred",
        "action_succeeded",
    ]
    assert result.events[1].payload["item_id"] == "inst_a"
    assert result.events[3].payload["from_id"] == "inst_z"
    assert world.state.entities["inst_z"].quantity == 2
    assert world.state.entities["inst_h"].quantity == 3


def test_wap22_tile_pickup_race_rechecks_stock(world: World) -> None:
    request = {"archetype_id": "arch_a", "quantity": 2}
    result = world.step(
        [
            turn(world, A, "pick_up", tile(2), request),
            turn(world, B, "pick_up", tile(2), request),
        ]
    )
    assert [action.outcome for action in result.actions] == ["success", "failure"]
    assert result.actions[1].failure_code == "ITEM_TAKEN"
    assert sum(event.type == "item_transferred" for event in result.events) == 1


def test_en17_container_capacity_and_slots(world: World) -> None:
    from living_island.world.v2.engine.items import slots_used
    from living_island.world.v2.engine.state import Held, Inside, Lineage
    from living_island.world.v2.protocol import Coord

    state = world.state
    state.residents[A].position = Coord(x=2, y=1)
    give_item(world)
    give_item(world, id_="inst_c")
    container = subject("entity", "inst_c")
    move = world.step([turn(world, A, "drop", container, held(quantity=2))])
    assert move.actions[0].outcome == "success"
    assert slots_used(world.state, Held(A)) == 2
    assert slots_used(world.state, Inside("inst_c")) == 2
    assert world.state.entities["inst_a"].place == Inside("inst_c")
    world.state.entities["inst_z"] = replace(
        world.state.entities["inst_a"],
        entity_id="inst_z",
        place=Held(A),
        quantity=1,
        lineage=(Lineage("inst_z", 0, 1, 7),),
    )
    fail = world.step([turn(world, A, "drop", container, held())])
    assert fail.actions[0].failure_code == "CONTAINER_FULL"
    take = world.step([turn(world, A, "pick_up", subject("entity", "inst_a"), {"quantity": 1})])
    assert take.actions[0].outcome == "success"
    assert take.events[1].payload["cause"] == "transfer"
    assert slots_used(world.state, Held(A)) == 4


def test_en18_counter_vectors_collision_and_terminal_failure(world: World, monkeypatch) -> None:
    from living_island.world.v2.engine import ids
    from living_island.world.v2.engine.ids import EntityCounter, corpse_id, entity_candidate

    counter = EntityCounter()
    assert [counter.allocate(20261108) for _ in range(2)] == [
        "e:380d791373097437",
        "e:cfa85a63518a57ef",
    ]
    assert corpse_id(A) == "corpse@res_a"
    assert "inst_a" in world.state.entities
    counter.issued.add(entity_candidate(20261108, 2, 0))
    assert counter.allocate(20261108) == entity_candidate(20261108, 2, 1)
    world.state.entity_counter.n = ids.MAX_EXACT - 1
    before = deepcopy(world.state)
    with pytest.raises(OverflowError, match="counter exhausted"):
        world.step([turn(world, A, "pick_up", subject("entity", "inst_a"), {"quantity": 1})])
    assert world.state == before
    monkeypatch.setattr(ids, "MAX_EXACT", 2)
    monkeypatch.setattr(ids, "entity_candidate", lambda *_: "already_issued")
    blocked = EntityCounter(issued={"already_issued"})
    with pytest.raises(OverflowError, match="collision"):
        blocked.allocate(1)
    assert blocked.n == 0 and blocked.issued == {"already_issued"}


def test_en19_bounds_are_atomic_and_reserve_room_for_corpses(world: World) -> None:
    from living_island.world.v2.engine.limits import entity_units, within_placement_limits
    from living_island.world.v2.engine.state import Limits

    state = world.state
    units = entity_units(state)
    limits = Limits(units + len(state.residents) + 1, 1)
    trial = deepcopy(state)
    trial.entities["inst_a"].quantity += 1
    assert within_placement_limits(trial, limits, [])
    trial.entities["inst_a"].quantity += 1
    assert not within_placement_limits(trial, limits, [])
    assert entity_units(state) == units
    result = world.step([turn(world, A, "pick_up", subject("entity", "inst_a"), {"quantity": 1})])
    assert result.actions[0].outcome == "success" and entity_units(world.state) == units


def test_en19_initial_pack_at_bound_is_refused(pack: Pack, setup: WorldSetup) -> None:
    from living_island.world.v2.engine import initialize

    limited = replace(
        pack,
        data={
            **pack.data,
            "limits": {
                **pack.data["limits"],
                "max_entity_units_world": 6,
            },
        },
    )
    with pytest.raises(ValueError, match="exceed entity limits"):
        initialize(limited, setup)


def test_inspect_uses_apparent_values_and_does_not_show_age(world: World) -> None:
    result = world.step([turn(world, A, "inspect", subject("entity", "inst_a"))])
    view = result.actions[0].visible_feedback.inspected
    assert view is not None and "created_tick" not in view.model_dump()
    words = {descriptor.property_id: descriptor.value for descriptor in view.descriptors}
    assert words["hardness"] == "soft"
    assert "weight" in words and "edible" not in words


def test_tick_replays_same_state_and_events_and_keeps_order(world: World) -> None:
    from living_island.world.v2.engine.events import EVENT_FIELDS
    from living_island.world.v2.protocol import encode_event_line

    other = deepcopy(world)
    inputs = [turn(world, B, "wait"), turn(world, A, "wait")]
    first, second = world.step(inputs), other.step(list(reversed(inputs)))
    assert world.state == other.state
    assert tuple(map(encode_event_line, first.events)) == tuple(
        map(encode_event_line, second.events)
    )
    assert world.state.clock_minute == 370
    assert world.state.event_log_cursor == len(world.initial_events) + len(first.events)
    assert [event.seq_in_tick for event in first.events] == list(range(len(first.events)))
    for event in (*world.initial_events, *first.events):
        assert event.payload.keys() == set(EVENT_FIELDS[event.type])


def test_actor_stop_is_deferred_and_continue_keeps_action(world: World) -> None:
    from living_island.world.v2.protocol import Coord

    give_item(world)
    world.state.residents[B].position = Coord(x=2, y=1)
    world.step([turn(world, A, "give", subject("resident", B), held())])
    world.step([continue_turn(world, A)])
    assert world.state.active_actions[A].elapsed_ticks == 2
    result = world.step([turn(world, A, "wait")])
    assert [action.outcome for action in result.actions] == ["stopped", "success"]
    assert result.actions[0].tick_finished == 2
    assert world.state.deferred_feedback[A].feedback[0].stop_reason == "own_choice"
    assert world.state.turn_ordinals[A] == 3


def test_wap10_transfer_into_and_out_of_a_process(world: World) -> None:
    from living_island.world.v2.engine.state import Held, Inside
    from living_island.world.v2.protocol import Coord

    world.state.residents[A].position = Coord(x=2, y=2)
    give_item(world)
    place = subject("entity", "inst_e")
    dropped = world.step([turn(world, A, "drop", place, held(quantity=2))])
    assert dropped.actions[0].outcome == "success"
    assert world.state.entities["inst_a"].place == Inside("inst_e")
    taken = world.step([turn(world, A, "pick_up", subject("entity", "inst_a"), {"quantity": 2})])
    assert taken.actions[0].outcome == "success"
    assert world.state.entities["inst_a"].place == Held(A)
    assert [entry.path for entry in taken.actions[0].state_delta] == ["/entities/inst_a/place"]


def test_wap20_inventory_full_give_has_no_effect(world: World) -> None:
    from living_island.world.v2.engine.state import Held
    from living_island.world.v2.protocol import Coord

    world.state.residents[B].position = Coord(x=2, y=1)
    give_item(world, id_="inst_c")
    give_item(world, B, id_="inst_a")
    world.state.entities["inst_a"].quantity = 6
    result = world.step([turn(world, A, "give", subject("resident", B), named("inst_c"))])
    assert result.actions[0].failure_code == "INVENTORY_FULL"
    assert world.state.entities["inst_c"].place == Held(A)


def test_cr011_receipt_only_target_does_not_reveal_a_start_look(world: World) -> None:
    world.state.visible_entities_by_resident[A].remove("inst_a")
    result = world.step(
        [
            turn(world, A, "pick_up", subject("entity", "inst_a"), {"quantity": 1}),
        ]
    )
    feedback = result.actions[0].visible_feedback
    assert feedback.status == "done" and feedback.start_target is None
    assert feedback.items_used == []


def test_en19_removal_is_legal_on_a_dense_tile(world: World) -> None:
    from living_island.world.v2.engine.limits import within_placement_limits
    from living_island.world.v2.engine.state import Limits

    state = world.state
    on_tile = state.entities["inst_a"].place
    state.entities["inst_c"].place = on_tile
    assert not within_placement_limits(state, Limits(32, 1), [on_tile.position])
    assert within_placement_limits(state, Limits(32, 1), [])


def test_configuration_refuses_invalid_terrain_and_pack_chain(
    pack: Pack, setup: WorldSetup
) -> None:
    from pydantic import ValidationError

    from living_island.world.v2.engine import MapConfig, initialize

    with pytest.raises(ValidationError, match="rectangle"):
        MapConfig(
            rows=(("grass",), ()),
            step_costs={"grass": 1},
            walk_budget=1,
            opaque_terrains=frozenset(),
        )
    with pytest.raises(ValidationError, match="impassable"):
        MapConfig(
            rows=(("sea",),),
            step_costs={"grass": 1, "sea": 1},
            walk_budget=1,
            opaque_terrains=frozenset(),
        )
    with pytest.raises(ValueError, match="base-first"):
        initialize(pack, setup.model_copy(update={"pack_ids": ("engine_core",)}))


def test_rule_additions_publish_before_actor_starts_and_refuse_duplicates(world: World) -> None:
    from living_island.world.v2.rules import ContentError

    rule = {
        "id": "added_a",
        "trigger": "verb:rest",
        "work_ticks": 1,
        "provenance": {
            "kind": "proposed",
            "llm_call_id": "call_a",
            "approved_by": A,
            "approved_at_tick": 0,
        },
    }
    initial_hash = world.state.library.rule_library_hash
    boundary = world.step([turn(world, A, "wait")], rule_additions=[rule])
    assert [event.type for event in boundary.events] == [
        "rule_added",
        "action_started",
        "action_succeeded",
    ]
    library = world.state.library
    assert library.rule_library_hash != initial_hash
    assert library.added_rules["added_a"].content_hash == boundary.events[0].payload["content_hash"]
    assert "added_a" in library.active_rule_ids
    before = deepcopy(world.state)
    with pytest.raises(ContentError, match="DUPLICATE_ID"):
        world.step(rule_additions=[rule])
    assert world.state == before


def test_delivery_acknowledgement_preserves_fatigue_counts(world: World) -> None:
    from living_island.world.v2.protocol import (
        BoundaryDelivery,
        InvalidTurn,
        Perception,
        WorldReport,
    )

    packet = BoundaryDelivery(
        delivery_id="packet_a",
        actor_id=A,
        observed_tick=0,
        perception=Perception(
            schema_version="wap/0.1",
            actor_id=A,
            tick=0,
            awareness="awake",
            needs=[],
            own_position=world.state.residents[A].position,
            inventory=[],
            running_action=None,
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
            WorldReport(
                kind="utterance_heard",
                subject_id="utterance_a",
                addressed=True,
                band=None,
                threshold_id=None,
            ),
            WorldReport(
                kind="entity_first_seen",
                subject_id="inst_a",
                addressed=None,
                band=None,
                threshold_id=None,
            ),
        ],
    )
    world.state.pending_deliveries[A] = packet
    with pytest.raises(InvalidTurn, match="acknowledged"):
        world.step()
    with pytest.raises(InvalidTurn, match="match a pending"):
        world.step(acknowledged={A: "older_packet"})
    assert world.state.pending_deliveries[A] == packet and world.state.tick == 0

    world.step(acknowledged={A: packet.delivery_id})
    assert A not in world.state.pending_deliveries
    assert world.state.fatigue_inputs[A].utterances_heard == 1
    assert world.state.fatigue_inputs[A].first_sightings == 1
