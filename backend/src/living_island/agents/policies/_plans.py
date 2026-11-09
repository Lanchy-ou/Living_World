"""Shared construction of typed policy plans."""

from collections.abc import Sequence

from living_island.agents.types import (
    DecisionRequest,
    IntentTemplate,
    build_intent_id,
    build_plan_id,
)
from living_island.world.protocol import ActionIntent, ActionPlan, EmptyParameters

WAIT = IntentTemplate(action_type="wait", target=None, parameters=EmptyParameters(), reason=None)


def make_plan(request: DecisionRequest, templates: Sequence[IntentTemplate]) -> ActionPlan:
    plan_id = build_plan_id(request.actor_id, request.decision_ordinal)
    return ActionPlan(
        plan_id=plan_id,
        actor_id=request.actor_id,
        created_at_tick=request.tick,
        intents=[
            ActionIntent(
                intent_id=build_intent_id(plan_id, index),
                plan_id=plan_id,
                actor_id=request.actor_id,
                action_type=template.action_type,
                target=template.target,
                parameters=template.parameters,
                reason=template.reason,
            )
            for index, template in enumerate(templates)
        ],
    )
