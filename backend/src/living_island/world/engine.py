"""P1 world engine and its single event allocator."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import replace
from typing import cast

from living_island.world import actions, dialogue, interrupts, results
from living_island.world.content import WorldContent, canonical_json_bytes
from living_island.world.death import apply_death
from living_island.world.facts import (
    ActionFailedPayload,
    ActionInterruptedPayload,
    ActionProgressedPayload,
    ActionStartedPayload,
    ActionSucceededPayload,
    EventType,
    ExplorationUpdatedPayload,
    StaminaActionCostAppliedPayload,
    TypedEventPayload,
    UtteranceHeardPayload,
    UtteranceSpokenPayload,
    WorldEvent,
    WorldInitializedPayload,
    format_event_id,
)
from living_island.world.movement import move, plan_movement
from living_island.world.physiology import (
    ActivityKind,
    TickActivity,
    apply_metabolism,
    apply_rest_sleep_gain,
    condition_fact,
    is_dead,
    near_cave,
)
from living_island.world.ports import (
    ObservationAccumulator,
    ObservationBatch,
    WorldTickCommit,
    begin_observation_tick,
    finish_observation_tick,
)
from living_island.world.protocol import (
    DECISION_TRIGGERS,
    ActionFeedback,
    ActionIntent,
    ActionResult,
    ActionStatus,
    BoundaryPerceptionDelivery,
    Coord,
    DecisionTrigger,
    EntityTarget,
    FailureCode,
    HeardUtterance,
    InterruptionReason,
    Perception,
    ResidentTarget,
    StateDelta,
    TileTarget,
    format_delivery_id,
)
from living_island.world.receipts import merge_receipts, merge_tile_indices
from living_island.world.resources import record_regrowth, regrow_fruit
from living_island.world.rng import shuffle
from living_island.world.rulefacts import PendingFact
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
    def __init__(
        self,
        content: WorldContent,
        restored_world: WorldState | None,
        history: Sequence[WorldEvent],
    ):
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
        self._requests: dict[str, dialogue.Request] = {}
        self._heard: dict[str, list[HeardUtterance]] = {}
        self._intent_ids = {action.intent.intent_id for action in self._state.active_actions}
        self._outcomes: dict[
            str, tuple[ActiveAction, ActionStatus, FailureCode | None, InterruptionReason | None]
        ] = {}
        self._deltas: dict[str, list[StateDelta]] = {}
        self._results: dict[str, ActionResult] = {}
        if restored_world is not None:
            self._restore_history(history)
        elif history:
            raise ValueError("fresh engine requires empty event history")

    def _restore(self, state: WorldState) -> WorldState:
        if state.next_event_seq_in_tick > state.event_log_cursor:
            raise ValueError("restored boundary event sequence exceeds the event log cursor")
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

    def _restore_history(self, history: Sequence[WorldEvent]) -> None:
        state = self._state
        if not history or len(history) != state.event_log_cursor:
            raise ValueError(
                f"restore history requires a complete prefix of length {state.event_log_cursor}"
            )
        first = history[0]
        if first.tick != 0 or first.type != "world_initialized":
            raise ValueError("restore history must begin with world_initialized at tick zero")
        tick, seq = 0, 0
        for event in history:
            if event.run_id != state.run_id:
                raise ValueError(f"restore history run_id must equal {state.run_id!r}")
            if event.tick > state.tick or event.tick < tick:
                raise ValueError("restore history ticks must be ordered through the checkpoint")
            if event.tick != tick:
                tick, seq = event.tick, 0
            if event.seq_in_tick != seq or event.event_id != format_event_id(
                state.run_id, tick, seq
            ):
                raise ValueError(
                    f"restore history IDs must be contiguous at tick {tick}, seq {seq}"
                )
            self._index_event(event)
            seq += 1
        # A tick with no facts is absent from the event prefix.
        if state.next_event_seq_in_tick != (seq if tick == state.tick else 0):
            raise ValueError("restore history does not match the checkpoint's event sequence")

    def _index_event(self, event: WorldEvent) -> None:
        if event.type == "action_started" and event.intent_id is not None:
            self._intent_ids.add(event.intent_id)
        payload = event.payload
        if isinstance(payload, UtteranceSpokenPayload) and payload.speech_act == "request":
            request = payload.request
            if request is None or event.actor_id is None or payload.utterance_id != event.event_id:
                raise ValueError("request utterance requires a speaker, request and matching ID")
            self._requests[event.event_id] = (
                event.actor_id,
                payload.addressee_id,
                request.item_type,
                request.quantity,
            )
        self._event_ids.add(event.event_id)

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
        self._append_fact(
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
        if intent.intent_id in self._intent_ids:
            raise ValueError(f"intent ID {intent.intent_id!r} has already been submitted")
        self._intent_ids.add(intent.intent_id)
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
        if type not in ("agent_fallback_used", "god_intervention_recorded"):
            raise ValueError(f"{type} cannot be emitted through the external append_fact port")
        return self._append_fact(
            type, actor_id, target_id, intent_id, llm_call_id, caused_by_event_ids, payload
        )

    def _append_fact(
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
        if any(cause not in self._event_ids for cause in caused_by_event_ids):
            raise ValueError("causal references must name known, already emitted events")
        seq = len(self._events)
        event_id = self._next_event_id()
        if isinstance(payload, UtteranceSpokenPayload) and payload.utterance_id != event_id:
            raise ValueError("utterance_id must equal its event ID")
        event = WorldEvent(
            schema_version=self._state.schema_version,
            run_id=self._state.run_id,
            event_id=event_id,
            tick=tick,
            seq_in_tick=seq,
            type=type,
            actor_id=actor_id,
            target_id=target_id,
            intent_id=intent_id,
            llm_call_id=llm_call_id,
            caused_by_event_ids=sorted(
                caused_by_event_ids,
                key=lambda event_id: tuple(int(part) for part in event_id.rsplit(":", 2)[1:]),
            ),
            payload=payload,
        ).model_copy(deep=True)
        self._index_event(event)
        self._events.append(event)
        return event.model_copy(deep=True)

    def _next_event_id(self) -> str:
        return format_event_id(self._state.run_id, self._open_tick(), len(self._events))

    def _action_fact(
        self,
        type: EventType,
        action: ActiveAction,
        payload: TypedEventPayload,
        *,
        causes: list[str] | None = None,
    ) -> WorldEvent:
        intent = action.intent
        target = intent.target
        target_id = target.id if isinstance(target, EntityTarget | ResidentTarget) else None
        return self._append_fact(
            type,
            intent.actor_id,
            target_id,
            intent.intent_id,
            None,
            causes or [],
            payload,
        )

    def _rule_fact(self, fact: PendingFact, intent_id: str | None = None) -> WorldEvent:
        return self._append_fact(
            fact.type,
            fact.actor_id,
            fact.target_id,
            intent_id,
            None,
            [],
            fact.payload,
        )

    def _validate(
        self,
        resident: ResidentPhysicalState,
        intent: ActionIntent,
        *,
        emission_tick: int | None = None,
    ) -> FailureCode | None:
        failure = actions.validate(self._config, self._state, resident, intent)
        if failure is None and intent.action_type == "talk":
            return dialogue.validate_talk(
                self._config,
                self._state,
                resident,
                intent,
                self._requests,
                emission_tick=emission_tick,
            )
        return failure

    def _start(self, resident: ResidentPhysicalState, intent: ActionIntent) -> ActiveAction:
        kind = intent.action_type
        route: list[Coord] | None = None
        failure = self._validate(resident, intent)
        if failure is None and kind == "move_to":
            assert isinstance(intent.target, TileTarget)
            if resident.stamina <= self._config.needs.min_value:
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
        if failure is not None:
            duration = self._config.actions.invalid_attempt_ticks
        elif kind == "move_to":
            duration = None
        else:
            duration = cast(int, getattr(self._config.actions, f"{kind}_ticks"))
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
    ) -> tuple[bool, int]:
        action.elapsed_ticks += 1
        if (
            action.pending_failure_code is None
            and action.intent.action_type in ("move_to", "gather")
            and resident.stamina <= self._config.needs.min_value
        ):
            action.pending_failure_code = "EXHAUSTED"
            return True, 0
        if action.remaining_ticks is not None:
            action.remaining_ticks -= 1
            return action.remaining_ticks == 0, 0
        steps, failure = move(
            self._map,
            self._state,
            resident,
            action,
            observations,
            self._config.map.walk_cost_budget_per_tick,
            lambda payload: self._action_fact("resident_moved", action, payload),
        )
        action.pending_failure_code = failure
        return failure is not None or action.route_cursor == len(action.route or []), steps

    def _progress_actions(
        self,
        observations: ObservationAccumulator,
    ) -> tuple[list[ActiveAction], dict[str, TickActivity]]:
        active = {action.intent.actor_id: action for action in self._state.active_actions}
        unfinished: list[ActiveAction] = []
        completions: list[ActiveAction] = []
        activity: dict[str, TickActivity] = {}
        for index, resident in enumerate(self._state.residents):
            action = active.get(resident.id)
            intent = self._submitted.get(resident.id)
            if intent is not None:
                action = self._start(resident, intent)
            if action is None:
                continue
            activity_kind: ActivityKind = "other"
            kind = action.intent.action_type
            prefix = f"residents/{resident.id}"
            position_before = resident.position
            if action.pending_failure_code is None and kind in ("rest", "sleep"):
                activity_kind = kind
                self._state.residents[index] = apply_rest_sleep_gain(
                    self._config,
                    resident,
                    kind,
                    near_cave(resident.position, self._state.cave),
                )
            done, steps = self._progress(resident, action, observations)
            self._deltas[resident.id] = results.changes(
                {f"{prefix}/position": position_before, f"{prefix}/stamina": resident.stamina},
                {
                    f"{prefix}/position": resident.position,
                    f"{prefix}/stamina": self._state.residents[index].stamina,
                },
            )
            activity[resident.id] = TickActivity(kind=activity_kind, tiles_traversed=steps)
            if done:
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
        return completions, activity

    def _settle_actions(
        self,
        completions: list[ActiveAction],
        activity: dict[str, TickActivity],
    ) -> None:
        completions.sort(key=lambda a: (a.intent.actor_id, a.intent.intent_id))
        self._state.resolution_rng_state_uint32 = shuffle(
            completions,
            self._state.resolution_rng_state_uint32,
        )
        residents = {resident.id: resident for resident in self._state.residents}
        for action in completions:
            intent = action.intent
            actor = residents[intent.actor_id]
            action_type = intent.action_type
            failure = cast(FailureCode | None, action.pending_failure_code)
            if failure is None and action_type != "move_to":
                failure = self._validate(actor, intent, emission_tick=self._open_tick())
            if failure is None:
                before = results.effect_values(self._state, actor, intent)
                if action_type == "talk":
                    self._speak(action, actor, activity)
                fact = actions.settle(self._config, self._state, actor, intent)
                if fact is not None:
                    self._rule_fact(fact, intent.intent_id)
                if action_type == "gather":
                    activity[actor.id] = replace(activity[actor.id], gather_completed=True)
                self._deltas[actor.id].extend(
                    results.changes(before, results.effect_values(self._state, actor, intent))
                )
            self._finish_action(action, failure=failure)

    def _finish_action(
        self,
        action: ActiveAction,
        *,
        failure: FailureCode | None = None,
        interruption: InterruptionReason | None = None,
        causes: list[str] | None = None,
    ) -> None:
        kind = action.intent.action_type
        actor = action.intent.actor_id
        assert actor not in self._outcomes
        status: ActionStatus
        if failure is not None:
            status = "failure"
            self._action_fact(
                "action_failed",
                action,
                ActionFailedPayload(action_type=kind, failure_code=failure),
            )
        elif interruption is not None:
            status = "interrupted"
            self._action_fact(
                "action_interrupted",
                action,
                ActionInterruptedPayload(action_type=kind, reason=interruption),
                causes=causes,
            )
        else:
            status = "success"
            self._action_fact(
                "action_succeeded",
                action,
                ActionSucceededPayload(action_type=kind, result_code="OK"),
            )
        self._outcomes[actor] = (action, status, failure, interruption)

    def _speak(
        self,
        action: ActiveAction,
        speaker: ResidentPhysicalState,
        activity: dict[str, TickActivity],
    ) -> None:
        tick = self._open_tick()
        payload = dialogue.speech_payload(action.intent, self._next_event_id())
        causes = [] if payload.in_reply_to is None else [payload.in_reply_to]
        spoken = self._action_fact("utterance_spoken", action, payload, causes=causes)
        heard = HeardUtterance(
            utterance_id=spoken.event_id,
            speaker_id=speaker.id,
            addressee_id=payload.addressee_id,
            speech_act=payload.speech_act,
            text=payload.text,
            request_item_type=payload.request.item_type if payload.request else None,
            request_quantity=payload.request.quantity if payload.request else None,
            in_reply_to=payload.in_reply_to,
            heard_at_tick=tick,
        )
        for listener in self._state.residents:
            if (
                not listener.alive
                or listener.id == speaker.id
                or activity.get(listener.id, TickActivity()).kind == "sleep"
                or actions.distance(listener.position, speaker.position)
                > self._config.perception.hearing_radius_tiles
            ):
                continue
            self._append_fact(
                "utterance_heard",
                listener.id,
                speaker.id,
                action.intent.intent_id,
                None,
                [spoken.event_id],
                UtteranceHeardPayload(utterance_id=spoken.event_id, listener_id=listener.id),
            )
            self._heard.setdefault(listener.id, []).append(heard)
        dialogue.count_turn(self._config, self._state, speaker.id, payload.addressee_id, tick)

    def _regrow(self, tick: int) -> None:
        regrowth = regrow_fruit(self._config, self._state.fruit_nodes, tick)
        self._state.fruit_nodes = regrowth.nodes
        self._state.lifetime_fruit_regrown = record_regrowth(
            self._state.lifetime_fruit_regrown,
            regrowth.regrown_total,
        )
        for fact in regrowth.facts:
            self._rule_fact(fact)

    def _metabolize(
        self,
        tick: int,
        before: list[ResidentPhysicalState],
        activity: dict[str, TickActivity],
        action_by_actor: dict[str, ActiveAction],
    ) -> None:
        for index, previous in enumerate(before):
            resident = self._state.residents[index]
            if not resident.alive:
                continue
            metabolism = apply_metabolism(
                self._config,
                resident,
                activity.get(resident.id, TickActivity()),
            )
            self._state.residents[index] = metabolism.resident
            for fact in metabolism.cost_facts:
                action = action_by_actor[resident.id]
                self._rule_fact(fact, action.intent.intent_id)
                assert isinstance(fact.payload, StaminaActionCostAppliedPayload)
                after = metabolism.resident.stamina
                self._deltas[resident.id].append(
                    StateDelta(
                        path=f"residents/{resident.id}/stamina",
                        before=after + fact.payload.amount,
                        after=after,
                    )
                )
            condition = condition_fact(previous, metabolism.resident)
            if condition is not None:
                self._rule_fact(condition)
            if is_dead(self._config, metabolism.resident):
                death = apply_death(self._config, self._state, resident.id, tick)
                self._state = death.state
                died, *drops = death.facts
                death_event = self._rule_fact(died)
                for fact in drops:
                    self._rule_fact(fact)
                if death.cancelled_action is not None:
                    self._finish_action(
                        death.cancelled_action,
                        interruption="DEATH",
                        causes=[death_event.event_id],
                    )

    def advance_tick(self) -> WorldTickCommit:
        tick = self._open_tick()
        before = [resident.model_copy(deep=True) for resident in self._state.residents]
        observations = begin_observation_tick(self._state, tick, self._content)
        completions, activity = self._progress_actions(observations)
        action_by_actor = {
            a.intent.actor_id: a for a in [*self._state.active_actions, *completions]
        }
        self._settle_actions(completions, activity)
        self._regrow(tick)
        self._metabolize(tick, before, activity, action_by_actor)
        batch = finish_observation_tick(observations, self._state)
        self._apply_observations(batch)
        self._exploration_facts(batch)
        triggers = self._resolve_boundary(before, set(batch.new_sight_actor_ids))
        self._build_results(tick)
        return self._commit(batch, triggers)

    def _resolve_boundary(
        self,
        before: list[ResidentPhysicalState],
        novel: set[str],
    ) -> dict[str, set[DecisionTrigger]]:
        active = {a.intent.actor_id: a for a in self._state.active_actions}
        triggers_by_actor: dict[str, set[DecisionTrigger]] = {}
        for previous, resident in zip(before, self._state.residents, strict=True):
            if not resident.alive:
                continue
            actor = resident.id
            triggers = interrupts.observations(
                self._config,
                previous,
                resident,
                self._heard.get(actor, []),
                actor in novel,
            )
            action = active.get(actor)
            if action is not None:
                if (
                    action.pending_failure_code is None
                    and action.intent.action_type in ("move_to", "gather")
                    and resident.stamina <= self._config.needs.min_value
                ):
                    self._finish_action(action, failure="EXHAUSTED")
                else:
                    reason = interrupts.soft_interrupt(action, triggers)
                    if reason is not None:
                        self._finish_action(action, interruption=reason)
            outcome = self._outcomes.get(actor)
            if outcome is not None:
                finished, status, _, _ = outcome
                if status == "failure":
                    triggers.add("ACTION_FAILED")
                if status == "interrupted":
                    triggers.add("ACTION_INTERRUPTED")
                if status != "failure" and finished.intent.action_type == "sleep":
                    triggers.add("WOKE")
            triggers_by_actor[actor] = triggers
        self._state.active_actions = [
            action
            for action in self._state.active_actions
            if action.intent.actor_id not in self._outcomes
        ]
        return triggers_by_actor

    def _build_results(self, tick: int) -> None:
        self._results = {}
        for actor, (action, status, failure, reason) in self._outcomes.items():
            intent = action.intent
            events = [event for event in self._events if event.intent_id == intent.intent_id]
            effect_types = {
                "resident_moved",
                "fruit_gathered",
                "fruit_consumed",
                "water_drank",
                "canteen_filled",
                "item_given",
                "item_picked_up",
                "utterance_spoken",
            }
            visible_effects: list[str] = list(
                dict.fromkeys(e.type for e in events if e.type in effect_types)
            )
            if action.pending_failure_code is None and intent.action_type in ("rest", "sleep"):
                if self._deltas[actor]:
                    visible_effects.append("stamina_recovered")
            self._results[actor] = ActionResult(
                intent_id=intent.intent_id,
                actor_id=actor,
                tick_started=action.tick_started,
                tick_finished=tick,
                status=status,
                failure_code=failure,
                interruption_reason=reason,
                state_delta=self._deltas[actor],
                event_ids=[event.event_id for event in events],
                visible_feedback=ActionFeedback(
                    intent_id=intent.intent_id,
                    status=status,
                    failure_code=failure,
                    interruption_reason=reason,
                    visible_effects=visible_effects,
                ),
            )

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
            self._append_fact(
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

    def _commit(
        self,
        batch: ObservationBatch,
        triggers: dict[str, set[DecisionTrigger]] | None = None,
    ) -> WorldTickCommit:
        tick = self._open_tick()
        triggers = triggers or {}
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
                        "heard_utterances": self._heard.get(sample.actor_id, []),
                        "last_action_feedback": (
                            self._results[sample.actor_id].visible_feedback
                            if sample.actor_id in self._results
                            else None
                        ),
                    }
                ),
                decision_triggers=[
                    code for code in DECISION_TRIGGERS if code in triggers.get(sample.actor_id, ())
                ],
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
        self._heard.clear()
        self._outcomes.clear()
        self._deltas.clear()
        self._tick = None
        return commit
