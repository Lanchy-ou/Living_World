"""Turn eligibility and assignment of world-facing submission identities."""

from dataclasses import dataclass
from typing import Literal

from living_island.world.v2.protocol import (
    BoundaryDelivery,
    ContinueAction,
    Intent,
    IntentAction,
    InvalidTurn,
    ModelTurn,
    TurnSubmission,
)

TurnReason = Literal["start", "woke", "action_ended", "notification"]


@dataclass(frozen=True)
class TurnRequest:
    delivery: BoundaryDelivery
    ordinal: int
    reasons: tuple[TurnReason, ...]

    @property
    def turn_id(self) -> str:
        return f"{self.delivery.actor_id}:t{self.ordinal:06d}"

    def check_binding(self, submission: TurnSubmission) -> None:
        """Require the callback answer to address this particular request."""
        actor_id = self.delivery.actor_id
        turn_id = self.turn_id
        if (submission.actor_id, submission.observed_tick, submission.turn_id) != (
            actor_id,
            self.delivery.observed_tick,
            turn_id,
        ):
            raise InvalidTurn("submission does not answer the scheduled turn")
        if submission.action.kind == "intent":
            intent = submission.action.intent
            if (intent.actor_id, intent.turn_id, intent.intent_id) != (
                actor_id,
                turn_id,
                f"{turn_id}:a",
            ):
                raise InvalidTurn("nested intent identity does not match the scheduled turn")

    def bind(self, choice: ModelTurn) -> TurnSubmission:
        """Attach the harness-owned IDs to an already typed model choice."""
        actor_id = self.delivery.actor_id
        turn_id = self.turn_id
        action = choice.action
        bound_action: ContinueAction | IntentAction
        if action.kind == "intent":
            shape = action.intent
            intent = Intent.model_construct(
                intent_id=f"{turn_id}:a",
                turn_id=turn_id,
                actor_id=actor_id,
                action=shape.action,
                verb=shape.verb,
                target=shape.target,
                instruments=shape.instruments,
                inputs=shape.inputs,
                params=shape.params,
                reason=shape.reason,
            )
            bound_action = IntentAction.model_construct(kind="intent", intent=intent)
        else:
            bound_action = action
        return TurnSubmission.model_construct(
            schema_version=self.delivery.perception.schema_version,
            turn_id=turn_id,
            actor_id=actor_id,
            observed_tick=self.delivery.observed_tick,
            action=bound_action,
            utterance=choice.utterance,
        )


def turn_reasons(packet: BoundaryDelivery, notified: bool) -> tuple[TurnReason, ...]:
    """Find the reasons for one turn from a living resident's packet."""
    if packet.perception.awareness != "awake":
        return ()
    reasons: list[TurnReason] = []
    if packet.observed_tick == 0:
        reasons.append("start")
    report_kinds = {report.kind for report in packet.reports}
    if "woke" in report_kinds:
        reasons.append("woke")
    if "action_ended" in report_kinds:
        reasons.append("action_ended")
    if notified and packet.perception.running_action is not None:
        reasons.append("notification")
    return tuple(reasons)
