"""Agent interface acceptance at the policy and decision-record boundary."""

from hashlib import sha256

import pytest
from test_sim_runtime import ROWS, WaitPolicy
from world_builders import tiny_content

from living_island.agents.policies._plans import WAIT, make_plan
from living_island.agents.policies.random_policy import RandomPolicy
from living_island.agents.policies.scripted import ScriptedPolicy
from living_island.agents.runtime import Runtime, create_runtime
from living_island.agents.types import ActorScript, OkOutcome, OwnProfile, PolicyConfig
from living_island.sim.runner import BoundaryLoop
from living_island.world.content import canonical_json_bytes
from living_island.world.ports import create_engine
from living_island.world.protocol import Coord, OwnInventory, TileView, VisibleEntity

PROFILE = OwnProfile(profile_id="ella-profile", initial_goal="Écouter")


def policy_config(kind="random-v0", **overrides):
    return PolicyConfig.model_validate(
        {
            "policy_id": kind,
            "seed": 31,
            "max_plan_actions": 2,
            "map_width": 7,
            "map_height": 5,
            "script_sha256": "1" * 64 if kind == "scripted-v0" else None,
            "source_trace_sha256": "2" * 64 if kind == "recorded-v0" else None,
            **overrides,
        }
    )


def test_ai01_same_context_for_all_policies_without_world_mutation():
    content = tiny_content(ROWS, {"ella": (2, 1)})
    commit = create_engine(content, None).initial_commit()
    before = commit.snapshot.model_dump()
    runtime = Runtime("ella", policy_config(), PROFILE, WaitPolicy())
    runtime.ingest(commit.pending_deliveries[0])
    request = runtime.make_request(0, [])
    script = ActorScript(actor_id="ella", on_exhausted="error", plans=[[WAIT]])

    class FakeLLM(WaitPolicy):
        def decide(self, supplied):
            assert supplied.context == request.context
            return super().decide(supplied)

    for policy in (RandomPolicy(policy_config()), ScriptedPolicy(script), FakeLLM()):
        assert isinstance(policy.decide(request), OkOutcome)
    assert runtime.decide(request).status == "ok"
    with pytest.raises(ValueError, match="uncommitted"):
        runtime.export_state()
    assert commit.snapshot.model_dump() == before


def test_ai02_context_contains_only_own_private_state_and_local_observations():
    content = tiny_content(
        ROWS, {"ella": (2, 2), "mia": (1, 2), "ryan": (5, 3)}, day_radius_tiles=1
    )
    commit = create_engine(content, None).initial_commit()
    runtime = Runtime("ella", policy_config(), PROFILE, WaitPolicy())
    runtime.ingest(commit.pending_deliveries[0])
    context = runtime.make_request(0, []).context
    assert [
        e.entity_id for e in context.perception.visible_entities if e.entity_type == "resident"
    ] == ["mia"]
    assert "ryan" not in context.model_dump_json()
    assert "fruit_01" not in context.model_dump_json()
    assert context.personality_profile.profile_id == PROFILE.profile_id
    assert context.personality_profile.values == []
    assert [g.model_dump() for g in context.current_goals] == [
        {"goal_id": "initial", "text": PROFILE.initial_goal, "priority": 0}
    ]
    assert context.recalled_episodes == context.beliefs == []
    assert context.current_plan_summary is None


@pytest.mark.parametrize("defect", ["empty", "oversize", "wrong-id", "wrong-parameters"])
def test_ai03_invalid_structure_records_wait_and_applies_metabolism(defect):
    class Broken(WaitPolicy):
        def decide(self, request):
            original = make_plan(request, [WAIT] * (3 if defect == "oversize" else 1))
            intents = original.intents
            if defect == "empty":
                intents = []
            elif defect == "wrong-id":
                intents = [intents[0].model_copy(update={"intent_id": "different"})]
            elif defect == "wrong-parameters":
                from living_island.world.protocol import DrinkParameters

                intents = [
                    intents[0].model_copy(update={"parameters": DrinkParameters(source="spring")})
                ]
            return OkOutcome(
                status="ok",
                policy_id=self.policy_id,
                plan=original.model_copy(update={"intents": intents}),
            )

    content = tiny_content(ROWS, {"ella": (2, 1)})
    runtime = Runtime("ella", policy_config(), PROFILE, Broken())
    loop = BoundaryLoop(create_engine(content, None), runtime)
    initial = loop.boundary
    original = initial.snapshot.model_dump()
    commit, [record] = loop.advance()
    assert initial.snapshot.model_dump() == original
    assert record.error_kind == "INVALID_PLAN"
    assert record.effective_policy_id == "sim-fallback-wait"
    assert [intent.action_type for intent in record.plan.intents] == ["wait"]
    assert commit.snapshot.residents[0].satiety < initial.snapshot.residents[0].satiety


def test_ai07_random_decision_records_are_deterministic():
    content = tiny_content(ROWS, {"ella": (2, 1)})

    def simulate():
        runtime = create_runtime("ella", policy_config(), PROFILE, None, None, None)
        loop = BoundaryLoop(create_engine(content, None), runtime)
        records = [record for _ in range(12) for record in loop.advance()[1]]
        assert records and all(record.status == "ok" for record in records)
        return canonical_json_bytes([record.model_dump(mode="json") for record in records])

    assert simulate() == simulate()


def test_ai09_scripted_exhaustion_records_substitute_and_one_ordinal():
    content = tiny_content(ROWS, {"ella": (2, 1)})
    script = ActorScript(actor_id="ella", on_exhausted="error", plans=[[WAIT]])
    runtime = create_runtime("ella", policy_config("scripted-v0"), PROFILE, script, None, None)
    loop = BoundaryLoop(create_engine(content, None), runtime)
    _, [original] = loop.advance()
    commit, [fault] = loop.advance()
    assert original.policy_id == fault.policy_id == "scripted-v0"
    assert (fault.status, fault.error_kind, fault.substituted) == (
        "error",
        "SCRIPT_EXHAUSTED",
        True,
    )
    assert fault.effective_policy_id == "sim-fallback-wait"
    assert fault.decision_ordinal == 1
    assert runtime.export_state().next_decision_ordinal == 2
    assert runtime.export_state().policy_state == {"cursor": 1}
    assert "agent_fallback_used" not in {e.type for e in commit.events}

    wait_script = script.model_copy(update={"on_exhausted": "wait", "plans": []})
    waiting = create_runtime(
        "ella",
        policy_config("scripted-v0"),
        PROFILE,
        wait_script,
        None,
        None,
    )
    _, [record] = BoundaryLoop(create_engine(content, None), waiting).advance()
    assert (record.status, record.substituted, waiting.export_state().policy_state) == (
        "ok",
        False,
        {"cursor": 0},
    )


def test_ai15_random_category_order_frontier_bounds_and_full_inventory():
    content = tiny_content(ROWS, {"ella": (2, 1)})
    runtime = Runtime("ella", policy_config(), PROFILE, WaitPolicy())
    runtime.ingest(create_engine(content, None).initial_commit().pending_deliveries[0])
    request = runtime.make_request(0, [])
    original = request.context.perception

    def tile(x, y, terrain):
        return TileView(position=Coord(x=x, y=y), terrain=terrain)

    def entity(entity_id, entity_type, x, y, *, fruit_band=None, quantity=None):
        return VisibleEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            position=Coord(x=x, y=y),
            observable_signs=[],
            fruit_band=fruit_band,
            quantity=quantity,
        )

    edge = original.model_copy(
        update={
            "own_position": Coord(x=0, y=0),
            "own_condition": original.own_condition.model_copy(
                update={
                    "satiety": "low",
                    "hydration": "low",
                    "stamina": "critical",
                }
            ),
            "own_inventory": OwnInventory(fruit_count=99, canteen_id="own", canteen_servings=99),
            "visible_tiles": [tile(1, 0, "spring")],
            "explored_static_tiles": [
                tile(0, 0, "grass"),
                tile(1, 0, "spring"),
                tile(0, 1, "woods"),
                tile(1, 1, "woods"),
                tile(6, 4, "sea"),
            ],
            "visible_entities": [
                entity("a", "ground_fruit", 0, 0, quantity=4),
                entity("b", "fruit_tree", 0, 1, fruit_band="few"),
                entity("c", "canteen", 0, 1),
                entity("d", "fruit_tree", 1, 0, fruit_band="empty"),
                entity("e", "fruit_tree", 1, 0, fruit_band="few"),
            ],
        }
    )
    policy = RandomPolicy(policy_config())
    categories = policy._categories(edge)
    assert [category[0].action_type for category in categories] == [
        "wait",
        "rest",
        "sleep",
        "eat",
        "drink",
        "drink",
        "fill_canteen",
        "gather",
        "pick_up",
        "move_to",
    ]
    assert [categories[i][0].parameters.source for i in (4, 5)] == ["spring", "canteen"]
    assert [template.target.id for template in categories[7]] == ["b", "e"]
    assert [t.parameters.item_type for t in categories[8]] == ["fruit", "canteen"]
    assert [(t.target.position.x, t.target.position.y) for t in categories[-1]] == [
        (0, 1),
        (1, 1),
        (2, 1),
        (0, 2),
        (1, 2),
    ]
    request = request.model_copy(
        update={
            "context": request.context.model_copy(update={"perception": edge}),
        }
    )
    for ordinal in range(100):
        request = request.model_copy(update={"decision_ordinal": ordinal})
        picks = [
            int(sha256(f"31|ella|{ordinal}|{i}".encode()).hexdigest()[:16], 16) for i in (0, 1)
        ]
        category = categories[picks[0] % len(categories)]
        expected = category[picks[1] % len(category)]
        [intent] = policy.decide(request).plan.intents
        assert (intent.action_type, intent.target, intent.parameters, intent.reason) == (
            expected.action_type,
            expected.target,
            expected.parameters,
            None,
        )
    empty = edge.model_copy(
        update={
            "own_condition": edge.own_condition.model_copy(update={"stamina": "strong"}),
            "own_inventory": OwnInventory(fruit_count=0, canteen_id=None, canteen_servings=None),
            "visible_tiles": [],
            "visible_entities": [],
            "explored_static_tiles": [],
        }
    )
    assert policy._categories(empty) == [[WAIT]]
