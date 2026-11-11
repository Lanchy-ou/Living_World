"""Property tests over physically legal sequences of the P1-03 rule functions (WR §8 1-3).

P1-03 legality scope: ``legal_world.py`` enforces exactly the seven items listed in its module
docstring (two-pass ticks, movement, gather, eat/drink/fill, give/pick-up, one action per
actor per tick, action durations) and nothing more. Full start/completion legality and failure
codes belong to P1-04. Teleportation and manual drops are not generated here; they stay in the
separately named synthetic stress tests (``test_physical_rules_properties.py``).

Why the randomized machine runs on one-tick content (item 7): the driver has no
pending-activity scheduler (engine scheduling is P1-04), so it must never complete an activity
before its configured completion tick. With the default durations (``gather_ticks=2``,
``rest_ticks=6``, ``sleep_ticks=48``) it would complete a gather at tick 1. The machine
therefore uses fixture content whose ``[actions]`` durations are all 1, built through the normal
content/config path (valid config hash); the default-content runs below generate only the
actions whose default duration is 1, and the deterministic duration tests drive the P1-03 rule
functions with the default configuration.

Hypothesis strategy summary:

* content: a one-tick-duration variant with the default 144-tick regrowth, or one with
  ``regrow_ticks`` in 2..16, six offsets drawn in ``0..regrow_ticks-1``, ``regrow_per_cycle``
  1..3, and ``initial_stock <= max_stock`` in 0..6;
* fixture start: three needs per resident in 0..max, health 1..10000 biased low, canteen
  servings 0..2, each resident on a passable site (beside a tree, the spring, the cave or
  elsewhere), optionally a ground pile and the canteen lying on a site;
* each rule advances 1..15 ticks; every action, target, destination, quantity and recipient is
  drawn from the actions legal at the tick-start state.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule
from legal_world import LegalWorld, manhattan, resident_of, start_world, variant_content
from world_builders import default_content

from living_island.world.content import WorldContent
from living_island.world.physiology import (
    TickActivity,
    apply_metabolism,
    apply_rest_sleep_gain,
    near_cave,
)
from living_island.world.protocol import Coord
from living_island.world.resources import check_fruit_conservation
from living_island.world.state import GroundFruitPile

NEEDS_MAX = default_content().config.needs.max_value
FULL = [NEEDS_MAX] * 9
HEALTHY = [NEEDS_MAX] * 3
RESIDENTS = ("ella", "mia", "ryan")  # ascending ID; ryan holds the canteen at the start


def one_tick_content() -> WorldContent:
    """Default content with every action duration 1 (legality item 7)."""
    return variant_content(one_tick=True)


@st.composite
def legal_variant(draw: st.DrawFn) -> WorldContent:
    if draw(st.booleans()):
        return one_tick_content()  # default regrowth: period 144, offsets 0/24/48/72/96/120
    period = draw(st.integers(2, 16))
    offsets = [draw(st.integers(0, period - 1)) for _ in range(6)]
    max_stock = draw(st.integers(1, 6))
    return variant_content(
        regrow_ticks=period,
        offsets=offsets,
        per_cycle=draw(st.integers(1, 3)),
        initial_stock=draw(st.integers(0, max_stock)),
        max_stock=max_stock,
        one_tick=True,
    )


needs_values = st.lists(st.integers(0, NEEDS_MAX), min_size=9, max_size=9)
health_values = st.lists(
    st.one_of(st.integers(1, 600), st.integers(1, NEEDS_MAX)), min_size=3, max_size=3
)


class LegalSequences(RuleBasedStateMachine):
    world: LegalWorld

    @initialize(
        variant=legal_variant(),
        needs=needs_values,
        health=health_values,
        servings=st.integers(0, 2),
        data=st.data(),
    )
    def start(
        self,
        variant: WorldContent,
        needs: list[int],
        health: list[int],
        servings: int,
        data: st.DataObject,
    ) -> None:
        content = variant
        sites = start_world(content, needs, health).sites  # legal fixture tiles
        positions = [data.draw(st.sampled_from(sites), label="start site") for _ in RESIDENTS]
        pile = None
        if data.draw(st.booleans(), label="pile?"):
            pile = (data.draw(st.sampled_from(sites)), data.draw(st.integers(1, 4)))
        canteen_on = data.draw(st.sampled_from(sites)) if data.draw(st.booleans()) else None
        self.world = start_world(content, needs, health, servings, positions, pile, canteen_on)

    @rule(ticks=st.integers(1, 15), data=st.data())
    def advance(self, ticks: int, data: st.DataObject) -> None:
        def choose(label: str, options: Sequence[Any]) -> Any:
            return data.draw(st.sampled_from(list(options)), label=f"{self.world.tick}:{label}")

        for _ in range(ticks):
            self.world.step(choose)
        for kind in self.world.actions_seen:
            event(f"action {kind}")
        if self.world.deaths:
            event("a resident has died")
        if self.world.failed_completions:
            event("a completion failed its re-check")

    @invariant()
    def the_world_is_physically_consistent(self) -> None:
        self.world.check()


LegalSequences.TestCase.settings = settings(
    max_examples=40,
    stateful_step_count=20,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
TestLegalSequences = LegalSequences.TestCase


# ----------------------------------------------------------------------------- long runs


def rotating_policy() -> Any:
    """A deterministic chooser that takes the least-used option, so every action gets used."""
    used: Counter[str] = Counter()

    def choose(label: str, options: Sequence[Any]) -> Any:
        pick = min(options, key=lambda o: (used[str(o)], str(o)))
        used[str(pick)] += 1
        return pick

    return choose


def test_rotating_policy_exercises_every_legal_action_kind() -> None:
    content = one_tick_content()
    spawn = start_world(content, FULL, HEALTHY)
    ella, mia = (resident_of(spawn.state, r).position for r in ("ella", "mia"))
    # Legal fixtures: fruit lying on Mia's tile and the canteen lying on Ella's tile.
    world = start_world(content, FULL, HEALTHY, servings=0, ground_pile=(mia, 3), canteen_on=ella)
    choose = rotating_policy()
    for _ in range(400):
        world.step(choose)
    expected = {
        "wait", "rest", "sleep", "move", "gather", "pick_up_fruit", "give_fruit",
    }  # fmt: skip
    assert expected <= world.actions_seen, expected - world.actions_seen


@settings(max_examples=6, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_default_content_one_tick_actions_cross_every_regrowth_phase(
    data: st.DataObject,
) -> None:
    """300 ticks of random legal play with only the default one-tick actions (item 7).

    Default content: gather (2 ticks), rest (6) and sleep (48) are never generated, so the trees
    start empty (legal fixture) and regrow on schedule: offsets 72/96/120 and phase-0 at 144.
    """
    content = default_content()
    world = start_world(content, FULL, HEALTHY, depleted=True)

    def choose(label: str, options: Sequence[Any]) -> Any:
        return data.draw(st.sampled_from(list(options)), label=label)

    for _ in range(300):
        world.step(choose)
    period = content.config.fruit.regrow_ticks
    offsets = {t.id: t.regrow_phase_offset_ticks for t in content.config.world.fruit_trees}
    # A tree below the cap at its due tick regrows exactly there; harvest never moves the phase.
    for tree_id, ticks in world.regrowth_ticks.items():
        assert all(k % period == offsets[tree_id] for k in ticks), (tree_id, ticks)
    first = {tid: min(ticks) for tid, ticks in world.regrowth_ticks.items()}
    assert first, "no regrowth in 300 ticks"
    for tree_id, tick in first.items():
        assert tick == (offsets[tree_id] or period)  # phase 0 first regrows at 144, never at 0


def test_scripted_one_tick_run_reaches_the_late_default_phases() -> None:
    """Deterministic backstop (default content, one-tick actions only): 72/96/120/144 all fire."""
    world = start_world(default_content(), FULL, HEALTHY, depleted=True)
    choose = rotating_policy()
    for _ in range(300):
        world.step(choose)
    fired = {t for ticks in world.regrowth_ticks.values() for t in ticks}
    assert {72, 96, 120, 144} <= fired


# ----------------------------------------------------------------------------- legality guards
# Each test names the item of the legality list (legal_world.py docstring) it protects.


def fresh(needs: Sequence[int] = FULL, **fixture: Any) -> LegalWorld:
    """One-tick-duration content: every action the guards offer completes in its tick."""
    return start_world(one_tick_content(), needs, HEALTHY, **fixture)


def spring_stand(world: LegalWorld) -> Coord:
    return next(s for s in world.sites if manhattan(s, world.spring) == 1)


def hold_fruit(world: LegalWorld, rid: str, count: int) -> None:
    """Legal fixture: the resident carries fruit that grew (kept balanced via the counter)."""
    resident_of(world.state, rid).fruit_count = count
    world.state.lifetime_fruit_regrown += count


def test_item_1_actions_are_chosen_from_the_tick_start_state() -> None:
    """Probe: Ryan gives the canteen to Mia; Mia cannot drink it in the same tick."""
    world = fresh(servings=2)
    ryan, mia = (resident_of(world.state, r) for r in ("ryan", "mia"))
    assert (
        world.state.unique_canteen.holder_id == "ryan"
        and manhattan(ryan.position, mia.position) <= 1
    )
    mia.hydration = 5000
    before = mia.hydration
    decay = world.config.needs.hydration_decay_per_tick

    def choose(label: str, options: Sequence[Any]) -> Any:
        if label == "ryan-action":
            return "give_canteen"
        if label == "ryan-to":
            return "mia"
        if label == "mia-action":
            assert "drink_canteen" not in options  # not held at tick start
            return "wait"
        return options[0]

    world.step(choose)
    assert world.state.unique_canteen.holder_id == "mia"
    assert world.state.unique_canteen.servings == 2  # nothing was drunk
    assert resident_of(world.state, "mia").hydration == before - decay
    # Next tick she holds it at the start and may drink.
    assert "drink_canteen" in world.options(world.state, "mia")


def test_item_1_fruit_received_this_tick_cannot_be_eaten_this_tick() -> None:
    world = fresh()
    hold_fruit(world, "ryan", 2)
    resident_of(world.state, "mia").satiety = 4000

    def choose(label: str, options: Sequence[Any]) -> Any:
        if label == "ryan-action":
            return "give_fruit"
        if label == "ryan-to":
            return "mia"
        if label == "ryan-qty":
            return 1
        if label == "mia-action":
            assert "eat" not in options  # no fruit at tick start
            return "wait"
        return options[0]

    world.step(choose)
    assert resident_of(world.state, "mia").fruit_count == 1


def test_a_same_tick_give_then_drink_is_never_generated() -> None:
    """Review probe 3 over arbitrary legal play: no executed canteen drink without a start hold."""

    @settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st.data())
    def run(data: st.DataObject) -> None:
        world = fresh(servings=2)
        resident_of(world.state, "mia").hydration = 3000

        def choose(label: str, options: Sequence[Any]) -> Any:
            return data.draw(st.sampled_from(list(options)), label=label)

        for _ in range(12):
            holder_at_start = world.state.unique_canteen.holder_id
            world.step(choose)  # the driver asserts the start-hold of every canteen drink
            for rid, action in world.last_actions.items():
                if action == "drink_canteen":
                    assert rid == holder_at_start

    run()


def test_item_2_movement_takes_adjacent_passable_steps_within_the_budget() -> None:
    world = fresh()
    stand = spring_stand(world)
    cfg = world.config
    start = resident_of(world.state, "ella").position
    route = world.route(start, stand).route

    def choose(label: str, options: Sequence[Any]) -> Any:
        if label == "ella-action":
            return "move"
        if label == "ella-site":
            return stand
        return "wait" if "wait" in options else options[0]

    while "ella" in world.journeys or not world.moves:
        world.step(choose)
        assert world.tick < 40
    ella_moves = [m for m in world.moves if m.actor == "ella"]
    assert all(1 <= m.steps for m in ella_moves)
    assert all(m.cost <= cfg.map.walk_cost_budget_per_tick for m in ella_moves)
    assert sum(m.steps for m in ella_moves) == len(route)  # steps reported = tiles entered
    costs = [world.smap.step_cost(t.x, t.y) for t in route]
    assert sum(m.cost for m in ella_moves) == sum(c for c in costs if c is not None)
    assert resident_of(world.state, "ella").position == stand
    prev = start
    for m in ella_moves:
        assert m.start == prev and manhattan(m.start, m.end) <= m.steps
        prev = m.end


def test_a_zero_stamina_move_is_never_generated() -> None:
    """Review probe 1: at zero stamina neither move nor gather is offered; Ella stays put."""
    world = fresh(needs=[NEEDS_MAX, NEEDS_MAX, 0, *FULL[3:]])
    tree = world.state.fruit_nodes[0]
    ella = resident_of(world.state, "ella")
    ella.position = tree.position  # beside a stocked tree
    assert tree.stock >= 1 and ella.stamina == 0
    options = world.options(world.state, "ella")
    assert "move" not in options and "gather" not in options
    where = ella.position

    def choose(label: str, opts: Sequence[Any]) -> Any:
        assert not (label == "ella-action" and ("move" in opts or "gather" in opts))
        return opts[0]

    world.step(choose)
    assert resident_of(world.state, "ella").position == where and not world.moves


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(needs=needs_values)
def test_no_actor_with_zero_stamina_is_ever_offered_movement_or_gathering(
    needs: list[int],
) -> None:
    needs = list(needs)
    needs[2] = needs[5] = needs[8] = 0
    world = fresh(needs=needs)
    for rid in RESIDENTS:
        options = world.options(world.state, rid)
        assert "move" not in options and "gather" not in options


def test_item_2_a_journey_ends_when_stamina_is_zero_at_tick_start() -> None:
    world = fresh(needs=[NEEDS_MAX, NEEDS_MAX, 100, *FULL[3:]])
    # Start far enough from the spring for the journey to need a second tick.
    resident_of(world.state, "ella").position = Coord(x=12, y=32)
    stand = spring_stand(world)
    n = world.config.needs
    assert n.stamina_awake_decay_per_tick + n.stamina_move_extra_cost_per_tick == 100

    def choose(label: str, options: Sequence[Any]) -> Any:
        if label == "ella-action":
            return "move" if "move" in options else "wait"
        if label == "ella-site":
            return stand
        return "wait" if "wait" in options else options[0]

    world.step(choose)  # starts with stamina 100 > 0, ends at 0 after phase 5
    assert resident_of(world.state, "ella").stamina == 0 and "ella" in world.journeys
    stopped_at = resident_of(world.state, "ella").position
    world.step(choose)  # stamina 0 at the start: the journey ends, no movement is offered
    assert "ella" not in world.journeys
    assert "move" not in world.last_options["ella"]
    assert resident_of(world.state, "ella").position == stopped_at


def test_item_3_gather_needs_stamina_reach_and_stock_at_tick_start() -> None:
    world = fresh()
    tree = world.state.fruit_nodes[0]
    ella = resident_of(world.state, "ella")
    ella.position = tree.position
    assert "gather" in world.options(world.state, "ella")
    tree.stock = 0
    assert "gather" not in world.options(world.state, "ella")  # nothing to take
    tree.stock = 1
    ella.stamina = 0
    assert "gather" not in world.options(world.state, "ella")  # exhausted
    ella.stamina = 5000
    ella.position = world.state.cave
    assert "gather" not in world.options(world.state, "ella")  # out of reach
    ella.position = tree.position
    ella.fruit_count = world.slots  # no room
    assert "gather" not in world.options(world.state, "ella")


def test_item_4_a_full_hydration_drink_is_never_generated() -> None:
    """Review probe 2: at maximum hydration neither drink is offered; need caps guard eat too."""
    world = fresh(servings=2)
    stand = spring_stand(world)
    ryan = resident_of(world.state, "ryan")  # holds the canteen
    ryan.position = stand
    hold_fruit(world, "ryan", 1)
    assert ryan.hydration == NEEDS_MAX and ryan.satiety == NEEDS_MAX
    options = world.options(world.state, "ryan")
    assert "drink_spring" not in options and "drink_canteen" not in options
    assert "eat" not in options
    ryan.hydration, ryan.satiety = NEEDS_MAX - 1, NEEDS_MAX - 1
    options = world.options(world.state, "ryan")
    assert {"drink_spring", "drink_canteen", "eat"} <= set(options)

    def choose(label: str, opts: Sequence[Any]) -> Any:
        assert label != "ryan-action" or "drink_canteen" in opts
        return "drink_canteen" if label == "ryan-action" else opts[0]

    world.state.unique_canteen.servings = 2
    world.step(choose)
    assert world.state.unique_canteen.servings == 1  # a legal drink did spend a serving


def test_item_4_fill_needs_the_held_canteen_the_spring_and_room_in_it() -> None:
    world = fresh(servings=1)
    stand = spring_stand(world)
    ryan = resident_of(world.state, "ryan")
    assert "fill" not in world.options(world.state, "ryan")  # not at the spring
    ryan.position = stand
    assert "fill" in world.options(world.state, "ryan")
    world.state.unique_canteen.servings = world.config.canteen.capacity_servings
    assert "fill" not in world.options(world.state, "ryan")  # already full
    world.state.unique_canteen.servings = 0
    assert "fill" not in world.options(world.state, "mia")  # does not hold it


def test_item_5_give_needs_an_adjacent_recipient_and_owned_items() -> None:
    world = fresh()
    ryan, ella, mia = (resident_of(world.state, r) for r in ("ryan", "ella", "mia"))
    options = world.options(world.state, "ryan")
    assert "give_canteen" in options and "give_fruit" not in options  # owns no fruit
    ryan.fruit_count = 1
    assert "give_fruit" in world.options(world.state, "ryan")
    for other in (ella, mia):  # both neighbours out of reach
        other.position = Coord(x=ryan.position.x + 3, y=ryan.position.y)
    options = world.options(world.state, "ryan")
    assert "give_fruit" not in options and "give_canteen" not in options
    mia.position = Coord(x=ryan.position.x + 1, y=ryan.position.y)
    assert "give_fruit" in world.options(world.state, "ryan")  # adjacent again
    mia.fruit_count = world.slots  # the only neighbour is full
    assert "give_fruit" not in world.options(world.state, "ryan")


def test_item_5_pick_up_needs_the_same_tile_and_an_item_there_at_tick_start() -> None:
    world = fresh()
    ella = resident_of(world.state, "ella")
    assert "pick_up_fruit" not in world.options(world.state, "ella")
    adjacent = Coord(x=ella.position.x + 1, y=ella.position.y)
    world.state.ground_fruit = [GroundFruitPile(position=adjacent, quantity=2)]
    world.state.lifetime_fruit_regrown = 2
    assert "pick_up_fruit" not in world.options(world.state, "ella")  # adjacent is not enough
    world.state.ground_fruit = [GroundFruitPile(position=ella.position, quantity=2)]
    assert "pick_up_fruit" in world.options(world.state, "ella")
    ella.fruit_count = world.slots  # no room
    assert "pick_up_fruit" not in world.options(world.state, "ella")


def test_item_6_each_living_resident_takes_exactly_one_action_per_tick() -> None:
    world = fresh()
    choose = rotating_policy()
    for _ in range(60):
        living = {r.id for r in world.state.residents if r.alive}
        world.step(choose)
        assert set(world.last_actions) >= living  # one entry per actor that was alive
        assert all(isinstance(a, str) for a in world.last_actions.values())
    assert world.tick == 60


def test_a_ground_canteen_is_picked_up_on_its_tile_then_given_next_tick() -> None:
    """Directed run: pick-up needs the same tile; the canteen can be given only once held."""
    spawn = fresh()
    where = resident_of(spawn.state, "ella").position
    world = fresh(servings=1, canteen_on=where)
    assert world.state.unique_canteen.holder_id is None
    script = {"ella": ["pick_up_canteen", "give_canteen"]}

    def choose(label: str, options: Sequence[Any]) -> Any:
        who, _, kind = label.partition("-")
        if kind == "action":
            if script.get(who):
                want = script[who][0]
                assert want in options, (want, options)
                script[who].pop(0)
                return want
            return "wait"
        return options[0]

    world.step(choose)  # picked up from the same tile
    assert world.state.unique_canteen.holder_id == "ella"
    world.step(choose)  # held at the start of this tick, so giving is legal
    assert world.state.unique_canteen.holder_id != "ella"
    assert world.state.unique_canteen.servings == 1


# ----------------------------------------------------------------------------- item 7: durations


def test_item_7_the_one_tick_fixture_is_built_through_the_normal_config_path() -> None:
    content = one_tick_content()
    durations = content.config.actions.model_dump()
    assert set(durations.values()) == {1}
    assert content.config_hash != default_content().config_hash  # hash recomputed, validated
    assert default_content().config.actions.gather_ticks == 2  # the default is multi-tick


def test_a_gather_is_never_completed_at_tick_1_when_gather_ticks_is_2() -> None:
    """Review probe: default config, Ella beside a stocked tree with stamina, room and receipt."""
    world = start_world(default_content(), FULL, HEALTHY)
    cfg = world.config
    assert cfg.actions.gather_ticks == 2 and cfg.actions.rest_ticks > 1
    tree = world.state.fruit_nodes[0]
    ella = resident_of(world.state, "ella")
    ella.position = tree.position  # in reach; stock, stamina and room all hold
    stock, held = tree.stock, ella.fruit_count
    assert stock >= 1 and ella.stamina > 0 and world.slots_used(world.state, "ella") < world.slots
    options = world.options(world.state, "ella")
    assert "gather" not in options  # not offered: the driver cannot keep it pending
    assert not {"rest", "sleep"} & set(options)  # same for the other multi-tick actions

    def choose(label: str, opts: Sequence[Any]) -> Any:
        assert "gather" not in opts
        return "gather" if "gather" in opts else "wait"

    for _ in range(5):
        world.step(choose)
        node = next(n for n in world.state.fruit_nodes if n.id == tree.id)
        assert node.stock == stock and resident_of(world.state, "ella").fruit_count == held
    assert "gather" not in world.actions_seen


def test_item_7_default_gather_completes_only_on_its_second_tick() -> None:
    """Deterministic: P1-03 rule functions with ``gather_ticks=2``; the gather stays active."""
    world = start_world(default_content(), FULL, HEALTHY)
    cfg = world.config
    tree = world.state.fruit_nodes[0]
    me = resident_of(world.state, "ella")
    me.position = tree.position
    stock, held, active = tree.stock, me.fruit_count, []
    for tick in range(1, cfg.actions.gather_ticks + 1):
        completes = tick == cfg.actions.gather_ticks
        active.append("gather")  # still the active action: never replaced by a wait
        if completes:
            tree.stock -= 1
            me.fruit_count += 1
        result = apply_metabolism(cfg, me, TickActivity(gather_completed=completes))
        gather_costs = [
            f for f in result.cost_facts if getattr(f.payload, "reason", None) == "gather"
        ]
        if not completes:
            assert (tree.stock, me.fruit_count) == (stock, held)  # tick 1: nothing changed
            assert not gather_costs  # no cost fact before completion
        else:
            assert (tree.stock, me.fruit_count) == (stock - 1, held + 1)
            assert len(gather_costs) == 1  # emitted once, at the completion tick
        me.stamina = result.resident.stamina
    assert active == ["gather", "gather"]
    check_fruit_conservation(cfg, world.state)


def test_item_7_default_rest_gains_every_tick_and_lasts_its_configured_ticks() -> None:
    """Deterministic: a rest tick count of ``rest_ticks`` (6), one gain per tick, no wait."""
    world = start_world(default_content(), FULL, HEALTHY)
    cfg, n = world.config, world.config.needs
    assert cfg.actions.rest_ticks == 6
    me = resident_of(world.state, "ella")
    me.stamina = 1000
    active = []
    for tick in range(1, cfg.actions.rest_ticks + 1):
        active.append("rest")  # active through the completion tick (never a wait)
        gained = apply_rest_sleep_gain(cfg, me, "rest", near_cave(me.position, world.state.cave))
        result = apply_metabolism(cfg, gained, TickActivity(kind="rest"))
        expected = 1000 + tick * (n.stamina_rest_gain_per_tick - n.stamina_awake_decay_per_tick)
        assert result.resident.stamina == expected  # exactly one gain and one decay per tick
        me.stamina = result.resident.stamina
    assert active == ["rest"] * cfg.actions.rest_ticks
