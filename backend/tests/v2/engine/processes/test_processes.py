"""Run process rules through the real tick and inspect objective effects."""

from copy import deepcopy
from dataclasses import replace

import pytest

A, B = "res_a", "res_b"


def turn(world, actor, action, target=None, *, verb=None, inputs=()):
    identity = f"{actor}:t{world.state.turn_ordinals[actor]:06d}"
    return {
        "schema_version": "wap/0.1",
        "turn_id": identity,
        "actor_id": actor,
        "observed_tick": world.state.tick,
        "action": {
            "kind": "intent",
            "intent": {
                "intent_id": f"{identity}:a",
                "turn_id": identity,
                "actor_id": actor,
                "action": action,
                "verb": verb,
                "target": target,
                "instruments": [],
                "inputs": list(inputs),
                "params": {},
                "reason": None,
            },
        },
        "utterance": None,
    }


def contribute(world, actor, key="inst_e"):
    return turn(world, actor, "contribute", {"kind": "entity", "id": key})


def proposed(rule_id, subject, condition, **fields):
    return {
        "id": rule_id,
        "trigger": f"when:{condition['id']}",
        "subject": {"archetype": subject},
        "conditions": [condition],
        "provenance": {
            "kind": "proposed",
            "llm_call_id": "fixture",
            "approved_by": A,
            "approved_at_tick": 0,
        },
        **fields,
    }


def payloads(result, kind):
    return [event.payload for event in result.events if event.type == kind]


def setup_existing_process(world):
    from living_island.world.v2.engine.state import Inside, OnTile
    from living_island.world.v2.protocol import Coord

    state = world.state
    state.residents[B].position = Coord(x=2, y=1)
    process = state.entities["inst_e"]
    process.place = OnTile(state.residents[B].position)
    state.entities["inst_a"].place = Inside(process.entity_id)
    return process.entity_id


def work(world, key):
    return world.state.entities[key].components["process"]["work_done"]


def test_en09_work_pauses_and_resumes_with_contents(world):
    from living_island.world.v2.engine.state import Inside, OnTile

    key = setup_existing_process(world)
    first = world.step([contribute(world, B), contribute(world, A)])
    assert not first.actions
    assert payloads(first, "process_progressed") == [
        {"process_id": key, "work_done": 1, "contributor_id": A},
        {"process_id": key, "work_done": 2, "contributor_id": B},
    ]
    world.state.entities["inst_a"].place = OnTile(world.state.residents[B].position)
    paused = world.step()
    assert work(world, key) == 2
    assert not paused.actions
    assert not payloads(paused, "process_progressed")
    world.state.entities["inst_a"].place = Inside(key)

    last = world.step()
    assert [entry["work_done"] for entry in payloads(last, "process_progressed")] == [3, 4]
    assert [(r.actor_id, r.outcome, r.tick_finished) for r in last.actions] == [
        (A, "success", 3),
        (B, "success", 3),
    ]
    assert not world.state.active_actions
    assert key not in world.state.entities
    [created] = payloads(last, "entity_created")
    assert (created["owner_id"], created["process_id"]) == (None, key)
    remainder = world.state.entities["inst_a"]
    assert remainder.quantity == 1
    assert remainder.place == OnTile(world.state.residents[B].position)


def test_en10_world_rule_takes_apart_active_process(world):
    key = setup_existing_process(world)
    first = world.step([contribute(world, A)])
    assert not first.actions

    take_apart = proposed(
        "take_apart",
        "arch_e",
        {
            "id": "work_started",
            "kind": "state",
            "of": "subject",
            "field": "process.work_done",
            "op": ">",
            "value": 0,
        },
        effects=[{"op": "consume", "of": "subject"}],
    )
    result = world.step(rule_additions=[take_apart])
    [action] = result.actions
    assert action.outcome == "stopped"
    assert action.tick_finished == 2
    assert action.stop.reason == "TARGET_GONE"
    assert key not in world.state.entities
    assert not payloads(result, "entity_created")


def test_en31_refused_spill_preserves_work_and_is_retried(world):
    from living_island.world.v2.engine.state import OnTile

    key = setup_existing_process(world)
    process = world.state.entities[key]
    process.components["process"]["work_done"] = 3
    blocker = world.state.entities["inst_f"]
    blocker.place = process.place
    before_counter = deepcopy(world.state.entity_counter)
    world.pack = replace(world.pack, limits=replace(world.pack.limits, max_entities_per_tile=1))
    refused = world.step([contribute(world, A)])
    assert work(world, key) == 4
    assert world.state.entities["inst_a"].quantity == 2
    assert A in world.state.active_actions
    assert not refused.actions
    assert not any(event.payload.get("rule_id") == "rule_g" for event in refused.events)
    assert world.state.entity_counter == before_counter

    # Keep the original work and admit the same branch once both placements fit.
    blocker = world.state.entities["inst_f"]
    blocker.place = OnTile(world.state.residents[A].position)
    world.pack = replace(world.pack, limits=replace(world.pack.limits, max_entities_per_tile=2))
    accepted = world.step()
    assert payloads(accepted, "process_progressed")[0]["work_done"] == 5
    assert accepted.actions[0].outcome == "success"
    assert key not in world.state.entities


@pytest.mark.parametrize("refused", ["none", "tile", "reservation", "death"])
def test_rr19_keep_progress_moves_inputs_or_falls_back_atomically(world, refused):
    from living_island.world.v2.engine.events import EventWriter
    from living_island.world.v2.engine.settle import interrupt
    from living_island.world.v2.engine.state import Held, Inside, OnTile
    from living_island.world.v2.engine.tick import TickContext
    from living_island.world.v2.protocol import Coord

    world.state.residents[B].position = Coord(x=2, y=1)
    world.state.entities["inst_a"].place = Held(A)
    point = world.state.residents[A].position
    build = turn(
        world,
        A,
        "act",
        {"kind": "tile", "position": {"x": point.x, "y": point.y}},
        verb="build",
        inputs=[{"item": {"kind": "held", "archetype_id": "arch_a"}, "quantity": 1}],
    )
    world.step([build])
    action = world.state.active_actions[A]
    assert action.rule_id == "rule_e"
    reserved = action.bindings[0].physical_id

    if refused == "tile":
        world.state.entities["inst_f"].place = OnTile(point)
        world.pack = replace(world.pack, limits=replace(world.pack.limits, max_entities_per_tile=1))
    if refused == "reservation":
        del world.state.entities[reserved]
    if refused == "death":
        world.state.residents[A].alive = False
    if refused in ("reservation", "death"):
        writer = EventWriter(world.state, 2)
        interrupt(TickContext(world.state, world.pack, writer), action)
        assert not any(
            event.type in ("entity_created", "entity_consumed") for event in writer.events
        )
        assert not action.bindings
        assert sum(e.quantity for e in world.state.entities.values() if e.place == Held(A)) == (
            1 if refused == "reservation" else 2
        )
        return

    result = world.step([turn(world, A, "wait")])
    if refused == "tile":
        assert not payloads(result, "entity_created")
        assert sum(e.quantity for e in world.state.entities.values() if e.place == Held(A)) == 2
        return
    [created] = payloads(result, "entity_created")
    key = created["entity_id"]
    assert work(world, key) == 1
    assert world.state.entities[key].place == OnTile(point)
    assert world.state.entities[reserved].place == Inside(key)

    from living_island.world.v2.engine.state import Exposure

    world.state.exposure_receipts_by_resident[B].entities[key] = Exposure(key, point, "arch_e")
    world.state.visible_entities_by_resident[B].add(key)
    world.step([contribute(world, B, key)])
    world.step()
    finished = world.step()
    assert [(row.actor_id, row.outcome) for row in finished.actions] == [(B, "success")]
    assert payloads(finished, "entity_created")[0]["process_id"] == key


READY_ARCHETYPES = """
[[archetype]]
id = "first_site"
kind = "process"
stackable = false
[archetype.components]
process = { work_required = 1, work_done = 1 }
container = { capacity = 1, accepts = {} }

[[archetype]]
id = "second_site"
kind = "process"
stackable = false
[archetype.components]
process = { work_required = 1, work_done = 1 }
container = { capacity = 1, accepts = {} }
"""


@pytest.mark.parametrize("first_in_4a", [False, True])
def test_round3_new_processes_wait_until_the_next_4b(process_world, first_in_4a):
    first_condition = (
        '{ id = "ready", kind = "state", of = "subject", field = "age", op = ">=", value = 1 }'
        if first_in_4a
        else '{ id = "ready", kind = "work_complete" }'
    )
    world = process_world(
        archetypes=READY_ARCHETYPES,
        instances="""
[[instance]]
id = "chain_start"
archetype = "first_site"
at = { tile = [3, 3] }
""",
        rules=f"""
[[rule]]
id = "first_complete"
trigger = "when:ready"
subject = {{ archetype = "first_site" }}
conditions = [{first_condition}]
effects = [{{ op = "consume", of = "subject" }}]
outputs = [{{ archetype = "second_site", quantity = 1, at = "subject.tile" }}]

[[rule]]
id = "second_complete"
trigger = "when:done"
subject = {{ archetype = "second_site" }}
conditions = [{{ id = "done", kind = "work_complete" }}]
effects = [{{ op = "consume", of = "subject" }}]
""",
    )
    one = world.step()
    [created] = payloads(one, "entity_created")
    assert created["process_id"] == (None if first_in_4a else "chain_start")
    key = created["entity_id"]
    first_rules = [
        row["rule_id"] for row in payloads(one, "world_rule_applied") if row["rule_id"] != "rule_f"
    ]
    assert first_rules == (
        ["first_complete", "second_complete"] if first_in_4a else ["first_complete"]
    )
    assert "chain_start" not in world.state.entities
    if not first_in_4a:
        assert work(world, key) == 1
    two = world.step()
    assert payloads(two, "world_rule_applied") == (
        [] if first_in_4a else [{"rule_id": "second_complete", "subject_id": key}]
    )
    assert key not in world.state.entities
    assert not payloads(world.step(), "world_rule_applied")
