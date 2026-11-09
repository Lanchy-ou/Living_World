"""The unique canteen: one place, servings within capacity, fill/spend/transfers."""

from __future__ import annotations

from typing import Any

import pytest
from world_builders import default_content, fresh_state, resident

from living_island.world.canteen import (
    check_canteen,
    drop_canteen,
    fill_canteen,
    give_canteen,
    pick_up_canteen,
    spend_serving,
)
from living_island.world.protocol import Coord
from living_island.world.state import UniqueCanteenState


def held(servings: int = 2, holder: str = "ryan") -> UniqueCanteenState:
    return UniqueCanteenState(
        id="canteen_01", holder_id=holder, ground_position=None, servings=servings
    )


def on_ground(servings: int = 1) -> UniqueCanteenState:
    return UniqueCanteenState(
        id="canteen_01", holder_id=None, ground_position=Coord(x=3, y=4), servings=servings
    )


def test_fill_goes_to_capacity_and_reports_before_and_after() -> None:
    cfg = default_content().config
    result = fill_canteen(cfg, held(servings=0))
    assert result.canteen.servings == cfg.canteen.capacity_servings
    assert result.canteen.holder_id == "ryan"
    p: Any = result.fact.payload
    assert result.fact.type == "canteen_filled"
    assert (p.canteen_id, p.servings_before, p.servings_after) == ("canteen_01", 0, 2)
    assert fill_canteen(cfg, held(servings=1)).canteen.servings == 2


def test_fill_requires_a_held_non_full_canteen() -> None:
    cfg = default_content().config
    with pytest.raises(ValueError, match="already full"):
        fill_canteen(cfg, held(servings=2))
    with pytest.raises(ValueError, match="held"):
        fill_canteen(cfg, on_ground(servings=0))


def test_spend_one_serving_at_a_time() -> None:
    start = held(servings=2)
    once = spend_serving(start)
    assert once.servings == 1 and start.servings == 2  # input untouched
    assert spend_serving(once).servings == 0
    with pytest.raises(ValueError, match="empty"):
        spend_serving(held(servings=0))
    with pytest.raises(ValueError, match="held"):
        spend_serving(on_ground())


def test_transfers_keep_the_servings_and_exactly_one_place() -> None:
    start = held(servings=1)
    given = give_canteen(start, "ryan", "mia")
    assert (given.holder_id, given.ground_position, given.servings) == ("mia", None, 1)
    dropped = drop_canteen(given, Coord(x=7, y=8))
    assert (dropped.holder_id, dropped.ground_position, dropped.servings) == (
        None,
        Coord(x=7, y=8),
        1,
    )
    picked = pick_up_canteen(dropped, "ella")
    assert (picked.holder_id, picked.ground_position, picked.servings) == ("ella", None, 1)
    for c in (given, dropped, picked):
        assert (c.holder_id is None) != (c.ground_position is None)


def test_transfer_preconditions_are_enforced() -> None:
    with pytest.raises(ValueError, match="does not hold"):
        give_canteen(held(holder="ryan"), "ella", "mia")
    with pytest.raises(ValueError, match="oneself"):
        give_canteen(held(holder="ryan"), "ryan", "ryan")
    with pytest.raises(ValueError, match="already on the ground"):
        drop_canteen(on_ground(), Coord(x=1, y=1))
    with pytest.raises(ValueError, match="not on the ground"):
        pick_up_canteen(held(), "ella")


def test_check_canteen_accepts_the_initial_world_and_a_ground_canteen() -> None:
    content = default_content()
    state = fresh_state(content)
    check_canteen(content.config, state)
    state.unique_canteen = on_ground()
    check_canteen(content.config, state)


def test_check_canteen_rejects_every_broken_invariant() -> None:
    content = default_content()
    cfg = content.config

    over = fresh_state(content)
    over.unique_canteen.servings = cfg.canteen.capacity_servings + 1
    with pytest.raises(ValueError, match="servings"):
        check_canteen(cfg, over)

    renamed = fresh_state(content)
    renamed.unique_canteen.id = "other"
    with pytest.raises(ValueError, match="unique item ID"):
        check_canteen(cfg, renamed)

    dead_holder = fresh_state(content)
    resident(dead_holder, dead_holder.unique_canteen.holder_id).alive = False
    with pytest.raises(ValueError, match="living"):
        check_canteen(cfg, dead_holder)

    stranger = fresh_state(content)
    stranger.unique_canteen = held(holder="nobody")
    with pytest.raises(ValueError, match="living"):
        check_canteen(cfg, stranger)

    full = fresh_state(content)
    resident(full, full.unique_canteen.holder_id).fruit_count = cfg.inventory.slot_capacity
    with pytest.raises(ValueError, match="slot_capacity"):
        check_canteen(cfg, full)
