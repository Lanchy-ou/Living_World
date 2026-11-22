"""Private outcome translation for the legacy rule-based policy."""

from typing import Literal, cast

from living_island.world import protocol as v1
from living_island.world.v2 import protocol as v2

from .config import BoundCompatPack


def legacy_result(
    intent: v1.ActionIntent,
    started: int,
    finished: int,
    *,
    code: v1.FailureCode | None = None,
    reason: v1.InterruptionReason | None = None,
) -> v1.ActionResult:
    status: v1.ActionStatus = (
        "interrupted" if reason is not None else "failure" if code is not None else "success"
    )
    feedback = v1.ActionFeedback(
        intent_id=intent.intent_id,
        status=status,
        failure_code=code,
        interruption_reason=reason,
        visible_effects=[],
    )
    return v1.ActionResult(
        intent_id=intent.intent_id,
        actor_id=intent.actor_id,
        tick_started=started,
        tick_finished=finished,
        status=status,
        failure_code=code,
        interruption_reason=reason,
        visible_feedback=feedback,
        state_delta=[],
        event_ids=[],
    )


def _kernel_code(code: v2.FailureCode) -> v1.FailureCode:
    return cast(v1.FailureCode, code) if code in v1.FAILURE_CODES else "INVALID_TARGET"


def _stop(
    intent: v1.ActionIntent,
    started: int,
    finished: int,
    reason: v2.HardStop,
) -> v1.ActionResult | None:
    if reason in ("EXHAUSTED", "PATH_BLOCKED"):
        return legacy_result(intent, started, finished, code=reason)
    if reason == "DEATH":
        return legacy_result(intent, started, finished, reason="DEATH")
    if reason == "WOKEN":
        return legacy_result(intent, started, finished, reason="URGENT_NEED")
    # Starter stops have no v1 reason. The host invalidates the queue.
    return None


def _talk_code(
    speech: v2.UtteranceFeedback | None,
    suppressed: bool,
) -> v1.FailureCode | None:
    if suppressed:
        return "INVALID_SPEECH_ACT"
    code = cast(v2.UtteranceFeedback, speech).failure_code
    return _kernel_code(code) if code is not None else None


class LegacyBridge:
    """Map the policy's own authoritative results using an admitted pack."""

    def __init__(self, bound: BoundCompatPack) -> None:
        if bound.pack.pack_id != "compat-v1":
            raise ValueError("legacy bridge requires compat-v1")
        self._codes = {rule: dict(checks) for rule, checks in bound.codes.items()}
        self.pack_hash = bound.pack.pack_hash

    def translate(
        self,
        intent: v1.ActionIntent,
        result: v2.ActionResult,
        speech: v2.UtteranceFeedback | None,
        *,
        suppressed: bool = False,
    ) -> v1.ActionResult | None:
        started, finished = result.tick_started, result.tick_finished
        if result.outcome == "stopped":
            stop = cast(v2.Stop, result.stop)
            # Policy-driven actor stops are consumed by the host using its saved legacy ID.
            return _stop(intent, started, finished, stop.reason) if stop.by == "world" else None
        code: v1.FailureCode | None = None
        if result.outcome == "failure":
            code = _kernel_code(cast(v2.FailureCode, result.failure_code))
        elif result.outcome == "settled":
            settlement = cast(v2.Settlement, result.settlement)
            if settlement.kind == "unmet":
                rule, check = cast(str, settlement.rule_id), cast(str, settlement.failed_check)
                mapped = self._codes[rule][check]
                if mapped in ("defect", "unreachable"):
                    raise ValueError(f"compatibility defect: {rule}.{check} settled unmet")
                code = cast(v1.FailureCode, mapped)
            elif settlement.kind != "applied":
                code = "INVALID_TARGET"
        elif intent.action_type == "talk":
            code = _talk_code(speech, suppressed)
        return legacy_result(intent, started, finished, code=code)


_VISIBLE_CODES: dict[str, dict[str, v1.FailureCode | None]] = {
    "gather": {
        "picks_fruit": None,
        "too_tired": "EXHAUSTED",
        "hands_full": "INVENTORY_FULL",
        "finds_nothing": "RESOURCE_TAKEN",
        "nothing_happens": "OUT_OF_REACH",
    },
    "eat": {"tastes_good": None, "not_hungry": "NO_NEED", "nothing_happens": "NO_ITEM"},
    "spring": {"drinks": None, "not_thirsty": "NO_NEED", "no_water_here": "OUT_OF_REACH"},
    "canteen": {
        "drinks": None,
        "not_thirsty": "NO_NEED",
        "no_water_here": "NO_WATER",
        "nothing_happens": "NO_ITEM",
    },
    "fill_canteen": {
        "fills_up": None,
        "no_water_here": "OUT_OF_REACH",
        "already_full": "ALREADY_FULL",
        "nothing_happens": "NO_ITEM",
    },
    "rest": {"rests": None},
    "sleep": {"sleeps": None},
}


def visible_result(
    intent: v1.ActionIntent,
    started: int,
    tick: int,
    feedback: v2.ActionFeedback,
    speech: v2.UtteranceFeedback | None,
    *,
    suppressed: bool = False,
) -> v1.ActionResult | None:
    """Derive a private policy result from its own intent and public feedback."""
    if feedback.status == "stopped":
        reason = cast(v2.HardStop | Literal["own_choice"], feedback.stop_reason)
        return None if reason == "own_choice" else _stop(intent, started, tick, reason)
    code: v1.FailureCode | None
    if feedback.status == "failed":
        code = _kernel_code(cast(v2.FailureCode, feedback.failure_code))
    elif intent.action_type == "talk":
        code = _talk_code(speech, suppressed)
    elif intent.action_type in ("move_to", "give", "pick_up", "wait"):
        code = None
    else:
        row = (
            cast(v1.DrinkParameters, intent.parameters).source
            if intent.action_type == "drink"
            else intent.action_type
        )
        table = _VISIBLE_CODES[row]
        code = next((table[word] for word in feedback.phenomena if word in table), "INVALID_TARGET")
    return legacy_result(intent, started, tick, code=code)
