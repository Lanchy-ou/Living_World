"""A physically legal driver for the P1-03 rule functions (used by the property tests).

P1-03 legality scope. ``LegalWorld`` enforces exactly this list (World Rules §3, §4.2, §5.4).
Full start/completion legality and failure codes belong to P1-04; this is the part the rule
functions' property tests need.

1. **Two-pass ticks.** Every living actor's action is chosen first, from the tick-START state
   (a deep-copied snapshot). Only then are progress (phase 2) and completions (phase 3)
   applied, so nothing is chosen from mid-tick results: a canteen received by ``give`` this
   tick cannot be drunk this tick.
2. **Movement** needs stamina > 0 at the start of every tick of the journey. A journey follows
   an adjacent-step route over passable tiles from P1-02 ``find_path``, takes steps while the
   running entry cost stays within ``map.walk_cost_budget_per_tick``, and reports as many
   traversed tiles as it took. A journey continues until arrival; when stamina is 0 at a tick's
   start it ends there (``EXHAUSTED``) and move/gather are not offered.
3. **Gather** needs stamina > 0, a tree within Manhattan reach and stock > 0 at tick start, and
   room in the inventory.
4. **Eat** needs an owned fruit and satiety below the maximum. **Drink** needs hydration below
   the maximum and either the spring within reach or the held canteen with servings > 0.
   **Fill** needs the held canteen, the spring within reach and servings below capacity.
5. **Give** needs a living recipient within Manhattan reach (WR §4.2) with room, and an owned
   item. **Pick-up** needs the same tile and an item there at tick start, and room.
6. **One progressing action per actor per tick.**
7. **Durations** (WR §4.1, §4.2, §5.4). No activity completes before its configured completion
   tick. The driver has no pending-activity scheduler (that is P1-04), so it chooses only
   actions whose configured duration is 1 tick, which then start and complete in their tick;
   an action with a longer duration (``gather_ticks=2``, ``rest_ticks=6``, ``sleep_ticks=48``
   in the default content) is never offered. The randomized machine therefore runs on fixture
   content whose durations are all 1 (``variant_content(one_tick=True)``, built through the
   normal content/config path with a valid config hash); a default-content run silently
   restricts itself to the default one-tick actions. Movement is the one multi-tick activity
   the driver models, as a journey.

Positions come only from legal fixture setup (a passable site) or legal movement; there is no
teleportation and no voluntary drop (the World Rules have no such action: ground items appear
by death or by fixture). Completions re-check the mutable preconditions in ascending actor
order and, if one no longer holds (a contested tree, a recipient that filled up), the action
has no effect.
Illegal and synthetic stress sequences live in ``test_physical_rules_properties.py``.
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
    fill_canteen,
    give_canteen,
    pick_up_canteen,
    spend_serving,
)
from living_island.world.content import WorldContent, build_world_content
from living_island.world.death import apply_death, corpse_id, deaths_due
from living_island.world.pathfinding import PathResult, find_path
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
    check_fruit_conservation,
    record_consumption,
    record_regrowth,
    regrow_fruit,
    remove_ground_fruit,
)
from living_island.world.space import StaticMap
from living_island.world.state import GroundFruitPile, WorldState

T = TypeVar("T")
Choose = Callable[[str, Sequence[T]], T]

# Configured duration (``[actions]`` key) of each single-tick action the driver can choose.
DURATION_KEY = {
    "wait": "wait_ticks",
    "rest": "rest_ticks",
    "sleep": "sleep_ticks",
    "gather": "gather_ticks",
    "eat": "eat_ticks",
    "drink_spring": "drink_ticks",
    "drink_canteen": "drink_ticks",
    "fill": "fill_canteen_ticks",
    "give_fruit": "give_ticks",
    "give_canteen": "give_ticks",
    "pick_up_fruit": "pick_up_ticks",
    "pick_up_canteen": "pick_up_ticks",
}

# Memoised routes per map: (map_hash, start, target) -> PathResult. Pure data, no content.
_ROUTES: dict[tuple[str, tuple[int, int], tuple[int, int]], PathResult] = {}


def variant_content(
    regrow_ticks: int | None = None,
    offsets: Sequence[int] | None = None,
    per_cycle: int | None = None,
    initial_stock: int | None = None,
    max_stock: int | None = None,
    one_tick: bool = False,
) -> WorldContent:
    """Default content with a legal regrowth period, tree phase offsets and stock bounds.

    ``one_tick`` sets every action duration (``[actions] *_ticks``) to 1, so each action the
    legal driver chooses completes in its own tick (legality item 7).
    """
    with (WORLDS / "default.toml").open("rb") as f:
        data: dict[str, Any] = copy.deepcopy(tomllib.load(f))
    fruit = data["fruit"]
    if one_tick:
        data["actions"] = {name: 1 for name in data["actions"]}
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


def resident_of(state: WorldState, rid: str) -> Any:
    return next(r for r in state.residents if r.id == rid)


@dataclass
class Move:
    """One tick of a journey as it actually happened."""

    tick: int
    actor: str
    steps: int
    cost: int
    start: Coord
    end: Coord


@dataclass
class LegalWorld:
    content: WorldContent
    state: WorldState
    tick: int = 0
    regrowth_ticks: dict[str, list[int]] = field(default_factory=dict)
    deaths: list[tuple[str, int]] = field(default_factory=list)
    actions_seen: set[str] = field(default_factory=set)
    failed_completions: int = 0
    last_options: dict[str, list[str]] = field(default_factory=dict)
    last_actions: dict[str, str] = field(default_factory=dict)
    moves: list[Move] = field(default_factory=list)
    journeys: dict[str, list[Coord]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.config = self.content.config
        self.smap = StaticMap.from_content(self.content)
        self.slots = self.config.inventory.slot_capacity
        self.spring = self.state.spring
        self.all_tiles = frozenset(range(self.smap.width * self.smap.height))
        self.sites = self._sites()

    def duration(self, action: str) -> int:
        """Configured completion tick count of ``action`` (``move`` is a journey, not timed)."""
        return int(getattr(self.config.actions, DURATION_KEY[action]))

    # ------------------------------------------------------------------ geometry

    def _passable_near(self, at: Coord) -> list[Coord]:
        out = []
        for dx, dy in ((0, 0), (0, -1), (1, 0), (0, 1), (-1, 0)):
            x, y = at.x + dx, at.y + dy
            if self.smap.in_bounds(x, y) and self.smap.step_cost(x, y) is not None:
                out.append(Coord(x=x, y=y))
        return out

    def _sites(self) -> list[Coord]:
        """Passable fixture/destination tiles: by each tree, by the spring, the cave, others."""
        tiles: dict[tuple[int, int], Coord] = {}
        for node in self.state.fruit_nodes:
            near = self._passable_near(node.position)
            tiles[(near[0].y, near[0].x)] = near[0]
        for tile in self._passable_near(self.spring)[:2]:
            tiles[(tile.y, tile.x)] = tile
        cave = self.state.cave
        tiles[(cave.y, cave.x)] = cave
        for x, y in ((20, 20), (30, 40)):
            if self.smap.step_cost(x, y) is not None:
                tiles[(y, x)] = Coord(x=x, y=y)
        return [tiles[k] for k in sorted(tiles)]

    def route(self, start: Coord, target: Coord) -> PathResult:
        key = (self.content.map_hash, (start.x, start.y), (target.x, target.y))
        found = _ROUTES.get(key)
        if found is None:
            found = find_path(self.smap, self.all_tiles, start, target)  # fully known map
            _ROUTES[key] = found
        return found

    def destinations(self, start: Coord) -> list[Coord]:
        return [s for s in self.sites if s != start and self.route(start, s).status == "ok"]

    # ------------------------------------------------------------------ start-state queries

    def slots_used(self, snap: WorldState, rid: str) -> int:
        held = snap.unique_canteen.holder_id == rid
        return resident_of(snap, rid).fruit_count + (1 if held else 0)

    def neighbours(self, snap: WorldState, rid: str) -> list[str]:
        me = resident_of(snap, rid)
        return [
            r.id
            for r in snap.residents
            if r.alive and r.id != rid and manhattan(r.position, me.position) <= 1
        ]

    def near_spring(self, snap: WorldState, rid: str) -> bool:
        return manhattan(resident_of(snap, rid).position, self.spring) <= 1

    def trees_in_reach(self, snap: WorldState, rid: str) -> list[str]:
        me = resident_of(snap, rid)
        return [
            n.id
            for n in snap.fruit_nodes
            if n.stock >= 1 and manhattan(me.position, n.position) <= 1
        ]

    def recipients(self, snap: WorldState, rid: str) -> list[str]:
        return [n for n in self.neighbours(snap, rid) if self.slots_used(snap, n) < self.slots]

    def options(self, snap: WorldState, rid: str) -> list[str]:
        """Actions legal for ``rid`` from the tick-start snapshot ``snap``."""
        me = resident_of(snap, rid)
        needs = self.config.needs
        if rid in self.journeys and me.stamina > 0:
            return ["move"]  # a journey continues until arrival
        canteen = snap.unique_canteen
        holds = canteen.holder_id == rid
        room = self.slots_used(snap, rid) < self.slots
        acts = ["wait", "rest", "sleep"]
        if me.stamina > 0:
            if self.destinations(me.position):
                acts.append("move")
            if room and self.trees_in_reach(snap, rid):
                acts.append("gather")
        if me.fruit_count >= 1 and me.satiety < needs.max_value:
            acts.append("eat")
        if me.hydration < needs.max_value:
            if self.near_spring(snap, rid):
                acts.append("drink_spring")
            if holds and canteen.servings >= 1:
                acts.append("drink_canteen")
        if holds and self.near_spring(snap, rid):
            if canteen.servings < self.config.canteen.capacity_servings:
                acts.append("fill")
        recipients = self.recipients(snap, rid)
        if recipients and me.fruit_count >= 1:
            acts.append("give_fruit")
        if recipients and holds:
            acts.append("give_canteen")
        pile_here = any(p.position == me.position for p in snap.ground_fruit)
        if pile_here and room:
            acts.append("pick_up_fruit")
        if canteen.ground_position == me.position and room:
            acts.append("pick_up_canteen")
        # Item 7: only actions that complete in the tick they start (no pending-activity engine).
        return [a for a in acts if a == "move" or self.duration(a) == 1]

    # ------------------------------------------------------------------ one completed tick

    def _walk(self, rid: str, snap_stamina: int) -> TickActivity:
        """Phase-2 movement: adjacent passable steps within the walk budget."""
        assert snap_stamina > 0, "a journey tick needs stamina > 0 at tick start"
        me = resident_of(self.state, rid)
        remaining = self.journeys[rid]
        budget = self.config.map.walk_cost_budget_per_tick
        start, here, spent, taken = me.position, me.position, 0, 0
        while remaining:
            step = remaining[0]
            cost = self.smap.step_cost(step.x, step.y)
            assert cost is not None and manhattan(here, step) == 1  # passable, adjacent
            if spent + cost > budget:
                break
            spent, taken, here = spent + cost, taken + 1, step
            remaining.pop(0)
        assert taken >= 1 and spent <= budget
        me.position = here
        if not remaining:
            del self.journeys[rid]
        self.moves.append(Move(self.tick, rid, taken, spent, start, here))
        return TickActivity(tiles_traversed=taken)

    def step(self, choose: Choose[Any]) -> None:
        self.tick += 1
        snap = self.state.model_copy(deep=True)  # the tick-start state
        living = [r.id for r in snap.residents if r.alive]

        # Pass 1: choose every actor's action and parameters from the snapshot only.
        plan: dict[str, tuple[str, dict[str, Any]]] = {}
        for rid in living:
            if rid in self.journeys and resident_of(snap, rid).stamina <= 0:
                del self.journeys[rid]  # EXHAUSTED ends the journey
            opts = self.options(snap, rid)
            self.last_options[rid] = opts
            action = choose(f"{rid}-action", opts)
            assert action in opts
            self.last_actions[rid] = action
            self.actions_seen.add(action)
            plan[rid] = (action, self._choose_params(snap, rid, action, choose))

        # Pass 2: progress (phase 2) then completions (phase 3), ascending actor ID.
        activities = {rid: TickActivity() for rid in living}
        for rid in living:
            action, params = plan[rid]
            me = resident_of(self.state, rid)
            if action in ("rest", "sleep"):
                gained = apply_rest_sleep_gain(
                    self.config, me, action, near_cave(me.position, self.state.cave)
                )
                me.stamina = gained.stamina
                activities[rid] = TickActivity(kind=action)
            elif action == "move":
                if rid not in self.journeys:
                    route = self.route(me.position, params["destination"])
                    assert route.status == "ok"
                    self.journeys[rid] = list(route.route)
                activities[rid] = self._walk(rid, resident_of(snap, rid).stamina)
        for rid in living:
            action, params = plan[rid]
            if action in ("wait", "rest", "sleep", "move"):
                continue
            if self._complete(snap, rid, action, params):
                if action == "gather":
                    activities[rid] = TickActivity(gather_completed=True)
            else:
                self.failed_completions += 1

        regrown = regrow_fruit(self.config, self.state.fruit_nodes, self.tick)  # phase 4
        self.state.fruit_nodes = regrown.nodes
        self.state.lifetime_fruit_regrown = record_regrowth(
            self.state.lifetime_fruit_regrown, regrown.regrown_total
        )
        for fact in regrown.facts:
            self.regrowth_ticks.setdefault(str(fact.target_id), []).append(self.tick)
        for rid in living:  # phase 5
            me = resident_of(self.state, rid)
            result = apply_metabolism(self.config, me, activities[rid])
            for name in ("satiety", "hydration", "stamina", "health"):
                setattr(me, name, getattr(result.resident, name))
        for rid in deaths_due(self.config, self.state):
            self.state = apply_death(self.config, self.state, rid, self.tick).state
            self.journeys.pop(rid, None)
            self.deaths.append((rid, self.tick))
        self.check()

    def _choose_params(
        self, snap: WorldState, rid: str, action: str, choose: Choose[Any]
    ) -> dict[str, Any]:
        me = resident_of(snap, rid)
        if action == "move":
            if rid in self.journeys:
                return {}
            return {"destination": choose(f"{rid}-site", self.destinations(me.position))}
        if action == "gather":
            return {"tree": choose(f"{rid}-tree", self.trees_in_reach(snap, rid))}
        if action == "give_fruit":
            to = choose(f"{rid}-to", self.recipients(snap, rid))
            room = self.slots - self.slots_used(snap, to)
            return {
                "to": to,
                "qty": choose(f"{rid}-qty", list(range(1, min(me.fruit_count, room) + 1))),
            }
        if action == "give_canteen":
            return {"to": choose(f"{rid}-to", self.recipients(snap, rid))}
        if action == "pick_up_fruit":
            pile = next(p for p in snap.ground_fruit if p.position == me.position)
            room = self.slots - self.slots_used(snap, rid)
            return {"qty": choose(f"{rid}-take", list(range(1, min(pile.quantity, room) + 1)))}
        return {}

    def _complete(self, snap: WorldState, rid: str, action: str, params: dict[str, Any]) -> bool:
        """Settle one completion; ``False`` if a mutable precondition no longer holds."""
        state, cfg = self.state, self.config
        me = resident_of(state, rid)
        start_me = resident_of(snap, rid)
        needs = cfg.needs
        if action == "gather":
            assert start_me.stamina > 0 and rid not in self.journeys
            node = next(n for n in state.fruit_nodes if n.id == params["tree"])
            if node.stock < 1 or self.slots_used(state, rid) >= self.slots:
                return False  # contested at completion
            node.stock -= 1
            me.fruit_count += 1
        elif action == "eat":
            assert start_me.satiety < needs.max_value and start_me.fruit_count >= 1
            if me.fruit_count < 1:
                return False
            me.fruit_count -= 1
            me.satiety = satiety_after_eating(cfg, me.satiety)
            state.lifetime_fruit_consumed = record_consumption(state.lifetime_fruit_consumed, 1)
        elif action == "drink_spring":
            assert start_me.hydration < needs.max_value and self.near_spring(snap, rid)
            if me.hydration >= needs.max_value:
                return False
            me.hydration = hydration_after_drinking(cfg, me.hydration)
        elif action == "drink_canteen":
            start_canteen = snap.unique_canteen
            assert start_me.hydration < needs.max_value
            assert start_canteen.holder_id == rid and start_canteen.servings >= 1  # held at start
            canteen = state.unique_canteen
            if canteen.holder_id != rid or canteen.servings < 1 or me.hydration >= needs.max_value:
                return False
            state.unique_canteen = spend_serving(canteen)
            me.hydration = hydration_after_drinking(cfg, me.hydration)
        elif action == "fill":
            assert snap.unique_canteen.holder_id == rid and self.near_spring(snap, rid)
            canteen = state.unique_canteen
            if canteen.holder_id != rid or canteen.servings >= cfg.canteen.capacity_servings:
                return False
            state.unique_canteen = fill_canteen(cfg, canteen).canteen
        elif action == "give_fruit":
            to = resident_of(state, params["to"])
            if not to.alive or manhattan(me.position, to.position) > 1:
                return False
            qty = params["qty"]
            if me.fruit_count < qty or self.slots_used(state, to.id) + qty > self.slots:
                return False
            me.fruit_count -= qty
            to.fruit_count += qty
        elif action == "give_canteen":
            to = resident_of(state, params["to"])
            canteen = state.unique_canteen
            if canteen.holder_id != rid or not to.alive or manhattan(me.position, to.position) > 1:
                return False
            if self.slots_used(state, to.id) >= self.slots:
                return False
            state.unique_canteen = give_canteen(canteen, rid, to.id)
        elif action == "pick_up_fruit":
            qty = params["qty"]
            pile = next((p for p in state.ground_fruit if p.position == me.position), None)
            room = self.slots - self.slots_used(state, rid)
            if pile is None or pile.quantity < qty or room < qty:
                return False
            state.ground_fruit = remove_ground_fruit(state.ground_fruit, me.position, qty)
            me.fruit_count += qty
        elif action == "pick_up_canteen":
            canteen = state.unique_canteen
            if canteen.ground_position != me.position or self.slots_used(state, rid) >= self.slots:
                return False
            state.unique_canteen = pick_up_canteen(canteen, rid)
        else:  # pragma: no cover - the option list is closed
            raise AssertionError(action)
        return True

    # ------------------------------------------------------------------ invariants

    def check(self) -> None:
        cfg, state, needs = self.config, self.state, self.config.needs
        for r in state.residents:
            for value in (r.satiety, r.hydration, r.stamina, r.health):
                assert type(value) is int and needs.min_value <= value <= needs.max_value
            assert r.fruit_count >= 0 and self.slots_used(state, r.id) <= self.slots
            if not r.alive:
                assert r.fruit_count == 0 and state.unique_canteen.holder_id != r.id
                assert r.id not in self.journeys
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
    positions: Sequence[Coord] | None = None,
    ground_pile: tuple[Coord, int] | None = None,
    canteen_on: Coord | None = None,
    depleted: bool = False,
) -> LegalWorld:
    """Legal fixture setup.

    Residents start on their spawn tiles, or on the given passable ``positions``; needs, health
    and servings come from the caller. ``ground_pile`` puts fruit on a tile (balanced through
    the regrowth counter) and ``canteen_on`` puts the canteen on the ground there. ``depleted``
    starts every tree empty (as if its fruit had been eaten, kept balanced through the consumed
    counter), so regrowth can act without any gathering.
    """
    state = fresh_state(content)
    for i, r in enumerate(state.residents):
        r.satiety, r.hydration, r.stamina = needs[3 * i : 3 * i + 3]
        r.health = health[i]
        if positions is not None:
            r.position = positions[i]
    if servings is not None:
        state.unique_canteen.servings = servings
    if depleted:
        for node in state.fruit_nodes:
            state.lifetime_fruit_consumed += node.stock
            node.stock = 0
    if ground_pile is not None:
        at, qty = ground_pile
        state.ground_fruit = [GroundFruitPile(position=at, quantity=qty)]
        state.lifetime_fruit_regrown += qty
    if canteen_on is not None:
        state.unique_canteen = state.unique_canteen.model_copy(
            update={"holder_id": None, "ground_position": canteen_on}
        )
    world = LegalWorld(content, state)
    world.check()
    return world
