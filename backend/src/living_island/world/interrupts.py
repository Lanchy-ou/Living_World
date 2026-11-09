"""Boundary triggers and the soft interruption table (WR §4.3–4.4)."""

from living_island.world.content import EffectiveConfig
from living_island.world.protocol import DecisionTrigger, HeardUtterance, InterruptionReason
from living_island.world.state import ActiveAction, ResidentPhysicalState


def observations(
    config: EffectiveConfig,
    before: ResidentPhysicalState,
    after: ResidentPhysicalState,
    heard: list[HeardUtterance],
    new_sight: bool,
) -> set[DecisionTrigger]:
    thresholds = config.agents
    triggers: set[DecisionTrigger] = set()
    if (
        before.satiety > thresholds.urgent_satiety_below >= after.satiety
        or before.hydration > thresholds.urgent_hydration_below >= after.hydration
        or before.stamina > thresholds.urgent_stamina_below >= after.stamina
    ):
        triggers.add("URGENT_NEED")
    if new_sight:
        triggers.add("NEW_SIGHT")
    if heard:
        triggers.add("UTTERANCE_HEARD")
    directed = [utterance for utterance in heard if utterance.addressee_id == after.id]
    if directed:
        triggers.add("DIRECT_SPEECH")
    if any(utterance.speech_act == "request" for utterance in directed):
        triggers.add("REPLY_REQUIRED")
    return triggers


def soft_interrupt(
    action: ActiveAction,
    triggers: set[DecisionTrigger],
) -> InterruptionReason | None:
    if action.pending_failure_code is not None:
        return None
    kind = action.intent.action_type
    if kind in ("move_to", "gather", "rest", "sleep") and "URGENT_NEED" in triggers:
        return "URGENT_NEED"
    if kind in ("move_to", "gather", "rest") and "DIRECT_SPEECH" in triggers:
        return "DIRECT_SPEECH"
    if kind == "move_to" and "NEW_SIGHT" in triggers:
        return "NEW_SIGHT"
    return None
