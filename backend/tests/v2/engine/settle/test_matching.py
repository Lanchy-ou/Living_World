"""Back-test objective descriptors and check the public settlement boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from test_settlement import A, combine, event, input_a, named, proposal, slot, target, turn

if TYPE_CHECKING:
    from living_island.world.v2.engine import World


def test_rr06_rr07_wap06_true_match_keeps_apparent_feedback(world: World) -> None:
    from living_island.world.v2.engine.items import true_values
    from living_island.world.v2.engine.state import Held
    from living_island.world.v2.rules.vocabulary import descriptor

    item = world.state.entities["inst_a"]
    item.place = Held(A)
    hardness = world.pack.source.vocabulary.properties["hardness"]
    assert true_values(world.pack, item)["hardness"] == 4
    started = world.step([combine(world)])
    assert not started.actions
    action = world.state.active_actions[A]
    assert action.rule_id == "rule_d"
    assert action.start_items[0].material_id == "mat_a"
    looks = {row.property_id: row.value for row in action.start_items[0].descriptors}
    assert looks["hardness"] == descriptor(hardness, 1)
    strength = world.pack.source.vocabulary.properties["strength"]
    assert looks["strength"] == descriptor(strength, 2)
    world.step()
    result = world.step()
    assert result.actions[0].settlement.kind == "applied"
    created = event(result, "entity_created")
    output = world.state.entities[created.payload["entity_id"]]
    assert output.material_id == "mat_a"
    assert not output.properties and not output.apparent and not output.tells
    assert output.owner_id is None


@pytest.mark.parametrize(
    ("quantity", "extra", "matched"), [(1, False, True), (2, False, False), (1, True, False)]
)
def test_rr09_rr10_exact_arity_quantity_and_permutation(
    world: World, quantity, extra, matched
) -> None:
    from living_island.world.v2.engine.state import Held, Lineage

    state = world.state
    for key in ("inst_a", "inst_d"):
        state.entities[key].place = Held(A)
    item = state.entities["inst_a"]
    if extra:
        item.quantity = 1
        item.lineage = (Lineage("inst_a", 0, 1, 1),)
        state.entities["extra"] = replace(item, entity_id="extra")
    rule = proposal(
        "permutation",
        "combine",
        inputs=[
            {"slot": "broad", "where": {"has_component": "portable"}, "qty": 1},
            slot("narrow", "arch_a"),
        ],
    )
    entries = [
        {"item": named("inst_a"), "quantity": quantity},
        {"item": named("inst_d"), "quantity": 1},
    ]
    if extra:
        entries.append(input_a())
    result = world.step([turn(world, verb="combine", inputs=entries)], rule_additions=[rule])
    assert result.actions[0].settlement.kind == ("applied" if matched else "unmatched")
    groups = event(result, "act_items").payload["slots"]
    if matched:
        assert [row["slot"] for row in groups] == ["broad", "narrow"]
        assert [row["parts"][0]["entity_id"] for row in groups] == ["inst_d", "inst_a"]


def test_rr35_target_alias_and_distinct_identical_items(world: World) -> None:
    from living_island.world.v2.engine.state import Held

    state = world.state
    item = state.entities["inst_d"]
    item.place = Held(A)
    state.entities["same"] = replace(item, entity_id="same")
    rule = proposal(
        "distinct_items",
        "strike",
        target={"where": {"archetype": "arch_d"}},
        instruments=[slot("tool", "arch_d")],
    )
    bad = turn(world, verb="strike", target=target("inst_d"), instruments=[named("inst_d")])
    assert world.step([bad], rule_additions=[rule]).actions[0].settlement.kind == "unmatched"
    good = turn(world, verb="strike", target=target("same"), instruments=[named("inst_d")])
    assert world.step([good]).actions[0].settlement.kind == "applied"


@pytest.mark.parametrize(
    ("variant", "expected"), [("same", "applied"), ("different", "unmatched"), ("state", "unmet")]
)
def test_rr35_multipart_homogeneity_and_every_part_state(
    world: World, variant: str, expected: str
) -> None:
    from living_island.world.v2.engine.state import Held, Lineage

    first = world.state.entities["inst_a"]
    first.place = Held(A)
    if variant != "state":
        first.quantity = 1
        first.lineage = (Lineage("inst_a", 0, 1, 1),)
    second = replace(
        first,
        entity_id="second",
        quantity=1,
        material_id=None if variant == "different" else first.material_id,
        lineage=(Lineage("second", 0, 1, 2),),
    )
    world.state.entities[second.entity_id] = second
    quantity = 3 if variant == "state" else 2
    conditions = (
        []
        if variant != "state"
        else [
            {
                "id": "every_part",
                "kind": "state",
                "of": "slot:batch",
                "field": "quantity",
                "op": ">=",
                "value": 2,
            }
        ]
    )
    rule = proposal(
        "multipart",
        "combine",
        inputs=[slot("batch", "arch_a", quantity)],
        conditions=conditions,
        outputs=[
            {"archetype_from": "batch", "material_from": "batch", "quantity": 1, "at": "actor"}
        ],
    )
    result = world.step([combine(world, quantity)], rule_additions=[rule]).actions[0]
    assert result.settlement.kind == expected
    if variant == "state":
        assert result.settlement.failed_check == "every_part"


@pytest.mark.parametrize(
    ("strength", "mixed", "expected"),
    [
        (4, False, ["leaves_dent", "nothing_happens"]),
        (1, False, ["nothing_happens"]),
        (4, True, ["nothing_happens"]),
    ],
)
def test_rr12_unmatched_compares_true_uniform_values(
    world: World, strength, mixed, expected
) -> None:
    from living_island.world.v2.engine.state import Held, Lineage

    state = world.state
    item = state.entities["inst_a"]
    item.place = Held(A)
    item.quantity = 1
    item.properties["strength"] = strength
    item.apparent["strength"] = 1
    item.lineage = (Lineage("inst_a", 0, 1, 1),)
    if mixed:
        state.entities["second"] = replace(item, entity_id="second", properties={"strength": 2})
    source = world.pack.source
    data = deepcopy(source.data)
    data["unmatched"]["combine"] = {
        "entries": [
            {
                "when": {"compare": ["input.strength", ">", 2]},
                "phenomena": ["nothing_happens", "leaves_dent"],
            },
            {"when": {"compare": [3, "<=", "input.strength"]}, "phenomena": ["leaves_dent"]},
            {"when": {"compare": ["target.hardness", "<", 2]}, "phenomena": ["leaves_dent"]},
        ],
        "default": ["nothing_happens"],
    }
    world.pack = replace(world.pack, source=replace(source, rules={}, data=data))
    boundary = world.step([combine(world, 2 if mixed else 1)])
    assert boundary.actions[0].settlement.kind == "unmatched"
    assert boundary.actions[0].visible_feedback.phenomena == expected


@pytest.mark.parametrize(
    ("kind", "true_fields", "false_fields"),
    [
        ("awareness", {"value": "awake"}, {"value": "asleep"}),
        (
            "need",
            {"need": "stamina", "op": "<", "value": "max"},
            {"need": "stamina", "op": "==", "value": "min"},
        ),
        ("free_slots", {"op": "==", "value": 4}, {"op": "<", "value": 4}),
        (
            "terrain_near",
            {"terrain": "grass", "distance": {"min": 1, "max": 1}},
            {"terrain": "grass", "distance": {"min": 1, "max": 1}},
        ),
        (
            "entity_near",
            {"where": {"has_component": "shelter"}, "distance": {"min": 0, "max": 2}},
            {"where": {"has_component": "shelter"}, "distance": {"min": 2, "max": 2}},
        ),
        ("terrain_at", {"of": "actor", "terrain": "grass"}, {"of": "actor", "terrain": "cave"}),
        (
            "state",
            {"of": "slot:part", "field": "quantity", "op": ">=", "value": 2},
            {"of": "slot:part", "field": "fuel.ticks_left", "op": "==", "value": 0},
        ),
        ("time_phase", {"value": "day"}, {"value": "night"}),
    ],
)
def test_rr14_rr15_live_and_saved_conditions_agree(
    world: World, kind, true_fields, false_fields
) -> None:
    from pydantic import TypeAdapter

    from living_island.world.v2.engine.conditions import first_failure
    from living_island.world.v2.engine.descriptors import AttemptDescriptor
    from living_island.world.v2.engine.match import match_attempt, slot_signatures
    from living_island.world.v2.engine.state import Held, OnTile
    from living_island.world.v2.protocol import Coord
    from living_island.world.v2.rules import validate_proposal

    world.state.entities["inst_a"].place = Held(A)
    world.state.entities["inst_f"].place = OnTile(Coord(x=2, y=1))
    source = world.pack.source
    world.pack = replace(world.pack, source=replace(source, rules={}))
    for label, fields in (("passing", true_fields), ("failing", false_fields)):
        variant = deepcopy(world)
        if kind == "terrain_near" and label == "failing":
            rows = [list(row) for row in variant.state.static_map.rows]
            rows[1][2] = rows[2][1] = "beach"
            variant.state.static_map = replace(
                variant.state.static_map, rows=tuple(map(tuple, rows))
            )
        rule_data = proposal(
            "backtest",
            "combine",
            inputs=[slot("part", "arch_a", 2)],
            conditions=[{"id": "the_check", "kind": kind, **fields}],
        )
        attempted = deepcopy(variant)
        result = attempted.step([combine(attempted, 2)])
        data = event(result, "attempt_unmatched").payload["descriptor"]
        descriptor = TypeAdapter(AttemptDescriptor).validate_python(data)
        rule = validate_proposal(variant.pack.source, rule_data)
        assigned = match_attempt(rule, descriptor)
        assert assigned is not None
        failure = first_failure(
            rule, descriptor, slot_signatures(descriptor, rule, assigned), variant.pack.needs
        )
        live = variant.step([combine(variant, 2)], rule_additions=[rule_data]).actions[0]
        assert failure == live.settlement.failed_check
        assert live.settlement.kind == ("applied" if label == "passing" else "unmet")


@pytest.mark.parametrize("failed_check", [None, "state"])
def test_en27_en33_witness_samples_at_each_benefit(world: World, failed_check: str | None) -> None:
    from living_island.world.v2.engine.state import OnTile
    from living_island.world.v2.protocol import Coord

    state = world.state
    near = state.entities["inst_f"]
    near.place = OnTile(Coord(x=2, y=1))
    state.entities["farther"] = replace(near, entity_id="farther", place=OnTile(Coord(x=2, y=2)))
    rule_data = proposal(
        "benefit",
        "rest",
        3,
        conditions=[
            {
                "id": "shelter",
                "kind": "entity_near",
                "where": {"has_component": "shelter"},
                "distance": {"min": 0, "max": 2},
            }
        ],
        effects=[
            {"op": "need", "need": "stamina", "delta": 1, "timing": "per_tick"},
            {"op": "need", "need": "stamina", "delta": 1, "timing": "completion"},
        ],
    )
    source = world.pack.source
    world.pack = replace(world.pack, source=replace(source, rules={}))
    first = world.step([turn(world, verb="rest")], rule_additions=[rule_data])
    assert event(first, "condition_witness").payload["entity_id"] == "inst_f"
    del world.state.entities["inst_f"]
    second = world.step()
    assert event(second, "condition_witness").payload["entity_id"] == "farther"
    if failed_check:
        del world.state.entities["farther"]
    last = world.step()
    witnesses = [row.payload for row in last.events if row.type == "condition_witness"]
    if failed_check:
        assert last.actions[0].settlement.failed_check == "shelter"
        assert [(row["timing"], row["entity_id"]) for row in witnesses] == [("per_tick", None)]
        assert world.state.needs[A]["stamina"] == 6003
    else:
        assert [(row["timing"], row["entity_id"]) for row in witnesses] == [
            ("per_tick", "farther"),
            ("completion", "farther"),
        ]
        assert world.state.needs[A]["stamina"] == 6004


def test_wap01_all_settlements_show_same_items(world: World) -> None:
    from living_island.world.v2.engine.state import Held

    state = world.state
    state.entities["inst_a"].place = Held(A)
    source = world.pack.source
    world.pack = replace(world.pack, source=replace(source, rules={}))
    results = []
    for outcome in ("applied", "chance_failed", "unmet", "unmatched"):
        variant = deepcopy(world)
        changes = []
        if outcome != "unmatched":
            changes = [
                proposal(
                    "same_action",
                    "combine",
                    inputs=[slot("part", "arch_a")],
                    success_per_mille=0 if outcome == "chance_failed" else 1000,
                    conditions=[{"id": "fails", "kind": "awareness", "value": "asleep"}]
                    if outcome == "unmet"
                    else [],
                    phenomena={
                        "success": ["fits_together"],
                        "chance_failed": ["slips"],
                        "unmet_by_check": {"fails": ["falls_apart"]},
                    }
                    if outcome == "unmet"
                    else {"success": ["fits_together"], "chance_failed": ["slips"]},
                )
            ]
        result = variant.step([combine(variant)], rule_additions=changes).actions[0]
        assert result.settlement.kind == outcome
        results.append(result.visible_feedback.model_dump(exclude={"phenomena"}))
    assert all(row == results[0] for row in results)
