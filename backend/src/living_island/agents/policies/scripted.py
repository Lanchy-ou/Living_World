"""Actor-local scripted scenarios (Agent Interface §4.2)."""

from pydantic import JsonValue

from living_island.agents.policies._plans import WAIT, make_plan
from living_island.agents.types import ActorScript, DecisionRequest, ErrorOutcome, OkOutcome


class ScriptedPolicy:
    policy_id = "scripted-v0"

    def __init__(self, script: ActorScript, cursor: int = 0) -> None:
        if not 0 <= cursor <= len(script.plans):
            raise ValueError(f"{script.actor_id}: script cursor outside the loaded script")
        self._script = script.model_copy(deep=True)
        self._cursor = cursor

    def decide(self, request: DecisionRequest) -> OkOutcome | ErrorOutcome:
        if self._cursor < len(self._script.plans):
            templates = self._script.plans[self._cursor]
        elif self._script.on_exhausted == "error":
            return ErrorOutcome(
                status="error",
                policy_id=self.policy_id,
                error_kind="SCRIPT_EXHAUSTED",
                detail=f"{request.actor_id}: no more scripted plans",
            )
        else:
            templates = [WAIT]
        return OkOutcome(status="ok", policy_id=self.policy_id, plan=make_plan(request, templates))

    def commit(self) -> None:
        self._cursor = min(self._cursor + 1, len(self._script.plans))

    def export_state(self) -> dict[str, JsonValue]:
        return {"cursor": self._cursor}
