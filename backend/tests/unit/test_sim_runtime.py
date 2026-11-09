"""Resident transactions through a real world boundary."""

import pytest
from world_builders import tiny_content

from living_island.agents.runtime import Runtime
from living_island.agents.types import (
    DecisionRequest,
    OkOutcome,
    OwnProfile,
    PolicyConfig,
    build_intent_id,
    build_plan_id,
)
from living_island.sim.boundary import BoundaryLoop
from living_island.world.ports import create_engine
from living_island.world.protocol import ActionIntent, ActionPlan, EmptyParameters

ROWS = ["~~~~~~~", "~S.F..~", "~..M..~", "~.C...~", "~~~~~~~"]


class WaitPolicy:
    policy_id = "test-wait"

    def decide(self, request: DecisionRequest) -> OkOutcome:
        plan_id = build_plan_id(request.actor_id, request.decision_ordinal)
        return OkOutcome(
            status="ok",
            policy_id=self.policy_id,
            plan=ActionPlan(
                plan_id=plan_id,
                actor_id=request.actor_id,
                created_at_tick=request.tick,
                intents=[
                    ActionIntent(
                        intent_id=build_intent_id(plan_id, 0),
                        plan_id=plan_id,
                        actor_id=request.actor_id,
                        action_type="wait",
                        target=None,
                        parameters=EmptyParameters(),
                        reason=None,
                    )
                ],
            ),
        )

    def export_state(self):
        return {}


def test_one_actor_ingests_then_decides_and_commits():
    content = tiny_content(ROWS, {"ella": (2, 1)})
    runtime = Runtime(
        "ella",
        PolicyConfig(
            policy_id="random-v0",
            seed=content.config.meta.seed,
            max_plan_actions=5,
            map_width=7,
            map_height=5,
            script_sha256=None,
            source_trace_sha256=None,
        ),
        OwnProfile(profile_id="ella-profile", initial_goal="Look around"),
        WaitPolicy(),
    )
    with pytest.raises(ValueError, match="no ingested perception"):
        runtime.make_request(0, [])
    loop = BoundaryLoop(create_engine(content, None), [runtime])
    initial = loop.boundary
    first, records = loop.advance()
    assert first.snapshot.tick == 1
    assert [r.triggers for r in records] == [[]]
    assert runtime.export_state().latest_perception_tick == 0
    assert runtime.export_state().next_decision_ordinal == 1
    with pytest.raises(ValueError, match="consecutive delivery"):
        runtime.ingest(initial.pending_deliveries[0])
    with pytest.raises(ValueError, match="no decision to commit"):
        runtime.commit_decision(records[0])
    second, records = loop.advance()
    assert second.snapshot.tick == 2
    assert records[0].decision_ordinal == 1
    assert "PLAN_FINISHED" in records[0].triggers
    assert runtime.export_state().latest_perception_tick == 1
