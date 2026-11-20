"""Convert world inputs and bound turns at the engine boundary."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Annotated, Literal, cast

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from ..protocol import (
    Coord,
    EnabledVerb,
    EntityTarget,
    Intent,
    InvalidTurn,
    ItemChoice,
    ProtocolModel,
    ResidentTarget,
    Terrain,
    TileTarget,
    TurnSubmission,
    VerbParameter,
    validate_turn_shape,
)
from ..rules import Pack
from ..rules.schema import Table
from .ids import MASK
from .state import (
    Act,
    BoundIntent,
    BoundTurn,
    Clock,
    Command,
    Components,
    Contribute,
    Cue,
    DialogueLimits,
    Drop,
    Give,
    Inside,
    Inspect,
    KernelTiming,
    Limits,
    Move,
    NeedSpec,
    NeedThreshold,
    OnTile,
    PickupEntity,
    PickupTile,
    PropertyValues,
    Senses,
    StaticMap,
    TimedKernel,
    Wait,
    WorldState,
)


class MapConfig(ProtocolModel):
    rows: tuple[tuple[Terrain, ...], ...]
    step_costs: dict[Terrain, PositiveInt]
    walk_budget: PositiveInt
    opaque_terrains: frozenset[Terrain]

    @model_validator(mode="after")
    def validate_map(self) -> "MapConfig":
        if (
            not self.rows
            or not self.rows[0]
            or any(len(row) != len(self.rows[0]) for row in self.rows)
        ):
            raise ValueError("terrain rows must form a nonempty rectangle")
        if {"sea", "rock", "spring"} & self.step_costs.keys():
            raise ValueError("impassable terrain cannot have a movement cost")
        if "grass" not in self.step_costs or max(self.step_costs.values()) > self.walk_budget:
            raise ValueError("movement budget must cover all step costs, including grass")
        return self


type Minute = Annotated[int, Field(ge=0, lt=1440)]


class ClockConfig(ProtocolModel):
    tick_minutes: PositiveInt
    start_minute: Minute
    day_start_minute: Minute
    day_end_minute: Annotated[int, Field(gt=0, le=1440)]

    @model_validator(mode="after")
    def validate_clock(self) -> "ClockConfig":
        if 1440 % self.tick_minutes or self.day_start_minute >= self.day_end_minute:
            raise ValueError("tick length must divide a day; daylight must have increasing bounds")
        return self


class ResidentSetup(ProtocolModel):
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")]
    position: Coord


class CueSetup(ProtocolModel):
    id: str
    kind: str
    position: Coord
    visible_description: str
    near_description: str
    direction: str | None = None


class SensesConfig(ProtocolModel):
    day_radius: NonNegativeInt
    night_radius: NonNegativeInt
    hearing_radius: NonNegativeInt
    cue_detail_radius: NonNegativeInt
    visible_weakness_below: NonNegativeInt
    visible_dehydration_below: NonNegativeInt
    visible_fatigue_below: NonNegativeInt


class DialogueConfig(ProtocolModel):
    max_turns: NonNegativeInt
    gap_ticks: NonNegativeInt
    cooldown_ticks: NonNegativeInt


class WorldSetup(ProtocolModel):
    world_id: Annotated[str, Field(min_length=1)]
    run_id: Annotated[str, Field(min_length=1)]
    seed: Annotated[int, Field(ge=1, le=MASK)]
    config_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    map_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    static_map_ref: Annotated[str, Field(min_length=1)]
    pack_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    terrain: MapConfig
    clock: ClockConfig
    senses: SensesConfig
    dialogue: DialogueConfig
    residents: tuple[ResidentSetup, ...]
    cues: tuple[CueSetup, ...] = ()

    @model_validator(mode="after")
    def validate_placements(self) -> "WorldSetup":
        smap = self.static_map()
        if len(set(self.pack_ids)) != len(self.pack_ids):
            raise ValueError("duplicate pack ID")
        if len({resident.id for resident in self.residents}) != len(self.residents):
            raise ValueError("duplicate resident ID")
        for resident in self.residents:
            if not smap.contains(resident.position) or smap.cost(resident.position) is None:
                raise ValueError(f"resident {resident.id!r} must start on a passable tile")
        if len({cue.id for cue in self.cues}) != len(self.cues) or any(
            not smap.contains(cue.position) for cue in self.cues
        ):
            raise ValueError("cues must have unique IDs and in-map positions")
        return self

    def static_map(self) -> StaticMap:
        return StaticMap(
            self.terrain.rows,
            dict(self.terrain.step_costs),
            self.terrain.walk_budget,
            self.terrain.opaque_terrains,
        )

    def world_clock(self) -> Clock:
        return Clock(
            self.clock.tick_minutes,
            self.clock.start_minute,
            self.clock.day_start_minute,
            self.clock.day_end_minute,
        )

    def world_cues(self) -> tuple[Cue, ...]:
        return tuple(
            Cue(
                cue.id,
                cue.kind,
                cue.position,
                cue.visible_description,
                cue.near_description,
                cue.direction,
            )
            for cue in self.cues
        )

    def world_senses(self) -> Senses:
        senses = self.senses
        return Senses(
            senses.day_radius,
            senses.night_radius,
            senses.hearing_radius,
            senses.cue_detail_radius,
            senses.visible_weakness_below,
            senses.visible_dehydration_below,
            senses.visible_fatigue_below,
        )

    def dialogue_limits(self) -> DialogueLimits:
        return DialogueLimits(
            self.dialogue.max_turns, self.dialogue.gap_ticks, self.dialogue.cooldown_ticks
        )


TIMED_ACTIONS: tuple[TimedKernel, ...] = ("give", "pick_up", "drop", "wait", "inspect")


@dataclass(frozen=True)
class VerbSpec:
    shape: EnabledVerb
    target_class: str | None
    must_be_held: bool
    min_reach: int
    max_reach: int


@dataclass(frozen=True)
class ArchetypeSpec:
    kind: Literal["item", "structure", "process", "feature"]
    stackable: bool
    properties: PropertyValues
    observations: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MaterialSpec:
    properties: PropertyValues
    apparent: PropertyValues


@dataclass(frozen=True)
class Placement:
    archetype_id: str
    material_id: str | None
    location: Coord | str
    quantity: int
    owner_id: str | None
    components: Components
    properties: PropertyValues
    apparent: PropertyValues
    tells: tuple[str, ...]
    phase_offsets: dict[str, int]
    contents: tuple[str, ...]

    @classmethod
    def from_row(cls, row: Table) -> "Placement":
        at = row["at"]
        location: Coord | str
        if "tile" in at:
            x, y = at["tile"]
            location = Coord.model_construct(x=x, y=y)
        else:
            location = at["holder"]
        return cls(
            row["archetype"],
            row.get("material"),
            location,
            row["quantity"],
            row.get("owner_id"),
            cast(Components, deepcopy(row["state"])),
            dict(row["properties"]),
            dict(row["apparent"]),
            tuple(row["tell"]),
            dict(row["phase_offset"]),
            tuple(row["contents"]),
        )


@dataclass(frozen=True)
class EnginePack:
    """Typed engine projection of one RR-01 validated composed pack."""

    source: Pack
    timing: KernelTiming
    limits: Limits
    inventory_slots: int
    needs: dict[str, NeedSpec]
    verbs: dict[str, VerbSpec]
    archetypes: dict[str, ArchetypeSpec]
    materials: dict[str, MaterialSpec]
    placements: dict[str, Placement]
    defaults: PropertyValues
    sight_while_asleep: bool

    @classmethod
    def from_pack(cls, pack: Pack) -> "EnginePack":
        data = pack.data
        timing: Table = data["timing"]
        limits: Table = data["limits"]
        try:
            kernel_timing = KernelTiming(
                timing["invalid_attempt_ticks"],
                {kind: timing[f"{kind}_ticks"] for kind in TIMED_ACTIONS},
                timing["attempt_ticks"] if data["enabled_verbs"] else {},
            )
            bounds = Limits(limits["max_entity_units_world"], limits["max_entities_per_tile"])
            inventory: int = data["inventory_slots"]
        except KeyError as exc:
            raise ValueError(f"pack {pack.pack_id!r} lacks engine setting {exc.args[0]}") from exc
        needs = {
            name: NeedSpec(
                row["min"],
                row["max"],
                row["initial"],
                tuple(row["band_cutoffs"]),
                row["max_gain_per_tick"],
                row["max_loss_per_tick"],
                tuple(
                    NeedThreshold(value["id"], value["at"], value["wakes"])
                    for value in row["thresholds"]
                ),
            )
            for name, row in data["needs"].items()
        }
        verbs = {}
        for name in data["enabled_verbs"]:
            verb = pack.vocabulary.verbs[name]
            target = verb["target"]
            shape = EnabledVerb(
                id=name,
                target_kinds=tuple(target["kinds"]),
                params=tuple(
                    VerbParameter(name=p["name"], min=p["min"], max=p["max"])
                    for p in verb["params"]
                ),
            )
            verbs[name] = VerbSpec(
                shape,
                target.get("class"),
                target.get("must_be_held", False),
                verb["reach"]["min"],
                verb["reach"]["max"],
            )
        archetypes = {
            key: ArchetypeSpec(
                row["kind"],
                row["stackable"],
                dict(row["properties"]),
                tuple((obs["as"], obs["field"]) for obs in row["observe"]),
            )
            for key, row in data["archetype"].items()
        }
        materials = {
            key: MaterialSpec(dict(row["properties"]), dict(row["apparent"]))
            for key, row in data["material"].items()
        }
        placements = {key: Placement.from_row(row) for key, row in sorted(data["instance"].items())}
        defaults = {
            key: row["default"]
            for key, row in pack.vocabulary.properties.items()
            if "default" in row
        }
        return cls(
            pack,
            kernel_timing,
            bounds,
            inventory,
            needs,
            verbs,
            archetypes,
            materials,
            placements,
            defaults,
            data["sight_while_asleep"],
        )


def command_for(intent: Intent) -> Command:
    """Project the validated action/target/params combination without rechecking its shape."""
    target = intent.target
    params = intent.params
    match intent.action:
        case "move_to":
            return Move(cast(TileTarget, target).position)
        case "give":
            return Give(
                cast(ResidentTarget, target).id,
                item_choice(params["item"]),
                cast(int, params["quantity"]),
            )
        case "pick_up":
            quantity = cast(int, params["quantity"])
            if isinstance(target, TileTarget):
                return PickupTile(target.position, cast(str, params["archetype_id"]), quantity)
            return PickupEntity(cast(EntityTarget, target).id, quantity)
        case "drop":
            destination = (
                OnTile(target.position)
                if isinstance(target, TileTarget)
                else Inside(cast(EntityTarget, target).id)
            )
            return Drop(destination, item_choice(params["item"]), cast(int, params["quantity"]))
        case "inspect":
            return Inspect(cast(EntityTarget, target).id)
        case "contribute":
            return Contribute(cast(EntityTarget, target).id)
        case "wait":
            return Wait()
        case "act":
            return Act(cast(str, intent.verb), cast(dict[str, int], params))


def item_choice(value: object) -> ItemChoice:
    # The WAP shape validator has already validated TransferParams.item.
    from ..protocol import HeldItem, NamedItem

    row = cast(dict[str, str], value)
    if row["kind"] == "held":
        return HeldItem.model_construct(kind="held", archetype_id=row["archetype_id"])
    return NamedItem.model_construct(kind="item", id=row["id"])


def bind_turns(
    state: WorldState, pack: EnginePack, submissions: Sequence[object]
) -> dict[str, BoundTurn]:
    verbs = tuple(verb.shape for verb in pack.verbs.values())
    bound: dict[str, BoundTurn] = {}
    for raw in submissions:
        actor_hint: object
        if isinstance(raw, TurnSubmission):
            actor_hint = raw.actor_id
        else:
            actor_hint = raw.get("actor_id") if isinstance(raw, Mapping) else None
        turn = validate_turn_shape(
            TurnSubmission,
            raw,
            enabled_verbs=verbs,
            has_running_action=isinstance(actor_hint, str) and actor_hint in state.active_actions,
        )
        actor_id = turn.actor_id
        actor = state.residents.get(actor_id)
        if actor is None or not actor.alive or state.awareness[actor_id].kind != "awake":
            raise InvalidTurn("actor is not eligible for a turn")
        ordinal = state.turn_ordinals[actor_id]
        turn_id = f"{actor_id}:t{ordinal:06d}"
        if turn.observed_tick != state.tick or turn.turn_id != turn_id or actor_id in bound:
            raise InvalidTurn("turn is stale, duplicated or does not match the expected ordinal")
        start = None
        if turn.action.kind == "intent":
            intent = turn.action.intent
            if (intent.actor_id, intent.turn_id, intent.intent_id) != (
                actor_id,
                turn_id,
                f"{turn_id}:a",
            ):
                raise InvalidTurn("nested intent identity does not match the turn")
            start = BoundIntent(intent, command_for(intent))
        bound[actor_id] = BoundTurn(actor_id, turn_id, start, turn.utterance)
    return bound


def check_acknowledgements(state: WorldState, acknowledged: Mapping[str, str]) -> None:
    if state.pending_deliveries.keys() - acknowledged.keys():
        raise InvalidTurn("pending deliveries must be acknowledged before advancing")
    for actor_id, delivery_id in acknowledged.items():
        packet = state.pending_deliveries.get(actor_id)
        if (
            packet is None
            or packet.delivery_id != delivery_id
            or packet.observed_tick != state.tick
        ):
            raise InvalidTurn("acknowledgement does not match a pending delivery at this boundary")
