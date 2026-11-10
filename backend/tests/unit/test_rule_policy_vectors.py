"""Rule Policy §10 decision vectors DV-01..DV-09 and DV-12..DV-15 (exact plans and states).

DV-10 and DV-11a/b are engine integration tests in ``test_rule_policy_scenarios.py``.
"""

from __future__ import annotations

from hashlib import sha256

from rule_policy_builders import config as rule_config
from rule_policy_builders import (
    empty_state,
    failed,
    failure,
    heard,
    make_policy,
    params,
    perception,
    res_t,
    resident,
    step,
    success,
    tile_t,
    tiles,
    tree,
)

from living_island.agents.types import RuleStateV0_1

WAIT_REST = [("rest", None, {})]


def h(text: str) -> int:
    return int.from_bytes(sha256(text.encode()).digest()[:8], "big")


def state(**updates):
    return {**empty_state(), **updates}


def talk(act, to, **extra):
    return ("talk", to, {"speech_act": act, "text": "", **extra})


def test_spec_hash_constants():
    assert h("1|a|0|rule-v0:tree") % 2 == 1
    assert h("1|a|0|rule-v0:explore") % 3 == 2
    assert h("1|a|10|rule-v0:tree") % 2 == 0


def test_dv01_slot_capacity_one():
    policy = make_policy()
    view = dict(canteen=("canteen_01", 1), entities=[tree("t1", (3, 2))])
    plan, saved = step(policy, perception(**view), 0)
    assert plan == [("gather", "t1", {}), ("gather", "t1", {})]
    assert saved["issued_intents"] == [
        {"intent_id": "a:p000000:i0", "action_type": "gather", "target": tile_t(3, 2)},
        {"intent_id": "a:p000000:i1", "action_type": "gather", "target": tile_t(3, 2)},
    ]
    plan, saved = step(
        policy, perception(tick=1, feedback=failure("a:p000000:i0", "INVENTORY_FULL"), **view), 1
    )
    assert plan == WAIT_REST
    assert saved["failed_targets"] == failed([("gather", {"kind": "self"}, "INVENTORY_FULL", 37)])


def _dv02(entry):
    policy = make_policy(state=state(failed_targets=[entry]))
    p = perception(
        tick=10,
        canteen=("canteen_01", 2),
        entities=[resident("b", (3, 2))],
        heard_utterances=[
            heard("toy:0000000010:000000", "b", "request", item="canteen", quantity=1, tick=10)
        ],
    )
    return step(policy, p, 3)


def test_dv02a_give_backoff_refuses_and_keeps_entry():
    entry = failed([("give", res_t("b"), "OUT_OF_REACH", 40)])[0]
    plan, saved = _dv02(entry)
    assert plan == [talk("refuse", "b", in_reply_to="toy:0000000010:000000")]
    assert saved["failed_targets"] == [entry]


def test_dv02a_r10_stays_blocked_until_expiry():
    entry = failed([("give", res_t("b"), "OUT_OF_REACH", 40)])[0]
    policy = make_policy(state=state(failed_targets=[entry]))
    signs = ["dehydrated"]
    view = dict(canteen=("canteen_01", 2), entities=[resident("b", (3, 2), signs)])
    assert step(policy, perception(tick=39, **view), 4)[0] == WAIT_REST
    plan, saved = step(policy, perception(tick=40, **view), 5)
    assert plan == [("give", "b", {"item_type": "canteen", "quantity": 1})]
    assert saved["failed_targets"] == []


def test_dv02b_talk_backoff_leaves_request_unanswered():
    entry = failed([("talk", res_t("b"), "OUT_OF_HEARING", 40)])[0]
    plan, saved = _dv02(entry)
    assert plan == WAIT_REST
    assert saved["failed_targets"] == [entry]


def test_dv03_give_no_item_is_not_a_backoff():
    refs = [
        {"intent_id": "a:p000003:i0", "action_type": "talk", "target": res_t("b")},
        {"intent_id": "a:p000003:i1", "action_type": "give", "target": res_t("b")},
    ]
    policy = make_policy(state=state(issued_intents=refs))
    plan, saved = step(policy, perception(tick=12, feedback=failure("a:p000003:i1", "NO_ITEM")), 4)
    assert plan == WAIT_REST
    assert saved["failed_targets"] == []
    ask = heard("toy:0000000013:000000", "b", "request", item="canteen", quantity=1, tick=13)
    plan, _ = step(
        policy, perception(tick=13, entities=[resident("b", (3, 2))], heard_utterances=[ask]), 5
    )
    assert plan == [talk("refuse", "b", in_reply_to="toy:0000000013:000000")]


SPRING = {(3, 2): "spring"}


def _spring_view(**kw):
    grid = tiles(overrides=SPRING)
    return dict(
        explored=grid,
        visible_tiles=[t for t in grid if (t.position.x, t.position.y) == (3, 2)],
        **kw,
    )


def test_dv04_fill_probe_empty():
    policy = make_policy()
    plan, _ = step(policy, perception(canteen=("canteen_01", 0), **_spring_view()), 0)
    assert plan == [("fill_canteen", "canteen_01", {})]
    plan, saved = step(
        policy,
        perception(
            tick=1, canteen=("canteen_01", 2), feedback=success("a:p000000:i0"), **_spring_view()
        ),
        1,
    )
    assert saved["canteen_capacity"] == 2
    assert plan == WAIT_REST


def test_dv05_fill_probe_partial_and_full():
    partial = make_policy()
    plan, _ = step(partial, perception(canteen=("canteen_01", 1), **_spring_view()), 0)
    assert plan == [("fill_canteen", "canteen_01", {})]
    plan, saved = step(
        partial,
        perception(
            tick=1, canteen=("canteen_01", 2), feedback=success("a:p000000:i0"), **_spring_view()
        ),
        1,
    )
    assert (plan, saved["canteen_capacity"]) == (WAIT_REST, 2)

    full = make_policy()
    plan, _ = step(full, perception(canteen=("canteen_01", 2), **_spring_view()), 0)
    assert plan == [("fill_canteen", "canteen_01", {})]
    plan, saved = step(
        full,
        perception(
            tick=1,
            canteen=("canteen_01", 2),
            feedback=failure("a:p000000:i0", "ALREADY_FULL"),
            **_spring_view(),
        ),
        1,
    )
    assert (plan, saved["canteen_capacity"], saved["failed_targets"]) == (WAIT_REST, 2, [])


def test_dv06_capacity_zero_never_fills_again():
    policy = make_policy()
    plan, _ = step(policy, perception(canteen=("canteen_01", 0), **_spring_view()), 0)
    assert plan == [("fill_canteen", "canteen_01", {})]
    for tick in (1, 2, 3):
        feedback = failure("a:p000000:i0", "ALREADY_FULL") if tick == 1 else None
        plan, saved = step(
            policy,
            perception(tick=tick, canteen=("canteen_01", 0), feedback=feedback, **_spring_view()),
            tick,
        )
        assert saved["canteen_capacity"] == 0
        assert plan == WAIT_REST


def test_dv07_unreachable_frontier():
    explored = tiles(
        overrides={
            **{(x, y): "-" for x in range(8) for y in range(8)},
            (0, 0): "grass",
            (0, 1): "grass",
            (1, 0): "rock",
            (1, 1): "rock",
            (0, 2): "rock",
            (3, 3): "grass",
        }
    )
    assert len(explored) == 6
    plan, saved = step(make_policy(), perception(pos=(0, 0), explored=explored), 0)
    assert plan == WAIT_REST
    assert saved["commitment"] is None


def test_dv08_shared_stand_dedup():
    explored = tiles(overrides={(2, 1): "fruit_tree", (2, 3): "fruit_tree"})
    plan, saved = step(make_policy(), perception(pos=(0, 0), explored=explored), 0)
    assert plan == [("move_to", (1, 1), {})]
    assert saved["commitment"] == {"goal": "tree", "target": {"x": 1, "y": 1}, "set_at_tick": 0}


IMPRESSION = {
    "cue_id": "moss",
    "position": {"x": 3, "y": 3},
    "detail_level": "near",
    "direction": "east",
}
COMMITTED_WEST = {"goal": "explore", "target": {"x": 0, "y": 4}, "set_at_tick": 0}


def test_dv09_cue_filter_overrides_commitment():
    explored = [t for t in tiles() if 1 <= t.position.x <= 5 and 3 <= t.position.y <= 5]
    policy = make_policy(state=state(commitment=COMMITTED_WEST, cue_impressions=[IMPRESSION]))
    plan, saved = step(policy, perception(pos=(3, 4), explored=explored), 0)
    assert plan == [("move_to", (4, 6), {})]
    assert saved["commitment"] == {"goal": "explore", "target": {"x": 4, "y": 6}, "set_at_tick": 0}
    # S5 contrast: with the cue ignored the committed frontier (0,4) is kept.
    ignored = make_policy(
        rule_config(rule=params(cue_use="ignored")),
        state(commitment=COMMITTED_WEST, cue_impressions=[IMPRESSION]),
    )
    plan, saved = step(ignored, perception(pos=(3, 4), explored=explored), 0)
    assert plan == [("move_to", (0, 4), {})]
    assert saved["commitment"] == COMMITTED_WEST


def test_dv12_empty_domain_fall_through_in_r6():
    plan, _ = step(make_policy(), perception(hydration="low"), 0)
    assert plan == WAIT_REST


def test_dv13_unmatched_feedback():
    refs = [{"intent_id": "a:p000006:i0", "action_type": "move_to", "target": tile_t(3, 3)}]
    policy = make_policy(state=state(issued_intents=refs))
    plan, saved = step(policy, perception(tick=20, feedback=failure("a:p000007:i0", "NO_PATH")), 8)
    assert plan == WAIT_REST
    assert saved["failed_targets"] == []


def test_dv14_failure_then_same_tick_regrowth():
    refs = [{"intent_id": "a:p000004:i0", "action_type": "gather", "target": tile_t(3, 2)}]
    policy = make_policy(state=state(issued_intents=refs))
    view = dict(entities=[tree("t1", (3, 2), "few")])
    feedback = failure("a:p000004:i0", "RESOURCE_TAKEN")
    plan, saved = step(policy, perception(tick=144, feedback=feedback, **view), 5)
    entry = failed([("gather", tile_t(3, 2), "RESOURCE_TAKEN", 180)])
    assert (plan, saved["failed_targets"]) == (WAIT_REST, entry)
    plan, saved = step(policy, perception(tick=179, **view), 6)
    assert (plan, saved["failed_targets"]) == (WAIT_REST, entry)
    plan, saved = step(policy, perception(tick=180, **view), 7)
    assert plan == [("gather", "t1", {})]
    assert saved["failed_targets"] == []


def test_dv15_local_cap_never_evicts_a_failure():
    overrides = {(x, y): "fruit_tree" for x in range(9) for y in range(7)}
    overrides.update({(1, 7): "fruit_tree", (8, 7): "fruit_tree"})
    explored = tiles(9, 8, overrides)
    local_tiles = [(x, y) for y in range(7) for x in range(9)] + [(1, 7)]
    assert len(local_tiles) == 64
    prior = failed([("gather", tile_t(x, y), "OBSERVED_EMPTY", 100) for x, y in local_tiles])
    prior.append(failed([("move_to", tile_t(0, 7), "NO_PATH", 90)])[0])
    policy = make_policy(rule_config(width=9, height=8), state(failed_targets=prior))
    p = perception(tick=80, pos=(4, 7), explored=explored, entities=[tree("t65", (8, 7), "empty")])
    plan, saved = step(policy, p, 10)
    expected = failed(
        [("gather", tile_t(x, y), "OBSERVED_EMPTY", 100) for x, y in local_tiles[1:]]
        + [("gather", tile_t(8, 7), "OBSERVED_EMPTY", 116)]
        + [("move_to", tile_t(0, 7), "NO_PATH", 90)]
    )
    assert saved["failed_targets"] == expected
    assert plan == [("move_to", (1, 0), {})]
    assert saved["commitment"] == {"goal": "tree", "target": {"x": 1, "y": 0}, "set_at_tick": 80}
    RuleStateV0_1.model_validate(saved)
