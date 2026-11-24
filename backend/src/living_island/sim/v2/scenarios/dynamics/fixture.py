"""Stage declared synthetic openings with the bound starter pack and no rule overrides."""

from copy import deepcopy
from dataclasses import replace
from functools import cache, partial

from pydantic import JsonValue

from living_island.sim.v2.cli import ROOT, VOCABULARY
from living_island.sim.v2.scenarios.runtime import Scenario, scripted
from living_island.sim.v2.scenarios.starter import StarterScenario, load_starter_pack
from living_island.sim.v2.turns import TurnRequest
from living_island.world.v2 import protocol as p
from living_island.world.v2.engine import World, initialize
from living_island.world.v2.engine.events import EventWriter
from living_island.world.v2.engine.items import place_payload
from living_island.world.v2.engine.perception import build_deliveries
from living_island.world.v2.engine.state import (
    Awareness,
    Components,
    DeferredFeedback,
    Entity,
    FatigueInputs,
    Held,
    Lineage,
    Place,
    Receipts,
    Resident,
)
from living_island.world.v2.engine.tick import TickContext
from living_island.world.v2.rules import load_vocabulary
from living_island.world.v2.rules.schema import content_hash

from ..receipts import State
from ..runtime import Observer

ACTOR = "ada"
WATCHER = "bea"
SEED = 2600456787
HOME = p.Coord(x=4, y=3)
NEXT = p.Coord(x=5, y=3)
ACTOR_INVENTORY = Held(ACTOR)
ROWS: tuple[tuple[p.Terrain, ...], ...] = tuple(
    tuple("spring" if y == 2 and x in (4, 6) else "grass" for x in range(9)) for y in range(7)
)
type Schedule = dict[tuple[str, int], p.ModelTurn]


@cache
def starter(seed: int) -> StarterScenario:
    return load_starter_pack(
        ROOT / "content/worlds/default.toml",
        ROOT / "content/packs/starter-v1",
        load_vocabulary(VOCABULARY),
        seed=seed,
    )


class Opening:
    def __init__(self, name: str, seed: int, *, tick: int = 0, watcher: bool = False) -> None:
        self.source = starter(seed)
        base = initialize(self.source.pack, self.source.setup)
        actors = {ACTOR: Resident(ACTOR, HOME)}
        if watcher:
            actors[WATCHER] = Resident(WATCHER, NEXT)
        map_hash = content_hash(ROWS)
        self.state = replace(
            base.state,
            world_id="m13-dynamics",
            run_id=f"m13-dynamics-{name}-{seed}",
            tick=tick,
            clock_minute=base.state.clock.minute_at(tick),
            static_map=replace(base.state.static_map, rows=ROWS),
            static_map_ref="ct08:9x7-spring",
            map_hash=map_hash,
            senses=replace(base.state.senses, day_radius=2, night_radius=2),
            residents=actors,
            cues=(),
            entities={},
            phase_offsets={},
            needs={
                actor: {key: need.initial for key, need in base.pack.needs.items()}
                for actor in actors
            },
            awareness={actor: Awareness("awake") for actor in actors},
            pending_deliveries={},
            fatigue_inputs={actor: FatigueInputs() for actor in actors},
            deferred_feedback={actor: DeferredFeedback() for actor in actors},
            explored_tiles_by_resident={actor: set() for actor in actors},
            exposure_receipts_by_resident={actor: Receipts() for actor in actors},
            visible_entities_by_resident={actor: set() for actor in actors},
            visible_tiles_by_resident={actor: set() for actor in actors},
            turn_ordinals=dict.fromkeys(actors, 0),
            next_event_seq_in_tick=0,
            event_log_cursor=0,
        )
        self.pack = base.pack

    def item(
        self,
        key: str,
        archetype: str,
        place: Place = ACTOR_INVENTORY,
        *,
        quantity: int = 1,
        material: str | None = None,
        components: Components | None = None,
        created: int = 0,
    ) -> None:
        pack = self.pack.source
        raw = pack.data["archetype"][archetype]
        spec = self.pack.archetypes[archetype]
        parts: Components = deepcopy(raw["components"])
        if components is not None:
            parts.update(components)
        self.state.entities[key] = Entity(
            key,
            archetype,
            raw.get("material") if material is None else material,
            quantity,
            created,
            None,
            place,
            parts,
            dict(spec.properties),
            {},
            (),
            spec.stackable,
            (Lineage(key, created, quantity, len(self.state.entities) + 1),),
        )

    def world(self) -> World:
        # Build the first genuine packets from the staged inputs. All subsequent changes
        # to the fixture go through the public turn boundary.
        state = self.state
        writer = EventWriter(state, state.tick)
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
        # Initial perceptions have no prior interval. Anchor their identities
        # at the declared opening tick when a fixture starts mid-cycle.
        build_deliveries(TickContext(state, self.pack, EventWriter(state, 0)))
        if state.tick:
            state.pending_deliveries = {
                actor: packet.model_copy(
                    update={
                        "observed_tick": state.tick,
                        "delivery_id": p.boundary_delivery_id(state.run_id, state.tick, actor),
                        "perception": packet.perception.model_copy(update={"tick": state.tick}),
                    }
                )
                for actor, packet in state.pending_deliveries.items()
            }
        return World(state, self.pack, tuple(writer.events))

    def scenario(self, schedule: Schedule, observe: Observer) -> Scenario:
        world = self.world()
        return Scenario(
            world,
            self.source.manifest.config_blob_sha256,
            world.state.map_hash,
            scripted(partial(Program, schedule)),
            observe,
        )


class Program:
    """All script position comes from the observed tick and the running action."""

    def __init__(self, schedule: Schedule, _restored: State | None) -> None:
        self.schedule = schedule

    def deliver(self, packet: p.BoundaryDelivery) -> bool:
        return (packet.actor_id, packet.observed_tick) in self.schedule

    def choose(self, request: TurnRequest) -> p.ModelTurn:
        packet = request.delivery
        scheduled = self.schedule.get((packet.actor_id, packet.observed_tick))
        if scheduled is not None:
            return scheduled
        return CONTINUE if packet.perception.running_action is not None else WAIT

    def checkpoint(self) -> State:
        return {}


def target(key: str) -> p.EntityTarget:
    return p.EntityTarget(kind="entity", id=key)


def named(key: str) -> p.NamedItem:
    return p.NamedItem(kind="item", id=key)


def turn(
    action: p.Action,
    *,
    verb: str | None = None,
    at: p.Target | None = None,
    instruments: tuple[str, ...] = (),
    inputs: tuple[p.ActionInput, ...] = (),
    params: dict[str, JsonValue] | None = None,
    utterance: p.Utterance | None = None,
) -> p.ModelTurn:
    shape = p.IntentShape(
        action=action,
        verb=verb,
        target=at,
        instruments=[named(key) for key in instruments],
        inputs=list(inputs),
        params={} if params is None else params,
        reason=None,
    )
    return p.ModelTurn(action=p.ModelIntentAction(kind="intent", intent=shape), utterance=utterance)


def sleep(duration: int) -> p.ModelTurn:
    return turn("act", verb="sleep", params={"duration_ticks": duration})


def drop(key: str, at: p.Target, quantity: int = 1) -> p.ModelTurn:
    return turn("drop", at=at, params={"item": {"kind": "item", "id": key}, "quantity": quantity})


def ground(point: p.Coord) -> p.TileTarget:
    return p.TileTarget(kind="tile", position=point)


def pickup(key: str) -> p.ModelTurn:
    return turn("pick_up", at=target(key), params={"quantity": 1})


WAIT = turn("wait")
DRINK = turn("act", verb="drink")
CONTINUE = p.ModelTurn(action=p.ContinueAction(kind="continue"), utterance=None)


def spring_schedule(opening: Opening, horizon: int) -> Schedule:
    water = opening.pack.physiology.hydration
    assert water is not None  # The admitted starter pack enables hydration.
    threshold = opening.pack.needs["hydration"].thresholds[0].at
    drink_gain = opening.pack.source.rules["compat_drink_spring"].data["effects"][0]["delta"]
    span = (
        min(opening.pack.needs["hydration"].initial - threshold, drink_gain) // water.awake_decay
    ) - 1
    return {(ACTOR, tick): DRINK for tick in range(span, horizon, span)}
