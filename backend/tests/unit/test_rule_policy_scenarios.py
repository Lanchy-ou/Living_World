"""rule-based-v0 through the real engine: DV-10, DV-11a/b, canteen, back-off, S4/S5 switches."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from rule_policy_builders import (
    config as rule_config,
)
from rule_policy_builders import (
    empty_state,
    failed,
    ground_canteen,
    make_policy,
    mutants,
    params,
    perception,
    plan_obj,
    ref,
    resident,
    state_obj,
    step,
    tile_t,
    tiles,
    verify,
)
from rule_policy_checks import no_repeat_violations
from test_sim_runtime import ROWS, WaitPolicy
from world_builders import WORLDS, default_content, p1_default_content, tiny_content

from living_island.agents.policies._plans import make_plan
from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.runtime import Runtime
from living_island.agents.types import (
    IntentTemplate,
    IssuedIntent,
    OkOutcome,
    OwnProfile,
    PolicyConfig,
)
from living_island.persistence.content import load_world_content
from living_island.sim.boundary import BoundaryLoop
from living_island.world.content import WorldContent, build_world_content, map_bytes_from_rows
from living_island.world.ports import create_engine
from living_island.world.protocol import (
    Coord,
    EmptyParameters,
    EntityTarget,
    TileTarget,
)

PROFILE = OwnProfile(profile_id="p", initial_goal="g")


def variant(residents: dict[str, tuple[int, int]] | None = None, **sections: dict[str, Any]):
    """Default-island content with some sections and resident positions replaced."""
    base = default_content()
    data = copy.deepcopy(base.config.model_dump(mode="json"))
    for name, values in sections.items():
        data[name].update(values)
    for r in data["residents"]:
        if residents and r["id"] in residents:
            r["position"] = list(residents[r["id"]])
    return build_world_content(data, map_bytes_from_rows(base.map_rows))


def policy_config(content: WorldContent, **rule: Any) -> PolicyConfig:
    return rule_config(
        width=content.config.map.width,
        height=content.config.map.height,
        seed=content.config.meta.seed,
        max_plan=content.config.agents.max_plan_actions,
        rule=params(**rule),
    )


class Injected(RuleBasedPolicy):
    """A rule policy whose first plan is injected (a scripted opening); later ones are real."""

    def __init__(self, cfg: PolicyConfig, first: list[IntentTemplate], refs: list[IssuedIntent]):
        super().__init__(cfg)
        self._first, self._refs = first, refs
        self.packets: dict[int, Any] = {}  # decision tick -> the perception it decided on

    def decide(self, request: Any) -> OkOutcome:
        self.packets[request.tick] = request.context.perception
        outcome = super().decide(request)
        if request.decision_ordinal != 0:
            return outcome
        assert self._pending is not None
        self._pending = self._pending.model_copy(
            update={"issued_intents": self._refs, "commitment": None}
        )
        return outcome.model_copy(update={"plan": make_plan(request, self._first)})


def move_template(x: int, y: int) -> IntentTemplate:
    return IntentTemplate(
        action_type="move_to",
        target=TileTarget(kind="tile", position=Coord(x=x, y=y)),
        parameters=EmptyParameters(),
        reason=None,
    )


def build_loop(content: WorldContent, policies: dict[str, Any], cfg: PolicyConfig):
    runtimes = {
        actor: Runtime(actor, cfg, PROFILE, policies.get(actor) or WaitPolicy())
        for actor in (r.id for r in content.config.residents)
    }
    return BoundaryLoop(create_engine(content, None), list(runtimes.values())), runtimes


def advance_until(loop, actor: str, ordinal: int, limit: int = 40):
    """Advance until ``actor``'s decision with this ordinal exists; return (commit, record)."""
    for _ in range(limit):
        commit, records = loop.advance()
        for record in records:
            if record.actor_id == actor and record.decision_ordinal == ordinal:
                return commit, record
    raise AssertionError("decision not reached")


def committed(runtime: Runtime) -> dict[str, Any]:
    return runtime.export_state().policy_state  # type: ignore[return-value]


NEAR_EAST = ("moss_east_01", "near", "east")
DISTANT = ("moss_east_01", "distant", None)


def _impression(detail: str = "near", direction: str | None = "east") -> dict[str, Any]:
    return {
        "cue_id": "moss_east_01",
        "position": {"x": 15, "y": 32},
        "detail_level": detail,
        "direction": direction,
    }


def _cues(perception: Any) -> list[tuple[str, str, str | None]]:
    return [(c.cue_id, c.detail_level, c.direction) for c in perception.environmental_cues]


def _record_pair(runtime: Runtime, record: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    return record.plan.model_dump(mode="json"), committed(runtime)


def _tile_move(actor: str, ordinal: int, x: int, y: int, tick: int):
    return plan_obj(tick, ordinal, [("move_to", tile_t(x, y), {})], actor=actor)


def _assert_whole_objects_and_rejections(steps: Any, expected: Any) -> None:
    verify(steps, expected)
    for i, (plan, state) in enumerate(expected):
        for wrong in mutants(plan):
            with pytest.raises(AssertionError, match=f"plan of decision {i}"):
                verify(steps, [*expected[:i], (wrong, state), *expected[i + 1 :]])
        for wrong in mutants(state):
            with pytest.raises(AssertionError, match=f"state of decision {i}"):
                verify(steps, [*expected[:i], (plan, wrong), *expected[i + 1 :]])


# DV-11 expectations. The tick-0 plan is injected; the tick-1 plan is the rule policy's own
# (R8b tree stand, which precedes exploration). Both are pinned as whole objects.
DV11 = {
    "dv11a-interrupted-move": dict(
        target=(21, 32),
        triggers={"ACTION_INTERRUPTED", "NEW_SIGHT"},
        position=(20, 32),
        expected=[
            (
                _tile_move("ella", 0, 21, 32, 0),
                state_obj(
                    issued_intents=[ref(0, 0, "move_to", tile_t(21, 32), "ella")],
                    cue_impressions=[_impression("distant", None)],
                ),
            ),
            (
                _tile_move("ella", 1, 17, 36, 1),
                state_obj(
                    commitment={"goal": "tree", "target": {"x": 17, "y": 36}, "set_at_tick": 1},
                    issued_intents=[ref(1, 0, "move_to", tile_t(17, 36), "ella")],
                    cue_impressions=[_impression()],
                ),
            ),
        ],
    ),
    "dv11b-completed-move": dict(
        target=(16, 32),
        triggers={"NEW_SIGHT", "PLAN_FINISHED"},
        position=(16, 32),
        expected=[
            (
                _tile_move("ella", 0, 16, 32, 0),
                state_obj(
                    issued_intents=[ref(0, 0, "move_to", tile_t(16, 32), "ella")],
                    cue_impressions=[_impression("distant", None)],
                ),
            ),
            (
                _tile_move("ella", 1, 16, 35, 1),
                state_obj(
                    commitment={"goal": "tree", "target": {"x": 16, "y": 35}, "set_at_tick": 1},
                    issued_intents=[ref(1, 0, "move_to", tile_t(16, 35), "ella")],
                    cue_impressions=[_impression()],
                ),
            ),
        ],
    ),
}


def run_dv11(case: dict[str, Any]):
    target = case["target"]
    content = p1_default_content()
    cfg = policy_config(content)
    refs = [
        IssuedIntent(
            intent_id="ella:p000000:i0",
            action_type="move_to",
            target=TileTarget(kind="tile", position=Coord(x=target[0], y=target[1])),
        )
    ]
    ella = Injected(cfg, [move_template(*target)], refs)
    loop, runtimes = build_loop(content, {"ella": ella}, cfg)
    steps = []
    triggers: dict[int, Any] = {}
    for _ in range(40):
        _, records = loop.advance()
        for record in records:
            if record.actor_id == "ella":
                steps.append(_record_pair(runtimes["ella"], record))
                triggers[record.tick] = set(record.triggers)
        if len(steps) == 2:
            break
    return steps, triggers, {t: _cues(p) for t, p in ella.packets.items()}, ella.packets[1]


@pytest.mark.parametrize("name", sorted(DV11))
def test_dv11_decision_captures_near_cue_direction(name):
    case = DV11[name]
    steps, triggers, packet_cues, packet = run_dv11(case)
    assert triggers[1] == case["triggers"]
    assert (packet.own_position.x, packet.own_position.y) == case["position"]
    assert packet_cues == {0: [DISTANT], 1: [NEAR_EAST]}  # the cue is in the decision packet
    _assert_whole_objects_and_rejections(steps, case["expected"])


def dv10_content() -> WorldContent:
    return variant(
        {"mia": (14, 32)},
        time={"start_hour": 5, "day_start_hour": 6, "day_end_hour": 7},
        perception={"night_radius_tiles": 0, "cue_detail_radius_tiles": 1},
        actions={"rest_ticks": 20},
    )


DV10_EXPECTED = [
    (
        plan_obj(0, 0, [("rest", None, {})], actor="mia"),
        state_obj(issued_intents=[ref(0, 0, "rest", None, "mia")]),
    ),
    (
        _tile_move("mia", 1, 16, 35, 20),
        state_obj(
            commitment={"goal": "tree", "target": {"x": 16, "y": 35}, "set_at_tick": 20},
            issued_intents=[ref(1, 0, "move_to", tile_t(16, 35), "mia")],
            cue_impressions=[],
        ),
    ),
]


def run_dv10():
    content = dv10_content()
    cfg = policy_config(content)
    rest = IntentTemplate(
        action_type="rest", target=None, parameters=EmptyParameters(), reason=None
    )
    refs = [IssuedIntent(intent_id="mia:p000000:i0", action_type="rest", target=None)]
    mia = Injected(cfg, [rest], refs)
    loop, runtimes = build_loop(content, {"mia": mia}, cfg)
    steps = []
    delivered: dict[int, Any] = {}
    for _ in range(21):
        commit, records = loop.advance()
        for delivery in commit.pending_deliveries:
            if delivery.actor_id == "mia":
                delivered[delivery.perception.tick] = _cues(delivery.perception)
        steps += [_record_pair(runtimes["mia"], r) for r in records if r.actor_id == "mia"]
    return steps, delivered, {t: _cues(p) for t, p in mia.packets.items()}


def test_dv10_decision_only_capture_loses_a_cue_seen_during_rest():
    steps, delivered, decided = run_dv10()
    # Tick 6 (06:00, daylight): the packet carries the cue and NEW_SIGHT, but Mia only rests.
    assert all(delivered[t] == [NEAR_EAST] for t in range(6, 12))
    assert all(delivered[t] == [] for t in [*range(1, 6), *range(12, 21)])
    assert sorted(decided) == [0, 20]  # no decision between tick 0 and tick 20
    # The decision at tick 20 gets a packet without the cue: the loss is expected.
    assert decided == {0: [], 20: []}
    assert steps[1][1]["cue_impressions"] == []
    _assert_whole_objects_and_rejections(steps, DV10_EXPECTED)


# --- canteen: drink, fill (probe outcomes) and give in the engine --------------------------


def tiny(residents, canteen=None, **sections):
    base = tiny_content(ROWS, residents)
    data = copy.deepcopy(base.config.model_dump(mode="json"))
    data["canteen"].update(canteen or {})
    for name, values in sections.items():
        data[name].update(values)
    data["canteen"]["initial_owner_id"] = next(iter(residents))
    return build_world_content(data, map_bytes_from_rows(ROWS))


def run_solo(content, ticks, actor="ella", **rule):
    cfg = policy_config(content, **rule)
    policy = RuleBasedPolicy(cfg)
    policies = {actor: policy}
    loop, runtimes = build_loop(content, policies, cfg)
    log = []
    for _ in range(ticks):
        commit, records = loop.advance()
        log.append((commit, [r for r in records if r.actor_id == actor]))
    return log, runtimes[actor], loop


def event_types(log):
    return [e.type for commit, _ in log for e in commit.events]


@pytest.mark.parametrize(
    ("canteen", "outcome", "capacity"),
    [
        ({"initial_servings": 0}, "canteen_filled", 2),
        ({"initial_servings": 1}, "canteen_filled", 2),
        ({"initial_servings": 2}, "ALREADY_FULL", 2),
        ({"capacity_servings": 0, "initial_servings": 0}, "ALREADY_FULL", 0),
    ],
    ids=["empty", "partial", "full", "capacity-zero"],
)
def test_fill_probe_in_the_engine(canteen, outcome, capacity):
    content = tiny({"ella": (2, 1)}, canteen)
    log, runtime, _ = run_solo(content, 4)
    first_plan = log[0][1][0].plan.intents[0]
    assert first_plan.action_type == "fill_canteen"
    if outcome == "ALREADY_FULL":
        failures = [
            e.payload.failure_code
            for commit, _ in log
            for e in commit.events
            if e.type == "action_failed"
        ]
        assert failures[0] == "ALREADY_FULL"
    else:
        assert "canteen_filled" in event_types(log)
    saved = committed(runtime)
    assert saved["canteen_capacity"] == capacity
    assert [e for e in saved["failed_targets"] if e["action"] == "fill_canteen"] == []
    fills = [r.plan.intents[0].action_type for _, rs in log for r in rs]
    assert fills.count("fill_canteen") == 1  # one probe, no refill once capacity is known


def test_drink_from_canteen_away_from_the_spring():
    content = tiny({"ella": (4, 2)}, needs={"initial_hydration": 3500})
    log, _, _ = run_solo(content, 2)
    plan = log[0][1][0].plan.intents[0]
    assert (plan.action_type, plan.parameters.source) == ("drink", "canteen")
    drank = [e for commit, _ in log for e in commit.events if e.type == "water_drank"]
    assert drank and drank[0].payload.source == "canteen"


def test_give_canteen_to_a_dehydrated_neighbor():
    content = tiny({"ella": (3, 2), "ryan": (4, 2)}, needs={"initial_hydration": 2400})
    cfg = policy_config(content)
    loop, runtimes = build_loop(content, {"ella": RuleBasedPolicy(cfg)}, cfg)
    gave = False
    for _ in range(6):
        commit, records = loop.advance()
        gave = gave or any(e.type == "item_given" for e in commit.events)
    assert gave
    assert [e for e in committed(runtimes["ella"])["failed_targets"] if e["action"] == "give"] == []


# --- world validation and back-off ----------------------------------------------------------


def test_invalid_plan_is_refused_by_the_world_and_backed_off():
    content = p1_default_content()
    cfg = policy_config(content)
    tree = EntityTarget(kind="entity", id="fruit_01")
    far_tree = next(t for t in content.config.world.fruit_trees if t.id == "fruit_01")
    pos = Coord(x=far_tree.position[0], y=far_tree.position[1])
    gather = IntentTemplate(
        action_type="gather", target=tree, parameters=EmptyParameters(), reason=None
    )
    ref = IssuedIntent(
        intent_id="ella:p000000:i0",
        action_type="gather",
        target=TileTarget(kind="tile", position=Coord(x=pos.x, y=pos.y)),
    )
    ella = Injected(cfg, [gather], [ref])
    loop, runtimes = build_loop(content, {"ella": ella}, cfg)
    _, record = advance_until(loop, "ella", 1)
    assert "ACTION_FAILED" in record.triggers
    saved = committed(runtimes["ella"])
    assert saved["failed_targets"] == failed(
        [("gather", tile_t(pos.x, pos.y), "OUT_OF_REACH", record.tick + 36)]
    )


def test_no_repeat_checker_flags_a_planted_repeat(tmp_path):
    plan = {
        "intents": [
            {
                "intent_id": "a:p000000:i0",
                "actor_id": "a",
                "action_type": "move_to",
                "target": {"kind": "tile", "position": {"x": 1, "y": 1}},
            }
        ]
    }
    again = {**plan, "intents": [{**plan["intents"][0], "intent_id": "a:p000001:i0"}]}
    decisions = [
        {"actor_id": "a", "tick": 0, "plan": plan},
        {"actor_id": "a", "tick": 1, "plan": {"intents": []}},
        {"actor_id": "a", "tick": 5, "plan": again},
    ]
    events = [
        {
            "type": "action_failed",
            "tick": 1,
            "intent_id": "a:p000000:i0",
            "payload": {"failure_code": "NO_PATH"},
        }
    ]
    (tmp_path / "decisions.jsonl").write_text("\n".join(map(json.dumps, decisions)))
    (tmp_path / "events.jsonl").write_text("\n".join(map(json.dumps, events)))
    assert no_repeat_violations(tmp_path, {}) == ["a@5: move_to ('tile', 1, 1)"]
    decisions[2]["tick"] = 37
    (tmp_path / "decisions.jsonl").write_text("\n".join(map(json.dumps, decisions)))
    assert no_repeat_violations(tmp_path, {}) == []


def test_scenario_no_repeat_over_a_rule_run(tmp_path):
    from living_island.sim.runner import run

    content = tiny(
        {"ella": (2, 1), "ryan": (3, 1)}, needs={"initial_hydration": 2500, "initial_satiety": 2500}
    )
    run(
        content,
        120,
        tmp_path / "run",
        rule_params=params(),
        checkpoint_every=None,
    )
    trees = {t.id: (t.position[0], t.position[1]) for t in content.config.world.fruit_trees}
    assert no_repeat_violations(tmp_path / "run", trees) == []


# --- S4 / S5 switches change only their §6.3 rules -----------------------------------------


def holder_view(**kw):
    return perception(canteen=("canteen_01", 2), **kw)


def decide_with(rule, p, state=None):
    cfg = rule_config(rule=rule)
    return step(make_policy(cfg, state), p, 0)[0]


def test_s4_restricted_changes_only_the_canteen_rules():
    on, off = params(), params(canteen_use="restricted")
    grid = tiles(overrides={(3, 2): "spring"})
    at_spring = dict(
        explored=grid, visible_tiles=[t for t in grid if (t.position.x, t.position.y) == (3, 2)]
    )
    # R2 drink from the canteen, R4 fill probe, R9 pick up, R10 give, R6b request.
    cases = [
        (holder_view(hydration="low"), [("drink", None, {"source": "canteen"})]),
        (holder_view(**at_spring), [("fill_canteen", "canteen_01", {})]),
        (
            perception(entities=[ground_canteen("canteen_01", (3, 2))]),
            [("pick_up", (3, 2), {"item_type": "canteen", "quantity": 1})],
        ),
        (
            holder_view(entities=[resident("b", (3, 2), ["dehydrated"])]),
            [("give", "b", {"item_type": "canteen", "quantity": 1})],
        ),
        (
            perception(hydration="critical", entities=[resident("b", (3, 2))]),
            [("talk", "b", None)],
        ),
    ]
    for p, expected in cases:
        got = decide_with(on, p)
        assert [(a, t) for a, t, _ in got] == [(a, t) for a, t, _ in expected]
        assert decide_with(off, p) != got
    # Rules that are not canteen rules are unchanged: spring drink, eat, fruit replies.
    unaffected = perception(hydration="moderate", **at_spring)
    assert decide_with(on, unaffected) == decide_with(off, unaffected)
    eat = perception(fruit=1, satiety="low")
    assert decide_with(on, eat) == decide_with(off, eat) == [("eat", None, {})]
    from rule_policy_builders import heard

    fruit_ask = heard("u:1", "b", "request", item="fruit", quantity=1)
    fruit_view = perception(fruit=2, entities=[resident("b", (3, 2))], heard_utterances=[fruit_ask])
    assert decide_with(on, fruit_view) == decide_with(off, fruit_view)
    assert decide_with(on, fruit_view)[1][0] == "give"


def test_s4_restricted_refuses_a_canteen_request_and_never_probes():
    from rule_policy_builders import heard

    ask = heard("u:1", "b", "request", item="canteen", quantity=1)
    p = holder_view(entities=[resident("b", (3, 2))], heard_utterances=[ask])
    assert decide_with(params(), p)[0][0] == "talk"
    on = decide_with(params(), p)
    off = decide_with(params(canteen_use="restricted"), p)
    assert [a for a, _, _ in on] == ["talk", "give"]  # accept plus give
    assert [a for a, _, _ in off] == ["talk"]  # refuse
    policy = make_policy(rule_config(rule=params(canteen_use="restricted")))
    _, saved = step(policy, holder_view(), 0)
    assert saved["canteen_capacity"] is None


def test_s5_ignored_changes_only_the_cue_filter_and_keeps_impressions():
    grid = [t for t in tiles() if 1 <= t.position.x <= 5 and 3 <= t.position.y <= 5]
    from rule_policy_builders import cue

    p = perception(pos=(3, 4), explored=grid, cues=[cue()])
    enabled = make_policy(rule_config(rule=params()))
    ignored = make_policy(rule_config(rule=params(cue_use="ignored")))
    plan_on, state_on = step(enabled, p, 0)
    plan_off, state_off = step(ignored, p, 0)
    assert state_on["cue_impressions"] == state_off["cue_impressions"] != []
    assert all(x > 3 for _, (x, _y), _ in plan_on)  # east half-plane preferred
    # The filter is the only difference: without a cue both arms agree exactly.
    q = perception(pos=(3, 4), explored=grid)
    assert step(make_policy(rule_config(rule=params())), q, 0) == step(
        make_policy(rule_config(rule=params(cue_use="ignored"))), q, 0
    )


def test_oq074_backed_off_ground_canteen_two_tiles_away_is_not_approached():
    entry = failed([("pick_up", tile_t(4, 2), "ITEM_TAKEN", 40)])
    state = {**empty_state(), "failed_targets": entry}
    p = perception(tick=10, pos=(2, 2), entities=[ground_canteen("canteen_01", (4, 2))])
    policy = make_policy(state=state)
    plan, _ = step(policy, p, 3)
    assert all(a != "move_to" for a, _, _ in plan)
    plan, _ = step(policy, perception(tick=39, pos=(2, 2), entities=p.visible_entities), 4)
    assert all(a != "move_to" for a, _, _ in plan)
    plan, _ = step(policy, perception(tick=40, pos=(2, 2), entities=p.visible_entities), 5)
    assert plan == [("move_to", (4, 2), {})]


def test_load_default_content_still_valid():
    assert load_world_content(WORLDS / "default.toml").config.meta.seed == 20261108
