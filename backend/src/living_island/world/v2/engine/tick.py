"""The atomic world boundary and deterministic seven-phase schedule."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from typing import Literal, cast

from pydantic_core import to_jsonable_python

from ..protocol import (
    ActionFeedback,
    ActionResult,
    ActorStop,
    Coord,
    FailureCode,
    HardStop,
    InspectView,
    Utterance,
    UtteranceFeedback,
    WorldEvent,
    WorldReport,
    WorldStop,
)
from ..rules import Pack, Rule, validate_proposal
from ..rules.schema import Table, content_hash
from . import kernel, perception, physiology, processes, settle, speech
from .events import EventWriter, json_object
from .ids import shuffle
from .items import accepts, entities_at, equal_stacks, merge, place_payload, slots_used
from .limits import validate_initial_limits
from .state import (
    Act,
    ActiveAction,
    Awareness,
    BoundTurn,
    Contribute,
    DeferredFeedback,
    Drop,
    Entity,
    FatigueInputs,
    Give,
    Held,
    Inside,
    Inspect,
    Library,
    Lineage,
    Move,
    OnTile,
    Part,
    PickupEntity,
    PickupTile,
    Place,
    Receipts,
    Resident,
    Route,
    TickActivity,
    TimedKernel,
    Wait,
    WorldState,
)
from .validate import EnginePack, WorldSetup, bind_turns, check_acknowledgements


@dataclass(frozen=True)
class TickResult:
    events: tuple[WorldEvent, ...]
    actions: tuple[ActionResult, ...]
    utterances: tuple[UtteranceFeedback, ...]


@dataclass
class SpeechAttempt:
    actor_id: str
    turn_id: str
    utterance: Utterance
    failure: FailureCode | None = None
    intent_id: str | None = None


@dataclass
class TickContext:
    state: WorldState
    pack: EnginePack
    writer: EventWriter
    activity: dict[str, TickActivity] = field(default_factory=dict)
    results: list[ActionResult] = field(default_factory=list)
    completed_actions: dict[str, ActiveAction] = field(default_factory=dict)
    started_actions: dict[str, ActiveAction] = field(default_factory=dict)
    utterances: list[UtteranceFeedback] = field(default_factory=list)

    @property
    def tick(self) -> int:
        return self.writer.tick

    def record_result(
        self,
        action: ActiveAction,
        *,
        failure: FailureCode | None = None,
        world_stop: HardStop | None = None,
        own_choice: bool = False,
        inspected: InspectView | None = None,
    ) -> None:
        intent = action.intent
        outcome: Literal["success", "failure", "settled", "stopped"]
        status: Literal["done", "failed", "stopped"]
        stop = None
        settlement = None
        phenomena = []
        if own_choice or world_stop is not None:
            outcome = "stopped"
            status = "stopped"
            stop_reason = "own_choice" if own_choice else world_stop
            stop = (
                ActorStop(by="actor")
                if world_stop is None
                else WorldStop(by="world", reason=world_stop)
            )
            self.writer.emit(
                "action_stopped",
                {
                    "action": intent.action,
                    "verb": intent.verb,
                    "by": stop.by,
                    "reason": world_stop,
                },
                action=action,
            )
        elif failure is not None:
            outcome = "failure"
            status = "failed"
            stop_reason = None
            self.writer.emit(
                "action_failed",
                {
                    "action": intent.action,
                    "verb": intent.verb,
                    "failure_code": failure,
                },
                action=action,
            )
        elif action.pending_settlement is not None:
            outcome = "settled"
            status = "done"
            stop_reason = None
            settlement = action.pending_settlement.settlement
            phenomena = list(action.pending_settlement.phenomena)
            self.writer.emit(
                "act_settled",
                json_object(
                    {
                        **settlement.model_dump(mode="json"),
                        "verb": intent.verb,
                        "phenomena": phenomena,
                    }
                ),
                action=action,
            )
        else:
            outcome = "success"
            status = "done"
            stop_reason = None
            self.writer.emit("action_succeeded", {"action": intent.action}, action=action)
        feedback = ActionFeedback(
            intent_id=intent.intent_id,
            status=status,
            failure_code=failure,
            stop_reason=stop_reason,
            phenomena=phenomena,
            inspected=inspected,
            start_target=action.start_target,
            items_used=list(action.start_items),
        )
        self.results.append(
            ActionResult(
                intent_id=intent.intent_id,
                actor_id=intent.actor_id,
                tick_started=action.tick_started,
                tick_finished=self.state.tick if own_choice else self.tick,
                outcome=outcome,
                failure_code=failure,
                stop=stop,
                settlement=settlement,
                state_delta=action.state_delta,
                visible_feedback=feedback,
                event_ids=action.event_ids,
            )
        )
        self.completed_actions[intent.intent_id] = action
        self.state.active_actions.pop(intent.actor_id)
        if own_choice:
            deferred = self.state.deferred_feedback[intent.actor_id]
            deferred.feedback.append(feedback)
            deferred.reports.append(
                WorldReport(
                    kind="action_ended",
                    subject_id=intent.intent_id,
                    addressed=None,
                    band=None,
                    threshold_id=None,
                )
            )


@dataclass(frozen=True)
class Completion:
    actor_id: str
    key: str
    action: ActiveAction | None
    utterance: SpeechAttempt | None


@dataclass
class World:
    """A world boundary and its typed, validated engine pack."""

    state: WorldState
    pack: EnginePack
    initial_events: tuple[WorldEvent, ...]

    def step(
        self,
        submissions: Sequence[object] = (),
        *,
        acknowledged: Mapping[str, str] | None = None,
        rule_additions: Sequence[Table] = (),
    ) -> TickResult:
        """Apply one boundary transaction and publish only a completed tick."""
        turns = bind_turns(self.state, self.pack, submissions)
        acknowledgements = {} if acknowledged is None else acknowledged
        check_acknowledgements(self.state, acknowledgements)
        next_pack, added = prepare_rules(self.pack, rule_additions)
        state = deepcopy(self.state)
        state.next_event_seq_in_tick = 0
        writer = EventWriter(state, state.tick + 1)
        ctx = TickContext(state, next_pack, writer)
        boundary_input(ctx, turns, acknowledgements, added)
        completions = action_progress(ctx, turns)
        resolve_completions(ctx, completions)
        processes.world_rules(ctx)
        processes.finish_processes(ctx)
        physiology.apply_physiology(ctx)
        physiology.hard_stops_and_waking(ctx)
        perception.build_deliveries(ctx)
        state.tick = ctx.tick
        state.clock_minute = state.clock.minute_at(state.tick)
        state.entities = dict(sorted(state.entities.items()))
        self.state = state
        self.pack = next_pack
        return TickResult(tuple(writer.events), tuple(ctx.results), tuple(ctx.utterances))


def prepare_rules(pack: EnginePack, additions: Sequence[Table]) -> tuple[EnginePack, list[Rule]]:
    added = []
    source = pack.source
    for raw in additions:
        rule = validate_proposal(source, raw)
        rules = dict(sorted({**source.rules, rule.id: rule}.items()))
        canonical = {key: value.data for key, value in rules.items()}
        source = replace(
            source,
            rules=rules,
            data={**source.data, "rule": canonical},
            rule_library_hash=content_hash(list(canonical.values())),
        )
        added.append(rule)
    return replace(pack, source=source), added


def boundary_input(
    ctx: TickContext,
    turns: dict[str, BoundTurn],
    acknowledged: Mapping[str, str],
    added: list[Rule],
) -> None:
    state = ctx.state
    for actor_id in sorted(acknowledged):
        packet = state.pending_deliveries.pop(actor_id)
        state.fatigue_inputs[actor_id] = FatigueInputs(
            sum(report.kind == "utterance_heard" for report in packet.reports),
            sum(report.kind == "entity_first_seen" for report in packet.reports),
        )
    for rule in added:
        state.library.added_rules[rule.id] = rule
        ctx.writer.emit(
            "rule_added",
            json_object(
                {
                    "rule_id": rule.id,
                    "content_hash": rule.content_hash,
                    "provenance": rule.data["provenance"],
                }
            ),
        )
    if added:
        state.library.rule_library_hash = ctx.pack.source.rule_library_hash
        state.library.active_rule_ids = tuple(ctx.pack.source.rules)
    for actor_id in sorted(turns):
        turn = turns[actor_id]
        state.turn_ordinals[actor_id] += 1
        action = state.active_actions.get(actor_id)
        if turn.action is not None and action is not None:
            if isinstance(action.command, Act):
                settle.interrupt(ctx, action)
            ctx.record_result(action, own_choice=True)


def start_action(ctx: TickContext, actor: Resident, action: ActiveAction) -> None:
    state, pack = ctx.state, ctx.pack
    command = action.command
    failure: FailureCode | None = None
    duration: int | None = None
    act_parts: tuple[tuple[Part, ...], ...] | None = None

    match command:
        case Move():
            movement = kernel.start_movement(state, pack, actor, command)
            if isinstance(movement, Route):
                action.route = movement
            else:
                failure = movement
        case Give() | Drop():
            selection = kernel.check_transfer(state, pack, actor, action, command, at_start=True)
            if isinstance(selection, str):
                failure = selection
            else:
                action.parts = selection
        case PickupEntity() | PickupTile():
            pickup = kernel.check_pickup(state, pack, actor, command)
            if isinstance(pickup, str):
                failure = pickup
            else:
                action.parts = pickup
        case Inspect() | Contribute():
            subject = kernel.check_subject(state, actor, command)
            if isinstance(subject, str):
                failure = subject
        case Act():
            groups = kernel.generic_act(state, pack, actor, action, command)
            if isinstance(groups, str):
                failure = groups
            else:
                act_parts = groups
        case Wait():
            pass

    if failure is not None:
        duration = pack.timing.invalid_attempt_ticks
        action.pending_failure = failure
    elif isinstance(command, (Give, Drop, PickupEntity, PickupTile, Inspect, Wait)):
        duration = pack.timing.durations[cast(TimedKernel, action.intent.action)]
    if duration is not None:
        action.due_tick = state.tick + duration
    if act_parts is not None:
        settle.start_act(ctx, action, act_parts)
        if action.due_tick is not None:
            duration = action.due_tick - state.tick
    elif failure is None:
        kernel.start_look(state, pack, actor, action)
    ctx.writer.emit(
        "action_started",
        {
            "action": action.intent.action,
            "verb": action.intent.verb,
            "turn_id": action.intent.turn_id,
            "duration_ticks": duration,
        },
        action=action,
    )
    if action.resolved_choices is not None:
        settle.record_act_started(ctx, action)


def progress_action(ctx: TickContext, actor: Resident, action: ActiveAction) -> bool:
    state = ctx.state
    command = action.command
    steps = 0
    done = action.due_tick == ctx.tick
    fixed = action.pending_failure is not None or action.pending_settlement is not None
    if not fixed:
        route = action.route
        if route is not None:
            if kernel.exhausted(state, ctx.pack, actor.id):
                action.pending_stop = "EXHAUSTED"
                done = True
            else:
                steps, done = kernel.progress_movement(
                    state,
                    actor,
                    route,
                    action,
                    ctx.writer,
                    lambda point, step: perception.observe_step(ctx, actor.id, point, step),
                )
        elif isinstance(command, Act):
            settle.progress_act(ctx, action)
            done = action.due_tick == ctx.tick or action.pending_stop is not None
        elif isinstance(command, Contribute):
            processes.contribute(ctx, action)
            done = action.pending_stop is not None
        if action.pending_stop is None:
            action.elapsed_ticks += 1
    ctx.activity[actor.id] = TickActivity(action.intent.action, steps)
    if not done:
        ctx.writer.emit(
            "action_progressed",
            {
                "action": action.intent.action,
                "elapsed_ticks": action.elapsed_ticks,
                "remaining_ticks": None if action.due_tick is None else action.due_tick - ctx.tick,
                "route_cursor": None if action.route is None else action.route.cursor,
            },
            action=action,
        )
    return done


def action_progress(ctx: TickContext, turns: dict[str, BoundTurn]) -> list[Completion]:
    state = ctx.state
    completions = []
    for actor_id, actor in sorted(state.residents.items()):
        if not actor.alive:
            continue
        turn = turns.get(actor_id)
        attempt = None
        if turn is not None and turn.utterance is not None:
            attempt = SpeechAttempt(
                actor_id,
                turn.turn_id,
                turn.utterance,
                intent_id=None if turn.action is None else turn.action.intent.intent_id,
            )
            speech.check_start(ctx, attempt)
        start = None if turn is None else turn.action
        if start is not None:
            action_started = ActiveAction(start.intent, start.command, state.tick)
            state.active_actions[actor_id] = action_started
            start_action(ctx, actor, action_started)
            ctx.started_actions[action_started.intent.intent_id] = action_started
        action = state.active_actions.get(actor_id)
        if action is None:
            ctx.activity[actor_id] = TickActivity(None, 0)
        elif progress_action(ctx, actor, action):
            completions.append(
                Completion(
                    actor_id,
                    action.intent.intent_id,
                    action,
                    attempt if start is not None else None,
                )
            )
            if start is not None:
                attempt = None
        if attempt is not None:
            completions.append(Completion(actor_id, f"{attempt.turn_id}:u", None, attempt))
    return completions


def resolve_completions(ctx: TickContext, completions: list[Completion]) -> None:
    state = ctx.state
    completions.sort(key=lambda entry: (entry.actor_id, entry.key))
    state.resolution_rng_state_uint32 = shuffle(completions, state.resolution_rng_state_uint32)
    for entry in completions:
        if entry.utterance is not None:
            speech.settle_utterance(ctx, entry.utterance)
        action = entry.action
        if action is None:
            continue
        if action.pending_failure is not None:
            ctx.record_result(action, failure=action.pending_failure)
        elif action.pending_stop is not None:
            if isinstance(action.command, Act):
                settle.interrupt(ctx, action)
            ctx.record_result(action, world_stop=action.pending_stop)
        elif isinstance(action.command, Act):
            settle.complete_act(ctx, action)
        else:
            result = kernel.complete_kernel(
                state, ctx.pack, state.residents[entry.actor_id], action, ctx.writer
            )
            ctx.record_result(action, failure=result.failure, inspected=result.inspected)


def place_entities(state: WorldState, pack: EnginePack) -> None:
    for order, (key, row) in enumerate(pack.placements.items(), start=1):
        if key in state.residents:
            raise ValueError(f"placement {key!r} collides with a resident ID")
        location = row.location
        place: Place
        if isinstance(location, Coord):
            tile = location
            if not state.static_map.contains(tile) or state.static_map.cost(tile) is None:
                raise ValueError(f"placement {key!r} is not on a passable tile")
            place = OnTile(tile)
        else:
            holder = location
            if holder in state.residents:
                place = Held(holder)
            elif holder in pack.placements:
                place = Inside(holder)
            else:
                raise ValueError(f"placement {key!r} has no such holder")
        owner = row.owner_id
        if owner is not None and owner not in state.residents:
            raise ValueError(f"placement {key!r} has no such owner")
        state.entities[key] = Entity(
            key,
            row.archetype_id,
            row.material_id,
            row.quantity,
            0,
            owner,
            place,
            deepcopy(row.components),
            dict(row.properties),
            dict(row.apparent),
            row.tells,
            pack.archetypes[row.archetype_id].stackable,
            (Lineage(key, 0, row.quantity, order),),
        )
        state.phase_offsets[key] = dict(row.phase_offsets)

    for entity in state.entities.values():
        place = entity.place
        if isinstance(place, (Held, Inside)) and "portable" not in entity.components:
            raise ValueError(f"nonportable placement {entity.entity_id!r} has a holder")
        if isinstance(place, Inside):
            parent = state.entities[place.container_id]
            if "container" not in parent.components or not accepts(pack, parent, entity):
                raise ValueError(f"container rejects placement {entity.entity_id!r}")
        seen = {entity.entity_id}
        while isinstance(place, Inside):
            if place.container_id in seen:
                raise ValueError("placement container cycle")
            seen.add(place.container_id)
            place = state.entities[place.container_id].place

        contents_place = Inside(entity.entity_id)
        declared = pack.placements[entity.entity_id].contents
        if declared and set(declared) != {
            item.entity_id for item in entities_at(state, contents_place)
        }:
            raise ValueError(f"declared contents disagree with placement of {entity.entity_id!r}")
        if (
            "container" in entity.components
            and slots_used(state, contents_place) > (entity.components["container"]["capacity"])
        ):
            raise ValueError(f"container {entity.entity_id!r} starts over capacity")
    for actor_id in state.residents:
        if slots_used(state, Held(actor_id)) > pack.inventory_slots:
            raise ValueError(f"resident {actor_id!r} starts over capacity")


def initialize(pack: Pack, setup: WorldSetup) -> World:
    """Initialize from a validated RR-01 pack and validated world setup."""
    content = EnginePack.from_pack(pack)
    smap = setup.static_map()
    clock = setup.world_clock()
    residents = {
        row.id: Resident(row.id, row.position)
        for row in sorted(setup.residents, key=lambda row: row.id)
    }
    parent = pack.data.get("extends")
    if (
        setup.pack_ids[-1] != pack.pack_id
        or (parent is not None and (len(setup.pack_ids) < 2 or setup.pack_ids[-2] != parent))
        or (parent is None and len(setup.pack_ids) != 1)
    ):
        raise ValueError("pack IDs must enumerate the active composition in base-first order")
    state = WorldState(
        world_id=setup.world_id,
        run_id=setup.run_id,
        seed=setup.seed,
        config_hash=setup.config_hash,
        map_hash=setup.map_hash,
        static_map_ref=setup.static_map_ref,
        static_map=smap,
        clock=clock,
        residents=residents,
        library=Library(
            pack.vocabulary_hash, pack.rule_library_hash, setup.pack_ids, tuple(sorted(pack.rules))
        ),
        resolution_rng_state_uint32=setup.seed,
        clock_minute=clock.minute_at(0),
        cues=setup.world_cues(),
        explored_tiles_by_resident={
            key: {smap.index(actor.position)} for key, actor in residents.items()
        },
        exposure_receipts_by_resident={key: Receipts() for key in residents},
        visible_entities_by_resident={key: set() for key in residents},
        visible_tiles_by_resident={key: set() for key in residents},
        needs={
            key: {name: need.initial for name, need in content.needs.items()} for key in residents
        },
        awareness={key: Awareness("awake") for key in residents},
        fatigue_inputs={key: FatigueInputs() for key in residents},
        deferred_feedback={key: DeferredFeedback() for key in residents},
        turn_ordinals=dict.fromkeys(residents, 0),
    )
    place_entities(state, content)
    writer = EventWriter(state, 0)
    payload = json_object(
        {
            "config_hash": state.config_hash,
            "map_hash": state.map_hash,
            "vocabulary_hash": state.library.vocabulary_hash,
            "rule_library_hash": state.library.rule_library_hash,
            "pack_ids": list(state.library.pack_ids),
            "initial_snapshot_hash": "",
        }
    )
    first = writer.emit("world_initialized", payload)
    for entity in state.entities.values():
        writer.emit(
            "entity_created",
            {
                "entity_id": entity.entity_id,
                "archetype_id": entity.archetype_id,
                "material_id": entity.material_id,
                "quantity": entity.quantity,
                "place": place_payload(entity.place),
                "owner_id": entity.owner_id,
                "rule_id": None,
                "source": None,
                "recreated_from": [],
                "made_from": [],
                "process_id": None,
            },
            target_id=entity.entity_id,
        )
    for entity in list(state.entities.values()):
        survivor = next(
            (
                other
                for other in entities_at(state, entity.place)
                if other.entity_id < entity.entity_id and equal_stacks(entity, other)
            ),
            None,
        )
        if survivor is not None:
            merge(state, entity, survivor, writer)
            del state.phase_offsets[entity.entity_id]
    validate_initial_limits(state, content.limits)
    perception.build_deliveries(TickContext(state, content, writer))
    # EN-07 owns the persistent snapshot format. This hash commits the initial core state.
    payload["initial_snapshot_hash"] = content_hash(to_jsonable_python(asdict(state)))
    writer.events[0] = first.model_copy(update={"payload": payload})
    return World(state, content, tuple(writer.events))
