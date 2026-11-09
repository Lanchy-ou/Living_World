"""Death: corpse, atomic inventory drop, facts in catalog order (WR §3, §6)."""

from __future__ import annotations

from typing import Any

import pytest
from world_builders import default_content, fresh_state, resident

from living_island.world.content import canonical_json_bytes
from living_island.world.death import apply_death, corpse_id, deaths_due
from living_island.world.protocol import ActionIntent, Coord, EmptyParameters
from living_island.world.resources import check_fruit_conservation
from living_island.world.state import ActiveAction, GroundFruitPile, WorldState

SPOT = Coord(x=20, y=21)


def dying(fruit: int = 0, canteen: bool = False, pile: int = 0) -> WorldState:
    """Ella is at minimum health at SPOT; fruit is taken from the trees so the world balances."""
    content = default_content()
    state = fresh_state(content)
    ella = resident(state, "ella")
    ella.position = SPOT
    ella.health = 0
    ella.fruit_count = fruit
    state.lifetime_fruit_regrown = fruit + pile - 0  # fruit and pile appear from regrowth
    if pile:
        state.ground_fruit = [GroundFruitPile(position=SPOT, quantity=pile)]
    if canteen:
        state.unique_canteen = state.unique_canteen.model_copy(
            update={"holder_id": "ella", "servings": 1}
        )
    check_fruit_conservation(content.config, state)
    return state


def active_wait(actor: str) -> ActiveAction:
    return ActiveAction(
        intent=ActionIntent(
            intent_id=f"{actor}:p000000:i0",
            plan_id=f"{actor}:p000000",
            actor_id=actor,
            action_type="wait",
            target=None,
            parameters=EmptyParameters(),
            reason=None,
        ),
        tick_started=0,
        elapsed_ticks=0,
        remaining_ticks=1,
        route=None,
        route_cursor=None,
        pending_failure_code=None,
    )


def test_death_creates_corpse_drops_everything_and_orders_facts() -> None:
    cfg = default_content().config
    state = dying(fruit=3, canteen=True)
    result = apply_death(cfg, state, "ella", tick=222)
    new = result.state
    ella = resident(new, "ella")
    assert ella.alive is False and ella.fruit_count == 0
    [corpse] = new.corpses
    assert (corpse.id, corpse.resident_id, corpse.position, corpse.death_tick) == (
        "corpse@ella",
        "ella",
        SPOT,
        222,
    )
    assert [(p.position, p.quantity) for p in new.ground_fruit] == [(SPOT, 3)]
    canteen = new.unique_canteen
    assert (canteen.holder_id, canteen.ground_position, canteen.servings) == (None, SPOT, 1)

    assert [f.type for f in result.facts] == [
        "resident_died",
        "corpse_created",
        "item_dropped",
        "item_dropped",
    ]
    died, created, fruit_drop, canteen_drop = (f.payload for f in result.facts)
    assert (died.resident_id, died.position, died.cause) == ("ella", SPOT, "DEPRIVATION")  # type: ignore[attr-defined]
    assert (created.corpse_id, created.position) == ("corpse@ella", SPOT)  # type: ignore[attr-defined]
    assert (fruit_drop.item_type, fruit_drop.quantity, fruit_drop.canteen_id) == ("fruit", 3, None)  # type: ignore[attr-defined]
    assert (canteen_drop.item_type, canteen_drop.quantity) == ("canteen", 1)  # type: ignore[attr-defined]
    assert (canteen_drop.canteen_id, canteen_drop.canteen_servings) == ("canteen_01", 1)  # type: ignore[attr-defined]
    check_fruit_conservation(cfg, new)


def test_death_on_a_tile_with_an_existing_pile_merges_into_it() -> None:
    cfg = default_content().config
    result = apply_death(cfg, dying(fruit=3, pile=2), "ella", tick=10)
    assert [(p.position, p.quantity) for p in result.state.ground_fruit] == [(SPOT, 5)]
    check_fruit_conservation(cfg, result.state)


def test_canteen_is_dropped_with_its_servings_even_without_fruit() -> None:
    cfg = default_content().config
    result = apply_death(cfg, dying(canteen=True), "ella", tick=10)
    assert [f.type for f in result.facts] == ["resident_died", "corpse_created", "item_dropped"]
    assert result.state.ground_fruit == []
    assert result.state.unique_canteen.servings == 1
    assert result.state.unique_canteen.ground_position == SPOT


def test_nothing_to_drop_means_only_the_two_death_facts() -> None:
    cfg = default_content().config
    state = dying()
    state.unique_canteen = state.unique_canteen.model_copy(update={"holder_id": "ryan"})
    result = apply_death(cfg, state, "ella", tick=10)
    assert [f.type for f in result.facts] == ["resident_died", "corpse_created"]
    assert result.state.unique_canteen.holder_id == "ryan"  # another holder keeps it


def test_the_corpse_id_is_stable_and_derived_from_the_resident() -> None:
    cfg = default_content().config
    assert corpse_id("ella") == "corpse@ella"
    a = apply_death(cfg, dying(fruit=1), "ella", tick=5)
    b = apply_death(cfg, dying(fruit=1), "ella", tick=99)
    assert a.state.corpses[0].id == b.state.corpses[0].id == "corpse@ella"


def test_the_active_action_is_cancelled_and_returned_for_the_engine() -> None:
    cfg = default_content().config
    state = dying()
    own, other = active_wait("ella"), active_wait("mia")
    state.active_actions = [own, other]
    result = apply_death(cfg, state, "ella", tick=7)
    assert result.cancelled_action == own
    assert [a.intent.actor_id for a in result.state.active_actions] == ["mia"]
    assert apply_death(cfg, dying(), "ella", tick=7).cancelled_action is None


def test_death_does_not_touch_other_residents_or_the_input() -> None:
    cfg = default_content().config
    state = dying(fruit=2)
    before = state.model_dump(mode="json")
    result = apply_death(cfg, state, "ella", tick=3)
    assert state.model_dump(mode="json") == before
    for rid in ("mia", "ryan"):
        assert resident(result.state, rid).model_dump() == resident(state, rid).model_dump()
    assert result.state is not state


def test_corpses_stay_sorted_by_id() -> None:
    cfg = default_content().config
    state = dying()
    mia = resident(state, "mia")
    mia.health = 0
    state = apply_death(cfg, state, "mia", tick=1).state
    state = apply_death(cfg, state, "ella", tick=2).state
    assert [c.id for c in state.corpses] == ["corpse@ella", "corpse@mia"]


def test_death_preconditions_are_enforced() -> None:
    cfg = default_content().config
    state = dying()
    with pytest.raises(ValueError, match="unknown"):
        apply_death(cfg, state, "nobody", tick=1)
    with pytest.raises(ValueError, match="minimum health"):
        apply_death(cfg, state, "mia", tick=1)
    dead = apply_death(cfg, state, "ella", tick=1).state
    with pytest.raises(ValueError, match="already dead"):
        apply_death(cfg, dead, "ella", tick=2)


def test_deaths_due_lists_living_residents_at_minimum_health_by_id() -> None:
    cfg = default_content().config
    state = fresh_state(default_content())
    assert deaths_due(cfg, state) == []
    resident(state, "ryan").health = 0
    resident(state, "ella").health = 0
    assert deaths_due(cfg, state) == ["ella", "ryan"]
    resident(state, "ella").alive = False
    assert deaths_due(cfg, state) == ["ryan"]


def test_identical_inputs_give_byte_identical_results() -> None:
    cfg = default_content().config

    def run() -> bytes:
        result = apply_death(cfg, dying(fruit=3, canteen=True, pile=2), "ella", tick=222)
        facts: list[Any] = [
            {
                "type": f.type,
                "actor": f.actor_id,
                "target": f.target_id,
                "payload": f.payload.model_dump(mode="json", by_alias=True),
            }
            for f in result.facts
        ]
        return canonical_json_bytes({"state": result.state.model_dump(mode="json"), "facts": facts})

    assert run() == run()
