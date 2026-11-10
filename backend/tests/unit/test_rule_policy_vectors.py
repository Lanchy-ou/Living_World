"""Rule Policy §10 decision vectors DV-01..DV-09 and DV-12..DV-15.

Every vector asserts, at each listed decision, the exact full ``ActionPlan`` and the complete
next ``RuleStateV0_1`` as whole canonical objects (Gate 2 G2-02). ``test_every_vector_rejects``
plants a wrong value in every leaf of every expected plan and state, one at a time, and in every
list length, and shows that ``verify`` fails each one. DV-10 and DV-11a/b are engine tests in
``test_rule_policy_scenarios.py``. The grid vectors DV-07, DV-08, DV-09 and DV-15 also assert
the stated distances from an independent BFS in the test.
"""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Any

import pytest
from rule_policy_builders import (
    bfs_distances,
    decide_step,
    empty_state,
    ent_t,
    failure,
    frontier_distances,
    heard,
    make_policy,
    mutants,
    params,
    perception,
    plan_obj,
    ref,
    res_t,
    resident,
    state_obj,
    success,
    tile_t,
    tiles,
    tree,
    verify,
)
from rule_policy_builders import config as rule_config

from living_island.agents.types import RuleStateV0_1

Steps = list[tuple[dict[str, Any], dict[str, Any]]]
VECTORS: dict[str, tuple[Callable[[], Steps], Steps]] = {}


def vector(name: str, expected: Steps) -> Callable[[Callable[[], Steps]], Callable[[], Steps]]:
    def register(run: Callable[[], Steps]) -> Callable[[], Steps]:
        VECTORS[name] = (run, expected)
        return run

    return register


def h(text: str) -> int:
    return int.from_bytes(sha256(text.encode()).digest()[:8], "big")


def base_state(**updates: Any) -> dict[str, Any]:
    return {**empty_state(), **updates}


def entry(action: str, target: Any, code: str, retry: int) -> dict[str, Any]:
    return {"action": action, "target": target, "code": code, "retry_after_tick": retry}


REST = ("rest", None, {})


def TALK_REFUSE(to, u):
    return (
        "talk",
        res_t(to),
        {"speech_act": "refuse", "text": "", "in_reply_to": u},
    )  # noqa: E731


FILL = ("fill_canteen", ent_t("canteen_01"), {})
GIVE_CANTEEN = lambda to: ("give", res_t(to), {"item_type": "canteen", "quantity": 1})  # noqa: E731
MOVE = lambda x, y: ("move_to", tile_t(x, y), {})  # noqa: E731
GATHER = lambda tree_id: ("gather", ent_t(tree_id), {})  # noqa: E731
REST_STATE = lambda ordinal, **kw: state_obj(issued_intents=[ref(ordinal, 0, "rest", None)], **kw)  # noqa: E731


def test_spec_hash_constants():
    assert h("1|a|0|rule-v0:tree") % 2 == 1
    assert h("1|a|0|rule-v0:explore") % 3 == 2
    assert h("1|a|10|rule-v0:tree") % 2 == 0


# --- DV-01 -----------------------------------------------------------------------------------

DV01_VIEW = dict(canteen=("canteen_01", 1), entities=[tree("t1", (3, 2))])


@vector(
    "DV-01",
    [
        (
            plan_obj(0, 0, [GATHER("t1"), GATHER("t1")]),
            state_obj(
                issued_intents=[
                    ref(0, 0, "gather", tile_t(3, 2)),
                    ref(0, 1, "gather", tile_t(3, 2)),
                ]
            ),
        ),
        (
            plan_obj(1, 1, [REST]),
            REST_STATE(1, failed_targets=[entry("gather", {"kind": "self"}, "INVENTORY_FULL", 37)]),
        ),
    ],
)
def run_dv01() -> Steps:
    policy = make_policy()
    first = decide_step(policy, perception(**DV01_VIEW), 0)
    feedback = failure("a:p000000:i0", "INVENTORY_FULL")
    return [first, decide_step(policy, perception(tick=1, feedback=feedback, **DV01_VIEW), 1)]


# --- DV-02a / DV-02b --------------------------------------------------------------------------

U10 = "toy:0000000010:000000"
GIVE_BACKOFF = entry("give", res_t("b"), "OUT_OF_REACH", 40)
TALK_BACKOFF = entry("talk", res_t("b"), "OUT_OF_HEARING", 40)


def _dv02(backoff: dict[str, Any]) -> Steps:
    policy = make_policy(state=base_state(failed_targets=[backoff]))
    p = perception(
        tick=10,
        canteen=("canteen_01", 2),
        entities=[resident("b", (3, 2))],
        heard_utterances=[heard(U10, "b", "request", item="canteen", quantity=1, tick=10)],
    )
    return [decide_step(policy, p, 3)]


@vector(
    "DV-02a",
    [
        (
            plan_obj(10, 3, [TALK_REFUSE("b", U10)]),
            state_obj(
                issued_intents=[ref(3, 0, "talk", res_t("b"))], failed_targets=[GIVE_BACKOFF]
            ),
        )
    ],
)
def run_dv02a() -> Steps:
    return _dv02(GIVE_BACKOFF)


@vector(
    "DV-02b",
    [(plan_obj(10, 3, [REST]), REST_STATE(3, failed_targets=[TALK_BACKOFF]))],
)
def run_dv02b() -> Steps:
    return _dv02(TALK_BACKOFF)


DEHYDRATED_B = dict(canteen=("canteen_01", 2), entities=[resident("b", (3, 2), ["dehydrated"])])


@vector(
    "DV-02a-r10",
    [
        (plan_obj(39, 4, [REST]), REST_STATE(4, failed_targets=[GIVE_BACKOFF])),
        (
            plan_obj(40, 5, [GIVE_CANTEEN("b")]),
            state_obj(issued_intents=[ref(5, 0, "give", res_t("b"))]),
        ),
    ],
)
def run_dv02a_r10() -> Steps:
    policy = make_policy(state=base_state(failed_targets=[GIVE_BACKOFF]))
    return [
        decide_step(policy, perception(tick=39, **DEHYDRATED_B), 4),
        decide_step(policy, perception(tick=40, **DEHYDRATED_B), 5),
    ]


# --- DV-03 -----------------------------------------------------------------------------------


@vector(
    "DV-03",
    [
        (plan_obj(12, 4, [REST]), REST_STATE(4)),
        (
            plan_obj(13, 5, [TALK_REFUSE("b", "toy:0000000013:000000")]),
            state_obj(issued_intents=[ref(5, 0, "talk", res_t("b"))]),
        ),
    ],
)
def run_dv03() -> Steps:
    refs = [ref(3, 0, "talk", res_t("b")), ref(3, 1, "give", res_t("b"))]
    policy = make_policy(state=base_state(issued_intents=refs))
    first = decide_step(policy, perception(tick=12, feedback=failure("a:p000003:i1", "NO_ITEM")), 4)
    ask = heard("toy:0000000013:000000", "b", "request", item="canteen", quantity=1, tick=13)
    view = perception(tick=13, entities=[resident("b", (3, 2))], heard_utterances=[ask])
    return [first, decide_step(policy, view, 5)]


# --- DV-04 .. DV-06 fill probe ----------------------------------------------------------------

SPRING_GRID = tiles(overrides={(3, 2): "spring"})
SPRING_VIEW = dict(
    explored=SPRING_GRID,
    visible_tiles=[t for t in SPRING_GRID if (t.position.x, t.position.y) == (3, 2)],
)
PROBE_STATE = state_obj(issued_intents=[ref(0, 0, "fill_canteen", ent_t("canteen_01"))])


def _learned(capacity: int, ordinal: int = 1, tick: int = 1, **kw: Any) -> tuple[Any, Any]:
    return plan_obj(tick, ordinal, [REST]), REST_STATE(ordinal, canteen_capacity=capacity, **kw)


@vector("DV-04", [(plan_obj(0, 0, [FILL]), PROBE_STATE), _learned(2)])
def run_dv04() -> Steps:
    policy = make_policy()
    first = decide_step(policy, perception(canteen=("canteen_01", 0), **SPRING_VIEW), 0)
    view = perception(
        tick=1, canteen=("canteen_01", 2), feedback=success("a:p000000:i0"), **SPRING_VIEW
    )
    return [first, decide_step(policy, view, 1)]


@vector("DV-05-partial", [(plan_obj(0, 0, [FILL]), PROBE_STATE), _learned(2)])
def run_dv05_partial() -> Steps:
    policy = make_policy()
    first = decide_step(policy, perception(canteen=("canteen_01", 1), **SPRING_VIEW), 0)
    view = perception(
        tick=1, canteen=("canteen_01", 2), feedback=success("a:p000000:i0"), **SPRING_VIEW
    )
    return [first, decide_step(policy, view, 1)]


@vector("DV-05-full", [(plan_obj(0, 0, [FILL]), PROBE_STATE), _learned(2)])
def run_dv05_full() -> Steps:
    policy = make_policy()
    first = decide_step(policy, perception(canteen=("canteen_01", 2), **SPRING_VIEW), 0)
    feedback = failure("a:p000000:i0", "ALREADY_FULL")
    view = perception(tick=1, canteen=("canteen_01", 2), feedback=feedback, **SPRING_VIEW)
    return [first, decide_step(policy, view, 1)]


@vector(
    "DV-06",
    [(plan_obj(0, 0, [FILL]), PROBE_STATE)] + [_learned(0, ordinal=t, tick=t) for t in (1, 2, 3)],
)
def run_dv06() -> Steps:
    policy = make_policy()
    steps = [decide_step(policy, perception(canteen=("canteen_01", 0), **SPRING_VIEW), 0)]
    for tick in (1, 2, 3):
        feedback = failure("a:p000000:i0", "ALREADY_FULL") if tick == 1 else None
        view = perception(tick=tick, canteen=("canteen_01", 0), feedback=feedback, **SPRING_VIEW)
        steps.append(decide_step(policy, view, tick))
    return steps


# --- DV-07 unreachable frontier ---------------------------------------------------------------

DV07_TILES = {
    (0, 0): "grass",
    (0, 1): "grass",
    (1, 0): "rock",
    (1, 1): "rock",
    (0, 2): "rock",
    (3, 3): "grass",
}


@vector("DV-07", [(plan_obj(0, 0, [REST]), REST_STATE(0))])
def run_dv07() -> Steps:
    explored = tiles(overrides={**{(x, y): "-" for x in range(8) for y in range(8)}, **DV07_TILES})
    cells = {(t.position.x, t.position.y) for t in explored}
    passable = {c for c in cells if DV07_TILES[c] == "grass"}
    assert passable == {(0, 0), (0, 1), (3, 3)}
    dist = bfs_distances(passable, (0, 0))
    assert dist == {(0, 0): 0, (0, 1): 1}  # (3,3) has no BFS distance
    assert frontier_distances(cells, passable, (0, 0), 8, 8) == {}
    return [decide_step(make_policy(), perception(pos=(0, 0), explored=explored), 0)]


# --- DV-08 shared stand dedup -----------------------------------------------------------------


@vector(
    "DV-08",
    [
        (
            plan_obj(0, 0, [MOVE(1, 1)]),
            state_obj(
                commitment={"goal": "tree", "target": {"x": 1, "y": 1}, "set_at_tick": 0},
                issued_intents=[ref(0, 0, "move_to", tile_t(1, 1))],
            ),
        )
    ],
)
def run_dv08() -> Steps:
    overrides = {(2, 1): "fruit_tree", (2, 3): "fruit_tree"}
    explored = tiles(overrides=overrides)
    cells = {(t.position.x, t.position.y): t.terrain for t in explored}
    passable = {c for c, name in cells.items() if name != "spring" and name != "rock"}
    dist = bfs_distances(passable, (0, 0))
    stands = {
        c: dist[c]
        for c in dist
        if any(
            n in overrides
            for n in ((c[0], c[1] - 1), (c[0] + 1, c[1]), (c[0], c[1] + 1), (c[0] - 1, c[1]))
        )
    }
    assert stands == {
        (2, 0): 2, (1, 1): 2, (3, 1): 4, (2, 2): 4,
        (1, 3): 4, (3, 3): 6, (2, 4): 6,
    }  # fmt: skip
    assert len(stands) == 7
    best = sorted((c for c, d in stands.items() if d == 2), key=lambda c: (c[1], c[0]))
    assert best == [(2, 0), (1, 1)]
    return [decide_step(make_policy(), perception(pos=(0, 0), explored=explored), 0)]


# --- DV-09 cue filter over a commitment -------------------------------------------------------

IMPRESSION = {
    "cue_id": "moss",
    "position": {"x": 3, "y": 3},
    "detail_level": "near",
    "direction": "east",
}
COMMITTED_WEST = {"goal": "explore", "target": {"x": 0, "y": 4}, "set_at_tick": 0}


def _dv09_view() -> Any:
    explored = [t for t in tiles() if 1 <= t.position.x <= 5 and 3 <= t.position.y <= 5]
    cells = {(t.position.x, t.position.y) for t in explored}
    frontier = frontier_distances(cells, cells, (3, 4), 8, 8)
    assert frontier[(0, 4)] == 3
    east = {c: d for c, d in frontier.items() if c[0] > 3}
    assert east == {
        (4, 2): 3, (5, 2): 4, (6, 3): 4, (6, 4): 3, (6, 5): 4, (4, 6): 3, (5, 6): 4,
    }  # fmt: skip
    best = sorted((c for c, d in east.items() if d == 3), key=lambda c: (c[1], c[0]))
    assert best == [(4, 2), (6, 4), (4, 6)]
    assert h("1|a|0|rule-v0:explore") % 3 == 2
    return perception(pos=(3, 4), explored=explored)


@vector(
    "DV-09",
    [
        (
            plan_obj(0, 0, [MOVE(4, 6)]),
            state_obj(
                commitment={"goal": "explore", "target": {"x": 4, "y": 6}, "set_at_tick": 0},
                issued_intents=[ref(0, 0, "move_to", tile_t(4, 6))],
                cue_impressions=[IMPRESSION],
            ),
        )
    ],
)
def run_dv09() -> Steps:
    policy = make_policy(state=base_state(commitment=COMMITTED_WEST, cue_impressions=[IMPRESSION]))
    return [decide_step(policy, _dv09_view(), 0)]


@vector(
    "DV-09-s5-ignored",
    [
        (
            plan_obj(0, 0, [MOVE(0, 4)]),
            state_obj(
                commitment=COMMITTED_WEST,
                issued_intents=[ref(0, 0, "move_to", tile_t(0, 4))],
                cue_impressions=[IMPRESSION],
            ),
        )
    ],
)
def run_dv09_ignored() -> Steps:
    cfg = rule_config(rule=params(cue_use="ignored"))
    policy = make_policy(cfg, base_state(commitment=COMMITTED_WEST, cue_impressions=[IMPRESSION]))
    return [decide_step(policy, _dv09_view(), 0)]


# --- DV-12, DV-13 -----------------------------------------------------------------------------


@vector("DV-12", [(plan_obj(0, 0, [REST]), REST_STATE(0))])
def run_dv12() -> Steps:
    return [decide_step(make_policy(), perception(hydration="low"), 0)]


@vector("DV-13", [(plan_obj(20, 8, [REST]), REST_STATE(8))])
def run_dv13() -> Steps:
    refs = [ref(6, 0, "move_to", tile_t(3, 3))]
    policy = make_policy(state=base_state(issued_intents=refs))
    feedback = failure("a:p000007:i0", "NO_PATH")
    return [decide_step(policy, perception(tick=20, feedback=feedback), 8)]


# --- DV-14 ------------------------------------------------------------------------------------

REGROWN = entry("gather", tile_t(3, 2), "RESOURCE_TAKEN", 180)


@vector(
    "DV-14",
    [
        (plan_obj(144, 5, [REST]), REST_STATE(5, failed_targets=[REGROWN])),
        (plan_obj(179, 6, [REST]), REST_STATE(6, failed_targets=[REGROWN])),
        (
            plan_obj(180, 7, [GATHER("t1")]),
            state_obj(issued_intents=[ref(7, 0, "gather", tile_t(3, 2))]),
        ),
    ],
)
def run_dv14() -> Steps:
    refs = [ref(4, 0, "gather", tile_t(3, 2))]
    policy = make_policy(state=base_state(issued_intents=refs))
    view = dict(entities=[tree("t1", (3, 2), "few")])
    feedback = failure("a:p000004:i0", "RESOURCE_TAKEN")
    return [
        decide_step(policy, perception(tick=144, feedback=feedback, **view), 5),
        decide_step(policy, perception(tick=179, **view), 6),
        decide_step(policy, perception(tick=180, **view), 7),
    ]


# --- DV-15 ------------------------------------------------------------------------------------

DV15_LOCAL = [(x, y) for y in range(7) for x in range(9)] + [(1, 7)]
DV15_FAILURE = entry("move_to", tile_t(0, 7), "NO_PATH", 90)


@vector(
    "DV-15",
    [
        (
            plan_obj(80, 10, [MOVE(1, 0)]),
            state_obj(
                commitment={"goal": "tree", "target": {"x": 1, "y": 0}, "set_at_tick": 80},
                issued_intents=[ref(10, 0, "move_to", tile_t(1, 0))],
                failed_targets=[
                    entry("gather", tile_t(x, y), "OBSERVED_EMPTY", 100) for x, y in DV15_LOCAL[1:]
                ]
                + [entry("gather", tile_t(8, 7), "OBSERVED_EMPTY", 116), DV15_FAILURE],
            ),
        )
    ],
)
def run_dv15() -> Steps:
    overrides = {(x, y): "fruit_tree" for x in range(9) for y in range(7)}
    overrides.update({(1, 7): "fruit_tree", (8, 7): "fruit_tree"})
    explored = tiles(9, 8, overrides)
    cells = {(t.position.x, t.position.y) for t in explored}
    passable = {(t.position.x, t.position.y) for t in explored}  # fruit_tree and grass
    dist = bfs_distances(passable, (4, 7))
    assert (dist[(1, 0)], dist[(0, 1)]) == (10, 10)
    assert len(cells) == 72 and len(DV15_LOCAL) == 64
    prior = [entry("gather", tile_t(x, y), "OBSERVED_EMPTY", 100) for x, y in DV15_LOCAL]
    prior.append(DV15_FAILURE)
    policy = make_policy(rule_config(width=9, height=8), base_state(failed_targets=prior))
    view = perception(
        tick=80, pos=(4, 7), explored=explored, entities=[tree("t65", (8, 7), "empty")]
    )
    steps = [decide_step(policy, view, 10)]
    RuleStateV0_1.model_validate(steps[0][1])
    return steps


# --- the tests --------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(VECTORS))
def test_vector_matches_whole_plan_and_state(name):
    run, expected = VECTORS[name]
    verify(run(), expected)


def test_all_spec_vectors_are_present():
    spec = {
        "DV-01", "DV-02a", "DV-02b", "DV-03", "DV-04", "DV-05-partial", "DV-05-full", "DV-06",
        "DV-07", "DV-08", "DV-09", "DV-12", "DV-13", "DV-14", "DV-15",
    }  # fmt: skip
    assert spec <= set(VECTORS)


@pytest.mark.parametrize("name", sorted(VECTORS))
def test_every_vector_rejects_a_planted_wrong_plan_or_state(name):
    run, expected = VECTORS[name]
    actual = run()
    checked = 0
    for i, (plan, state) in enumerate(expected):
        for wrong in mutants(plan):
            planted = [*expected[:i], (wrong, state), *expected[i + 1 :]]
            with pytest.raises(AssertionError, match=f"plan of decision {i}"):
                verify(actual, planted)
            checked += 1
        for wrong in mutants(state):
            planted = [*expected[:i], (plan, wrong), *expected[i + 1 :]]
            with pytest.raises(AssertionError, match=f"state of decision {i}"):
                verify(actual, planted)
            checked += 1
    assert checked > 10
