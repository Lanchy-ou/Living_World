"""Synchronous simulation boundary orchestration."""

from living_island.agents.base import ResidentRuntime
from living_island.agents.types import DecisionRecord
from living_island.sim.decisions import decision_record
from living_island.world.ports import WorldEngine, WorldTickCommit
from living_island.world.protocol import DECISION_TRIGGERS, DecisionTrigger, format_delivery_id


class BoundaryLoop:
    """Drive the engine from a committed boundary and acknowledge each packet once."""

    def __init__(self, engine: WorldEngine, runtime: ResidentRuntime) -> None:
        self._engine = engine
        self._runtime = runtime
        self._cursor = -1
        self._deferred: set[DecisionTrigger] = set()
        self._commit = engine.initial_commit()

    @property
    def boundary(self) -> WorldTickCommit:
        return self._commit

    def advance(self) -> tuple[WorldTickCommit, list[DecisionRecord]]:
        snapshot = self._commit.snapshot
        actor_id = self._runtime.actor_id
        self._engine.begin_tick()
        records: list[DecisionRecord] = []
        if self._commit.pending_deliveries:
            (packet,) = self._commit.pending_deliveries
            if (
                packet.actor_id != actor_id
                or packet.delivery_id
                != format_delivery_id(snapshot.run_id, snapshot.tick, actor_id)
                or packet.observed_tick != snapshot.tick
                or self._cursor != snapshot.tick - 1
            ):
                raise ValueError(f"{actor_id}: invalid pending delivery at tick {snapshot.tick}")
            self._runtime.ingest(packet)
            self._cursor = packet.observed_tick
            self._deferred.update(packet.decision_triggers)
            if not snapshot.active_actions:
                if snapshot.tick:
                    self._deferred.add("PLAN_FINISHED")
                triggers = [trigger for trigger in DECISION_TRIGGERS if trigger in self._deferred]
                request = self._runtime.make_request(snapshot.tick, triggers)
                outcome = self._runtime.decide(request)
                record = decision_record(snapshot.run_id, request, outcome)
                (intent,) = record.plan.intents
                records.append(record)
                self._runtime.commit_decision(record)
                self._deferred.clear()
                self._engine.start_intent(intent)
        self._commit = self._engine.advance_tick()
        return self._commit, records
