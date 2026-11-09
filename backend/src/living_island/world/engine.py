"""P1 world engine and its single event allocator."""

from __future__ import annotations

import hashlib

from living_island.world.content import WorldContent, canonical_json_bytes
from living_island.world.facts import (
    ActionFailedPayload,
    ActionProgressedPayload,
    ActionStartedPayload,
    ActionSucceededPayload,
    EventType,
    ExplorationUpdatedPayload,
    TypedEventPayload,
    WorldEvent,
    WorldInitializedPayload,
    format_event_id,
)
from living_island.world.movement import move, plan_movement
from living_island.world.ports import (
    ObservationAccumulator,
    ObservationBatch,
    WorldTickCommit,
    begin_observation_tick,
    finish_observation_tick,
)
from living_island.world.protocol import (
    ActionIntent,
    BoundaryPerceptionDelivery,
    Coord,
    FailureCode,
    Perception,
    TileTarget,
    format_delivery_id,
)
from living_island.world.receipts import merge_receipts, merge_tile_indices
from living_island.world.space import StaticMap
from living_island.world.state import (
    ActiveAction,
    CueState,
    ExploredTiles,
    ExposureReceipts,
    FruitNodeState,
    ResidentPhysicalState,
    RuleOverrides,
    UniqueCanteenState,
    WorldState,
)


def _coord(pair: list[int]) -> Coord:
    return Coord(x=pair[0], y=pair[1])


def _initialize(content: WorldContent) -> WorldState:
    config = content.config
    residents = sorted(config.residents, key=lambda resident: resident.id)
    return WorldState(
        schema_version=config.meta.schema_version,
        world_id=config.meta.world_id,
        run_id=config.meta.run_id,
        tick=0,
        config_hash=content.config_hash,
        map_hash=content.map_hash,
        static_map_ref=config.map.layout_file,
        residents=[
            ResidentPhysicalState(
                id=resident.id,
                position=_coord(resident.position),
                alive=True,
                satiety=config.needs.initial_satiety,
                hydration=config.needs.initial_hydration,
                stamina=config.needs.initial_stamina,
                health=config.needs.initial_health,
                fruit_count=0,
            )
            for resident in residents
        ],
        fruit_nodes=[
            FruitNodeState(
                id=tree.id,
                position=_coord(tree.position),
                stock=config.fruit.initial_stock_per_tree,
                regrow_phase_offset_ticks=tree.regrow_phase_offset_ticks,
            )
            for tree in sorted(config.world.fruit_trees, key=lambda tree: tree.id)
        ],
        cave=_coord(config.world.initial_cave),
        spring=_coord(config.world.spring),
        cues=[
            CueState(id=cue.id, kind=cue.kind, position=_coord(cue.position))
            for cue in sorted(config.world.cues, key=lambda cue: cue.id)
        ],
        ground_fruit=[],
        lifetime_fruit_regrown=0,
        lifetime_fruit_consumed=0,
        unique_canteen=UniqueCanteenState(
            id=config.canteen.unique_item_id,
            holder_id=config.canteen.initial_owner_id,
            ground_position=None,
            servings=config.canteen.initial_servings,
        ),
        corpses=[],
        dialogue_sessions=[],
        active_actions=[],
        explored_tiles_by_resident=[
            ExploredTiles(resident_id=resident.id, tile_indices=[]) for resident in residents
        ],
        exposure_receipts_by_resident=[
            ExposureReceipts(resident_id=resident.id, entities=[], cue_detail_seen=[])
            for resident in residents
        ],
        resolution_rng_state_uint32=config.meta.seed,
        next_event_seq_in_tick=0,
        event_log_cursor=0,
        rule_overrides=RuleOverrides(),
    )


class Engine:
    def __init__(self, content: WorldContent, restored_world: WorldState | None):
        self._content = WorldContent.model_validate(content.model_dump())
        self._config = self._content.config
        self._map = StaticMap.from_content(self._content)
        self._state = (
            _initialize(self._content) if restored_world is None else self._restore(restored_world)
        )
        self._initial_pending = restored_world is None
        self._tick: int | None = None
        self._events: list[WorldEvent] = []
        self._event_ids: set[str] = set()
        self._submitted: dict[str, ActionIntent] = {}

    def _restore(self, state: WorldState) -> WorldState:
        if (
            state.config_hash != self._content.config_hash
            or state.map_hash != self._content.map_hash
            or state.world_id != self._config.meta.world_id
            or state.run_id != self._config.meta.run_id
            or state.schema_version != self._config.meta.schema_version
            or state.static_map_ref != self._config.map.layout_file
        ):
            raise ValueError("restored world does not match the verified content identities")
        return WorldState.model_validate(state.model_dump())

    def initial_commit(self) -> WorldTickCommit:
        if not self._initial_pending:
            raise RuntimeError("initial_commit is only available once on a fresh engine")
        self._initial_pending = False
        self._tick = 0
        batch = finish_observation_tick(
            begin_observation_tick(self._state, 0, self._content), self._state
        )
        self._apply_observations(batch)
        # Hash the final tick-zero snapshot, including the cursors for its known fact count.
        initial_count = 1 + len(batch.new_static_tiles_by_actor)
        initial_snapshot = self._state.model_copy(
            update={
                "event_log_cursor": initial_count,
                "next_event_seq_in_tick": initial_count,
            }
        )
        digest = hashlib.sha256(canonical_json_bytes(initial_snapshot.model_dump(mode="json")))
        self.append_fact(
            "world_initialized",
            None,
            None,
            None,
            None,
            [],
            WorldInitializedPayload(
                config_hash=self._state.config_hash,
                map_hash=self._state.map_hash,
                initial_snapshot_hash=digest.hexdigest(),
            ),
        )
        self._exploration_facts(batch)
        return self._commit(batch)

    def begin_tick(self) -> None:
        if self._initial_pending or self._tick is not None:
            raise RuntimeError("begin_tick requires a committed boundary")
        self._tick = self._state.tick + 1

    def _open_tick(self) -> int:
        if self._tick is None:
            raise RuntimeError("begin_tick must open the next tick first")
        return self._tick

    def start_intent(self, intent: ActionIntent) -> None:
        self._open_tick()
        actor = intent.actor_id
        if not any(resident.id == actor for resident in self._state.residents):
            raise ValueError(f"unknown actor {actor!r}")
        if actor in self._submitted or any(
            action.intent.actor_id == actor for action in self._state.active_actions
        ):
            raise RuntimeError(f"{actor!r} already has an action for this interval")
        self._submitted[actor] = intent.model_copy(deep=True)

    def append_fact(
        self,
        type: EventType,
        actor_id: str | None,
        target_id: str | None,
        intent_id: str | None,
        llm_call_id: str | None,
        caused_by_event_ids: list[str],
        payload: TypedEventPayload,
    ) -> WorldEvent:
        tick = self._open_tick()
        if type == "config_changed" or (type == "world_initialized" and (tick or self._events)):
            raise ValueError(f"{type} cannot be emitted at this boundary")
        if any(cause not in self._event_ids for cause in caused_by_event_ids):
            raise ValueError("causal references must name events already emitted by this engine")
        seq = len(self._events)
        event = WorldEvent(
            schema_version=self._state.schema_version,
            run_id=self._state.run_id,
            event_id=format_event_id(self._state.run_id, tick, seq),
            tick=tick,
            seq_in_tick=seq,
            type=type,
            actor_id=actor_id,
            target_id=target_id,
            intent_id=intent_id,
            llm_call_id=llm_call_id,
            caused_by_event_ids=list(caused_by_event_ids),
            payload=payload,
        ).model_copy(deep=True)
        self._events.append(event)
        self._event_ids.add(event.event_id)
        return event.model_copy(deep=True)

    def _action_fact(
        self, type: EventType, action: ActiveAction, payload: TypedEventPayload
    ) -> None:
        intent = action.intent
        self.append_fact(type, intent.actor_id, None, intent.intent_id, None, [], payload)

    def _start(self, resident: ResidentPhysicalState, intent: ActionIntent) -> ActiveAction:
        if intent.action_type != "move_to":
            raise RuntimeError("only movement is wired at checkpoint A")
        assert isinstance(intent.target, TileTarget)
        route: list[Coord] | None = None
        failure: FailureCode | None = None
        if not resident.alive:
            failure = "DEAD"
        elif resident.stamina <= self._config.needs.min_value:
            failure = "EXHAUSTED"
        else:
            explored = next(
                group.tile_indices
                for group in self._state.explored_tiles_by_resident
                if group.resident_id == resident.id
            )
            path = plan_movement(self._map, explored, resident.position, intent.target.position)
            if isinstance(path, str):
                failure = path
            elif path.status != "ok":
                failure = path.status
            else:
                route = list(path.route)
        duration = None if failure is None else self._config.actions.invalid_attempt_ticks
        action = ActiveAction(
            intent=intent,
            tick_started=self._state.tick,
            elapsed_ticks=0,
            remaining_ticks=duration,
            route=route,
            route_cursor=0 if route is not None else None,
            pending_failure_code=failure,
        )
        self._action_fact(
            "action_started",
            action,
            ActionStartedPayload(
                action_type=intent.action_type,
                plan_id=intent.plan_id,
                duration_ticks=duration,
            ),
        )
        return action

    def _progress(
        self,
        resident: ResidentPhysicalState,
        action: ActiveAction,
        observations: ObservationAccumulator,
    ) -> bool:
        action.elapsed_ticks += 1
        if action.remaining_ticks is not None:
            action.remaining_ticks -= 1
            return action.remaining_ticks == 0
        if resident.stamina <= self._config.needs.min_value:
            action.pending_failure_code = "EXHAUSTED"
            return True
        _, failure = move(
            self._map,
            self._state,
            resident,
            action,
            observations,
            self._config.map.walk_cost_budget_per_tick,
            lambda payload: self._action_fact("resident_moved", action, payload),
        )
        action.pending_failure_code = failure
        return failure is not None or action.route_cursor == len(action.route or [])

    def advance_tick(self) -> WorldTickCommit:
        tick = self._open_tick()
        observations = begin_observation_tick(self._state, tick, self._content)
        active = {action.intent.actor_id: action for action in self._state.active_actions}
        unfinished: list[ActiveAction] = []
        completions: list[ActiveAction] = []
        for resident in self._state.residents:
            action = active.get(resident.id)
            intent = self._submitted.get(resident.id)
            if intent is not None:
                action = self._start(resident, intent)
            if action is None:
                continue
            if self._progress(resident, action, observations):
                completions.append(action)
            else:
                unfinished.append(action)
                self._action_fact(
                    "action_progressed",
                    action,
                    ActionProgressedPayload(
                        action_type=action.intent.action_type,
                        elapsed_ticks=action.elapsed_ticks,
                        remaining_ticks=action.remaining_ticks,
                        route_cursor=action.route_cursor,
                    ),
                )
        self._state.active_actions = unfinished
        for action in completions:
            action_type = action.intent.action_type
            if action.pending_failure_code is None:
                self._action_fact(
                    "action_succeeded",
                    action,
                    ActionSucceededPayload(
                        action_type=action_type,
                        result_code="OK",
                    ),
                )
            else:
                self._action_fact(
                    "action_failed",
                    action,
                    ActionFailedPayload(
                        action_type=action_type,
                        failure_code=action.pending_failure_code,
                    ),
                )

        batch = finish_observation_tick(observations, self._state)
        self._apply_observations(batch)
        self._exploration_facts(batch)
        return self._commit(batch)

    def _apply_observations(self, batch: ObservationBatch) -> None:
        updates = {update.actor_id: update for update in batch.exposure_receipt_updates}
        receipts = self._state.exposure_receipts_by_resident
        for index, group in enumerate(receipts):
            update = updates.get(group.resident_id)
            if update is not None:
                receipts[index] = merge_receipts(group, update.entities, update.cue_detail_seen)
        explored = {group.resident_id: group for group in self._state.explored_tiles_by_resident}
        for tiles in batch.new_static_tiles_by_actor:
            footprint = explored[tiles.actor_id]
            footprint.tile_indices = merge_tile_indices(footprint.tile_indices, tiles.tile_indices)

    def _exploration_facts(self, batch: ObservationBatch) -> None:
        for update in batch.new_static_tiles_by_actor:
            self.append_fact(
                "exploration_updated",
                update.actor_id,
                None,
                None,
                None,
                [],
                ExplorationUpdatedPayload(
                    resident_id=update.actor_id,
                    newly_seen_tile_indices=update.tile_indices,
                ),
            )

    def _commit(self, batch: ObservationBatch) -> WorldTickCommit:
        tick = self._open_tick()
        self._state.tick = tick
        self._state.next_event_seq_in_tick = len(self._events)
        self._state.event_log_cursor += len(self._events)
        deliveries = [
            BoundaryPerceptionDelivery(
                delivery_id=format_delivery_id(self._state.run_id, tick, sample.actor_id),
                actor_id=sample.actor_id,
                observed_tick=tick,
                perception=Perception.model_validate(
                    {
                        **sample.model_dump(),
                        "heard_utterances": [],
                        "last_action_feedback": None,
                    }
                ),
                decision_triggers=["NEW_SIGHT"]
                if sample.actor_id in batch.new_sight_actor_ids
                else [],
            )
            for sample in batch.physical_samples_by_actor
        ]
        commit = WorldTickCommit(
            snapshot=self._state,
            events=self._events,
            pending_deliveries=deliveries,
        ).model_copy(deep=True)
        self._events = []
        self._submitted.clear()
        self._tick = None
        return commit
