"""Timed action effects, failure handling and contention through the engine ports."""

from typing import Any

import pytest
from test_engine_movement import ROWS, tick
from world_builders import tiny_content

from living_island.world.content import WorldContent, build_world_content, map_bytes_from_rows
from living_island.world.facts import ActionFailedPayload
from living_island.world.ports import WorldTickCommit, create_engine
from living_island.world.protocol import ActionIntent, ActionType, Coord
from living_island.world.state import GroundFruitPile, ReceiptEntity, UniqueCanteenState, WorldState


def intent(
    kind: ActionType,
    actor: str = "ella",
    *,
    id: str | None = None,
    target: dict[str, Any] | None = None,
    **params: Any,
) -> ActionIntent:
    return ActionIntent.model_validate(
        {
            "intent_id": id or f"{actor}:{kind}",
            "plan_id": f"{actor}:plan",
            "actor_id": actor,
            "action_type": kind,
            "target": target,
            "parameters": params,
            "reason": None,
        }
    )


def content_with(
    residents: dict[str, tuple[int, int]],
    **sections: dict[str, Any],
) -> WorldContent:
    base = tiny_content(ROWS, residents)
    config = base.config.model_dump()
    for name, values in sections.items():
        config[name].update(values)
    return build_world_content(config, map_bytes_from_rows(ROWS))


def snapshot(content: WorldContent) -> WorldState:
    return create_engine(content, None).initial_commit().snapshot


def failures(commit: WorldTickCommit) -> list[str]:
    return [
        e.payload.failure_code for e in commit.events if isinstance(e.payload, ActionFailedPayload)
    ]


TREE = {"kind": "entity", "id": "fruit_01"}
CANTEEN = {"kind": "entity", "id": "canteen_01"}
RYAN = {"kind": "resident", "id": "ryan"}


def test_last_fruit_resolves_after_full_duration_before_regrowth() -> None:
    content = content_with({"ella": (2, 2), "ryan": (4, 2)}, fruit={"regrow_ticks": 2})
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    first = tick(engine, intent("gather", "ryan", target=TREE), intent("gather", target=TREE))
    assert first.snapshot.fruit_nodes[0].stock == 1
    assert all(r.fruit_count == 0 for r in first.snapshot.residents)
    assert (
        first.snapshot.resolution_rng_state_uint32 == initial.snapshot.resolution_rng_state_uint32
    )
    assert [a.remaining_ticks for a in first.snapshot.active_actions] == [1, 1]
    second = tick(engine)
    assert failures(second) == ["RESOURCE_TAKEN"]
    assert sum(r.fruit_count for r in second.snapshot.residents) == 1
    facts = [(e.type, e.actor_id, e.target_id) for e in second.events]
    gather = next(f for f in facts if f[0] == "fruit_gathered")
    assert facts.index(gather) < facts.index(("fruit_regrew", None, "fruit_01"))
    assert ("stamina_action_cost_applied", gather[1], None) in facts
    assert second.snapshot.fruit_nodes[0].stock == content.config.fruit.regrow_per_cycle


@pytest.mark.parametrize("item", ["fruit", "canteen"])
def test_ground_item_contention_is_atomic(item: str) -> None:
    content = content_with({"ella": (2, 3), "ryan": (3, 4)})
    state = snapshot(content)
    position = Coord(x=3, y=3)
    if item == "fruit":
        state.ground_fruit = [GroundFruitPile(position=position, quantity=1)]
        receipt = ReceiptEntity(
            entity_id="ground_fruit@3,3", entity_type="ground_fruit", position=position
        )
    else:
        state.unique_canteen = UniqueCanteenState(
            id="canteen_01",
            holder_id=None,
            ground_position=position,
            servings=2,
        )
        receipt = ReceiptEntity(entity_id="canteen_01", entity_type="canteen", position=position)
    for group in state.exposure_receipts_by_resident:
        group.entities = sorted(
            [*group.entities, receipt],
            key=lambda e: (e.entity_id, e.position.y, e.position.x),
        )
    target = {"kind": "tile", "position": position}
    settled = tick(
        create_engine(content, state),
        intent("pick_up", "ryan", target=target, item_type=item, quantity=1),
        intent("pick_up", target=target, item_type=item, quantity=1),
    )
    assert failures(settled) == ["ITEM_TAKEN"]
    winner = next(e.actor_id for e in settled.events if e.type == "item_picked_up")
    if item == "fruit":
        assert not settled.snapshot.ground_fruit
        assert sum(r.fruit_count for r in settled.snapshot.residents) == 1
    else:
        assert settled.snapshot.unique_canteen.holder_id == winner
        assert settled.snapshot.unique_canteen.ground_position is None


def test_give_and_pick_up_contend_for_the_receivers_last_slot() -> None:
    content = content_with({"ella": (2, 3), "ryan": (3, 3)}, inventory={"slot_capacity": 1})
    state = snapshot(content)
    position = Coord(x=3, y=3)
    state.ground_fruit = [GroundFruitPile(position=position, quantity=1)]
    state.exposure_receipts_by_resident[1].entities.append(
        ReceiptEntity(entity_id="ground_fruit@3,3", entity_type="ground_fruit", position=position)
    )
    group = state.exposure_receipts_by_resident[1]
    group.entities = sorted(group.entities, key=lambda e: (e.entity_id, e.position.y, e.position.x))
    commit = tick(
        create_engine(content, state),
        intent("give", target=RYAN, item_type="canteen", quantity=1),
        intent(
            "pick_up",
            "ryan",
            target={"kind": "tile", "position": position},
            item_type="fruit",
            quantity=1,
        ),
    )
    assert failures(commit) == ["INVENTORY_FULL"]
    ryan = commit.snapshot.residents[1]
    assert ryan.fruit_count + int(commit.snapshot.unique_canteen.holder_id == ryan.id) == 1


def test_eat_drink_fill_and_give_effects() -> None:
    content = content_with({"ella": (9, 1), "ryan": (9, 2)})
    state = snapshot(content)
    state.residents[0].fruit_count = 2
    engine = create_engine(content, state)
    given = tick(engine, intent("give", target=RYAN, item_type="fruit", quantity=1))
    assert [r.fruit_count for r in given.snapshot.residents] == [1, 1]
    ate = tick(engine, intent("eat"))
    assert ate.snapshot.lifetime_fruit_consumed == 1
    assert ate.snapshot.residents[0].satiety > given.snapshot.residents[0].satiety
    drank = tick(engine, intent("drink", source="canteen"))
    assert drank.snapshot.unique_canteen.servings == content.config.canteen.capacity_servings - 1
    filled = tick(engine, intent("fill_canteen", target=CANTEEN))
    fill = next(e for e in filled.events if e.type == "canteen_filled")
    assert (fill.actor_id, fill.target_id) == ("ella", "canteen_01")
    assert filled.snapshot.unique_canteen.servings == content.config.canteen.capacity_servings
    spring = tick(engine, intent("drink", id="spring", source="spring"))
    assert not failures(spring)
    assert any(e.type == "water_drank" for e in spring.events)
    assert spring.snapshot.unique_canteen == filled.snapshot.unique_canteen
    canteen = tick(
        engine, intent("give", id="give-canteen", target=RYAN, item_type="canteen", quantity=1)
    )
    assert canteen.snapshot.unique_canteen.holder_id == "ryan"


def test_invalid_start_consumes_configured_duration() -> None:
    content = content_with({"ella": (2, 3)}, actions={"invalid_attempt_ticks": 2})
    engine = create_engine(content, None)
    engine.initial_commit()
    first = tick(engine, intent("eat"))
    assert not failures(first)
    assert first.snapshot.active_actions[0].remaining_ticks == 1
    second = tick(engine)
    assert failures(second) == ["NO_ITEM"]
    assert not second.snapshot.active_actions


@pytest.mark.parametrize("kind", ["rest", "sleep", "wait"])
def test_recovery_and_wait_through_completion(kind: ActionType) -> None:
    content = content_with({"ella": (2, 3)}, actions={f"{kind}_ticks": 1})
    state = snapshot(content)
    actor = state.residents[0]
    actor.stamina = 1000
    result = tick(create_engine(content, state), intent(kind))
    needs = content.config.needs
    if kind == "rest":
        gain = needs.stamina_rest_gain_per_tick - needs.stamina_awake_decay_per_tick
    elif kind == "sleep":
        gain = needs.stamina_sleep_gain_per_tick + needs.stamina_sleep_cave_bonus_per_tick
    else:
        gain = -needs.stamina_awake_decay_per_tick
    assert result.snapshot.residents[0].stamina == actor.stamina + gain
    assert any(e.type == "action_succeeded" for e in result.events)


def test_death_facts_keep_rule_targets_and_precede_causal_interrupt() -> None:
    content = content_with({"ella": (2, 3)})
    state = snapshot(content)
    resident = state.residents[0]
    resident.satiety = 0
    resident.health = 1
    resident.fruit_count = 1
    engine = create_engine(content, state)
    result = tick(engine, intent("rest"))
    facts = [(e.type, e.actor_id, e.target_id) for e in result.events]
    assert facts[-6:] == [
        ("condition_updated", "ella", None),
        ("resident_died", "ella", None),
        ("corpse_created", "ella", "corpse@ella"),
        ("item_dropped", "ella", "ground_fruit@2,3"),
        ("item_dropped", "ella", "canteen_01"),
        ("action_interrupted", "ella", None),
    ]
    assert result.events[-1].caused_by_event_ids == [result.events[-5].event_id]
    assert not result.pending_deliveries
    assert failures(tick(engine, intent("wait"))) == ["DEAD"]
