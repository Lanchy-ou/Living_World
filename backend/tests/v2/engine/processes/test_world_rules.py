"""World-rule ordering, capacity, and exact contents search acceptance."""

from itertools import combinations
from time import perf_counter_ns

import pytest
from test_processes import A, B, contribute, payloads, proposed, turn

STORE_ARCHETYPE = """
[[archetype]]
id = "timer_tree"
kind = "structure"
stackable = false
components = { store = { archetype = "arch_a", capacity = 4 } }
"""


def test_en11_rr21_periods_offsets_and_full_store(process_world):
    world = process_world(
        archetypes=STORE_ARCHETYPE,
        rules="""
[[rule]]
id = "grow"
trigger = "every:144"
subject = { archetype = "timer_tree" }
conservation = "source"
[[rule.outputs]]
archetype = "arch_a"
quantity = { of = "fit:subject.store" }
at = "subject.store"
source = "src_a"
""",
        instances="""
[[instance]]
id = "offset_zero"
archetype = "timer_tree"
at = { tile = [3, 3] }

[[instance]]
id = "offset_twenty_four"
archetype = "timer_tree"
at = { tile = [3, 3] }
phase_offset = { grow = 24 }
""",
    )
    assert not any(row.type == "world_rule_applied" for row in world.initial_events)
    fired = []
    for tick in range(1, 289):
        result = world.step()
        for row in payloads(result, "store_count_changed"):
            if row["rule_id"] == "grow":
                assert (row["before"], row["after"]) == (0, 4)
                fired.append((tick, row["entity_id"]))
        if tick == 24:
            count = world.state.entities["offset_twenty_four"].components["store"]
            assert count["count"] == 4
            count["count"] = 0
        if tick == 288:
            assert not any(
                row["rule_id"] == "grow" for row in payloads(result, "world_rule_applied")
            )
    assert fired == [(24, "offset_twenty_four"), (144, "offset_zero"), (168, "offset_twenty_four")]


def test_en11_same_rule_does_not_revisit_its_output(world):
    renewal = proposed(
        "renew",
        "arch_f",
        {"id": "ready", "kind": "state", "of": "subject", "field": "age", "op": ">=", "value": 0},
        effects=[{"op": "consume", "of": "subject"}],
        outputs=[{"archetype": "arch_f", "quantity": 1, "at": "subject.place"}],
    )
    result = world.step(rule_additions=[renewal])
    assert [
        row["subject_id"]
        for row in payloads(result, "world_rule_applied")
        if row["rule_id"] == "renew"
    ] == ["inst_f"]
    [created] = payloads(result, "entity_created")
    assert created["entity_id"] in world.state.entities
    next_tick = world.step()
    assert payloads(next_tick, "world_rule_applied") == [
        {"rule_id": "renew", "subject_id": created["entity_id"]}
    ]


def test_rr21_when_observes_completed_wear_once(world):
    wear = proposed(
        "a_wear",
        "arch_d",
        {
            "id": "wear",
            "kind": "state",
            "of": "subject",
            "field": "durability.left",
            "op": ">",
            "value": 0,
        },
        effects=[{"op": "set_state", "of": "subject", "field": "durability.wear", "add": 1}],
    )
    assert not payloads(world.step(rule_additions=[wear]), "entity_consumed")
    assert not payloads(world.step(), "entity_consumed")
    assert not payloads(world.step(), "entity_consumed")
    last = world.step()
    assert [
        row["rule_id"] for row in payloads(last, "world_rule_applied") if row["rule_id"] != "rule_j"
    ] == ["a_wear", "rule_i"]
    assert payloads(last, "entity_consumed")[0]["entity_id"] == "inst_d"
    assert not payloads(world.step(), "entity_consumed")


PROCESS_ARCHETYPE = """
[[archetype]]
id = "worksite"
kind = "process"
stackable = false
matter = { mineral = 1 }
[archetype.components]
process = { work_required = 4, work_done = 3 }
container = { capacity = 30, accepts = { material = "mat_a" } }
fuel = { ticks_left = 2 }
portable = { slots_per_unit = 1 }
"""

ORDER_RULES = """
[[rule]]
id = "a_finish"
trigger = "when:ready"
subject = { archetype = "worksite" }
conditions = [{ id = "ready", kind = "work_complete" }]
effects = [{ op = "consume", of = "subject" }]
outputs = [{ archetype = "arch_f", quantity = 1, at = "subject.tile" }]

[[rule]]
id = "z_finish"
trigger = "when:ready"
subject = { archetype = "worksite" }
conditions = [
  { id = "ready", kind = "work_complete" },
  { id = "fuel", kind = "state", of = "subject", field = "fuel.ticks_left", op = ">", value = 0 }
]
effects = [{ op = "consume", of = "subject" }]
outputs = [{ archetype = "arch_d", quantity = 1, at = "subject.tile" }]

[[rule]]
id = "m_change"
trigger = "when:near_fire"
subject = { archetype = "worksite" }
conditions = [
  { id="near_fire", kind="entity_near", where={archetype="arch_f"}, distance={min=0, max=0} },
  { id="still_fueled", kind="state", of="subject", field="fuel.ticks_left", op=">", value=0 }
]
effects = [{ op = "set_state", of = "subject", field = "fuel.ticks_left", set = 0 }]
"""


@pytest.mark.parametrize("earlier_world_rule", [True, False])
def test_en09_en31_rr20_4a_then_one_completion_per_subject(process_world, earlier_world_rule):
    rules = ORDER_RULES.replace("m_change", "zz_change") if not earlier_world_rule else ORDER_RULES
    world = process_world(
        archetypes=PROCESS_ARCHETYPE,
        rules=rules,
        instances="""
[[instance]]
id = "a_site"
archetype = "worksite"
at = { tile = [1, 1] }

[[instance]]
id = "b_site"
archetype = "worksite"
at = { tile = [4, 2] }
""",
    )
    from living_island.world.v2.protocol import Coord

    world.state.residents[B].position = Coord(x=4, y=1)
    result = world.step([contribute(world, B, "b_site"), contribute(world, A, "a_site")])
    change = "m_change" if earlier_world_rule else "zz_change"
    assert [
        (row["rule_id"], row["subject_id"])
        for row in payloads(result, "world_rule_applied")
        if row["rule_id"] != "rule_f"
    ] == [(change, "b_site"), ("z_finish", "a_site"), ("a_finish", "b_site")]
    assert [(entry.actor_id, entry.outcome, entry.tick_finished) for entry in result.actions] == [
        (A, "success", 1),
        (B, "success", 1),
    ]
    assert [row["entity_id"] for row in payloads(result, "entity_consumed")] == ["a_site", "b_site"]
    assert [
        (row["archetype_id"], row["process_id"], row["owner_id"])
        for row in payloads(result, "entity_created")
    ] == [("arch_d", "a_site", None), ("arch_f", "b_site", None)]


def test_en31_only_contributor_still_in_reach_succeeds(process_world):
    from living_island.world.v2.protocol import Coord

    world = process_world(
        archetypes=PROCESS_ARCHETYPE,
        rules=ORDER_RULES,
        instances="""
[[instance]]
id = "carried_site"
archetype = "worksite"
at = { holder = "res_b" }
""",
    )
    world.state.residents[A].position = Coord(x=2, y=1)
    move = turn(world, B, "move_to", {"kind": "tile", "position": {"x": 4, "y": 1}})
    result = world.step([contribute(world, A, "carried_site"), move])
    assert payloads(result, "process_progressed")[0]["contributor_id"] == A
    assert "carried_site" not in world.state.entities
    outcomes = {entry.actor_id: entry for entry in result.actions}
    assert outcomes[B].outcome == "success"
    assert outcomes[A].outcome == "stopped"
    assert outcomes[A].stop.reason == "TARGET_GONE"


def test_en34_rr38_dense_search_matches_exhaustive(process_world, record_property):
    from living_island.world.v2.engine.events import EventWriter
    from living_island.world.v2.engine.tick import TickContext
    from living_island.world.v2.engine.world_rules import ContentsSearch

    instances = """
[[instance]]
id = "work"
archetype = "worksite"
at = { tile = [3, 3] }
"""
    count = 14
    need = count // 2
    for i in range(count):
        archetype = "arch_a" if i < need else "arch_d"
        instances += f'''
[[instance]]
id = "item_{i:02}"
archetype = "{archetype}"
at = {{ holder = "work" }}
properties = {{ strength = {i % 6}, weight = {i // 6} }}
'''
    world = process_world(
        archetypes=PROCESS_ARCHETYPE,
        instances=instances,
        rules=f"""
[[rule]]
id = "large_job"
trigger = "when:ready"
subject = {{ archetype = "worksite" }}
conditions = [{{ id = "ready", kind = "work_complete" }}]
inputs = [
  {{ slot = "broad", where = {{}}, qty = {need} }},
  {{ slot = "restricted", where = {{ archetype = "arch_a" }}, qty = {need} }}
]
effects = [{{ op = "consume", of = "subject" }}]
""",
    )
    state = world.state
    ctx = TickContext(state, world.pack, EventWriter(state, 1))
    search = ContentsSearch(ctx, state.entities["work"], world._schedule.processes["worksite"][0])

    started = perf_counter_ns()
    result = search.first()
    search_ns = perf_counter_ns() - started
    assert result is not None
    selected = tuple(tuple(part.entity_id for part in slot) for slot in result)
    restricted = set(range(need))
    tried = 0

    started = perf_counter_ns()
    for broad in combinations(range(count), need):
        tried += 1
        remaining = restricted.difference(broad)
        if len(remaining) == need:
            exhaustive = tuple(
                tuple(f"item_{i:02}" for i in indices) for indices in (broad, sorted(remaining))
            )
            break
    exhaustive_ns = perf_counter_ns() - started

    assert selected == exhaustive
    assert all(part.quantity == 1 for slot in result for part in slot)
    assert search.visited_prefixes < tried
    record_property("pruned_prefixes", search.visited_prefixes)
    record_property("exhaustive_allocations", tried)
    record_property("pruned_ns", search_ns)
    record_property("exhaustive_ns", exhaustive_ns)
    print(
        f"RR-38 and EN-34: {search.visited_prefixes} pruned prefixes in {search_ns} ns, "
        f"{tried} exhaustive allocations in {exhaustive_ns} ns"
    )


def test_en30_initial_cap_reserves_a_corpse_for_each_living_resident(process_world):
    with pytest.raises(ValueError, match="initial placements exceed entity limits"):
        process_world(world_limit=7)


def test_en30_full_receiving_tile_blocks_fire_spill(process_world):
    from dataclasses import replace

    world = process_world(
        archetypes=PROCESS_ARCHETYPE,
        instances="""
[[instance]]
id = "spent_fire"
archetype = "worksite"
at = { tile = [4, 2] }
state = { fuel = { ticks_left = 0 } }

[[instance]]
id = "stored_item"
archetype = "arch_a"
at = { holder = "spent_fire" }
""",
        rules="""
[[rule]]
id = "clear_fire"
trigger = "when:out"
subject = { archetype = "worksite" }
conditions = [
  { id = "out", kind = "state", of = "subject", field = "fuel.ticks_left", op = "==", value = 0 }
]
effects = [{ op = "consume", of = "subject" }]
""",
    )
    from living_island.world.v2.engine.state import Inside

    world.pack = replace(world.pack, limits=replace(world.pack.limits, max_entities_per_tile=1))
    first = world.step()
    assert not payloads(first, "entity_consumed")
    assert not payloads(first, "matter_moved")
    assert world.state.entities["spent_fire"].components["fuel"]["ticks_left"] == 0
    assert world.state.entities["stored_item"].place == Inside("spent_fire")

    world.pack = replace(world.pack, limits=replace(world.pack.limits, max_entities_per_tile=2))
    second = world.step()
    assert payloads(second, "world_rule_applied") == [
        {"rule_id": "clear_fire", "subject_id": "spent_fire"}
    ]
    assert payloads(second, "matter_moved")[0]["entity_id"] == "stored_item"
    assert "spent_fire" not in world.state.entities


def test_en30_rot_refused_by_original_container_preserves_fruit(world):
    from living_island.world.v2.engine.state import Inside, OnTile
    from living_island.world.v2.protocol import Coord

    fruit = world.state.entities["inst_a"]
    fruit.place = Inside("inst_c")
    rot = proposed(
        "rot",
        "arch_a",
        {"id": "old", "kind": "state", "of": "subject", "field": "age", "op": ">=", "value": 1},
        effects=[{"op": "consume", "of": "subject"}],
        outputs=[
            {"archetype": "arch_d", "quantity": {"of": "subject.quantity"}, "at": "subject.place"}
        ],
    )
    initial_counter = world.state.entity_counter
    first = world.step(rule_additions=[rot])
    assert not payloads(first, "entity_consumed")
    assert not payloads(first, "entity_created")
    assert world.state.entities["inst_a"] == fruit
    assert world.state.entity_counter == initial_counter

    world.state.entities["inst_a"].place = OnTile(Coord(x=1, y=1))
    later = world.step()
    assert [event["quantity"] for event in payloads(later, "entity_created")] == [1, 1]
    assert "inst_a" not in world.state.entities


def test_process_stops_in_phase2_when_an_earlier_actor_moves_it(process_world):
    from living_island.world.v2.protocol import Coord

    world = process_world(
        archetypes=PROCESS_ARCHETYPE,
        rules=ORDER_RULES,
        instances="""
[[instance]]
id = "carried_site"
archetype = "worksite"
at = { holder = "res_a" }
state = { process = { work_done = 0 } }
""",
    )
    world.state.residents[A].position = Coord(x=2, y=1)
    first = world.step([contribute(world, B, "carried_site")])
    assert payloads(first, "process_progressed")[0]["work_done"] == 1
    assert not first.actions
    move = turn(world, A, "move_to", {"kind": "tile", "position": {"x": 1, "y": 1}})
    final = world.step([move])
    assert not payloads(final, "process_progressed")
    result = next(entry for entry in final.actions if entry.actor_id == B)
    assert result.stop.reason == "TARGET_GONE"
    assert world.state.entities["carried_site"].components["process"]["work_done"] == 1


def test_subject_created_in_4a_can_run_in_later_ordinary_rule_with_default_offset(process_world):
    world = process_world(
        archetypes=STORE_ARCHETYPE,
        rules="""
[[rule]]
id = "a_convert"
trigger = "when:old"
subject = { archetype = "arch_f" }
conditions = [{ id = "old", kind = "state", of = "subject", field = "age", op = ">=", value = 1 }]
effects = [{ op = "consume", of = "subject" }]
outputs = [{ archetype = "timer_tree", quantity = 1, at = "subject.place" }]

[[rule]]
id = "z_grow"
trigger = "every:1"
subject = { archetype = "timer_tree" }
conservation = "source"
[[rule.outputs]]
archetype = "arch_a"
quantity = { of = "fit:subject.store" }
at = "subject.store"
source = "src_a"
""",
    )
    result = world.step()
    [tree] = payloads(result, "entity_created")
    applied = payloads(result, "world_rule_applied")
    assert applied[0] == {"rule_id": "a_convert", "subject_id": "inst_f"}
    assert applied[-1] == {"rule_id": "z_grow", "subject_id": tree["entity_id"]}
    assert world.state.entities[tree["entity_id"]].components["store"]["count"] == 4


def test_contents_match_uses_first_homogeneous_allocation(process_world):
    from living_island.world.v2.engine.state import OnTile
    from living_island.world.v2.protocol import Coord

    world = process_world(
        archetypes=PROCESS_ARCHETYPE,
        instances="""
[[instance]]
id = "work"
archetype = "worksite"
at = { tile = [3, 3] }
state = { process = { work_done = 4 } }

[[instance]]
id = "item_a"
archetype = "arch_a"
at = { holder = "work" }

[[instance]]
id = "item_b"
archetype = "arch_d"
at = { holder = "work" }

[[instance]]
id = "item_c"
archetype = "arch_d"
at = { holder = "work" }
""",
        rules="""
[[rule]]
id = "finish"
trigger = "when:ready"
subject = { archetype = "worksite" }
conditions = [{ id = "ready", kind = "work_complete" }]
inputs = [{ slot = "parts", where = {}, qty = 2 }]
effects = [{ op = "consume", of = "subject" }]
outputs = [
  { archetype_from = "parts", material_from = "parts", quantity = 2, at = "subject.tile" }
]
""",
    )
    result = world.step()
    used = payloads(result, "entity_consumed")
    assert [row["entity_id"] for row in used] == ["item_b", "item_c", "work"]
    created = payloads(result, "entity_created")
    assert [row["recreated_from"] for row in created] == [
        [{"physical_id": "item_b", "quantity": 1}],
        [{"physical_id": "item_c", "quantity": 1}],
    ]
    assert world.state.entities["item_a"].place == OnTile(Coord(x=3, y=3))
