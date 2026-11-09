"""Record accepted plans and explicit P1 wait substitutions."""

from living_island.agents.policies._plans import WAIT, make_plan
from living_island.agents.policies.recorded import ReplayDiverged, request_sha256
from living_island.agents.types import (
    SIM_FALLBACK_WAIT_POLICY_ID,
    DecisionOutcome,
    DecisionRecord,
    DecisionRequest,
)


def decision_record(
    run_id: str,
    request: DecisionRequest,
    outcome: DecisionOutcome,
) -> DecisionRecord:
    if outcome.status == "replayed":
        if outcome.source_record.run_id != run_id:
            raise ReplayDiverged(f"{request.actor_id}: record belongs to another run")
        return outcome.source_record
    if outcome.status == "error" and outcome.error_kind == "REPLAY_DIVERGED":
        raise ReplayDiverged(outcome.detail)
    return DecisionRecord(
        record_schema_version="0.1",
        run_id=run_id,
        tick=request.tick,
        actor_id=request.actor_id,
        decision_ordinal=request.decision_ordinal,
        policy_id=outcome.policy_id,
        effective_policy_id=(
            outcome.policy_id if outcome.status == "ok" else SIM_FALLBACK_WAIT_POLICY_ID
        ),
        triggers=request.triggers,
        request_sha256=request_sha256(request),
        status=outcome.status,
        error_kind=outcome.error_kind if outcome.status == "error" else None,
        plan=outcome.plan if outcome.status == "ok" else make_plan(request, [WAIT]),
        substituted=outcome.status == "error",
        llm_call_id=None,
    )
