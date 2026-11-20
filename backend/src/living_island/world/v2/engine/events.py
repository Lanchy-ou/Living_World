"""Objective event contracts and the single per-tick event cursor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, cast

from ..protocol import Coord, IntegerJson, WorldEvent

if TYPE_CHECKING:
    from .state import ActiveAction, WorldState

type EventType = Literal[
    "world_initialized",
    "action_started",
    "action_progressed",
    "action_succeeded",
    "action_failed",
    "action_stopped",
    "act_settled",
    "attempt_unmatched",
    "resident_moved",
    "item_transferred",
    "entity_inspected",
    "action_observed",
    "utterance_spoken",
    "utterance_heard",
    "agreement_accepted",
    "exploration_updated",
    "resident_fell_asleep",
    "resident_woke",
    "resident_fainted",
    "resident_died",
    "corpse_created",
    "rule_added",
    "agent_fallback_used",
    "entity_created",
    "entity_consumed",
    "matter_moved",
    "store_count_changed",
    "entity_state_changed",
    "stack_split",
    "stack_merged",
    "needs_changed",
    "act_items",
    "condition_witness",
    "world_rule_applied",
    "process_progressed",
]

# Required payload keys for WAP §9 and engine §11. The wire model owns envelope validation.
EVENT_FIELDS: dict[EventType, tuple[str, ...]] = {
    "world_initialized": (
        "config_hash",
        "map_hash",
        "vocabulary_hash",
        "rule_library_hash",
        "pack_ids",
        "initial_snapshot_hash",
    ),
    "action_started": ("action", "verb", "turn_id", "duration_ticks"),
    "action_progressed": ("action", "elapsed_ticks", "remaining_ticks", "route_cursor"),
    "action_succeeded": ("action",),
    "action_failed": ("action", "verb", "failure_code"),
    "action_stopped": ("action", "verb", "by", "reason"),
    "act_settled": ("verb", "rule_id", "kind", "at", "failed_check", "phenomena"),
    "attempt_unmatched": ("verb", "descriptor"),
    "resident_moved": ("from", "to", "step_cost_units"),
    "item_transferred": (
        "item_id",
        "archetype_id",
        "quantity",
        "from",
        "to",
        "via",
        "owner_before",
        "owner_after",
    ),
    "entity_inspected": ("entity_id", "descriptors"),
    "action_observed": ("observer_id", "actor_id", "observed_intent_id", "phase"),
    "utterance_spoken": (
        "utterance_id",
        "addressee_id",
        "speech_act",
        "text",
        "terms",
        "in_reply_to",
    ),
    "utterance_heard": ("utterance_id", "listener_id"),
    "agreement_accepted": ("agreement_id", "proposal_id", "acceptance_id", "terms"),
    "exploration_updated": ("resident_id", "newly_seen_tile_indices"),
    "resident_fell_asleep": ("resident_id", "duration_ticks"),
    "resident_woke": ("resident_id", "early"),
    "resident_fainted": ("resident_id",),
    "resident_died": ("resident_id", "position", "cause"),
    "corpse_created": ("corpse_id", "resident_id", "position"),
    "rule_added": ("rule_id", "content_hash", "provenance"),
    "agent_fallback_used": ("resident_id", "turn_id", "reason", "fallback_policy_id"),
    "entity_created": (
        "entity_id",
        "archetype_id",
        "material_id",
        "quantity",
        "place",
        "owner_id",
        "rule_id",
        "source",
        "recreated_from",
        "made_from",
        "process_id",
    ),
    "entity_consumed": ("entity_id", "archetype_id", "quantity", "rule_id"),
    "matter_moved": ("archetype_id", "quantity", "from", "to", "entity_id", "rule_id"),
    "store_count_changed": ("entity_id", "archetype_id", "before", "after", "rule_id", "source"),
    "entity_state_changed": ("entity_id", "field", "before", "after", "rule_id"),
    "stack_split": ("from_id", "new_id", "quantity", "cause"),
    "stack_merged": ("from_id", "into_id", "quantity"),
    "needs_changed": ("resident_id", "changes", "causes"),
    "act_items": ("rule_id", "target", "slots"),
    "condition_witness": ("intent_id", "condition_id", "entity_id", "tick", "timing"),
    "world_rule_applied": ("rule_id", "subject_id"),
    "process_progressed": ("process_id", "work_done", "contributor_id"),
}


def coord_payload(coord: Coord) -> dict[str, IntegerJson]:
    return {"x": coord.x, "y": coord.y}


@dataclass
class EventWriter:
    state: WorldState
    tick: int
    events: list[WorldEvent] = field(default_factory=list)

    def emit(
        self,
        kind: EventType,
        payload: dict[str, IntegerJson],
        *,
        actor_id: str | None = None,
        target_id: str | None = None,
        action: ActiveAction | None = None,
        llm_call_id: str | None = None,
        caused_by: tuple[str, ...] = (),
    ) -> WorldEvent:
        seq = self.state.next_event_seq_in_tick
        event_id = f"{self.state.run_id}:{self.tick:010d}:{seq:06d}"
        if target_id is None and action is not None:
            target = action.intent.target
            if target is not None and target.kind != "tile":
                target_id = target.id
        event = WorldEvent(
            schema_version="wap/0.1",
            run_id=self.state.run_id,
            event_id=event_id,
            tick=self.tick,
            seq_in_tick=seq,
            type=kind,
            actor_id=actor_id if action is None else action.intent.actor_id,
            target_id=target_id,
            intent_id=None if action is None else action.intent.intent_id,
            llm_call_id=llm_call_id,
            caused_by_event_ids=list(caused_by),
            payload=payload,
        )
        self.state.next_event_seq_in_tick += 1
        self.state.event_log_cursor += 1
        self.events.append(event)
        if action is not None:
            action.event_ids.append(event_id)
        return event


def json_object(value: object) -> dict[str, IntegerJson]:
    """Project a known protocol payload whose fields are JSON values."""
    return cast(dict[str, IntegerJson], value)
