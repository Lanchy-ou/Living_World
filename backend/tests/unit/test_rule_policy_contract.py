"""rule-based-v0 determinism (§9), the §1 input boundary, state validity and the S1/S3 fixtures."""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from rule_policy_builders import config as rule_config
from rule_policy_builders import (
    cue,
    ground_canteen,
    heard,
    make_policy,
    perception,
    request,
    resident,
    tiles,
    tree,
)
from world_builders import WORLDS

from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.types import Goal, ResidentRuntimeState
from living_island.persistence.content import load_world_content
from living_island.world.canteen import check_canteen  # noqa: F401
from living_island.world.ports import create_engine

PKG = Path(__file__).resolve().parents[2] / "src" / "living_island" / "agents" / "rule_based"
ROOT = Path(__file__).resolve().parents[3]
ALLOWED_IMPORTS = {
    "living_island.world.protocol",
    "living_island.agents.types",
    "living_island.agents.policies._plans",
}
FORBIDDEN_FIELDS = {
    "triggers",
    "personality_profile",
    "current_goals",
    "recalled_episodes",
    "beliefs",
    "current_plan_summary",
}


def canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --- input boundary -------------------------------------------------------------------------


def _sources():
    return {path.name: ast.parse(path.read_text(encoding="utf-8")) for path in PKG.glob("*.py")}


def test_policy_imports_only_the_allowed_modules():
    stdlib = {"__future__", "collections", "dataclasses", "hashlib", "typing"}
    for name, tree_ in _sources().items():
        for node in ast.walk(tree_):
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [("." * node.level) + (node.module or "")]
            else:
                continue
            for module in modules:
                root = module.split(".")[0]
                ok = (
                    module.startswith(".")
                    or module in ALLOWED_IMPORTS
                    or module.startswith("living_island.agents.rule_based")
                    or root in stdlib
                )
                assert ok, f"{name} imports {module}"


def test_policy_never_names_a_forbidden_request_field():
    for name, tree_ in _sources().items():
        attributes = {n.attr for n in ast.walk(tree_) if isinstance(n, ast.Attribute)}
        names = {n.id for n in ast.walk(tree_) if isinstance(n, ast.Name)}
        assert not (attributes | names) & FORBIDDEN_FIELDS, name
        banned = {"random", "time", "os", "environ", "open", "float", "resolution_rng", "uuid"}
        assert not (attributes | names) & banned, name
        assert not [
            n for n in ast.walk(tree_) if isinstance(n, ast.Constant) and type(n.value) is float
        ]


def _scene():
    grid = tiles(overrides={(3, 2): "spring", (5, 5): "fruit_tree"})
    return dict(
        pos=(2, 2),
        explored=grid,
        visible_tiles=[t for t in grid if (t.position.x, t.position.y) == (3, 2)],
        entities=[resident("b", (2, 3)), tree("t1", (5, 5), "few")],
        cues=[cue()],
        canteen=("canteen_01", 1),
        hydration="low",
    )


def test_forbidden_fields_do_not_change_plan_or_state():
    p = perception(tick=5, **_scene())
    base = make_policy()
    plain = base.decide(request(p, 1, triggers=["PLAN_FINISHED"]))
    base.finish_decision(True)
    other = make_policy()
    varied = other.decide(
        request(
            p,
            1,
            profile="other-profile",
            goals=[Goal(goal_id="g1", text="different goal", priority=9)],
            triggers=["ACTION_FAILED", "URGENT_NEED", "NEW_SIGHT"],
        )
    )
    other.finish_decision(True)
    assert canon(plain.plan.model_dump(mode="json")) == canon(varied.plan.model_dump(mode="json"))
    assert canon(base.export_state()) == canon(other.export_state())


# --- determinism ------------------------------------------------------------------------------

bands = st.sampled_from(["critical", "low", "moderate", "good", "strong"])
fruit_bands = st.sampled_from(["empty", "few", "many"])
positions = st.tuples(st.integers(0, 5), st.integers(0, 5))
terrains = st.sampled_from(["grass", "grass", "beach", "woods", "rock", "spring", "fruit_tree"])


@st.composite
def scenes(draw):
    kept = draw(st.sets(positions, min_size=1, max_size=36))
    pos = draw(st.sampled_from(sorted(kept)))
    terrain = {p: draw(terrains) for p in sorted(kept)}
    terrain[pos] = "grass"
    grid = tiles(6, 6, {(x, y): "-" for x in range(6) for y in range(6)} | terrain)
    entities = []
    others = sorted(p for p in kept if p != pos)
    for i in range(draw(st.integers(0, 3))):
        if not others:
            break
        where = draw(st.sampled_from(others))
        kind = draw(st.sampled_from(["tree", "resident", "canteen"]))
        if kind == "tree":
            entities.append(tree(f"t{i}", where, draw(fruit_bands)))
        elif kind == "resident":
            signs = draw(st.sampled_from([[], ["dehydrated"], ["weak", "fatigued"]]))
            entities.append(resident(f"r{i}", where, signs))
        else:
            entities.append(ground_canteen(f"c{i}", where))
    ids = {e.entity_id for e in entities}
    utterances = []
    if draw(st.booleans()) and "r0" in ids:
        item = draw(st.sampled_from([("canteen", 1), ("fruit", 1), ("fruit", 3)]))
        utterances.append(heard("u:1", "r0", "request", item=item[0], quantity=item[1], tick=3))
    visible = [t for t in grid if abs(t.position.x - pos[0]) + abs(t.position.y - pos[1]) <= 3]
    return dict(
        pos=pos,
        explored=grid,
        visible_tiles=visible,
        entities=entities,
        cues=draw(
            st.sampled_from([[], [cue(direction="east")], [cue(detail="distant", direction=None)]])
        ),
        heard_utterances=utterances,
        satiety=draw(bands),
        hydration=draw(bands),
        stamina=draw(bands),
        fruit=draw(st.integers(0, 4)),
        canteen=draw(st.sampled_from([None, ("canteen_01", 0), ("canteen_01", 2)])),
    )


CODES = [
    "NO_PATH",
    "OUT_OF_REACH",
    "RESOURCE_TAKEN",
    "INVENTORY_FULL",
    "NO_ITEM",
    "ALREADY_FULL",
    "ITEM_TAKEN",
    "OUT_OF_HEARING",
    "DEAD",
]


def _chain(first, second, code, params_kw, seed):
    """Two consecutive decisions; returns (plans, states) as canonical strings."""
    from rule_policy_builders import failure

    cfg = rule_config(seed=seed, rule=params_kw)
    policy = make_policy(cfg)
    out = []
    p1 = perception(tick=0, **first)
    out.append(policy.decide(request(p1, 0)))
    policy.finish_decision(True)
    saved1 = policy.export_state()
    p2 = perception(tick=1, feedback=failure("a:p000000:i0", code), **second)
    restored = RuleBasedPolicy(cfg, make_policy(cfg, saved1)._state)  # a save/restore round trip
    out.append(restored.decide(request(p2, 1)))
    restored.finish_decision(True)
    saved2 = restored.export_state()
    resumed = make_policy(cfg, saved1)
    out2 = resumed.decide(request(p2, 1))
    resumed.finish_decision(True)
    assert canon(out[1].plan.model_dump(mode="json")) == canon(out2.plan.model_dump(mode="json"))
    assert canon(saved2) == canon(resumed.export_state())
    return [o.plan.model_dump(mode="json") for o in out], [saved1, saved2]


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    first=scenes(),
    second=scenes(),
    code=st.sampled_from(CODES),
    seed=st.integers(1, 2**32 - 1),
    canteen=st.sampled_from(["enabled", "restricted"]),
    cue_use=st.sampled_from(["enabled", "ignored"]),
)
def test_same_request_state_and_config_give_identical_bytes(
    first, second, code, seed, canteen, cue_use
):
    from rule_policy_builders import params

    kw = params(canteen_use=canteen, cue_use=cue_use)
    plans_a, states_a = _chain(first, second, code, kw, seed)
    plans_b, states_b = _chain(first, second, code, kw, seed)
    assert canon(plans_a) == canon(plans_b)
    assert canon(states_a) == canon(states_b)
    # every committed state passes the restore validator
    cfg = rule_config(seed=seed, rule=kw)
    for ordinal, state in enumerate(states_a, start=1):
        ResidentRuntimeState.model_validate(
            {
                "actor_id": "a",
                "policy_config": cfg.model_dump(mode="json"),
                "next_decision_ordinal": ordinal,
                "policy_state": state,
                "latest_perception_tick": ordinal - 1,
            }
        )


# --- fixtures ---------------------------------------------------------------------------------


def _raw(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def _differences(a: Any, b: Any, path: str = "") -> set[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: set[str] = set()
        for key in sorted(a.keys() | b.keys()):
            out |= _differences(a.get(key), b.get(key), f"{path}.{key}" if path else key)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = set()
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out |= _differences(x, y, f"{path}[{i}]")
        return out
    return set() if a == b else {path}


SCENARIOS = ROOT / "content" / "scenarios"
DEFAULT = WORLDS / "default.toml"


def test_s1_differs_from_default_only_in_spawns_and_metadata():
    s1 = SCENARIOS / "s1-spring-visible" / "orig.toml"
    assert _differences(_raw(DEFAULT), _raw(s1)) == {
        "meta.run_id",
        "map.layout_file",
        "residents[0].position[0]",
        "residents[1].position[0]",
        "residents[2].position[0]",
    }
    raw = _raw(s1)
    assert raw["meta"]["run_id"] == "s1_spring_visible"
    assert raw["map"]["layout_file"] == "../../worlds/default-island.map"
    assert [r["position"] for r in raw["residents"]] == [[33, 32], [34, 32], [35, 32]]
    assert [r["id"] for r in raw["residents"]] == ["ella", "ryan", "mia"]
    assert (raw["meta"]["world_id"], raw["meta"]["seed"]) == (
        _raw(DEFAULT)["meta"]["world_id"],
        _raw(DEFAULT)["meta"]["seed"],
    )


def test_s3_differs_from_default_only_in_regrowth_and_metadata():
    s3 = SCENARIOS / "s3-regrow288" / "orig.toml"
    assert _differences(_raw(DEFAULT), _raw(s3)) == {
        "meta.run_id",
        "map.layout_file",
        "fruit.regrow_ticks",
    }
    raw = _raw(s3)
    assert raw["meta"]["run_id"] == "s3_regrow288"
    assert raw["fruit"]["regrow_ticks"] == 288


def test_fixtures_load_with_the_same_map_and_s1_sees_the_spring_at_tick_zero():
    default = load_world_content(DEFAULT)
    for name in ("s1-spring-visible", "s3-regrow288"):
        content = load_world_content(SCENARIOS / name / "orig.toml")
        assert content.map_hash == default.map_hash
    s1 = load_world_content(SCENARIOS / "s1-spring-visible" / "orig.toml")
    initial = create_engine(s1, None).initial_commit()
    assert len(initial.pending_deliveries) == 3
    spring = tuple(s1.config.world.spring)
    for delivery in initial.pending_deliveries:
        seen = {
            (t.position.x, t.position.y)
            for t in delivery.perception.visible_tiles
            if t.terrain == "spring"
        }
        assert spring in seen, delivery.perception.actor_id
