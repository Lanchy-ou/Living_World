"""Builders for rule-based-v0 decision-vector tests (Rule Policy §10 common setup)."""

from __future__ import annotations

from typing import Any

from living_island.agents.policies._plans import make_plan  # noqa: F401  (re-exported for tests)
from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.types import (
    DecisionContext,
    DecisionRequest,
    Goal,
    PersonalityProfile,
    PolicyConfig,
    RuleParams,
    RuleStateV0_1,
)
from living_island.world.protocol import (
    ActionFeedback,
    Coord,
    EnvironmentalCue,
    HeardUtterance,
    NeedBand,
    OwnCondition,
    OwnInventory,
    Perception,
    TileView,
    TransientSighting,
    VisibleEntity,
)

Pos = tuple[int, int]


def params(
    canteen_use: str = "enabled",
    cue_use: str = "enabled",
    carry: int = 2,
    retry: int = 36,
) -> RuleParams:
    return RuleParams.model_validate(
        {
            "rule_params_version": "0.1",
            "canteen_use": canteen_use,
            "cue_use": cue_use,
            "fruit_carry_target": carry,
            "failed_target_retry_ticks": retry,
        }
    )


def config(
    *,
    width: int = 8,
    height: int = 8,
    seed: int = 1,
    max_plan: int = 5,
    rule: RuleParams | None = None,
) -> PolicyConfig:
    return PolicyConfig(
        policy_id="rule-based-v0",
        seed=seed,
        max_plan_actions=max_plan,
        map_width=width,
        map_height=height,
        script_sha256=None,
        source_trace_sha256=None,
        rule_params=rule if rule is not None else params(),
    )


def tiles(
    width: int = 8, height: int = 8, overrides: dict[Pos, str] | None = None
) -> list[TileView]:
    """A full grass grid, with ``overrides`` replacing terrain; ``"-"`` removes the tile."""
    overrides = overrides or {}
    out = []
    for y in range(height):
        for x in range(width):
            terrain = overrides.get((x, y), "grass")
            if terrain != "-":
                out.append(TileView(position=Coord(x=x, y=y), terrain=terrain))  # type: ignore[arg-type]
    return out


def tree(entity_id: str, pos: Pos, band: str = "many", *, sighting: bool = False) -> Any:
    kwargs: dict[str, Any] = dict(
        entity_id=entity_id,
        entity_type="fruit_tree",
        position=Coord(x=pos[0], y=pos[1]),
        observable_signs=[],
        fruit_band=band,
        quantity=None,
    )
    if sighting:
        return TransientSighting(seen_at_step=1, **kwargs)
    return VisibleEntity(**kwargs)


def resident(entity_id: str, pos: Pos, signs: list[str] | None = None) -> VisibleEntity:
    return VisibleEntity(
        entity_id=entity_id,
        entity_type="resident",
        position=Coord(x=pos[0], y=pos[1]),
        observable_signs=signs or [],  # type: ignore[arg-type]
        fruit_band=None,
        quantity=None,
    )


def ground_canteen(entity_id: str, pos: Pos) -> VisibleEntity:
    return VisibleEntity(
        entity_id=entity_id,
        entity_type="canteen",
        position=Coord(x=pos[0], y=pos[1]),
        observable_signs=[],
        fruit_band=None,
        quantity=None,
    )


def cue(cue_id: str = "moss", pos: Pos = (3, 3), detail: str = "near", direction: Any = "east"):
    return EnvironmentalCue(
        cue_id=cue_id,
        position=Coord(x=pos[0], y=pos[1]),
        detail_level=detail,  # type: ignore[arg-type]
        physical_description="moss",
        direction=direction,
    )


def heard(
    utterance_id: str,
    speaker: str,
    act: str,
    *,
    addressee: str = "a",
    item: str | None = None,
    quantity: int | None = None,
    in_reply_to: str | None = None,
    tick: int = 0,
) -> HeardUtterance:
    return HeardUtterance(
        utterance_id=utterance_id,
        speaker_id=speaker,
        addressee_id=addressee,
        speech_act=act,  # type: ignore[arg-type]
        text="",
        request_item_type=item,
        request_quantity=quantity,
        in_reply_to=in_reply_to,
        heard_at_tick=tick,
    )


def failure(intent_id: str, code: str) -> ActionFeedback:
    return ActionFeedback(
        intent_id=intent_id,
        status="failure",
        failure_code=code,  # type: ignore[arg-type]
        interruption_reason=None,
        visible_effects=[],
    )


def success(intent_id: str) -> ActionFeedback:
    return ActionFeedback(
        intent_id=intent_id,
        status="success",
        failure_code=None,
        interruption_reason=None,
        visible_effects=[],
    )


def perception(
    *,
    tick: int = 0,
    actor: str = "a",
    pos: Pos = (2, 2),
    explored: list[TileView] | None = None,
    visible_tiles: list[TileView] | None = None,
    entities: list[VisibleEntity] | None = None,
    sightings: list[TransientSighting] | None = None,
    cues: list[EnvironmentalCue] | None = None,
    heard_utterances: list[HeardUtterance] | None = None,
    feedback: ActionFeedback | None = None,
    satiety: NeedBand = "good",
    hydration: NeedBand = "good",
    stamina: NeedBand = "good",
    health: NeedBand = "good",
    fruit: int = 0,
    canteen: tuple[str, int] | None = None,
) -> Perception:
    return Perception(
        schema_version="0.1",
        actor_id=actor,
        tick=tick,
        own_condition=OwnCondition(
            satiety=satiety, hydration=hydration, stamina=stamina, health=health
        ),
        own_position=Coord(x=pos[0], y=pos[1]),
        own_inventory=OwnInventory(
            fruit_count=fruit,
            canteen_id=canteen[0] if canteen else None,
            canteen_servings=canteen[1] if canteen else None,
        ),
        visible_tiles=visible_tiles or [],
        visible_entities=sorted(entities or [], key=lambda e: e.entity_id),
        transient_sightings=sightings or [],
        explored_static_tiles=explored if explored is not None else tiles(),
        environmental_cues=cues or [],
        heard_utterances=heard_utterances or [],
        last_action_feedback=feedback,
    )


def request(
    p: Perception,
    ordinal: int = 0,
    profile: str = "p",
    goals: list[Goal] | None = None,
    triggers: list[Any] | None = None,
) -> DecisionRequest:
    if triggers is None:
        triggers = [] if (p.tick, ordinal) == (0, 0) else ["PLAN_FINISHED"]
    return DecisionRequest(
        actor_id=p.actor_id,
        tick=p.tick,
        decision_ordinal=ordinal,
        triggers=triggers,
        context=DecisionContext(
            perception=p,
            personality_profile=PersonalityProfile(profile_id=profile, values=[]),
            current_goals=goals or [],
            recalled_episodes=[],
            beliefs=[],
            current_plan_summary=None,
        ),
    )


def empty_state() -> dict[str, Any]:
    return {
        "rule_state_version": "0.1",
        "commitment": None,
        "issued_intents": [],
        "failed_targets": [],
        "cue_impressions": [],
        "canteen_capacity": None,
    }


def make_policy(cfg: PolicyConfig | None = None, state: dict[str, Any] | None = None):
    return RuleBasedPolicy(
        cfg or config(), RuleStateV0_1.model_validate(state) if state is not None else None
    )


def step(
    policy: RuleBasedPolicy, p: Perception, ordinal: int = 0
) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    """Decide and commit; returns (plan summary, committed policy state)."""
    outcome = policy.decide(request(p, ordinal))
    policy.finish_decision(True)
    return summarize(outcome.plan), policy.export_state()  # type: ignore[return-value]


def summarize(plan: Any) -> list[tuple[Any, ...]]:
    """One tuple per intent: action, target tuple or None, parameters dict."""
    out = []
    for i in plan.intents:
        t = i.target
        target = None if t is None else (t.position.x, t.position.y) if t.kind == "tile" else t.id
        out.append((i.action_type, target, i.parameters.model_dump(mode="json")))
    return out


def failed(entries: list[tuple[str, dict[str, Any], str, int]]) -> list[dict[str, Any]]:
    return [{"action": a, "target": t, "code": c, "retry_after_tick": r} for a, t, c, r in entries]


def tile_t(x: int, y: int) -> dict[str, Any]:
    return {"kind": "tile", "position": {"x": x, "y": y}}


def res_t(rid: str) -> dict[str, Any]:
    return {"kind": "resident", "id": rid}


def ent_t(eid: str) -> dict[str, Any]:
    return {"kind": "entity", "id": eid}


# --- whole-object comparison (Gate 2 G2-02) -------------------------------------------------

import copy  # noqa: E402
import json  # noqa: E402
from collections import deque  # noqa: E402
from collections.abc import Iterator  # noqa: E402


def canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def plan_obj(
    tick: int, ordinal: int, intents: list[tuple[str, Any, dict[str, Any]]], actor: str = "a"
) -> dict[str, Any]:
    """The full expected ``ActionPlan`` as canonical JSON data."""
    plan_id = f"{actor}:p{ordinal:06d}"
    return {
        "plan_id": plan_id,
        "actor_id": actor,
        "created_at_tick": tick,
        "intents": [
            {
                "intent_id": f"{plan_id}:i{i}",
                "plan_id": plan_id,
                "actor_id": actor,
                "action_type": action,
                "target": target,
                "parameters": parameters,
                "reason": None,
            }
            for i, (action, target, parameters) in enumerate(intents)
        ],
    }


def state_obj(**updates: Any) -> dict[str, Any]:
    """The full expected ``RuleStateV0_1`` (every field present)."""
    return {**empty_state(), **updates}


def ref(ordinal: int, index: int, action: str, target: Any, actor: str = "a") -> dict[str, Any]:
    return {
        "intent_id": f"{actor}:p{ordinal:06d}:i{index}",
        "action_type": action,
        "target": target,
    }


def decide_step(
    policy: RuleBasedPolicy, p: Perception, ordinal: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decide and commit; returns the full ActionPlan and the full committed state."""
    outcome = policy.decide(request(p, ordinal))
    policy.finish_decision(True)
    return outcome.plan.model_dump(mode="json"), policy.export_state()


def verify(actual: list[tuple[Any, Any]], expected: list[tuple[Any, Any]]) -> None:
    """Whole canonical objects, decision by decision."""
    assert len(actual) == len(expected), "decision count"
    for i, ((plan_a, state_a), (plan_e, state_e)) in enumerate(zip(actual, expected, strict=True)):
        assert canon(plan_a) == canon(plan_e), f"plan of decision {i}"
        assert canon(state_a) == canon(state_e), f"state of decision {i}"


def _leaf_paths(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    if isinstance(value, dict):
        for key in value:
            yield from _leaf_paths(value[key], (*path, key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _leaf_paths(item, (*path, i))
    else:
        yield path


def _tweak(leaf: Any) -> Any:
    if isinstance(leaf, bool):
        return not leaf
    if isinstance(leaf, int):
        return leaf + 1
    if isinstance(leaf, str):
        return leaf + "x"
    return "x"


def mutants(value: Any) -> Iterator[Any]:
    """Every single-leaf change of ``value``, plus every list shortened by its last item."""
    for path in _leaf_paths(value):
        clone = copy.deepcopy(value)
        node = clone
        for key in path[:-1]:
            node = node[key]
        if path:
            node[path[-1]] = _tweak(node[path[-1]])
            yield clone

    def lists(node: Any, path: tuple[Any, ...]) -> Iterator[tuple[Any, ...]]:
        if isinstance(node, list):
            if node:
                yield path
            for i, item in enumerate(node):
                yield from lists(item, (*path, i))
        elif isinstance(node, dict):
            for key, item in node.items():
                yield from lists(item, (*path, key))

    for path in lists(value, ()):
        clone = copy.deepcopy(value)
        node = clone
        for key in path:
            node = node[key]
        node.pop()
        yield clone


def bfs_distances(passable: set[Pos], start: Pos) -> dict[Pos, int]:
    """Independent unit-cost BFS in N, E, S, W order (the test's oracle for §2 ``d``)."""
    dist = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for n in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if n in passable and n not in dist:
                dist[n] = dist[(x, y)] + 1
                queue.append(n)
    return dist


def frontier_distances(
    explored: set[Pos], passable: set[Pos], start: Pos, width: int, height: int
) -> dict[Pos, int]:
    """§2 frontier tiles with their distance, from the oracle BFS."""
    dist = bfs_distances(passable, start)
    out: dict[Pos, int] = {}
    for x in range(width):
        for y in range(height):
            if (x, y) in explored:
                continue
            near = [
                dist[n]
                for n in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
                if n in passable and n in dist
            ]
            if near:
                out[(x, y)] = 1 + min(near)
    return out
