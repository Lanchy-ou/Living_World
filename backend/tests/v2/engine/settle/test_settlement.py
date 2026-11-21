"""Exercise act selection, physical reservations and timing through World.step."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.world.v2.engine import World

A, B = "res_a", "res_b"


def turn(world: World, actor: str = A, *, action: str = "act", **fields) -> dict:
    identity = f"{actor}:t{world.state.turn_ordinals[actor]:06d}"
    intent = {
        "intent_id": identity + ":a",
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
    }
    return {
        "schema_version": "wap/0.1",
        "actor_id": actor,
        "turn_id": identity,
        "observed_tick": world.state.tick,
        "action": {"kind": "intent", "intent": intent},
        "utterance": None,
    }


def named(id_: str) -> dict:
    return {"kind": "item", "id": id_}


def target(id_: str) -> dict:
    return {"kind": "entity", "id": id_}


def input_a(quantity: int = 1) -> dict:
    return {"item": {"kind": "held", "archetype_id": "arch_a"}, "quantity": quantity}


def proposal(id_: str, verb: str, work_ticks: int = 1, **data) -> dict:
    return {
        "id": id_,
        "trigger": f"verb:{verb}",
        "work_ticks": work_ticks,
        "provenance": {
            "kind": "proposed",
            "llm_call_id": "call_a",
            "approved_by": A,
            "approved_at_tick": 0,
        },
        **data,
    }


def slot(name: str, archetype: str, quantity: int = 1) -> dict:
    return {"slot": name, "where": {"archetype": archetype}, "qty": quantity}


def combine(world: World, quantity: int = 1) -> dict:
    return turn(world, verb="combine", inputs=[input_a(quantity)])


def event(result, kind: str):
    return next(row for row in result.events if row.type == kind)


def until_result(world: World, result):
    while not result.actions:
        result = world.step()
    return result


def test_en05_last_stock_obeys_action_shuffle(world: World) -> None:
    from living_island.world.v2.engine.ids import shuffle
    from living_island.world.v2.protocol import Coord

    world.state.residents[A].position = Coord(x=2, y=2)
    expected = [A, B]
    rng = shuffle(expected, world.state.resolution_rng_state_uint32)
    copy = deepcopy(world)
    boundary = world.step(
        [turn(world, actor, verb="gather", target=target("inst_b")) for actor in (B, A)]
    )
    assert (
        copy.step([turn(copy, actor, verb="gather", target=target("inst_b")) for actor in (A, B)])
        == boundary
    )
    assert copy.state == world.state
    assert world.state.resolution_rng_state_uint32 == rng
    assert [result.actor_id for result in boundary.actions] == expected
    first, second = boundary.actions
    assert first.settlement.kind == "applied"
    assert second.settlement.kind == "unmet"
    assert second.settlement.at == "completion"
    assert second.settlement.failed_check == "check_a"
    assert world.state.entities["inst_b"].components["store"]["count"] == 4
    refill = next(
        row
        for row in boundary.events
        if row.type == "store_count_changed" and row.payload["rule_id"] == "rule_f"
    )
    assert (refill.payload["before"], refill.payload["after"]) == (0, 4)
    settlements = [row for row in boundary.events if row.type == "act_settled"]
    assert [row.intent_id for row in settlements] == [first.intent_id, second.intent_id]
    assert all(row.seq_in_tick < refill.seq_in_tick for row in settlements)
    act_items = [row for row in boundary.events if row.type == "act_items"]
    for entry in act_items:
        assert entry.payload["slots"] == [
            {
                "slot": "target",
                "role": "target",
                "parts": [
                    {
                        "entity_id": "inst_b",
                        "physical_id": "inst_b",
                        "archetype_id": "arch_b",
                        "material_id": None,
                        "quantity": 1,
                    }
                ],
            }
        ]


@pytest.mark.parametrize(
    ("target_id", "verb", "expected"),
    [
        ("missing", "strike", "INVALID_TARGET"),
        ("inst_c", "gather", "INVALID_TARGET"),
        ("inst_c", "fill", "NO_ITEM"),
        ("inst_b", "gather", "OUT_OF_REACH"),
    ],
)
def test_wap21_generic_failure_precedes_matching(
    world: World, target_id: str, verb: str, expected: str
) -> None:
    from living_island.world.v2.engine.state import Exposure
    from living_island.world.v2.protocol import Coord

    world.state.exposure_receipts_by_resident[A].entities["missing"] = Exposure(
        "missing", Coord(x=1, y=1)
    )
    result = world.step([turn(world, verb=verb, target=target(target_id))]).actions[0]
    assert result.tick_finished == world.pack.timing.invalid_attempt_ticks
    assert result.failure_code == expected
    assert result.settlement is None


@pytest.mark.parametrize("change", ["gone", "moved", "wrong_predicate", "not_held"])
def test_en05_completion_rechecks_binding(world: World, change: str) -> None:
    from living_island.world.v2.engine.state import Held, OnTile
    from living_island.world.v2.protocol import Coord

    if change == "not_held":
        world.state.entities["inst_c"].place = Held(A)
        verb, key = "fill", "inst_c"
    else:
        world.state.residents[A].position = Coord(x=2, y=2)
        verb, key = "gather", "inst_b"
    conditions = [{"id": "specific", "kind": "awareness", "value": "awake"}]
    if change == "wrong_predicate":
        world.state.entities[key].properties["hardness"] = 4
    rule = proposal(
        "long_attempt",
        verb,
        2,
        target={"where": {"archetype": "arch_c" if verb == "fill" else "arch_b", "hardness_min": 4}}
        if change == "wrong_predicate"
        else {"where": {"archetype": "arch_c" if verb == "fill" else "arch_b"}},
        conditions=conditions,
    )
    assert not world.step(
        [turn(world, verb=verb, target=target(key))], rule_additions=[rule]
    ).actions
    if change == "gone":
        world.state.entities.pop(key)
    elif change == "wrong_predicate":
        world.state.entities[key].properties["hardness"] = 1
    else:
        world.state.entities[key].place = OnTile(Coord(x=1 if change == "not_held" else 5, y=2))
        if change == "not_held":
            world.state.entities[key].place = OnTile(world.state.residents[A].position)
    result = world.step().actions[0]
    assert result.settlement.rule_id == "long_attempt"
    assert result.settlement.at == "completion"
    assert result.settlement.failed_check == "target"
    assert result.tick_finished == 2


@pytest.mark.parametrize("change", ["gone", "other_holder", "mixed", "predicate"])
def test_rr28_rr35_completion_never_reassigns_a_slot(world: World, change: str) -> None:
    from living_island.world.v2.engine.state import Held, Lineage

    first = world.state.entities["inst_a"]
    first.place = Held(A)
    first.quantity = 1
    first.lineage = (Lineage("inst_a", 0, 1, 1),)
    second = replace(first, entity_id="second", properties=dict(first.properties))
    world.state.entities[second.entity_id] = second
    rule = proposal(
        "two_units",
        "combine",
        2,
        inputs=[{"slot": "stuff", "where": {"archetype": "arch_a", "hardness_min": 3}, "qty": 2}],
        outputs=[
            {"archetype_from": "stuff", "material_from": "stuff", "quantity": 1, "at": "actor"}
        ],
    )
    assert not world.step([combine(world, 2)], rule_additions=[rule]).actions
    if change == "gone":
        world.state.entities.pop("second")
    elif change == "other_holder":
        world.state.entities["second"].place = Held(B)
    elif change == "mixed":
        world.state.entities["second"].properties["hardness"] = 4
        world.state.entities["second"].material_id = None
    else:
        world.state.entities["second"].properties["hardness"] = 1
    result = world.step().actions[0]
    assert result.settlement.failed_check == "stuff"
    assert result.tick_finished == 2
    assert result.visible_feedback.items_used[-1].entity_id == "second"


@pytest.mark.parametrize(
    ("enabled", "stamina", "rule_id", "kind", "check"),
    [
        ("both", 9999, "specific_a", "applied", None),
        ("both", 10000, "fallback", "applied", None),
        ("specific", 10000, "specific_a", "unmet", "energy"),
        ("neither", 10000, None, "unmatched", None),
    ],
)
def test_en03_en04_selection_and_fixed_outcomes(
    world: World, enabled, stamina, rule_id, kind, check
) -> None:
    base = world.pack.source
    world.pack = replace(world.pack, source=replace(base, rules={}))
    changes = []
    if enabled in ("both", "specific"):
        conditions = [
            {"id": "energy", "kind": "need", "need": "stamina", "op": "<", "value": "max"},
            {"id": "second", "kind": "need", "need": "stamina", "op": "<", "value": 10000},
        ]
        changes.extend(
            proposal(name, "rest", 2, conditions=conditions)
            for name in ("specific_z", "specific_a")
        )
    if enabled == "both":
        changes.append(proposal("fallback", "rest"))
    world.state.needs[A]["stamina"] = stamina
    started = world.step([turn(world, verb="rest")], rule_additions=changes)
    finished = until_result(world, started)
    result = finished.actions[0]
    assert (result.settlement.rule_id, result.settlement.kind, result.settlement.failed_check) == (
        rule_id,
        kind,
        check,
    )
    assert result.tick_finished == (2 if rule_id == "specific_a" and check is None else 1)
    if kind == "unmatched":
        settled = event(finished, "act_settled")
        unmatched = event(finished, "attempt_unmatched")
        assert unmatched.seq_in_tick == settled.seq_in_tick + 1
        assert unmatched.event_id in result.event_ids
        assert unmatched.payload["descriptor"]["context"]["needs"] == [
            {"need_id": "stamina", "value": stamina}
        ]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("lose", "stopped"), ("partial", "stopped"), ("exhausted", "stopped"), ("success", "settled")],
)
def test_en35_split_release_and_progress(world: World, mode: str, expected: str) -> None:
    from living_island.world.v2.engine.settle import progress_word
    from living_island.world.v2.engine.state import Held, Lineage

    item = world.state.entities["inst_a"]
    item.place = Held(A)
    item.lineage = (Lineage("older", 0, 1, 1), Lineage("newer", 1, 1, 2))
    rule = proposal(
        "use_item",
        "combine",
        6,
        inputs=[slot("piece", "arch_a")],
        on_interrupt={
            "partial": [
                {"archetype_from": "piece", "material_from": "piece", "quantity": 1, "at": "actor"}
            ]
        }
        if mode == "partial"
        else "lose",
        exhaustion_stops=mode == "exhausted",
        effects=[{"op": "need", "need": "stamina", "delta": 1, "timing": "per_tick"}],
    )
    base = world.pack.source
    world.pack = replace(world.pack, source=replace(base, rules={}))
    original = deepcopy(world)
    started = world.step([combine(world)], rule_additions=[rule])
    assert original.step([combine(original)], rule_additions=[rule]) == started
    split = event(started, "stack_split")
    reserved_id = split.payload["new_id"]
    assert split.payload == {
        "from_id": "inst_a",
        "new_id": reserved_id,
        "quantity": 1,
        "cause": "reservation",
    }
    actor = world.state.active_actions[A]
    assert progress_word(actor) == "started"
    assert actor.start_items[0].entity_id == "inst_a"
    assert actor.bindings[0].physical_id == reserved_id
    assert world.state.entities[reserved_id].lineage[0].origin_id == "older"
    assert world.state.entities["inst_a"].lineage[0].origin_id == "newer"
    assert world.state.needs[A]["stamina"] == 6001
    if mode == "exhausted":
        world.state.needs[A]["stamina"] = 0
        end = world.step()
        assert end.actions[0].stop.reason == "EXHAUSTED"
        assert world.state.needs[A]["stamina"] == 0
    elif mode == "success":
        world.step()
        assert progress_word(world.state.active_actions[A]) == "halfway"
        world.step()
        world.step()
        assert progress_word(world.state.active_actions[A]) == "nearly_done"
        end = until_result(world, world.step())
        assert world.state.needs[A]["stamina"] == 6006
    else:
        end = world.step([turn(world, action="wait")])
        assert world.state.needs[A]["stamina"] == 6001
    assert end.actions[0].outcome == expected
    assert end.actions[0].visible_feedback.items_used[0].entity_id == "inst_a"
    if mode == "partial":
        created = event(end, "entity_created")
        assert (
            created.payload["recreated_from"]
            == created.payload["made_from"]
            == [{"physical_id": reserved_id, "quantity": 1}]
        )
        assert event(end, "entity_consumed").payload["entity_id"] == reserved_id
    elif mode == "success":
        assert event(end, "entity_consumed").payload["entity_id"] == reserved_id
    else:
        assert event(end, "stack_merged").payload["quantity"] == 1
        assert len([item for item in world.state.entities.values() if item.place == Held(A)]) == 1


def test_fixed_unmatched_preserves_start_descriptor_across_ticks(world: World) -> None:
    from living_island.world.v2.engine.state import Held, state_snapshot_hash

    item = world.state.entities["inst_a"]
    item.place = Held(A)
    attempts = {**world.pack.timing.attempts, "combine": 2}
    world.pack = replace(world.pack, timing=replace(world.pack.timing, attempts=attempts))
    start = world.step([combine(world, 2)])
    # Two units do not match rule_d's one-unit input.
    assert not start.actions
    assert state_snapshot_hash(world.state) == state_snapshot_hash(deepcopy(world.state))
    world.state.needs[A]["stamina"] = 5
    finished = world.step()
    assert finished.actions[0].tick_finished == 2
    descriptor = event(finished, "attempt_unmatched").payload["descriptor"]
    assert descriptor["context"]["needs"] == [{"need_id": "stamina", "value": 6000}]


def test_progress_returns_opening_values_for_phase_five(world: World) -> None:
    rule = proposal(
        "progress_need",
        "rest",
        2,
        effects=[
            {"op": "need", "need": "stamina", "delta": 1, "timing": "per_tick"},
            {"op": "need", "need": "stamina", "delta": 2, "timing": "per_tick"},
        ],
    )
    first = world.step([turn(world, verb="rest")], rule_additions=[rule])
    second = world.step()
    for result, opening in ((first, 6000), (second, 6003)):
        changed = event(result, "needs_changed")
        assert changed.payload["causes"] == ["physiology", "progress_need"]
        assert changed.payload["changes"] == [
            {"need_id": "stamina", "before": opening, "after": opening + 3}
        ]
