"""Fruit resources: regrowth, ground piles, lifetime counters and conservation accounting.

World Rules §3 (fruit), §5.4 phase 4, §5.5 and §8 invariant 2. Pure integer functions; no RNG
(regrowth never draws), no event IDs. See ``rulefacts`` for the calling convention.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from living_island.world.content import EffectiveConfig
from living_island.world.facts import FruitRegrewPayload
from living_island.world.protocol import Coord
from living_island.world.rulefacts import PendingFact
from living_island.world.state import FruitNodeState, GroundFruitPile, WorldState

# ---------------------------------------------------------------------------
# Regrowth (WR §5.5, §5.4 phase 4)
# ---------------------------------------------------------------------------


def regrowth_due(config: EffectiveConfig, node: FruitNodeState, completed_tick: int) -> bool:
    """Due at completed tick ``k >= 1`` when ``k % regrow_ticks == regrow_phase_offset_ticks``.

    Never due at tick zero, so a phase-zero tree first regrows at ``regrow_ticks``. The phase
    is a fixed property of the node and is never reset by harvest.
    """
    if completed_tick < 1:
        return False
    return completed_tick % config.fruit.regrow_ticks == node.regrow_phase_offset_ticks


@dataclass(frozen=True)
class RegrowthResult:
    nodes: list[FruitNodeState]  # new objects, ascending node ID
    regrown_total: int  # fruit actually created this tick
    facts: list[PendingFact]  # ``fruit_regrew``, ascending node ID


def regrow_fruit(
    config: EffectiveConfig, nodes: Sequence[FruitNodeState], completed_tick: int
) -> RegrowthResult:
    """Apply regrowth to every due node in ascending node-ID order.

    Adds up to ``regrow_per_cycle`` fruit, never above ``max_stock_per_tree``. A node already at
    the cap creates nothing and emits no fact; a partial top-up stops at the cap and reports the
    quantity actually created. Inputs are not modified.
    """
    cap = config.fruit.max_stock_per_tree
    out: list[FruitNodeState] = []
    facts: list[PendingFact] = []
    total = 0
    for node in sorted(nodes, key=lambda n: n.id):
        new = node.model_copy(deep=True)
        if regrowth_due(config, node, completed_tick):
            created = min(config.fruit.regrow_per_cycle, max(0, cap - node.stock))
            if created > 0:
                new.stock = node.stock + created
                total += created
                facts.append(
                    PendingFact(
                        type="fruit_regrew",
                        actor_id=None,
                        target_id=node.id,
                        payload=FruitRegrewPayload(
                            tree_id=node.id,
                            quantity=created,
                            stock_before=node.stock,
                            stock_after=new.stock,
                        ),
                    )
                )
        out.append(new)
    return RegrowthResult(out, total, facts)


# ---------------------------------------------------------------------------
# Ground piles (Interface Contract §2.2)
# ---------------------------------------------------------------------------


def add_ground_fruit(
    piles: Sequence[GroundFruitPile], position: Coord, quantity: int
) -> list[GroundFruitPile]:
    """New pile list with ``quantity`` fruit added at ``position``, merged and sorted ``(y,x)``."""
    if quantity < 1:
        raise ValueError("quantity must be positive")
    by_tile = {(p.position.y, p.position.x): p.model_copy(deep=True) for p in piles}
    key = (position.y, position.x)
    if key in by_tile:
        by_tile[key].quantity += quantity
    else:
        by_tile[key] = GroundFruitPile(
            position=Coord(x=position.x, y=position.y), quantity=quantity
        )
    return [by_tile[k] for k in sorted(by_tile)]


def remove_ground_fruit(
    piles: Sequence[GroundFruitPile], position: Coord, quantity: int
) -> list[GroundFruitPile]:
    """New pile list with ``quantity`` removed; a pile reaching zero disappears."""
    if quantity < 1:
        raise ValueError("quantity must be positive")
    by_tile = {(p.position.y, p.position.x): p.model_copy(deep=True) for p in piles}
    key = (position.y, position.x)
    pile = by_tile.get(key)
    if pile is None or pile.quantity < quantity:
        raise ValueError("not enough fruit on that tile")
    if pile.quantity == quantity:
        del by_tile[key]  # a zero-quantity pile is removed (the handle may be reused later)
    else:
        pile.quantity -= quantity
    return [by_tile[k] for k in sorted(by_tile)]


# ---------------------------------------------------------------------------
# Lifetime counters and conservation (WR §8 invariant 2)
# ---------------------------------------------------------------------------


def record_regrowth(lifetime_regrown: int, quantity: int) -> int:
    """New ``lifetime_fruit_regrown`` after ``quantity`` fruit actually grew."""
    if quantity < 0:
        raise ValueError("quantity must be nonnegative")
    return lifetime_regrown + quantity


def record_consumption(lifetime_consumed: int, quantity: int) -> int:
    """New ``lifetime_fruit_consumed`` after residents ate ``quantity`` fruit."""
    if quantity < 0:
        raise ValueError("quantity must be nonnegative")
    return lifetime_consumed + quantity


@dataclass(frozen=True)
class FruitLedger:
    """Both sides of WR §8.2: initial + regrowth = trees + inventories + ground + consumed."""

    initial_on_trees: int
    regrown: int
    on_trees: int
    in_inventories: int
    on_ground: int
    consumed: int

    @property
    def supply(self) -> int:
        return self.initial_on_trees + self.regrown

    @property
    def holdings(self) -> int:
        return self.on_trees + self.in_inventories + self.on_ground + self.consumed

    @property
    def balanced(self) -> bool:
        return self.supply == self.holdings


def fruit_ledger(config: EffectiveConfig, state: WorldState) -> FruitLedger:
    """Account for every fruit in ``state``.

    ``initial_on_trees`` is fixed by the configured content (configured tree count times
    ``initial_stock_per_tree``), never by the nodes currently in ``state``.
    """
    return FruitLedger(
        initial_on_trees=len(config.world.fruit_trees) * config.fruit.initial_stock_per_tree,
        regrown=state.lifetime_fruit_regrown,
        on_trees=sum(n.stock for n in state.fruit_nodes),
        in_inventories=sum(r.fruit_count for r in state.residents),
        on_ground=sum(p.quantity for p in state.ground_fruit),
        consumed=state.lifetime_fruit_consumed,
    )


def check_fruit_conservation(config: EffectiveConfig, state: WorldState) -> FruitLedger:
    """Return the ledger, or raise ``ValueError`` if fruit was created or destroyed.

    The state's fruit nodes must also be exactly the configured trees (same IDs and
    positions); a missing, extra or renamed node is refused even if its stock is zero.
    """
    configured = {t.id: tuple(t.position) for t in config.world.fruit_trees}
    actual = {n.id: (n.position.x, n.position.y) for n in state.fruit_nodes}
    if len(actual) != len(state.fruit_nodes) or actual != configured:
        raise ValueError("fruit nodes must be exactly the configured trees")
    ledger = fruit_ledger(config, state)
    if not ledger.balanced:
        raise ValueError(f"fruit conservation violated: {ledger}")
    return ledger
