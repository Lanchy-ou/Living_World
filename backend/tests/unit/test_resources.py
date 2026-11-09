"""Regrowth, ground piles, lifetime counters and fruit accounting (WR §5.5, §8.2)."""

from __future__ import annotations

from typing import Any

import pytest
from world_builders import default_content, fresh_state

from living_island.world.content import EffectiveConfig
from living_island.world.protocol import Coord
from living_island.world.resources import (
    add_ground_fruit,
    check_fruit_conservation,
    fruit_ledger,
    record_consumption,
    record_regrowth,
    regrow_fruit,
    regrowth_due,
    remove_ground_fruit,
)
from living_island.world.state import FruitNodeState, GroundFruitPile


def config() -> EffectiveConfig:
    return default_content().config


def with_fruit(cfg: EffectiveConfig, **update: int) -> EffectiveConfig:
    return cfg.model_copy(update={"fruit": cfg.fruit.model_copy(update=update)})


def node(node_id: str, stock: int, offset: int) -> FruitNodeState:
    return FruitNodeState(
        id=node_id, position=Coord(x=5, y=5), stock=stock, regrow_phase_offset_ticks=offset
    )


def stocks(nodes: list[FruitNodeState]) -> dict[str, int]:
    return {n.id: n.stock for n in nodes}


# ------------------------------------------------------------------ regrowth edges


def test_never_due_at_tick_zero_even_for_phase_zero() -> None:
    cfg = config()
    assert not regrowth_due(cfg, node("t", 1, 0), 0)
    result = regrow_fruit(cfg, [node("t", 1, 0)], 0)
    assert result.regrown_total == 0 and result.facts == []


def test_phase_zero_first_regrows_at_regrow_ticks() -> None:
    cfg = config()
    period = cfg.fruit.regrow_ticks
    tree = node("t", 1, 0)
    due = [k for k in range(0, 3 * period + 1) if regrowth_due(cfg, tree, k)]
    assert due == [period, 2 * period, 3 * period]
    grown = regrow_fruit(cfg, [tree], period)
    assert stocks(grown.nodes) == {"t": 1 + cfg.fruit.regrow_per_cycle}


def test_offset_trees_regrow_on_different_ticks() -> None:
    cfg = config()
    trees = [node("a", 1, 0), node("b", 1, 24), node("c", 1, 48)]
    at24 = regrow_fruit(cfg, trees, 24)
    assert stocks(at24.nodes) == {"a": 1, "b": 2, "c": 1}
    at48 = regrow_fruit(cfg, trees, 48)
    assert stocks(at48.nodes) == {"a": 1, "b": 1, "c": 2}
    assert [f.target_id for f in at24.facts] == ["b"]


def test_default_trees_each_regrow_once_per_period_on_their_offset() -> None:
    cfg = config()
    state = fresh_state(default_content())
    period = cfg.fruit.regrow_ticks
    for tree in state.fruit_nodes:
        ticks = [k for k in range(1, period + 1) if regrowth_due(cfg, tree, k)]
        assert ticks == [tree.regrow_phase_offset_ticks or period]


def test_capped_tree_creates_nothing_and_emits_no_fact() -> None:
    cfg = config()
    cap = cfg.fruit.max_stock_per_tree
    result = regrow_fruit(cfg, [node("t", cap, 0)], cfg.fruit.regrow_ticks)
    assert result.regrown_total == 0
    assert result.facts == []
    assert stocks(result.nodes) == {"t": cap}


def test_partial_top_up_stops_at_the_cap_and_reports_the_real_quantity() -> None:
    cfg = with_fruit(config(), regrow_per_cycle=3)
    cap = cfg.fruit.max_stock_per_tree
    result = regrow_fruit(cfg, [node("t", cap - 1, 0)], cfg.fruit.regrow_ticks)
    assert stocks(result.nodes) == {"t": cap}
    assert result.regrown_total == 1
    [fact] = result.facts
    payload: Any = fact.payload
    assert (payload.quantity, payload.stock_before, payload.stock_after) == (1, cap - 1, cap)
    assert fact.type == "fruit_regrew" and fact.target_id == "t"


def test_full_cycle_adds_regrow_per_cycle() -> None:
    cfg = with_fruit(config(), regrow_per_cycle=2)
    result = regrow_fruit(cfg, [node("t", 1, 0)], cfg.fruit.regrow_ticks)
    assert stocks(result.nodes) == {"t": 3} and result.regrown_total == 2


def test_nodes_are_processed_and_returned_in_ascending_id_order() -> None:
    cfg = config()
    trees = [node("c", 1, 0), node("a", 1, 0), node("b", 1, 0)]
    result = regrow_fruit(cfg, trees, cfg.fruit.regrow_ticks)
    assert [n.id for n in result.nodes] == ["a", "b", "c"]
    assert [f.target_id for f in result.facts] == ["a", "b", "c"]
    assert result.regrown_total == 3 * cfg.fruit.regrow_per_cycle


def test_harvest_never_resets_the_phase() -> None:
    cfg = config()
    tree = node("t", 1, 24)
    harvested = tree.model_copy(update={"stock": 0})  # gathered the last fruit
    assert regrowth_due(cfg, harvested, 24) and regrowth_due(cfg, harvested, 24 + 144)
    assert not regrowth_due(cfg, harvested, 25)
    assert regrow_fruit(cfg, [harvested], 24).nodes[0].regrow_phase_offset_ticks == 24


def test_regrowth_does_not_modify_its_inputs() -> None:
    cfg = config()
    trees = [node("t", 1, 0)]
    regrow_fruit(cfg, trees, cfg.fruit.regrow_ticks)
    assert trees[0].stock == 1


# ------------------------------------------------------------------ ground piles


def test_ground_piles_merge_sort_and_reuse_the_handle() -> None:
    piles = add_ground_fruit([], Coord(x=4, y=2), 2)
    piles = add_ground_fruit(piles, Coord(x=1, y=5), 1)
    piles = add_ground_fruit(piles, Coord(x=4, y=2), 3)  # merges into the existing pile
    assert [(p.position.x, p.position.y, p.quantity) for p in piles] == [(4, 2, 5), (1, 5, 1)]
    emptied = remove_ground_fruit(piles, Coord(x=4, y=2), 5)
    assert [(p.position.x, p.position.y) for p in emptied] == [(1, 5)]  # zero pile removed
    again = add_ground_fruit(emptied, Coord(x=4, y=2), 1)
    assert [(p.position.x, p.position.y, p.quantity) for p in again] == [(4, 2, 1), (1, 5, 1)]


def test_ground_pile_operations_reject_bad_amounts_and_do_not_mutate() -> None:
    piles = [GroundFruitPile(position=Coord(x=1, y=1), quantity=2)]
    with pytest.raises(ValueError):
        add_ground_fruit(piles, Coord(x=1, y=1), 0)
    with pytest.raises(ValueError):
        remove_ground_fruit(piles, Coord(x=1, y=1), 3)
    with pytest.raises(ValueError):
        remove_ground_fruit(piles, Coord(x=9, y=9), 1)
    add_ground_fruit(piles, Coord(x=1, y=1), 5)
    assert piles[0].quantity == 2


# ------------------------------------------------------------------ counters and conservation


def test_lifetime_counters_accumulate() -> None:
    cfg = config()
    result = regrow_fruit(cfg, [node("t", 1, 0), node("u", 1, 0)], cfg.fruit.regrow_ticks)
    assert record_regrowth(10, result.regrown_total) == 10 + result.regrown_total
    assert record_consumption(3, 2) == 5
    with pytest.raises(ValueError):
        record_regrowth(0, -1)
    with pytest.raises(ValueError):
        record_consumption(0, -1)


def test_fresh_world_is_balanced_and_unbalanced_worlds_are_caught() -> None:
    content = default_content()
    state = fresh_state(content)
    ledger = check_fruit_conservation(content.config, state)
    assert ledger.initial_on_trees == 6 and ledger.on_trees == 6 and ledger.balanced
    state.fruit_nodes[0].stock += 1  # fruit from nowhere
    assert not fruit_ledger(content.config, state).balanced
    with pytest.raises(ValueError, match="conservation"):
        check_fruit_conservation(content.config, state)


def test_ledger_counts_every_holding() -> None:
    content = default_content()
    state = fresh_state(content)
    state.fruit_nodes[0].stock -= 1
    state.residents[0].fruit_count = 1
    state.ground_fruit = [GroundFruitPile(position=Coord(x=2, y=2), quantity=2)]
    state.lifetime_fruit_regrown = 2  # +2 supply matches the pile on the ground
    ledger = check_fruit_conservation(content.config, state)
    assert (ledger.in_inventories, ledger.on_ground, ledger.on_trees) == (1, 2, 5)
    state.lifetime_fruit_consumed = 1
    state.lifetime_fruit_regrown = 3
    assert check_fruit_conservation(content.config, state).consumed == 1


def test_identical_inputs_give_byte_identical_regrowth_results() -> None:
    from living_island.world.content import canonical_json_bytes

    cfg = config()

    def run() -> bytes:
        state = fresh_state(default_content())
        out = regrow_fruit(cfg, state.fruit_nodes, 24 + cfg.fruit.regrow_ticks)
        facts: list[Any] = [
            {
                "type": f.type,
                "actor": f.actor_id,
                "target": f.target_id,
                "payload": f.payload.model_dump(mode="json"),
            }
            for f in out.facts
        ]
        return canonical_json_bytes(
            {
                "nodes": [n.model_dump(mode="json") for n in out.nodes],
                "total": out.regrown_total,
                "facts": facts,
            }
        )

    assert run() == run()


def test_initial_supply_comes_from_the_configured_trees_not_the_state_nodes() -> None:
    """G2-01: removing a tree and its fruit must not rebalance the books."""
    content = default_content()
    state = fresh_state(content)
    removed = state.fruit_nodes.pop(0)
    assert removed.stock == 1
    ledger = fruit_ledger(content.config, state)
    assert ledger.initial_on_trees == 6  # configured: six trees x stock 1
    assert ledger.on_trees == 5 and not ledger.balanced
    with pytest.raises(ValueError):
        check_fruit_conservation(content.config, state)


def test_a_missing_node_is_refused_even_when_its_stock_was_zero() -> None:
    content = default_content()
    state = fresh_state(content)
    state.fruit_nodes[0].stock = 0
    state.lifetime_fruit_consumed = 1  # the fruit was eaten: the ledger balances
    check_fruit_conservation(content.config, state)
    state.fruit_nodes.pop(0)  # now the node itself is gone; the counts still balance
    with pytest.raises(ValueError, match="configured trees"):
        check_fruit_conservation(content.config, state)


def test_an_extra_node_is_refused() -> None:
    content = default_content()
    state = fresh_state(content)
    state.fruit_nodes.append(
        FruitNodeState(
            id="fruit_99", position=Coord(x=7, y=7), stock=0, regrow_phase_offset_ticks=0
        )
    )
    with pytest.raises(ValueError, match="configured trees"):
        check_fruit_conservation(content.config, state)
    state.fruit_nodes[-1].stock = 1  # an extra node carrying fruit is refused too
    with pytest.raises(ValueError):
        check_fruit_conservation(content.config, state)


@pytest.mark.parametrize("change", ["renamed", "moved", "stock"])
def test_an_altered_node_is_refused(change: str) -> None:
    content = default_content()
    state = fresh_state(content)
    node = state.fruit_nodes[0]
    if change == "renamed":
        node.id = "fruit_00"
    elif change == "moved":
        node.position = Coord(x=node.position.x + 1, y=node.position.y)
    else:
        node.stock += 1
    with pytest.raises(ValueError):
        check_fruit_conservation(content.config, state)


def test_a_valid_state_still_balances_after_regrowth_and_eating() -> None:
    content = default_content()
    cfg = content.config
    state = fresh_state(content)
    grown = regrow_fruit(cfg, state.fruit_nodes, cfg.fruit.regrow_ticks)
    state.fruit_nodes = grown.nodes
    state.lifetime_fruit_regrown = record_regrowth(0, grown.regrown_total)
    state.fruit_nodes[0].stock -= 1
    state.residents[0].fruit_count = 1
    ledger = check_fruit_conservation(cfg, state)
    assert ledger.initial_on_trees == 6 and ledger.regrown == grown.regrown_total
