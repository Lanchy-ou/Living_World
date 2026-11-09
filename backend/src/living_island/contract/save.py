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
    format_delivery_id,
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
        """Pre-ingest checkpoint invariants S1-S11 (P1-01a handoff, invariant table)."""
        world, agents = self.world, self.agent_state
        tick = world.tick
        resident_ids = [r.id for r in world.residents]
        living = {r.id for r in world.residents if r.alive}
        # S1: event cursor
        if self.event_cursor != world.event_log_cursor:
            raise ValueError("event_cursor must equal world.event_log_cursor")
        # S2: canonical identities
        if (self.canonical_config_hash, self.canonical_map_hash) != (
            world.config_hash,
            world.map_hash,
        ):
            raise ValueError("canonical hashes must match the world snapshot identities")
        # S3: one runtime state per resident
        runtimes = {r.actor_id: r for r in agents.runtime_states}
        if list(runtimes) != resident_ids:
            raise ValueError("runtime_states must hold exactly one entry per world resident")
        # S4: ordinals sum to the committed decision count
        if sum(r.next_decision_ordinal for r in runtimes.values()) != self.decision_record_cursor:
            raise ValueError("runtime ordinals must sum to decision_record_cursor")
        # S5: no decision before the first ingest (tick-zero initialization)
        if tick == 0 and self.decision_record_cursor != 0:
            raise ValueError("a tick-zero checkpoint has no committed decisions")
        # S6: one delivery cursor per resident, none foreign
        cursors = {c.actor_id: c.last_observed_tick for c in agents.delivered_perception_ticks}
        if list(cursors) != resident_ids:
            raise ValueError("delivered_perception_ticks must hold one cursor per resident")
        for actor_id in resident_ids:
            cursor = cursors[actor_id]
            # S7: delivery cursor equals runtime ingest bookkeeping
            if runtimes[actor_id].latest_perception_tick != cursor:
                raise ValueError(f"{actor_id}: latest_perception_tick must equal its cursor")
            # S8: pre-ingest: living actors acknowledged exactly tick-1 (-1 at tick 0);
            # nobody has acknowledged the saved tick or a future one
            if actor_id in living and cursor != tick - 1:
                raise ValueError(f"{actor_id}: living actor cursor must be {tick - 1}")
            if cursor >= tick:
                raise ValueError(f"{actor_id}: cursor must be before the saved tick")
        # S9: pending packets sorted by (observed_tick, actor_id), unique
        keys = [(d.observed_tick, d.actor_id) for d in self.pending_perception_deliveries]
        if any(a >= b for a, b in zip(keys, keys[1:], strict=False)):
            raise ValueError("pending deliveries sort by (observed_tick, actor_id), unique")
        # S10: exactly one packet per living actor, none for dead
        if {d.actor_id for d in self.pending_perception_deliveries} != living or len(
            self.pending_perception_deliveries
        ) != len(living):
            raise ValueError("exactly one pending delivery per living actor, none for dead")
        # S11: packet for the saved tick with the exact canonical delivery ID
        for d in self.pending_perception_deliveries:
            if d.observed_tick != tick:
                raise ValueError("pending deliveries must be for the saved world tick")
            if d.delivery_id != format_delivery_id(world.run_id, tick, d.actor_id):
                raise ValueError("pending delivery_id must equal format_delivery_id")
        return self
