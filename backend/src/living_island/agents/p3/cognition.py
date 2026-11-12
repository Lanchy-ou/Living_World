"""Pure P3 goal transitions and model-proposal validation."""

from __future__ import annotations

from collections.abc import Sequence

from living_island.agents.p3.types import (
    CognitiveDelta,
    Commitment,
    DecisionProposal,
    DecisionRequestP3,
    GoalChange,
    GoalEvidence,
    GoalState,
    OwnActionSuccessPredicate,
    P3PolicyConfig,
    build_goal_id,
)
from living_island.agents.types import build_intent_id, build_plan_id
from living_island.memory.p3_types import (
    OwnedIntentRef,
    build_decision_id,
    canonical_bytes,
    canonical_sha256,
)
from living_island.world.protocol import (
    ActionIntent,
    ActionPlan,
    BoundaryPerceptionDelivery,
    format_delivery_id,
)


def initial_goal_state() -> GoalState:
    return GoalState(goal_schema_version="0.1", current=None, next_goal_sequence=0)


def _matches(predicate: OwnActionSuccessPredicate, intent: ActionIntent) -> bool:
    return (
        predicate.action_type == intent.action_type
        and canonical_bytes(predicate.target) == canonical_bytes(intent.target)
        and canonical_bytes(predicate.parameters) == canonical_bytes(intent.parameters)
    )


def _validate_reference(ref: OwnedIntentRef, *, actor_id: str, run_id: str) -> None:
    plan_id = build_plan_id(actor_id, ref.decision_ordinal)
    if (
        ref.intent.actor_id != actor_id
        or ref.intent.plan_id != plan_id
        or ref.decision_id != build_decision_id(run_id, actor_id, ref.decision_ordinal)
    ):
        raise ValueError("owned intent must belong to this actor and run")
    prefix = f"{plan_id}:i"
    suffix = ref.intent.intent_id.removeprefix(prefix)
    if (
        not ref.intent.intent_id.startswith(prefix)
        or not suffix.isascii()
        or not suffix.isdecimal()
        or ref.intent.intent_id != build_intent_id(plan_id, int(suffix))
    ):
        raise ValueError("owned intent must use the deterministic intent ID")


def validate_goal_state(state: GoalState, *, actor_id: str) -> None:
    """Check resident identity and evidence beyond the closed local DTO shape."""
    checked = GoalState.model_validate(state.model_dump(mode="json"))
    current = checked.current
    if current is None:
        return
    if checked.next_goal_sequence < 1 or current.goal_id != build_goal_id(
        actor_id, checked.next_goal_sequence - 1
    ):
        raise ValueError("current goal must be this actor's latest allocated goal")
    evidence = current.evidence
    if current.status == "intended":
        if evidence is not None:
            raise ValueError("an intended commitment has no delivered evidence")
        return
    if evidence is None:
        raise ValueError("attempted/completed commitments require evidence")
    ref = evidence.owned_intent
    suffix = f":perception:{evidence.observed_tick:010d}:{actor_id}"
    if not evidence.delivery_id.endswith(suffix):
        raise ValueError("goal evidence must be this actor's delivery")
    run_id = evidence.delivery_id[: -len(suffix)]
    if not run_id:
        raise ValueError("goal evidence requires a run identity")
    _validate_reference(ref, actor_id=actor_id, run_id=run_id)
    if (
        ref.goal_id != current.goal_id
        or evidence.feedback.intent_id != ref.intent.intent_id
        or ref.committed_tick < current.created_at_tick
        or evidence.observed_tick <= ref.committed_tick
    ):
        raise ValueError("goal evidence must follow its own accepted intention")
    completed = (
        evidence.feedback.status == "success"
        and isinstance(current.completion, OwnActionSuccessPredicate)
        and _matches(current.completion, ref.intent)
    )
    if (current.status == "observed_complete") != completed:
        raise ValueError("goal status must agree with the exact delivered action verdict")


def apply_goal_change(
    state: GoalState, change: GoalChange, *, actor_id: str, tick: int
) -> GoalState:
    """Stage an accepted change; stale expectations reject without mutating input."""
    validate_goal_state(state, actor_id=actor_id)
    if type(tick) is not int or tick < 0:
        raise ValueError("tick must be a nonnegative integer")
    checked = GoalChange.model_validate(change.model_dump(mode="json"))
    current = state.current
    if current is not None and (
        tick < current.created_at_tick
        or (current.evidence is not None and tick < current.evidence.observed_tick)
    ):
        raise ValueError("a decision cannot precede its current goal/evidence")
    expected = None if current is None else current.goal_id
    if checked.expected_goal_id != expected:
        raise ValueError("expected_goal_id does not match the current goal")
    if checked.operation == "continue":
        return state.model_copy(deep=True)
    if checked.operation == "abandon":
        if current is None:
            raise ValueError("abandon requires a current goal")
        return GoalState(
            goal_schema_version="0.1", current=None, next_goal_sequence=state.next_goal_sequence
        )
    proposal = checked.proposal
    if proposal is None:
        raise ValueError("revise requires a proposal")
    result = GoalState(
        goal_schema_version="0.1",
        current=Commitment(
            goal_id=build_goal_id(actor_id, state.next_goal_sequence),
            text=proposal.text,
            completion=proposal.completion.model_copy(deep=True),
            status="intended",
            created_at_tick=tick,
            evidence=None,
        ),
        next_goal_sequence=state.next_goal_sequence + 1,
    )
    validate_goal_state(result, actor_id=actor_id)
    return result


def advance_goal_evidence(
    delivery: BoundaryPerceptionDelivery,
    owned_intents: Sequence[OwnedIntentRef],
    state: GoalState,
    *,
    run_id: str,
) -> GoalState:
    """Reduce only this delivery's feedback, before references or memory are pruned."""
    packet = BoundaryPerceptionDelivery.model_validate(delivery.model_dump(mode="json"))
    actor_id = packet.actor_id
    validate_goal_state(state, actor_id=actor_id)
    if packet.delivery_id != format_delivery_id(run_id, packet.observed_tick, actor_id):
        raise ValueError("delivery belongs to another run")
    if not run_id:
        raise ValueError("goal evidence requires a trusted run identity")
    current = state.current
    if current is not None:
        if current.created_at_tick > packet.observed_tick:
            raise ValueError("delivery cannot precede its current goal")
        evidence = current.evidence
        if evidence is not None and (
            evidence.observed_tick > packet.observed_tick
            or evidence.delivery_id != format_delivery_id(run_id, evidence.observed_tick, actor_id)
        ):
            raise ValueError("existing goal evidence must belong to this run and boundary prefix")
    refs = [OwnedIntentRef.model_validate(ref.model_dump(mode="json")) for ref in owned_intents]
    if len({ref.intent.intent_id for ref in refs}) != len(refs):
        raise ValueError("owned intent references must be unique")
    for index, candidate in enumerate(refs):
        _validate_reference(candidate, actor_id=actor_id, run_id=run_id)
        if candidate.committed_tick > packet.observed_tick:
            raise ValueError("owned intention cannot come from a future boundary")
        first = refs[0]
        if (
            candidate.intent.plan_id != first.intent.plan_id
            or candidate.decision_id != first.decision_id
            or candidate.decision_ordinal != first.decision_ordinal
            or candidate.committed_tick != first.committed_tick
            or candidate.goal_id != first.goal_id
            or candidate.intent.intent_id != build_intent_id(first.intent.plan_id, index)
        ):
            raise ValueError("owned references must be the ordered complete latest plan")
    current = state.current
    feedback = packet.perception.last_action_feedback
    if current is None or current.status == "observed_complete" or feedback is None:
        return state.model_copy(deep=True)
    ref = next((ref for ref in refs if ref.intent.intent_id == feedback.intent_id), None)
    if ref is None or ref.goal_id != current.goal_id:
        return state.model_copy(deep=True)
    if ref.committed_tick < current.created_at_tick or packet.observed_tick <= ref.committed_tick:
        raise ValueError("feedback must follow this commitment's accepted intention")
    completed = (
        feedback.status == "success"
        and isinstance(current.completion, OwnActionSuccessPredicate)
        and _matches(current.completion, ref.intent)
    )
    result = GoalState(
        goal_schema_version="0.1",
        current=Commitment(
            goal_id=current.goal_id,
            text=current.text,
            completion=current.completion.model_copy(deep=True),
            status="observed_complete" if completed else "attempted",
            created_at_tick=current.created_at_tick,
            evidence=GoalEvidence(
                delivery_id=packet.delivery_id,
                observed_tick=packet.observed_tick,
                owned_intent=ref.model_copy(deep=True),
                feedback=feedback.model_copy(deep=True),
            ),
        ),
        next_goal_sequence=state.next_goal_sequence,
    )
    validate_goal_state(result, actor_id=actor_id)
    return result


def attached_goal_id(state: GoalState) -> str | None:
    current = state.current
    if current is None or current.status == "observed_complete":
        return None
    return current.goal_id


def validate_proposal(
    proposal: DecisionProposal, request: DecisionRequestP3, config: P3PolicyConfig
) -> tuple[ActionPlan, CognitiveDelta]:
    """Validate a whole proposal and construct metadata, without accepting it."""
    checked = DecisionProposal.model_validate(proposal.model_dump(mode="json"))
    request = DecisionRequestP3.model_validate(request.model_dump(mode="json"))
    config = P3PolicyConfig.model_validate(config.model_dump(mode="json"))
    if request.actor_id != request.context.identity.actor_id:
        raise ValueError("request identity belongs to another actor")
    if config.identity_sha256 != canonical_sha256(request.context.identity):
        raise ValueError("policy identity does not match the request")
    if len(checked.actions) > config.max_plan_actions:
        raise ValueError("proposal exceeds max_plan_actions")
    apply_goal_change(
        request.context.goals,
        checked.cognitive_delta.goal_change,
        actor_id=request.actor_id,
        tick=request.tick,
    )
    plan_id = build_plan_id(request.actor_id, request.decision_ordinal)
    plan = ActionPlan(
        plan_id=plan_id,
        actor_id=request.actor_id,
        created_at_tick=request.tick,
        intents=[
            ActionIntent(
                intent_id=build_intent_id(plan_id, index),
                plan_id=plan_id,
                actor_id=request.actor_id,
                action_type=template.action_type,
                target=template.target.model_copy(deep=True)
                if template.target is not None
                else None,
                parameters=template.parameters.model_copy(deep=True),
                reason=template.reason,
            )
            for index, template in enumerate(checked.actions)
        ],
    )
    return plan, checked.cognitive_delta.model_copy(deep=True)
