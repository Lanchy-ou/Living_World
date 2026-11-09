"""Property tests over arbitrary legal sequences of the P1-03 rule functions (WR §8 1-3).

The machine drives regrowth, physiology, gathering, eating, giving, dropping, picking up,
canteen use and death. Gather/eat/give/pick-up are written here only as thin legal moves over
the rule helpers (their real settlement is P1-04's); the invariants are checked after every
step.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, event, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule
from world_builders import default_content, fresh_state

from living_island.world.canteen import (
    drop_canteen,
    fill_canteen,
    give_canteen,
    pick_up_canteen,
    spend_serving,
)
from living_island.world.content import canonical_json_bytes
from living_island.world.death import apply_death, corpse_id, deaths_due
from living_island.world.perception import ground_fruit_id
from living_island.world.physiology import (
    TickActivity,
    apply_metabolism,
    apply_rest_sleep_gain,
    condition_fact,
    hydration_after_drinking,
    near_cave,
    satiety_after_eating,
)
from living_island.world.protocol import Coord
from living_island.world.resources import (
    add_ground_fruit,
    check_fruit_conservation,
    record_consumption,
    record_regrowth,
    regrow_fruit,
    remove_ground_fruit,
)
from living_island.world.state import WorldState

CONTENT = default_content()
CONFIG = CONTENT.config
NEEDS = CONFIG.needs
SLOTS = CONFIG.inventory.slot_capacity
RESIDENTS = ("ella", "mia", "ryan")

pick_resident = st.sampled_from(RESIDENTS)
activity = st.builds(
    TickActivity,
    kind=st.sampled_from(["other", "rest", "sleep"]),
    tiles_traversed=st.integers(0, 8),
    gather_completed=st.booleans(),
)


def slots_used(state: WorldState, resident_id: str) -> int:
    r = next(r for r in state.residents if r.id == resident_id)
    held = state.unique_canteen.holder_id == resident_id
    return r.fruit_count + (1 if held else 0)


class PhysicalRules(RuleBasedStateMachine):
    state: WorldState
    tick: int

    @initialize(
        health=st.integers(1, 400),
        needs=st.lists(st.integers(0, NEEDS.max_value), min_size=9, max_size=9),
        stock=st.integers(0, 5),
    )
    def start(self, health: int, needs: list[int], stock: int) -> None:
        state = fresh_state(CONTENT)
        for i, r in enumerate(state.residents):
            r.health = health + 70 * i  # low health so deaths are reachable
            r.satiety, r.hydration, r.stamina = needs[3 * i : 3 * i + 3]
        for node in state.fruit_nodes:
            node.stock = stock
        # Six trees start at stock 1 (the ledger's initial_on_trees); balance the starting
        # stock through the lifetime counters as if growth or eating had already happened.
        trees = len(state.fruit_nodes)
        if stock >= 1:
            state.lifetime_fruit_regrown = trees * (stock - 1)
        else:
            state.lifetime_fruit_consumed = trees
        self.state = state
        self.tick = 0
        check_fruit_conservation(CONFIG, self.state)

    # ---- rules -------------------------------------------------------------------------

    @rule(data=st.data())
    def metabolise(self, data: st.DataObject) -> None:
        self.tick += 1
        new = self.state.model_copy(deep=True)
        regrown = regrow_fruit(CONFIG, new.fruit_nodes, self.tick)
        new.fruit_nodes = regrown.nodes
        new.lifetime_fruit_regrown = record_regrowth(
            new.lifetime_fruit_regrown, regrown.regrown_total
        )
        for i, r in enumerate(new.residents):
            if not r.alive:
                continue
            act = data.draw(activity, label=f"activity-{r.id}")
            gained = apply_rest_sleep_gain(CONFIG, r, act.kind, near_cave(r.position, new.cave))
            after = apply_metabolism(CONFIG, gained, act).resident
            condition_fact(r, after)  # must always be buildable
            new.residents[i] = after
        for rid in deaths_due(CONFIG, new):
            result = apply_death(CONFIG, new, rid, self.tick)
            new = result.state
            event("death")
            event(f"death drops: {[f.type for f in result.facts][2:]}")
        self.state = new

    @precondition(lambda self: any(n.stock > 0 for n in self.state.fruit_nodes))
    @rule(who=pick_resident, data=st.data())
    def gather(self, who: str, data: st.DataObject) -> None:
        r = next(r for r in self.state.residents if r.id == who)
        trees = [n for n in self.state.fruit_nodes if n.stock > 0]
        if not r.alive or slots_used(self.state, who) >= SLOTS or not trees:
            return
        tree_id = data.draw(st.sampled_from([n.id for n in trees]))
        new = self.state.model_copy(deep=True)
        next(n for n in new.fruit_nodes if n.id == tree_id).stock -= 1
        next(x for x in new.residents if x.id == who).fruit_count += 1
        self.state = new

    @rule(who=pick_resident)
    def eat(self, who: str) -> None:
        new = self.state.model_copy(deep=True)
        r = next(x for x in new.residents if x.id == who)
        if not r.alive or r.fruit_count < 1:
            return
        r.fruit_count -= 1
        r.satiety = satiety_after_eating(CONFIG, r.satiety)
        new.lifetime_fruit_consumed = record_consumption(new.lifetime_fruit_consumed, 1)
        self.state = new

    @rule(who=pick_resident)
    def drink_canteen(self, who: str) -> None:
        c = self.state.unique_canteen
        r = next(x for x in self.state.residents if x.id == who)
        if not r.alive or c.holder_id != who or c.servings < 1:
            return
        new = self.state.model_copy(deep=True)
        new.unique_canteen = spend_serving(c)
        next(x for x in new.residents if x.id == who).hydration = hydration_after_drinking(
            CONFIG, r.hydration
        )
        self.state = new

    @rule()
    def refill(self) -> None:
        c = self.state.unique_canteen
        if c.holder_id is None or c.servings >= CONFIG.canteen.capacity_servings:
            return
        new = self.state.model_copy(deep=True)
        new.unique_canteen = fill_canteen(CONFIG, c).canteen
        self.state = new

    @rule(to=pick_resident)
    def give_the_canteen(self, to: str) -> None:
        c = self.state.unique_canteen
        recipient = next(x for x in self.state.residents if x.id == to)
        if c.holder_id is None or c.holder_id == to or not recipient.alive:
            return
        if slots_used(self.state, to) >= SLOTS:
            return
        new = self.state.model_copy(deep=True)
        new.unique_canteen = give_canteen(c, c.holder_id, to)
        self.state = new

    @rule(x=st.integers(0, 63), y=st.integers(0, 63))
    def drop_the_canteen(self, x: int, y: int) -> None:
        c = self.state.unique_canteen
        if c.holder_id is None:
            return
        new = self.state.model_copy(deep=True)
        new.unique_canteen = drop_canteen(c, Coord(x=x, y=y))
        self.state = new

    @rule(who=pick_resident)
    def pick_up_the_canteen(self, who: str) -> None:
        c = self.state.unique_canteen
        r = next(x for x in self.state.residents if x.id == who)
        if c.ground_position is None or not r.alive or slots_used(self.state, who) >= SLOTS:
            return
        new = self.state.model_copy(deep=True)
        new.unique_canteen = pick_up_canteen(c, who)
        self.state = new

    @rule(who=pick_resident, give_to=pick_resident, qty=st.integers(1, 3))
    def give_fruit(self, who: str, give_to: str, qty: int) -> None:
        a = next(x for x in self.state.residents if x.id == who)
        b = next(x for x in self.state.residents if x.id == give_to)
        if not (a.alive and b.alive) or who == give_to or a.fruit_count < qty:
            return
        if slots_used(self.state, give_to) + qty > SLOTS:
            return
        new = self.state.model_copy(deep=True)
        next(x for x in new.residents if x.id == who).fruit_count -= qty
        next(x for x in new.residents if x.id == give_to).fruit_count += qty
        self.state = new

    @rule(who=pick_resident, data=st.data())
    def drop_fruit_then_pick_up(self, who: str, data: st.DataObject) -> None:
        r = next(x for x in self.state.residents if x.id == who)
        if not r.alive or r.fruit_count < 1:
            return
        qty = data.draw(st.integers(1, r.fruit_count))
        new = self.state.model_copy(deep=True)
        me = next(x for x in new.residents if x.id == who)
        me.fruit_count -= qty
        new.ground_fruit = add_ground_fruit(new.ground_fruit, me.position, qty)
        if data.draw(st.booleans()):  # take part of it straight back (reuses the handle)
            back = data.draw(st.integers(1, qty))
            new.ground_fruit = remove_ground_fruit(new.ground_fruit, me.position, back)
            me.fruit_count += back
        self.state = new

    # ---- invariants ----------------------------------------------------------------------

    @invariant()
    def values_are_integers_within_bounds(self) -> None:
        lo, hi = NEEDS.min_value, NEEDS.max_value
        for r in self.state.residents:
            for value in (r.satiety, r.hydration, r.stamina, r.health):
                assert type(value) is int and lo <= value <= hi
            assert r.fruit_count >= 0
        for n in self.state.fruit_nodes:
            assert 0 <= n.stock <= CONFIG.fruit.max_stock_per_tree
        assert all(p.quantity >= 1 for p in self.state.ground_fruit)

    @invariant()
    def fruit_is_conserved(self) -> None:
        check_fruit_conservation(CONFIG, self.state)

    @invariant()
    def canteen_is_in_exactly_one_place(self) -> None:
        c = self.state.unique_canteen
        assert (c.holder_id is None) != (c.ground_position is None)
        assert 0 <= c.servings <= CONFIG.canteen.capacity_servings
        if c.holder_id is not None:
            holder = next(r for r in self.state.residents if r.id == c.holder_id)
            assert holder.alive  # ownership is consistent: only a living resident holds it

    @invariant()
    def dead_residents_hold_nothing_and_leave_one_corpse(self) -> None:
        dead = [r for r in self.state.residents if not r.alive]
        for r in dead:
            assert r.fruit_count == 0
            assert self.state.unique_canteen.holder_id != r.id
        assert sorted(c.id for c in self.state.corpses) == sorted(corpse_id(r.id) for r in dead)

    @invariant()
    def ground_piles_have_unique_tiles_and_stable_handles(self) -> None:
        tiles = [(p.position.y, p.position.x) for p in self.state.ground_fruit]
        assert tiles == sorted(set(tiles))
        assert len({ground_fruit_id(p.position) for p in self.state.ground_fruit}) == len(tiles)

    @invariant()
    def inventories_respect_the_slot_capacity(self) -> None:
        for r in self.state.residents:
            assert slots_used(self.state, r.id) <= SLOTS


PhysicalRules.TestCase.settings = settings(
    max_examples=60,
    stateful_step_count=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
TestPhysicalRules = PhysicalRules.TestCase


# ----------------------------------------------------------------------------- static checks


def _rule_sources() -> list[Path]:
    world = Path(__file__).resolve().parents[2] / "src" / "living_island" / "world"
    return [
        world / f"{name}.py"
        for name in ("resources", "physiology", "canteen", "death", "rulefacts")
    ]


def test_rule_modules_use_no_floats_and_no_rng() -> None:
    for path in _rule_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                assert not isinstance(node.value, float), f"float literal in {path.name}"
            if isinstance(node, ast.BinOp):
                assert not isinstance(node.op, ast.Div), f"true division in {path.name}"
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] != "random" for a in node.names), path.name
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "random", path.name
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "float", f"float() in {path.name}"


def test_machine_helpers_are_exercised_by_a_direct_scenario() -> None:
    """A deterministic sanity run of the same helpers the machine uses (no hypothesis)."""
    state = fresh_state(CONTENT)
    for tick in range(1, 400):
        regrown: Any = regrow_fruit(CONFIG, state.fruit_nodes, tick)
        state.fruit_nodes = regrown.nodes
        state.lifetime_fruit_regrown = record_regrowth(
            state.lifetime_fruit_regrown, regrown.regrown_total
        )
        check_fruit_conservation(CONFIG, state)
    assert state.lifetime_fruit_regrown > 0
    assert canonical_json_bytes(state.model_dump(mode="json"))
