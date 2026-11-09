"""Property tests over physically legal sequences of the P1-03 rule functions (WR §8 1-3).

Every generated sequence is legal: one progressing action per living resident per tick, chosen
from the actions legal at that moment (reach, ownership, room, own-tile drops and pick-ups; see
``legal_world.py``). Regrowth periods, phase offsets and stock bounds vary over legal content,
and a long default-content run crosses every default regrowth phase. Illegal and synthetic
stress sequences live in ``test_physical_rules_properties.py`` under their own names.

Hypothesis strategy summary:

* content: ``None`` (the default 144-tick content) or a legal variant with ``regrow_ticks`` in
  2..16, six offsets drawn in ``0..regrow_ticks-1``, ``regrow_per_cycle`` 1..3, and
  ``initial_stock <= max_stock`` in 0..6;
* start: three needs per resident in 0..max, health 1..10000 biased low so deaths occur,
  canteen servings 0..2;
* each rule advances 1..15 ticks; every action, target, destination, step count, quantity and
  recipient is drawn from the legal options at that moment.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule
from legal_world import LegalWorld, start_world, variant_content
from world_builders import default_content

from living_island.world.content import WorldContent

NEEDS_MAX = default_content().config.needs.max_value


@st.composite
def legal_variant(draw: st.DrawFn) -> WorldContent | None:
    if draw(st.booleans()):
        return None  # default content: period 144, offsets 0/24/48/72/96/120
    period = draw(st.integers(2, 16))
    offsets = [draw(st.integers(0, period - 1)) for _ in range(6)]
    max_stock = draw(st.integers(1, 6))
    return variant_content(
        regrow_ticks=period,
        offsets=offsets,
        per_cycle=draw(st.integers(1, 3)),
        initial_stock=draw(st.integers(0, max_stock)),
        max_stock=max_stock,
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
    )
    def start(
        self, variant: WorldContent | None, needs: list[int], health: list[int], servings: int
    ) -> None:
        self.world = start_world(variant or default_content(), needs, health, servings)

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
    content = default_content()
    world = start_world(content, [NEEDS_MAX] * 9, [NEEDS_MAX] * 3)
    choose = rotating_policy()
    for _ in range(400):
        world.step(choose)
    expected = {
        "idle", "rest", "sleep", "move", "gather", "eat", "drink_spring", "give_fruit",
        "give_canteen", "drop_fruit", "pick_up_fruit", "drop_canteen", "pick_up_canteen",
    }  # fmt: skip
    assert expected <= world.actions_seen, expected - world.actions_seen


@settings(max_examples=6, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_default_run_crosses_every_regrowth_phase_and_stays_consistent(
    data: st.DataObject,
) -> None:
    """300 ticks of random legal play: offsets 72/96/120 and phase-0 at 144 all regrow."""
    content = default_content()
    world = start_world(content, [NEEDS_MAX] * 9, [NEEDS_MAX] * 3)

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


def test_scripted_long_run_reaches_the_late_default_phases() -> None:
    """Deterministic backstop: with trees kept below the cap, 72, 96, 120 and 144 all fire."""
    content = default_content()
    world = start_world(content, [NEEDS_MAX] * 9, [NEEDS_MAX] * 3)
    choose = rotating_policy()
    for _ in range(300):
        world.step(choose)
    fired = {t for ticks in world.regrowth_ticks.values() for t in ticks}
    assert {72, 96, 120, 144} <= fired


def test_canteen_use_at_the_spring_follows_the_legal_script() -> None:
    """Directed run: the holder walks to the spring, drinks a serving, then fills the canteen."""
    content = default_content()
    world = start_world(content, [NEEDS_MAX] * 9, [NEEDS_MAX] * 3, servings=1)
    holder = world.state.unique_canteen.holder_id
    assert holder is not None
    stand = next(
        s for s in world.sites if abs(s.x - world.spring.x) + abs(s.y - world.spring.y) <= 1
    )
    plan = ["move", "drink_canteen", "fill"]
    seen: list[str] = []

    def choose(label: str, options: Sequence[Any]) -> Any:
        who, _, kind = label.partition("-")
        if kind == "action":
            if who != holder or not plan:
                return "idle"
            want = plan[0]
            assert want in options, (want, options)  # the script is legal at each step
            plan.pop(0)
            seen.append(want)
            return want
        if kind == "site":
            return stand
        return options[0]

    for _ in range(3):
        world.step(choose)
    assert seen == ["move", "drink_canteen", "fill"]
    assert world.state.unique_canteen.servings == content.config.canteen.capacity_servings
