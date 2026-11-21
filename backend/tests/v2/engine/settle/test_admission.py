"""Exercise complete selected branches, including refusal and replay lineage."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from typing import TYPE_CHECKING

import pytest
from test_settlement import A, B, combine, event, input_a, named, proposal, slot, target, turn

if TYPE_CHECKING:
    from pathlib import Path

    from living_island.world.v2.engine import World, WorldSetup
    from living_island.world.v2.rules import Pack


@pytest.mark.parametrize(
    ("seed", "tick", "rule", "subject", "roll"),
    [
        (20261108, 10, "make_stone_axe", "ella:t000003:a", 325),
        (20261108, 11, "make_stone_axe", "ella:t000003:a", 493),
        (20261108, 10, "make_stone_axe", "mia:t000003:a", 225),
        (1, 1, "a", "b", 418),
        (1, 1, "a", "b:3158505", 507),
    ],
)
def test_en06_chance_vectors(seed, tick, rule, subject, roll) -> None:
    from living_island.world.v2.engine.chance import chance_roll

    assert chance_roll(seed, tick, rule, subject) == roll
    if roll == 325:
        encoded = (
            b'{"k":0,"rule_id":"make_stone_axe","seed":20261108,'
            b'"stream":"chance","subject":"ella:t000003:a","tick":10}'
        )
        assert int.from_bytes(sha256(encoded + b"\n").digest()[:4], "big") == 976841585


@pytest.mark.parametrize(
    ("increment", "spend", "kind", "remaining", "wear"),
    [
        (1, False, "applied", 0, 0),
        (0, False, "chance_failed", 1, 1),
        (0, True, "chance_failed", 0, 1),
    ],
)
def test_en06_en07_chance_branches(world: World, increment, spend, kind, remaining, wear) -> None:
    from living_island.world.v2.engine.chance import chance_roll
    from living_island.world.v2.engine.state import Held, Lineage

    state = world.state
    initial = state.resolution_rng_state_uint32
    for name in ("inst_a", "inst_d"):
        state.entities[name].place = Held(A)
    state.entities["inst_a"].quantity = 1
    state.entities["inst_a"].lineage = (Lineage("inst_a", 0, 1, 1),)
    intent = turn(world, verb="combine", instruments=[named("inst_d")], inputs=[input_a()])
    identity = intent["action"]["intent"]["intent_id"]
    rule = proposal(
        "test_chance",
        "combine",
        instruments=[slot("tool", "arch_d")],
        inputs=[slot("piece", "arch_a")],
        success_per_mille=chance_roll(state.seed, 1, "test_chance", identity) + increment,
        on_chance_failed="consume_inputs" if spend else "keep_inputs",
        chance_failed_effects=[
            {"op": "set_state", "of": "slot:tool", "field": "durability.wear", "add": 1}
        ],
    )
    parallel = deepcopy(world)
    result = world.step([intent], rule_additions=[rule])
    other = parallel.step([intent, turn(parallel, B, action="wait")], rule_additions=[rule])
    assert result.actions[0].settlement.kind == kind
    assert (
        next(row for row in other.actions if row.actor_id == A).settlement
        == result.actions[0].settlement
    )
    assert world.state.resolution_rng_state_uint32 == initial
    assert parallel.state.resolution_rng_state_uint32 != initial
    assert ("inst_a" in world.state.entities) == bool(remaining)
    assert world.state.entities["inst_d"].components["durability"]["wear"] == wear


@pytest.mark.parametrize(("cap", "count"), [(2, 1), (1, 0), (0, 0)])
def test_rr26_captured_fit(world: World, cap: int, count: int) -> None:
    from living_island.world.v2.engine.state import Held, Inside, Lineage

    state = world.state
    container = state.entities["inst_c"]
    container.place = Held(A)
    container.components["container"]["capacity"] = cap
    if count:
        item = state.entities["inst_a"]
        item.place = Inside(container.entity_id)
        item.quantity = count
        item.lineage = (Lineage("inst_a", 0, count, 1),)
    boundary = world.step([turn(world, verb="fill", target=target("inst_c"))])
    assert boundary.actions[0].settlement.kind == "applied"
    assert (
        sum(
            item.quantity
            for item in world.state.entities.values()
            if item.place == Inside("inst_c")
        )
        == cap
    )
    if cap > count:
        assert event(boundary, "entity_created").payload["quantity"] == cap - count
    else:
        assert not any(row.type == "entity_created" for row in boundary.events)


def test_en28_competing_fits_discard_every_effect(world: World) -> None:
    from living_island.world.v2.engine.state import Held, Lineage

    state = world.state
    container = state.entities["inst_c"]
    container.place = Held(A)
    container.components["container"]["capacity"] = 1
    item = state.entities["inst_a"]
    item.place = Held(A)
    item.quantity = 1
    item.lineage = (Lineage("inst_a", 0, 1, 1),)
    fit = {
        "archetype": "arch_a",
        "quantity": {"upto": 1, "of": "fit:target.contents"},
        "at": "target.contents",
        "source": "src_fit",
    }
    source = world.pack.source
    data = deepcopy(source.data)
    data["source"]["src_fit"] = {"id": "src_fit", "archetype": "arch_a", "max_per_application": 2}
    world.pack = replace(world.pack, source=replace(source, data=data))
    rule = proposal(
        "two_fits",
        "fill",
        target={"where": {"archetype": "arch_c"}},
        inputs=[slot("spent", "arch_a")],
        conservation="source",
        outputs=[fit, deepcopy(fit)],
        effects=[{"op": "need", "need": "stamina", "delta": 1, "timing": "completion"}],
    )
    before = deepcopy(state)
    boundary = world.step(
        [turn(world, verb="fill", target=target("inst_c"), inputs=[input_a()])],
        rule_additions=[rule],
    )
    assert boundary.actions[0].settlement.failed_check == "world_limit"
    assert world.state.entities == before.entities
    assert world.state.needs == before.needs
    assert world.state.entity_counter == before.entity_counter
    assert [row.type for row in boundary.events] == [
        "rule_added",
        "action_started",
        "act_items",
        "act_settled",
    ]


def test_en28_dense_tile_removal_then_receiving_refusal(world: World) -> None:
    from living_island.world.v2.engine.limits import tile_loads
    from living_island.world.v2.engine.state import Held, OnTile
    from living_island.world.v2.protocol import Coord

    state = world.state
    point = state.residents[A].position
    ground = OnTile(point)
    world.pack = replace(
        world.pack,
        limits=replace(world.pack.limits, max_entity_units_world=64, max_entities_per_tile=16),
    )
    tool = state.entities["inst_d"]
    item = state.entities["inst_a"]
    item.place = ground
    item.quantity = 1
    item.lineage = tuple(replace(part, quantity=1) for part in item.lineage)
    for index in range(15):
        key = f"tile_{index:02}"
        state.entities[key] = replace(tool, entity_id=key, place=ground)
    tool.place = Held(A)
    state.visible_entities_by_resident[A].add("inst_d")
    drop = turn(
        world,
        action="drop",
        target={"kind": "tile", "position": point.model_dump()},
        params={"item": named("inst_d"), "quantity": 1},
    )
    assert world.step([drop]).actions[0].outcome == "success"
    assert tile_loads(world.state)[point] == 17
    remove = proposal(
        "remove_unit",
        "strike",
        target={"where": {"archetype": "arch_a"}},
        effects=[{"op": "consume", "of": "target"}],
    )
    result = world.step(
        [turn(world, verb="strike", target=target("inst_a"))], rule_additions=[remove]
    )
    assert result.actions[0].settlement.kind == "applied"
    assert tile_loads(world.state)[point] == 16
    rule = proposal(
        "put_back",
        "build",
        target={"terrain": "grass"},
        conservation="source",
        outputs=[{"archetype": "arch_a", "quantity": 1, "at": "target.tile", "source": "src_a"}],
    )
    before = deepcopy(world.state.entity_counter)
    result = world.step(
        [
            turn(
                world,
                verb="build",
                target={"kind": "tile", "position": Coord(x=1, y=1).model_dump()},
            )
        ],
        rule_additions=[rule],
    )
    assert result.actions[0].settlement.failed_check == "world_limit"
    assert tile_loads(world.state)[point] == 16
    assert world.state.entity_counter == before


@pytest.mark.parametrize("fail", [False, True])
def test_rr37_chance_branch_selected_before_spill_admission(world: World, fail: bool) -> None:
    from living_island.world.v2.engine.state import Held, Inside, Lineage, OnTile
    from living_island.world.v2.protocol import Coord

    state = world.state
    position = Coord(x=1, y=1)
    state.entities["inst_c"].place = OnTile(position)
    state.entities["inst_d"].place = OnTile(position)
    item = state.entities["inst_a"]
    item.quantity = 1
    item.lineage = (Lineage("inst_a", 0, 1, 1),)
    item.place = Held(A)
    content = replace(item, entity_id="content", place=Inside("inst_c"), properties={"hardness": 4})
    state.entities[content.entity_id] = content
    # The tile is already dense because a kernel drop may exceed the rule limit.
    state.entities["inst_f"].place = OnTile(position)
    rule = proposal(
        "spill",
        "strike",
        target={"where": {"archetype": "arch_c"}},
        inputs=[slot("spent", "arch_a")],
        effects=[{"op": "consume", "of": "target"}],
        success_per_mille=0 if fail else 1000,
        on_chance_failed="consume_inputs",
    )
    result = world.step(
        [turn(world, verb="strike", target=target("inst_c"), inputs=[input_a()])],
        rule_additions=[rule],
    ).actions[0]
    assert result.settlement.kind == ("chance_failed" if fail else "unmet")
    assert result.settlement.failed_check == (None if fail else "world_limit")
    assert ("inst_a" in world.state.entities) != fail
    assert world.state.entities["content"].place == Inside("inst_c")
    assert "inst_c" in world.state.entities


@pytest.mark.parametrize("refusal", ["dead", "lost", "limit", "admit"])
def test_partial_falls_back_to_lose(world: World, refusal: str) -> None:
    from living_island.world.v2.engine.events import EventWriter
    from living_island.world.v2.engine.settle import interrupt
    from living_island.world.v2.engine.state import Held, Lineage, OnTile
    from living_island.world.v2.engine.tick import TickContext

    item = world.state.entities["inst_a"]
    item.place = Held(A)
    item.quantity = 1
    item.lineage = (Lineage("inst_a", 0, 1, 1),)
    if refusal == "limit":
        world.state.entities["inst_d"].place = OnTile(world.state.residents[A].position)
        world.state.entities["inst_f"].place = OnTile(world.state.residents[A].position)
    rule = proposal(
        "mineral_return",
        "combine",
        4,
        inputs=[slot("mineral", "arch_a")],
        conditions=[{"id": "meets", "kind": "awareness", "value": "awake"}],
        on_interrupt={
            "partial": [
                {
                    "archetype_from": "mineral",
                    "material_from": "mineral",
                    "quantity": 1,
                    "at": "actor.tile",
                }
            ]
        },
    )
    source = world.pack.source
    world.pack = replace(world.pack, source=replace(source, rules={}))
    world.step([combine(world)], rule_additions=[rule])
    state = world.state
    if refusal == "dead":
        state.residents[A].alive = False
        state.entities["inst_a"].place = OnTile(state.residents[A].position)
    elif refusal == "lost":
        del state.entities["inst_a"]
    before = deepcopy(state)
    writer = EventWriter(state, state.tick)
    interrupt(TickContext(state, world.pack, writer), state.active_actions[A])
    if refusal == "admit":
        assert [row.type for row in writer.events] == ["entity_consumed", "entity_created"]
    else:
        assert not writer.events
        assert state.entities == before.entities
        assert state.entity_counter == before.entity_counter
    assert state.active_actions[A].bindings == ()


def test_extension_pack_changes_settlement_and_refuses_nonconservation(
    pack: Pack, setup: WorldSetup, tmp_path: Path
) -> None:
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.rules import ContentError, load_pack

    extension = tmp_path / "engine_extension"
    extension.mkdir()
    (extension / "pack.toml").write_text(
        f"""
pack_id = "engine_extension"
pack_version = "0.1"
extends = "engine_core"
vocabulary_version = "vocab/0.1"
vocabulary_hash = "{pack.vocabulary.vocabulary_hash}"
""",
        encoding="utf-8",
    )
    path = extension / "rules.toml"
    path.write_text(
        """
[[rule]]
id = "new_rest"
trigger = "verb:rest"
work_ticks = 1
effects = [{ op = "need", need = "stamina", delta = 3, timing = "completion" }]
phenomena = { success = ["nothing_happens"] }
""",
        encoding="utf-8",
    )
    loaded = load_pack(extension, pack.vocabulary)
    world = initialize(
        loaded, setup.model_copy(update={"pack_ids": (*setup.pack_ids, "engine_extension")})
    )
    result = world.step([turn(world, verb="rest")]).actions[0]
    assert result.settlement.rule_id == "new_rest"
    assert result.settlement.kind == "applied"
    assert world.state.needs[A]["stamina"] == 6003
    with path.open("a", encoding="utf-8") as handle:
        handle.write('outputs = [{ archetype = "arch_a", quantity = 1, at = "actor" }]\n')
    with pytest.raises(ContentError, match="CONSERVATION"):
        load_pack(extension, pack.vocabulary)


@pytest.mark.parametrize(
    "failure", ["store_full", "holder_gone", "source_gone", "state_target_gone"]
)
def test_rr37_preflight_checks_live_capacity_and_surviving_references(
    world: World, failure: str
) -> None:
    from living_island.world.v2.engine.state import Held, Inside, Lineage, OnTile

    state = world.state
    point = state.residents[A].position
    state.entities["inst_b"].place = OnTile(point)
    state.entities["inst_c"].place = Held(A)
    state.entities["inst_d"].place = Held(A)
    source_id = (
        "inst_b"
        if failure == "store_full"
        else "inst_d"
        if failure == "state_target_gone"
        else "inst_c"
    )
    rule = proposal(
        "admission",
        "strike",
        target={"where": {"archetype": state.entities[source_id].archetype_id}},
    )
    if failure == "store_full":
        state.entities["inst_b"].components["store"]["count"] = 4
        rule.update(
            conservation="source",
            outputs=[
                {"archetype": "arch_a", "quantity": 1, "at": "target.store", "source": "src_a"}
            ],
        )
    elif failure == "state_target_gone":
        rule["effects"] = [
            {"op": "consume", "of": "target"},
            {"op": "set_state", "of": "target", "field": "durability.wear", "add": 1},
        ]
    else:
        rule["effects"] = [{"op": "consume", "of": "target"}]
        if failure == "holder_gone":
            rule.update(
                conservation="source",
                outputs=[
                    {
                        "archetype": "arch_a",
                        "quantity": 1,
                        "at": "target.contents",
                        "source": "src_a",
                    }
                ],
            )
        else:
            item = state.entities["inst_a"]
            item.place = Inside("inst_c")
            item.quantity = 1
            item.lineage = (Lineage("inst_a", 0, 1, 1),)
            rule["conditions"] = [
                {
                    "id": "stock",
                    "kind": "state",
                    "of": "target",
                    "field": "container.count:arch_a",
                    "op": ">=",
                    "value": 1,
                }
            ]
            rule["effects"].append(
                {
                    "op": "move",
                    "from": "target.contents",
                    "to": "actor",
                    "archetype": "arch_a",
                    "quantity": 1,
                }
            )

    before = deepcopy(state)
    boundary = world.step(
        [turn(world, verb="strike", target=target(source_id))], rule_additions=[rule]
    )
    assert boundary.actions[0].settlement.failed_check == "world_limit"
    assert world.state.entities == before.entities
    assert world.state.entity_counter == before.entity_counter
    assert not any(
        event.type
        in (
            "entity_consumed",
            "entity_created",
            "entity_state_changed",
            "matter_moved",
            "store_count_changed",
        )
        for event in boundary.events
    )


@pytest.mark.parametrize("fits", [True, False])
def test_rr37_move_admission_checks_destination_acceptance(world: World, fits: bool) -> None:
    from living_island.world.v2.engine.state import Held, Inside, Lineage

    state = world.state
    container = state.entities["inst_c"]
    container.place = Held(A)
    existing = replace(deepcopy(container), entity_id="tool")
    state.entities[existing.entity_id] = existing
    if not fits:
        container.components["container"]["accepts"] = {"archetype": "arch_d"}
    item = state.entities["inst_a"]
    item.place = Inside("tool")
    item.quantity = 1
    item.lineage = (Lineage("inst_a", 0, 1, 1),)
    rule = proposal(
        "pour",
        "fill",
        target={"where": {"archetype": "arch_c"}},
        instruments=[slot("donor", "arch_c")],
        conditions=[
            {
                "id": "stock",
                "kind": "state",
                "of": "slot:donor",
                "field": "container.count:arch_a",
                "op": ">=",
                "value": 1,
            }
        ],
        effects=[
            {
                "op": "move",
                "from": "slot:donor.contents",
                "to": "target.contents",
                "archetype": "arch_a",
                "quantity": 1,
            }
        ],
    )
    boundary = world.step(
        [turn(world, verb="fill", target=target("inst_c"), instruments=[named("tool")])],
        rule_additions=[rule],
    )
    assert boundary.actions[0].settlement.failed_check == (None if fits else "world_limit")
    assert world.state.entities["inst_a"].place == Inside("inst_c" if fits else "tool")


@pytest.mark.parametrize("store", [True, False])
def test_rr26_fit_of_a_different_place_can_be_zero(world: World, store: bool) -> None:
    from living_island.world.v2.engine.state import OnTile

    state = world.state
    target_id = "inst_b" if store else "inst_c"
    state.entities[target_id].place = OnTile(state.residents[A].position)
    archetype = state.entities[target_id].archetype_id
    pack = world.pack.source
    data = deepcopy(pack.data)
    data["source"]["src_tool"] = {"id": "src_tool", "archetype": "arch_d", "max_per_application": 4}
    world.pack = replace(world.pack, source=replace(pack, data=data))
    rule = proposal(
        "capture_other_place",
        "strike",
        target={"where": {"archetype": archetype}},
        conservation="source",
        outputs=[
            {
                "archetype": "arch_d",
                "quantity": {"of": "fit:target.store" if store else "fit:target.contents"},
                "at": "actor.tile",
                "source": "src_tool",
            }
        ],
    )
    result = world.step(
        [turn(world, verb="strike", target=target(target_id))], rule_additions=[rule]
    )
    assert result.actions[0].settlement.kind == "applied"
    assert not any(event.type == "entity_created" for event in result.events)


def test_rr27_en33_two_returns_use_disjoint_physical_debits(world: World, monkeypatch) -> None:
    from living_island.world.v2.engine import perception
    from living_island.world.v2.engine.state import Held

    state = world.state
    for entity_id in ("inst_a", "inst_d", "inst_c"):
        state.entities[entity_id].place = Held(A)
    rule = proposal(
        "two_returns",
        "combine",
        inputs=[slot("head", "arch_a"), slot("handle", "arch_d"), slot("binder", "arch_c")],
        outputs=[
            {"archetype_from": key, "material_from": key, "quantity": 1, "at": "actor"}
            for key in ("head", "handle")
        ],
    )
    phases = []
    monkeypatch.setattr(
        perception,
        "build_deliveries",
        lambda ctx: phases.extend(
            action.settle_location for action in ctx.completed_actions.values()
        ),
    )
    intent = turn(
        world,
        verb="combine",
        inputs=[{"item": named(key), "quantity": 1} for key in ("inst_a", "inst_d", "inst_c")],
    )
    result = world.step([intent], rule_additions=[rule])
    assert result.actions[0].settlement.kind == "applied"
    physical_head = event(result, "stack_split").payload["new_id"]
    outputs = [row.payload for row in result.events if row.type == "entity_created"]
    assert [row["recreated_from"] for row in outputs] == [
        [{"physical_id": physical_head, "quantity": 1}],
        [{"physical_id": "inst_d", "quantity": 1}],
    ]
    for row in outputs:
        assert row["made_from"] == [
            {"physical_id": key, "quantity": 1} for key in (physical_head, "inst_d", "inst_c")
        ]
        assert row["material_id"] == "mat_a"
    assert outputs[1]["owner_id"] == A
    assert [item.look.role for item in phases[0].items] == ["output", "output"]


def test_partial_with_disappeared_placement_target_releases(world: World) -> None:
    from living_island.world.v2.engine.state import Held, OnTile

    state = world.state
    state.entities["inst_a"].place = Held(A)
    state.entities["inst_f"].place = OnTile(state.residents[A].position)
    rule = proposal(
        "partial_target_tile",
        "strike",
        3,
        target={"where": {"archetype": "arch_f"}},
        inputs=[slot("piece", "arch_a")],
        on_interrupt={
            "partial": [
                {
                    "archetype_from": "piece",
                    "material_from": "piece",
                    "quantity": 1,
                    "at": "target.tile",
                }
            ]
        },
    )
    intent = turn(world, verb="strike", target=target("inst_f"), inputs=[input_a()])
    assert not world.step([intent], rule_additions=[rule]).actions
    del world.state.entities["inst_f"]
    boundary = world.step([turn(world, action="wait")])
    assert boundary.actions[0].outcome == "stopped"
    assert not any(row.type == "entity_consumed" for row in boundary.events)
    assert event(boundary, "stack_merged").payload["quantity"] == 1


def test_rr26_captures_target_quantity_before_whole_consumption(world: World) -> None:
    from living_island.world.v2.engine.state import OnTile

    item = world.state.entities["inst_a"]
    point = world.state.residents[A].position
    item.place = OnTile(point)
    rule = proposal(
        "reform_stack",
        "strike",
        target={"where": {"archetype": "arch_a"}},
        effects=[{"op": "consume", "of": "target"}],
        outputs=[
            {"archetype": "arch_a", "quantity": {"of": "target.quantity"}, "at": "target.tile"}
        ],
    )
    boundary = world.step(
        [turn(world, verb="strike", target=target("inst_a"))], rule_additions=[rule]
    )
    assert boundary.actions[0].settlement.kind == "applied"
    created = event(boundary, "entity_created")
    assert created.payload["quantity"] == 2
    assert created.payload["made_from"] == [{"physical_id": "inst_a", "quantity": 2}]
    assert "inst_a" not in world.state.entities
    assert world.state.entities[created.payload["entity_id"]].place == OnTile(point)


def test_en27_sourced_store_refill_records_source(world: World) -> None:
    from living_island.world.v2.engine.state import Held, OnTile

    state = world.state
    state.entities["inst_b"].place = OnTile(state.residents[A].position)
    state.entities["inst_d"].place = Held(A)
    boundary = world.step(
        [turn(world, verb="strike", target=target("inst_b"), instruments=[named("inst_d")])]
    )
    assert boundary.actions[0].settlement.kind == "applied"
    refill = event(boundary, "store_count_changed")
    assert refill.payload == {
        "entity_id": "inst_b",
        "archetype_id": "arch_a",
        "before": 1,
        "after": 2,
        "rule_id": "rule_h",
        "source": "src_a",
    }
    assert event(boundary, "entity_state_changed").seq_in_tick < refill.seq_in_tick
    assert not any(row.type == "entity_created" for row in boundary.events)


@pytest.mark.parametrize("amount", [1, 2])
def test_rule_world_cap_preserves_corpse_room_after_merges(world: World, amount: int) -> None:
    from living_island.world.v2.engine.limits import entity_units
    from living_island.world.v2.engine.state import OnTile

    state = world.state
    existing = state.entities["inst_a"]
    existing.place = OnTile(state.residents[A].position)
    # Match the prototype exactly so even a single final stack is checked by units.
    existing.properties.clear()
    existing.apparent.clear()
    existing.tells = ()
    units = entity_units(state)
    maximum = units + len(state.residents) + 1
    world.pack = replace(
        world.pack, limits=replace(world.pack.limits, max_entity_units_world=maximum)
    )
    rule = proposal(
        "sourced_stack",
        "rest",
        conservation="source",
        outputs=[
            {"archetype": "arch_a", "quantity": amount, "at": "actor.tile", "source": "src_a"}
        ],
    )
    before = deepcopy(state)
    result = world.step([turn(world, verb="rest")], rule_additions=[rule])
    if amount == 1:
        assert result.actions[0].settlement.kind == "applied"
        assert event(result, "stack_merged").payload["into_id"] == "inst_a"
        assert world.state.entities["inst_a"].quantity == 3
    else:
        assert result.actions[0].settlement.failed_check == "world_limit"
        assert world.state.entities == before.entities
        assert world.state.entity_counter == before.entity_counter
