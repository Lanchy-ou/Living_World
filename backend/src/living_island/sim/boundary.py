"""Synchronous simulation boundary orchestration."""

from collections import deque
from collections.abc import Sequence

from living_island.agents.base import ResidentRuntime
from living_island.agents.types import DecisionRecord
from living_island.contract.save import AgentStateSection, DeliveryCursor, SavePackage
from living_island.sim.decisions import decision_record
from living_island.world.ports import WorldEngine, WorldTickCommit
from living_island.world.protocol import (
    DECISION_TRIGGERS,
    ActionIntent,
    ActionPlan,
    DecisionTrigger,
    DeferredDecisionTriggers,
    format_delivery_id,
)


class BoundaryLoop:
    """Drive the engine from a committed boundary and acknowledge each packet once."""

    def __init__(
        self,
        engine: WorldEngine,
        runtimes: Sequence[ResidentRuntime],
        restored: SavePackage | None = None,
    ) -> None:
        self._engine = engine
        self._commit = (
            engine.initial_commit()
            if restored is None
            else WorldTickCommit(
                snapshot=restored.world,
                events=[],
                pending_deliveries=restored.pending_perception_deliveries,
            ).model_copy(deep=True)
        )
        self._runtimes = {runtime.actor_id: runtime for runtime in runtimes}
        if len(self._runtimes) != len(runtimes) or set(self._runtimes) != {
            resident.id for resident in self._commit.snapshot.residents
        }:
            raise ValueError("simulation requires one runtime per configured resident")
        self._cursors = dict.fromkeys(self._runtimes, -1)
        self._deferred: dict[str, set[DecisionTrigger]] = {
            actor_id: set() for actor_id in self._runtimes
        }
        self._queued: dict[str, ActionPlan] = {}
        self._at_boundary = True
        self._decision_cursor = 0
        if restored is not None:
            self._restore_agents(restored)

    def _restore_agents(self, save: SavePackage) -> None:
        agents = save.agent_state
        self._decision_cursor = save.decision_record_cursor
        self._cursors = {
            c.actor_id: c.last_observed_tick for c in agents.delivered_perception_ticks
        }
        living = {r.id for r in save.world.residents if r.alive}
        for plan in agents.queued_plans:
            if plan.actor_id not in living or plan.actor_id in self._queued:
                raise ValueError(f"{plan.actor_id}: invalid restored queue")
            self._queued[plan.actor_id] = plan.model_copy(deep=True)
        for entry in agents.deferred_decision_triggers:
            if entry.actor_id not in living:
                raise ValueError(f"{entry.actor_id}: invalid restored deferred triggers")
            self._deferred[entry.actor_id].update(entry.reasons)

    @property
    def decision_record_cursor(self) -> int:
        return self._decision_cursor

    def checkpoint(self) -> SavePackage:
        if not self._at_boundary:
            raise ValueError("checkpoint requires a completed pre-ingest boundary")
        world = self._commit.snapshot
        return SavePackage(
            save_schema_version="0.1",
            world=world,
            agent_state=AgentStateSection(
                profiles=[],
                goal_states=[],
                personal_memories=[],
                relationships=[],
                queued_plans=[self._queued[actor] for actor in sorted(self._queued)],
                deferred_decision_triggers=[
                    DeferredDecisionTriggers(
                        actor_id=actor,
                        reasons=[
                            code for code in DECISION_TRIGGERS if code in self._deferred[actor]
                        ],
                    )
                    for actor in sorted(self._deferred)
                    if self._deferred[actor]
                ],
                delivered_perception_ticks=[
                    DeliveryCursor(actor_id=actor, last_observed_tick=tick)
                    for actor, tick in sorted(self._cursors.items())
                ],
                runtime_states=[
                    self._runtimes[actor].export_state() for actor in sorted(self._runtimes)
                ],
            ),
            event_cursor=world.event_log_cursor,
            llm_record_cursor=0,
            decision_record_cursor=self._decision_cursor,
            pending_perception_deliveries=self._commit.pending_deliveries,
            canonical_config_hash=world.config_hash,
            canonical_map_hash=world.map_hash,
        ).model_copy(deep=True)

    @property
    def boundary(self) -> WorldTickCommit:
        return self._commit

    def advance(self) -> tuple[WorldTickCommit, list[DecisionRecord]]:
        if not self._at_boundary:
            raise ValueError("simulation stopped before a completed boundary")
        self._at_boundary = False
        self._engine.begin_tick()
        self._ingest()
        records, starts = self._schedule()
        for intent in starts:
            self._engine.start_intent(intent)
        self._commit = self._engine.advance_tick()
        self._discard_unstarted()
        self._decision_cursor += len(records)
        self._at_boundary = True
        return self._commit, records

    def _ingest(self) -> None:
        snapshot = self._commit.snapshot
        pending = deque(self._commit.pending_deliveries)
        living = sorted(resident.id for resident in snapshot.residents if resident.alive)
        if [packet.actor_id for packet in pending] != living:
            raise ValueError(
                f"expected one pending delivery per living actor at tick {snapshot.tick}"
            )
        while pending:
            packet = pending[0]
            actor_id = packet.actor_id
            if (
                packet.delivery_id != format_delivery_id(snapshot.run_id, snapshot.tick, actor_id)
                or packet.observed_tick != snapshot.tick
                or self._cursors[actor_id] != snapshot.tick - 1
            ):
                raise ValueError(f"{actor_id}: invalid pending delivery at tick {snapshot.tick}")
            self._runtimes[actor_id].ingest(packet)
            self._cursors[actor_id] = packet.observed_tick
            pending.popleft()
            self._deferred[actor_id].update(packet.decision_triggers)
            feedback = packet.perception.last_action_feedback
            if (
                feedback is not None
                and feedback.status == "success"
                and actor_id not in self._queued
            ):
                self._deferred[actor_id].add("PLAN_FINISHED")

    def _schedule(self) -> tuple[list[DecisionRecord], list[ActionIntent]]:
        snapshot = self._commit.snapshot
        active = {action.intent.actor_id for action in snapshot.active_actions}
        records: list[DecisionRecord] = []
        starts: list[ActionIntent] = []
        for actor_id in sorted(self._runtimes):
            if actor_id in active or self._cursors[actor_id] != snapshot.tick:
                continue
            runtime = self._runtimes[actor_id]
            deferred = self._deferred[actor_id]
            if snapshot.tick == 0 or deferred:
                self._queued.pop(actor_id, None)
                triggers = (
                    [code for code in DECISION_TRIGGERS if code in deferred]
                    if snapshot.tick
                    else []
                )
                request = runtime.make_request(snapshot.tick, triggers)
                record = decision_record(snapshot.run_id, request, runtime.decide(request))
                self._queued[actor_id] = record.plan
                records.append(record)
                runtime.commit_decision(record)
                deferred.clear()
            plan = self._queued.pop(actor_id)
            intent, *remaining = plan.intents
            starts.append(intent)
            if remaining:
                self._queued[actor_id] = plan.model_copy(update={"intents": remaining})
        return records, starts

    def _discard_unstarted(self) -> None:
        """Clean up invalidated queues before the next pre-ingest checkpoint."""
        for resident in self._commit.snapshot.residents:
            if not resident.alive:
                self._queued.pop(resident.id, None)
                self._deferred[resident.id].clear()
        for packet in self._commit.pending_deliveries:
            feedback = packet.perception.last_action_feedback
            if feedback is not None and feedback.status != "success":
                self._queued.pop(packet.actor_id, None)
