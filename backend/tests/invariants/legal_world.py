"""A physically legal driver for the P1-03 rule functions (used by the property tests).

``LegalWorld`` advances a world one completed tick at a time with exactly one progressing
action per living resident per tick, chosen from the actions that are legal *right now*:

* ``gather`` only on a tree with stock, from a tile Manhattan-adjacent to it, with room;
* ``fill`` and ``drink_spring`` only next to the spring; ``drink_canteen`` only with servings;
* ``give_*`` only to a living neighbour with room;
* drops land on the actor's own tile and pick-ups happen only on that tile.

Settlement of these actions is written here as thin moves over the rule helpers (the real
settlement is P1-04's); the tick follows WR §5.4: phase 2 rest/sleep gains, phase 3 settle,
phase 4 regrowth, phase 5 metabolism and deaths. Choices go through ``choose`` so Hypothesis
(or a fixed policy) decides them.
"""

from __future__ import annotations

import copy
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from world_builders import WORLDS, fresh_state

from living_island.world.canteen import (
    check_canteen,
    drop_canteen,
    fill_canteen,
    give_canteen,
    pick_up_canteen,
    spend_serving,
)
from living_island.world.content import (
    WorldContent,
    build_world_content,
)
from living_island.world.death import apply_death, corpse_id, deaths_due
from living_island.world.perception import ground_fruit_id
from living_island.world.physiology import (
    TickActivity,
    apply_metabolism,
    apply_rest_sleep_gain,
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
from living_island.world.space import StaticMap
from living_island.world.state import WorldState

T = TypeVar("T")
Choose = Callable[[str, Sequence[T]], T]
SLOTS_LABEL = "slots"


def variant_content(
    regrow_ticks: int | None = None,
    offsets: Sequence[int] | None = None,
    per_cycle: int | None = None,
    initial_stock: int | None = None,
    max_stock: int | None = None,
) -> WorldContent:
    """Default content with a legal regrowth period, tree phase offsets and stock bounds."""
    with (WORLDS / "default.toml").open("rb") as f:
        data: dict[str, Any] = copy.deepcopy(tomllib.load(f))
    fruit = data["fruit"]
    if regrow_ticks is not None:
        fruit["regrow_ticks"] = regrow_ticks
    if per_cycle is not None:
        fruit["regrow_per_cycle"] = per_cycle
    if max_stock is not None:
        fruit["max_stock_per_tree"] = max_stock
    if initial_stock is not None:
        fruit["initial_stock_per_tree"] = initial_stock
    if offsets is not None:
        for tree, offset in zip(data["world"]["fruit_trees"], offsets, strict=True):
            tree["regrow_phase_offset_ticks"] = offset
    return build_world_content(data, Path(WORLDS / "default-island.map").read_bytes())


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


@dataclass
class LegalWorld:
    content: WorldContent
    state: WorldState
    tick: int = 0
    regrowth_ticks: dict[str, list[int]] = field(default_factory=dict)
    deaths: list[tuple[str, int]] = field(default_factory=list)
    actions_seen: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.config = self.content.config
        self.smap = StaticMap.from_content(self.content)
        self.slots = self.config.inventory.slot_capacity
        self.spring = self.state.spring
        self.sites = self._sites()

    # ------------------------------------------------------------------ geometry

    def _passable_near(self, at: Coord) -> list[Coord]:
        out = []
        for dx, dy in ((0, 0), (0, -1), (1, 0), (0, 1), (-1, 0)):
            x, y = at.x + dx, at.y + dy
            if self.smap.in_bounds(x, y) and self.smap.step_cost(x, y) is not None:
                out.append(Coord(x=x, y=y))
        return out

    def _sites(self) -> list[Coord]:
        tiles: dict[tuple[int, int], Coord] = {}
        anchors = [n.position for n in self.state.fruit_nodes] + [self.spring, self.state.cave]
        for anchor in anchors:
            for tile in self._passable_near(anchor):
                tiles[(tile.y, tile.x)] = tile
        for x, y in ((20, 20), (30, 40), (45, 15)):  # a few unrelated passable tiles
            if self.smap.step_cost(x, y) is not None:
                tiles[(y, x)] = Coord(x=x, y=y)
        return [tiles[k] for k in sorted(tiles)]

    # ------------------------------------------------------------------ small accessors

    def resident(self, rid: str) -> Any:
        return next(r for r in self.state.residents if r.id == rid)

    def slots_used(self, rid: str) -> int:
        held = self.state.unique_canteen.holder_id == rid
        return self.resident(rid).fruit_count + (1 if held else 0)

    def neighbours(self, rid: str) -> list[str]:
        me = self.resident(rid)
        return [
            r.id
            for r in self.state.residents
            if r.alive and r.id != rid and manhattan(r.position, me.position) <= 1
        ]

    def near_spring(self, rid: str) -> bool:
        return manhattan(self.resident(rid).position, self.spring) <= 1

    def trees_in_reach(self, rid: str) -> list[str]:
        me = self.resident(rid)
        return [
            n.id
            for n in self.state.fruit_nodes
            if n.stock >= 1 and manhattan(me.position, n.position) <= 1
        ]

    # ------------------------------------------------------------------ legal actions

    def legal_actions(self, rid: str) -> list[str]:
        me = self.resident(rid)
        canteen = self.state.unique_canteen
        holds = canteen.holder_id == rid
        here = (me.position.y, me.position.x)
        pile_here = any((p.position.y, p.position.x) == here for p in self.state.ground_fruit)
        room = self.slots_used(rid) < self.slots
        acts = ["idle", "rest", "sleep", "move"]
        if self.trees_in_reach(rid) and room:
            acts.append("gather")
        if me.fruit_count >= 1:
            acts += ["eat", "drop_fruit"]
        if self.near_spring(rid):
            acts.append("drink_spring")
            if holds and canteen.servings < self.config.canteen.capacity_servings:
                acts.append("fill")
        if holds and canteen.servings >= 1:
            acts.append("drink_canteen")
        recipients = [n for n in self.neighbours(rid) if self.slots_used(n) < self.slots]
        if recipients and me.fruit_count >= 1:
            acts.append("give_fruit")
        if recipients and holds:
            acts.append("give_canteen")
        if holds:
            acts.append("drop_canteen")
        if pile_here and room:
            acts.append("pick_up_fruit")
        if canteen.ground_position == me.position and room:
            acts.append("pick_up_canteen")
        return acts

    def _apply(self, rid: str, action: str, choose: Choose[Any]) -> TickActivity:
        """Settle one legal action (phase 3); returns what physiology must account for."""
        state = self.state
        me = self.resident(rid)
        activity = TickActivity()
        if action == "rest":
            return TickActivity(kind="rest")
        if action == "sleep":
            return TickActivity(kind="sleep")
        if action == "move":
            target = choose(f"{rid}-site", self.sites)
            steps = choose(f"{rid}-steps", list(range(1, 9)))
            me.position = target
            return TickActivity(tiles_traversed=steps)
        if action == "gather":
            tree_id = choose(f"{rid}-tree", self.trees_in_reach(rid))
            node = next(n for n in state.fruit_nodes if n.id == tree_id)
            assert manhattan(me.position, node.position) <= 1 and node.stock >= 1
            node.stock -= 1
            me.fruit_count += 1
            return TickActivity(gather_completed=True)
        if action == "eat":
            assert me.fruit_count >= 1
            me.fruit_count -= 1
            me.satiety = satiety_after_eating(self.config, me.satiety)
            state.lifetime_fruit_consumed = record_consumption(state.lifetime_fruit_consumed, 1)
        elif action == "drink_spring":
            assert self.near_spring(rid)
            me.hydration = hydration_after_drinking(self.config, me.hydration)
        elif action == "drink_canteen":
            state.unique_canteen = spend_serving(state.unique_canteen)
            me.hydration = hydration_after_drinking(self.config, me.hydration)
        elif action == "fill":
            assert self.near_spring(rid)
            state.unique_canteen = fill_canteen(self.config, state.unique_canteen).canteen
        elif action == "give_fruit":
            to = choose(
                f"{rid}-to", [n for n in self.neighbours(rid) if self.slots_used(n) < self.slots]
            )
            me.fruit_count -= 1
            self.resident(to).fruit_count += 1
        elif action == "give_canteen":
            to = choose(
                f"{rid}-to", [n for n in self.neighbours(rid) if self.slots_used(n) < self.slots]
            )
            state.unique_canteen = give_canteen(state.unique_canteen, rid, to)
        elif action == "drop_fruit":
            qty = choose(f"{rid}-qty", list(range(1, me.fruit_count + 1)))
            me.fruit_count -= qty
            state.ground_fruit = add_ground_fruit(state.ground_fruit, me.position, qty)  # own tile
        elif action == "pick_up_fruit":
            pile = next(p for p in state.ground_fruit if p.position == me.position)
            room = self.slots - self.slots_used(rid)
            qty = choose(f"{rid}-take", list(range(1, min(pile.quantity, room) + 1)))
            state.ground_fruit = remove_ground_fruit(state.ground_fruit, me.position, qty)
            me.fruit_count += qty
        elif action == "drop_canteen":
            state.unique_canteen = drop_canteen(state.unique_canteen, me.position)  # own tile
        elif action == "pick_up_canteen":
            assert state.unique_canteen.ground_position == me.position
            state.unique_canteen = pick_up_canteen(state.unique_canteen, rid)
        return activity

    # ------------------------------------------------------------------ one completed tick

    def step(self, choose: Choose[Any]) -> None:
        self.tick += 1
        activities: dict[str, TickActivity] = {}
        living = [r.id for r in self.state.residents if r.alive]
        for rid in living:  # ascending ID (WorldState keeps residents sorted)
            action = choose(f"{rid}-action", self.legal_actions(rid))
            self.actions_seen.add(action)
            me = self.resident(rid)
            if action in ("rest", "sleep"):  # phase 2
                gained = apply_rest_sleep_gain(
                    self.config,
                    me,
                    action,
                    near_cave(me.position, self.state.cave),  # type: ignore[arg-type]
                )
                me.stamina = gained.stamina
            activities[rid] = self._apply(rid, action, choose)  # phase 3
        regrown = regrow_fruit(self.config, self.state.fruit_nodes, self.tick)  # phase 4
        self.state.fruit_nodes = regrown.nodes
        self.state.lifetime_fruit_regrown = record_regrowth(
            self.state.lifetime_fruit_regrown, regrown.regrown_total
        )
        for fact in regrown.facts:
            self.regrowth_ticks.setdefault(str(fact.target_id), []).append(self.tick)
        for rid in living:  # phase 5
            me = self.resident(rid)
            result = apply_metabolism(self.config, me, activities[rid])
            for field_name in ("satiety", "hydration", "stamina", "health"):
                setattr(me, field_name, getattr(result.resident, field_name))
        for rid in deaths_due(self.config, self.state):
            self.state = apply_death(self.config, self.state, rid, self.tick).state
            self.deaths.append((rid, self.tick))
        self.check()

    # ------------------------------------------------------------------ invariants

    def check(self) -> None:
        cfg, state, needs = self.config, self.state, self.config.needs
        for r in state.residents:
            for value in (r.satiety, r.hydration, r.stamina, r.health):
                assert type(value) is int and needs.min_value <= value <= needs.max_value
            assert r.fruit_count >= 0 and self.slots_used(r.id) <= self.slots
            if not r.alive:
                assert r.fruit_count == 0 and state.unique_canteen.holder_id != r.id
        for node in state.fruit_nodes:
            assert 0 <= node.stock <= cfg.fruit.max_stock_per_tree
        assert all(p.quantity >= 1 for p in state.ground_fruit)
        tiles = [(p.position.y, p.position.x) for p in state.ground_fruit]
        assert tiles == sorted(set(tiles))
        assert len({ground_fruit_id(p.position) for p in state.ground_fruit}) == len(tiles)
        dead = [r.id for r in state.residents if not r.alive]
        assert sorted(c.id for c in state.corpses) == sorted(corpse_id(r) for r in dead)
        check_fruit_conservation(cfg, state)
        check_canteen(cfg, state)


def start_world(
    content: WorldContent,
    needs: Sequence[int],
    health: Sequence[int],
    servings: int | None = None,
) -> LegalWorld:
    """Residents keep their spawn tiles; needs, health and servings come from the caller."""
    state = fresh_state(content)
    for i, r in enumerate(state.residents):
        r.satiety, r.hydration, r.stamina = needs[3 * i : 3 * i + 3]
        r.health = health[i]
    if servings is not None:
        state.unique_canteen.servings = servings
    world = LegalWorld(content, state)
    world.check()
    return world
