"""Authoritative state and typed inputs shared by the engine phases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypedDict

from ..protocol import (
    Action,
    ActionFeedback,
    BoundaryDelivery,
    Coord,
    FailureCode,
    HardStop,
    Intent,
    ItemChoice,
    ItemUse,
    Settlement,
    StartTarget,
    StateDelta,
    Terms,
    Terrain,
    Utterance,
    WorldReport,
)
from ..rules import Rule
from ..rules.schema import Table
from .ids import EntityCounter

type PropertyValues = dict[str, int | bool]
type AwarenessKind = Literal["awake", "asleep", "unconscious"]
type TimedKernel = Literal["give", "pick_up", "drop", "wait", "inspect"]


@dataclass(frozen=True)
class OnTile:
    position: Coord


@dataclass(frozen=True)
class Held:
    holder_id: str


@dataclass(frozen=True)
class Inside:
    container_id: str


@dataclass(frozen=True)
class InStore:
    entity_id: str


type Place = OnTile | Held | Inside | InStore


class Portable(TypedDict):
    slots_per_unit: int


class Store(TypedDict):
    archetype: str
    count: int
    capacity: int


class Container(TypedDict):
    capacity: int
    accepts: Table


class Durability(TypedDict):
    wear: int
    max_wear: int


class Fuel(TypedDict):
    ticks_left: int


class Footprint(TypedDict):
    blocks_movement: bool
    opaque: bool


class Process(TypedDict):
    work_done: int
    work_required: int


class Components(TypedDict):
    portable: NotRequired[Portable]
    store: NotRequired[Store]
    container: NotRequired[Container]
    durability: NotRequired[Durability]
    fuel: NotRequired[Fuel]
    shelter: NotRequired[dict[str, bool]]
    footprint: NotRequired[Footprint]
    process: NotRequired[Process]


@dataclass
class Entity:
    entity_id: str
    archetype_id: str | None
    material_id: str | None
    quantity: int
    created_tick: int
    owner_id: str | None
    place: Place
    components: Components
    properties: PropertyValues
    apparent: PropertyValues
    tells: tuple[str, ...]
    stackable: bool
    # Each entry preserves the origin of a contiguous quantity, oldest first.
    lineage: tuple[Lineage, ...]
    corpse_resident_id: str | None = None
    death_tick: int | None = None


@dataclass(frozen=True)
class Lineage:
    origin_id: str
    created_tick: int
    quantity: int
    event_order: int


@dataclass
class Resident:
    id: str
    position: Coord
    alive: bool = True


@dataclass(frozen=True)
class Awareness:
    kind: AwarenessKind
    unconscious_until: int | None = None


@dataclass(frozen=True)
class FatigueInputs:
    utterances_heard: int = 0
    first_sightings: int = 0


@dataclass
class DialogueSession:
    pair_ids: tuple[str, str]
    turn_count: int
    last_utterance_tick: int
    cooldown_until_tick: int


@dataclass
class Proposal:
    utterance_id: str
    speaker_id: str
    addressee_id: str
    terms: Terms
    dialogue_session: tuple[str, str]
    answer: Literal["accept", "refuse"] | None = None


@dataclass(frozen=True)
class Agreement:
    agreement_id: str
    proposal_id: str
    acceptance_id: str
    terms: Terms
    tick: int


@dataclass(frozen=True)
class Exposure:
    entity_id: str
    position: Coord
    archetype_id: str | None = None


@dataclass
class Receipts:
    entities: dict[str, Exposure] = field(default_factory=dict)
    item_tiles: set[tuple[str, Coord]] = field(default_factory=set)
    cue_detail_seen: dict[str, Literal["distant", "near"]] = field(default_factory=dict)


@dataclass
class DeferredFeedback:
    feedback: list[ActionFeedback] = field(default_factory=list)
    reports: list[WorldReport] = field(default_factory=list)


@dataclass
class Library:
    vocabulary_hash: str
    rule_library_hash: str
    pack_ids: tuple[str, ...]
    active_rule_ids: tuple[str, ...]
    added_rules: dict[str, Rule] = field(default_factory=dict)


@dataclass(frozen=True)
class Part:
    entity_id: str
    quantity: int


@dataclass(frozen=True)
class Binding:
    original_id: str
    physical_id: str
    quantity: int


@dataclass(frozen=True)
class Move:
    target: Coord


@dataclass(frozen=True)
class Give:
    recipient_id: str
    item: ItemChoice
    quantity: int


@dataclass(frozen=True)
class PickupEntity:
    entity_id: str
    quantity: int


@dataclass(frozen=True)
class PickupTile:
    tile: Coord
    archetype_id: str
    quantity: int


@dataclass(frozen=True)
class Drop:
    destination: OnTile | Inside
    item: ItemChoice
    quantity: int


@dataclass(frozen=True)
class Inspect:
    entity_id: str


@dataclass(frozen=True)
class Contribute:
    process_id: str


@dataclass(frozen=True)
class Wait:
    """A timed kernel wait."""


@dataclass(frozen=True)
class Act:
    verb: str
    params: dict[str, int]


type Command = Move | Give | PickupEntity | PickupTile | Drop | Inspect | Contribute | Wait | Act


@dataclass
class Route:
    steps: tuple[Coord, ...]
    cursor: int = 0


@dataclass(frozen=True)
class PhaseItem:
    look: ItemUse
    place: Place


@dataclass(frozen=True)
class PhaseLocation:
    actor: Coord
    target: Coord | None
    items: tuple[PhaseItem, ...]
    target_view: StartTarget | None = None


@dataclass(frozen=True)
class PendingSettlement:
    settlement: Settlement
    phenomena: tuple[str, ...]


@dataclass
class ActiveAction:
    intent: Intent
    command: Command
    tick_started: int
    elapsed_ticks: int = 0
    due_tick: int | None = None
    route: Route | None = None
    rule_id: str | None = None
    resolved_choices: tuple[tuple[Part, ...], ...] | None = None
    bindings: tuple[Binding, ...] = ()
    start_items: tuple[ItemUse, ...] = ()
    start_target: StartTarget | None = None
    start_location: PhaseLocation | None = None
    stop_location: PhaseLocation | None = None
    settle_location: PhaseLocation | None = None
    received_items: tuple[ItemUse, ...] = ()
    pending_failure: FailureCode | None = None
    pending_stop: HardStop | None = None
    pending_settlement: PendingSettlement | None = None
    parts: tuple[Part, ...] = ()
    state_delta: list[StateDelta] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Clock:
    tick_minutes: int
    start_minute: int
    day_start_minute: int
    day_end_minute: int

    def minute_at(self, tick: int) -> int:
        return (self.start_minute + tick * self.tick_minutes) % 1440


@dataclass(frozen=True)
class StaticMap:
    rows: tuple[tuple[Terrain, ...], ...]
    step_costs: dict[Terrain, int]
    walk_budget: int
    opaque_terrains: frozenset[Terrain]

    @property
    def width(self) -> int:
        return len(self.rows[0])

    def contains(self, point: Coord) -> bool:
        return 0 <= point.x < self.width and 0 <= point.y < len(self.rows)

    def index(self, point: Coord) -> int:
        return point.y * self.width + point.x

    def terrain(self, point: Coord) -> Terrain:
        return self.rows[point.y][point.x]

    def cost(self, point: Coord) -> int | None:
        return self.step_costs.get(self.terrain(point))


@dataclass(frozen=True)
class Cue:
    id: str
    kind: str
    position: Coord
    visible_description: str
    near_description: str
    direction: str | None


@dataclass(frozen=True)
class Senses:
    day_radius: int
    night_radius: int
    hearing_radius: int
    cue_detail_radius: int
    visible_weakness_below: int
    visible_dehydration_below: int
    visible_fatigue_below: int


@dataclass(frozen=True)
class DialogueLimits:
    max_turns: int
    gap_ticks: int
    cooldown_ticks: int


@dataclass(frozen=True)
class KernelTiming:
    invalid_attempt_ticks: int
    durations: dict[TimedKernel, int]
    attempts: dict[str, int]


@dataclass(frozen=True)
class Limits:
    max_entity_units_world: int
    max_entities_per_tile: int


@dataclass(frozen=True)
class NeedSpec:
    minimum: int
    maximum: int
    initial: int
    band_cutoffs: tuple[int, ...]
    max_gain_per_tick: int
    max_loss_per_tick: int
    thresholds: tuple[NeedThreshold, ...]


@dataclass(frozen=True)
class NeedThreshold:
    id: str
    at: int
    wakes: bool


@dataclass
class WorldState:
    world_id: str
    run_id: str
    seed: int
    config_hash: str
    map_hash: str
    static_map_ref: str
    static_map: StaticMap
    clock: Clock
    senses: Senses
    dialogue_limits: DialogueLimits
    residents: dict[str, Resident]
    library: Library
    resolution_rng_state_uint32: int
    schema_version: Literal["wap/0.1"] = "wap/0.1"
    tick: int = 0
    clock_minute: int = 0
    cues: tuple[Cue, ...] = ()
    explored_tiles_by_resident: dict[str, set[int]] = field(default_factory=dict)
    exposure_receipts_by_resident: dict[str, Receipts] = field(default_factory=dict)
    visible_entities_by_resident: dict[str, set[str]] = field(default_factory=dict)
    visible_tiles_by_resident: dict[str, set[int]] = field(default_factory=dict)
    dialogue_sessions: dict[tuple[str, str], DialogueSession] = field(default_factory=dict)
    next_event_seq_in_tick: int = 0
    event_log_cursor: int = 0
    entities: dict[str, Entity] = field(default_factory=dict)
    entity_counter: EntityCounter = field(default_factory=EntityCounter)
    needs: dict[str, dict[str, int]] = field(default_factory=dict)
    awareness: dict[str, Awareness] = field(default_factory=dict)
    active_actions: dict[str, ActiveAction] = field(default_factory=dict)
    phase_offsets: dict[str, dict[str, int]] = field(default_factory=dict)
    fatigue_inputs: dict[str, FatigueInputs] = field(default_factory=dict)
    pending_deliveries: dict[str, BoundaryDelivery] = field(default_factory=dict)
    deferred_feedback: dict[str, DeferredFeedback] = field(default_factory=dict)
    proposals: dict[str, Proposal] = field(default_factory=dict)
    agreements: dict[str, Agreement] = field(default_factory=dict)
    turn_ordinals: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class BoundIntent:
    intent: Intent
    command: Command


@dataclass(frozen=True)
class BoundTurn:
    actor_id: str
    turn_id: str
    action: BoundIntent | None
    utterance: Utterance | None


@dataclass(frozen=True)
class TickActivity:
    action: Action | None
    tiles_traversed: int
