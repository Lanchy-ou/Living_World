"""Backend-only ``SavePackage`` envelope (Interface Contract §5 as amended by A1).

Reuses canonical world and agent models; neither ``world`` nor ``agents`` imports back.
Not exported to TypeScript generation (not listed in ``contract.__all__``).
"""

from __future__ import annotations

from pydantic import JsonValue, model_validator

from living_island.agents.types import ResidentRuntimeState
from living_island.world.protocol import (
    ActionPlan,
    BoundaryPerceptionDelivery,
    CursorTick,
    DeferredDecisionTriggers,
    NonNegInt,
    ProtocolModel,
    require_sorted_unique,
)
from living_island.world.state import WorldState


class DeliveryCursor(ProtocolModel):
    actor_id: str
    last_observed_tick: CursorTick


class AgentStateSection(ProtocolModel):
    profiles: list[dict[str, JsonValue]]
    goal_states: list[dict[str, JsonValue]]
    personal_memories: list[dict[str, JsonValue]]
    relationships: list[dict[str, JsonValue]]
    queued_plans: list[ActionPlan]  # unstarted intents only; the active intent lives in world
    deferred_decision_triggers: list[DeferredDecisionTriggers]
    delivered_perception_ticks: list[DeliveryCursor]
    runtime_states: list[ResidentRuntimeState]  # A1

    @model_validator(mode="after")
    def _sorted(self) -> AgentStateSection:
        require_sorted_unique(
            [d.actor_id for d in self.deferred_decision_triggers], "deferred_decision_triggers"
        )
        require_sorted_unique(
            [d.actor_id for d in self.delivered_perception_ticks], "delivered_perception_ticks"
        )
        require_sorted_unique([r.actor_id for r in self.runtime_states], "runtime_states")
        return self


class SavePackage(ProtocolModel):
    save_schema_version: str
    world: WorldState
    agent_state: AgentStateSection
    event_cursor: NonNegInt
    llm_record_cursor: NonNegInt
    decision_record_cursor: NonNegInt  # A1
    pending_perception_deliveries: list[BoundaryPerceptionDelivery]
    canonical_config_hash: str
    canonical_map_hash: str

    @model_validator(mode="after")
    def _consistent(self) -> SavePackage:
        if self.event_cursor != self.world.event_log_cursor:
            raise ValueError("event_cursor must equal world.event_log_cursor")
        ordinals = sum(r.next_decision_ordinal for r in self.agent_state.runtime_states)
        if ordinals != self.decision_record_cursor:
            raise ValueError("runtime ordinals must sum to decision_record_cursor")
        if (self.canonical_config_hash, self.canonical_map_hash) != (
            self.world.config_hash,
            self.world.map_hash,
        ):
            raise ValueError("canonical hashes must match the world snapshot identities")
        keys = [(d.observed_tick, d.actor_id) for d in self.pending_perception_deliveries]
        if any(a >= b for a, b in zip(keys, keys[1:], strict=False)):
            raise ValueError("pending deliveries sort by (observed_tick, actor_id), unique")
        # Resumable pre-ingest checkpoint (IC §5, AI §6): exactly one packet per living
        # actor for the saved tick, none for dead actors.
        resident_ids = [r.id for r in self.world.residents]
        living = [r.id for r in self.world.residents if r.alive]
        for d in self.pending_perception_deliveries:
            if d.observed_tick != self.world.tick:
                raise ValueError("pending deliveries must be for the saved world tick")
            if not d.delivery_id.startswith(f"{self.world.run_id}:perception:"):
                raise ValueError("pending delivery_id must use the saved run_id")
        if [d.actor_id for d in self.pending_perception_deliveries] != living:
            raise ValueError("exactly one pending delivery per living actor, none for dead")
        if [r.actor_id for r in self.agent_state.runtime_states] != resident_ids:
            raise ValueError("runtime_states actor set must match the world residents")
        return self
