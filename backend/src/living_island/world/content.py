"""Typed effective configuration and static map, validated without IO.

``EffectiveConfig`` mirrors the landed TOML tree (``content/worlds/default.toml``) field by
field. ``build_world_content`` checks configuration domains (World Rules §1.1) and the map
grammar and positions (World Rules §1.2), and computes canonical identities
(Interface Contract §6.3). File reading belongs to ``living_island.persistence.content``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from living_island.world.protocol import Coord, NonNegInt, PosInt

UINT32_MAX = 0xFFFFFFFF


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# TOML ``[x, y]`` syntax; convert explicitly with ``to_coord`` (Interface Contract §1).
ConfigPosition = Annotated[list[NonNegInt], Field(min_length=2, max_length=2)]


def to_coord(position: list[int]) -> Coord:
    return Coord(x=position[0], y=position[1])


class MetaConfig(ContentModel):
    schema_version: str
    world_id: str
    run_id: str
    seed: Annotated[int, Field(ge=1, le=UINT32_MAX)]


class MapConfig(ContentModel):
    width: PosInt
    height: PosInt
    layout_file: str
    tile_size_m: PosInt
    tile_meaning: str
    walk_cost_budget_per_tick: PosInt
    step_cost_beach: PosInt
    step_cost_grass: PosInt
    step_cost_woods: PosInt
    step_cost_cave: PosInt
    step_cost_damp_moss: PosInt
    step_cost_fruit_tree: PosInt

    @model_validator(mode="after")
    def _costs_fit_budget(self) -> MapConfig:
        for name in (
            "step_cost_beach",
            "step_cost_grass",
            "step_cost_woods",
            "step_cost_cave",
            "step_cost_damp_moss",
            "step_cost_fruit_tree",
        ):
            if getattr(self, name) > self.walk_cost_budget_per_tick:
                raise ValueError(f"map.{name} must be in 1..map.walk_cost_budget_per_tick")
        return self


class TimeConfig(ContentModel):
    tick_minutes: PosInt
    start_hour: Annotated[int, Field(ge=0, le=23)]
    day_start_hour: Annotated[int, Field(ge=0, le=24)]
    day_end_hour: Annotated[int, Field(ge=0, le=24)]

    @model_validator(mode="after")
    def _clock(self) -> TimeConfig:
        if 1440 % self.tick_minutes != 0:
            raise ValueError("time.tick_minutes must divide 1440")
        if not self.day_start_hour < self.day_end_hour:
            raise ValueError("require 0 <= day_start_hour < day_end_hour <= 24")
        return self


class NeedsConfig(ContentModel):
    min_value: Literal[0]
    max_value: PosInt
    initial_satiety: NonNegInt
    initial_hydration: NonNegInt
    initial_stamina: NonNegInt
    initial_health: NonNegInt
    satiety_decay_per_tick: NonNegInt
    hydration_decay_per_tick: NonNegInt
    stamina_awake_decay_per_tick: NonNegInt
    stamina_move_extra_cost_per_tick: NonNegInt
    stamina_gather_cost_per_completion: NonNegInt
    satiety_gain_per_fruit: NonNegInt
    hydration_gain_per_serving: NonNegInt
    health_loss_per_tick_if_deprived: NonNegInt
    health_recovery_sleep_per_tick: NonNegInt
    health_recovery_min_satiety: NonNegInt
    health_recovery_min_hydration: NonNegInt
    stamina_rest_gain_per_tick: NonNegInt
    stamina_sleep_gain_per_tick: NonNegInt
    stamina_sleep_cave_bonus_per_tick: NonNegInt

    @model_validator(mode="after")
    def _bounds(self) -> NeedsConfig:
        for name in (
            "initial_satiety",
            "initial_hydration",
            "initial_stamina",
            "initial_health",
            "health_recovery_min_satiety",
            "health_recovery_min_hydration",
        ):
            if getattr(self, name) > self.max_value:
                raise ValueError(f"needs.{name} must be within [min_value, max_value]")
        return self


class FruitConfig(ContentModel):
    initial_stock_per_tree: NonNegInt
    max_stock_per_tree: NonNegInt
    regrow_ticks: PosInt
    regrow_per_cycle: NonNegInt

    @model_validator(mode="after")
    def _stock(self) -> FruitConfig:
        if self.initial_stock_per_tree > self.max_stock_per_tree:
            raise ValueError("fruit.initial_stock_per_tree must not exceed max_stock_per_tree")
        return self


class InventoryConfig(ContentModel):
    slot_capacity: PosInt


class CanteenConfig(ContentModel):
    unique_item_id: str
    capacity_servings: NonNegInt
    initial_servings: NonNegInt
    initial_owner_id: str

    @model_validator(mode="after")
    def _servings(self) -> CanteenConfig:
        if self.initial_servings > self.capacity_servings:
            raise ValueError("canteen.initial_servings must not exceed capacity_servings")
        return self


class ActionsConfig(ContentModel):
    invalid_attempt_ticks: PosInt
    gather_ticks: PosInt
    eat_ticks: PosInt
    drink_ticks: PosInt
    fill_canteen_ticks: PosInt
    rest_ticks: PosInt
    sleep_ticks: PosInt
    talk_ticks: PosInt
    give_ticks: PosInt
    pick_up_ticks: PosInt
    wait_ticks: PosInt


class PerceptionConfig(ContentModel):
    day_radius_tiles: NonNegInt
    night_radius_tiles: NonNegInt
    hearing_radius_tiles: NonNegInt
    cue_detail_radius_tiles: NonNegInt
    fruit_few_max: NonNegInt
    need_band_cutoffs: Annotated[list[int], Field(min_length=4, max_length=4)]
    visible_weakness_health_below: NonNegInt
    visible_dehydration_hydration_below: NonNegInt
    visible_fatigue_stamina_below: NonNegInt


class SocialConfig(ContentModel):
    max_dialogue_turns: NonNegInt
    dialogue_gap_ticks: NonNegInt
    dialogue_cooldown_ticks: NonNegInt


class AgentsConfig(ContentModel):
    max_plan_actions: PosInt
    urgent_satiety_below: NonNegInt
    urgent_hydration_below: NonNegInt
    urgent_stamina_below: NonNegInt
    max_high_level_decisions_per_resident_per_day_soft: NonNegInt
    llm_retry_on_parse_error: NonNegInt


class CueConfig(ContentModel):
    id: str
    # Only the damp-moss cue (map symbol ``M``) exists in v0.1 (World Rules §1.2).
    kind: Literal["damp_moss"]
    position: ConfigPosition
    visible_description: str
    near_description: str
    direction: str | None = None


class FruitTreeConfig(ContentModel):
    id: str
    position: ConfigPosition
    regrow_phase_offset_ticks: NonNegInt


class WorldSection(ContentModel):
    initial_cave: ConfigPosition
    spring: ConfigPosition
    cues: list[CueConfig]
    fruit_trees: list[FruitTreeConfig]


class ResidentConfig(ContentModel):
    id: str
    name: str
    position: ConfigPosition
    profile_id: str
    initial_goal: str


def _unique(values: list[Any], what: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{what} must be unique")


class EffectiveConfig(ContentModel):
    """The typed TOML tree, with the landed field names."""

    meta: MetaConfig
    map: MapConfig
    time: TimeConfig
    needs: NeedsConfig
    fruit: FruitConfig
    inventory: InventoryConfig
    canteen: CanteenConfig
    actions: ActionsConfig
    perception: PerceptionConfig
    social: SocialConfig
    agents: AgentsConfig
    world: WorldSection
    residents: Annotated[list[ResidentConfig], Field(min_length=1)]

    @model_validator(mode="after")
    def _cross_section(self) -> EffectiveConfig:
        lo, hi = self.needs.min_value, self.needs.max_value
        cut = self.perception.need_band_cutoffs
        if not lo < cut[0] < cut[1] < cut[2] < cut[3] < hi:
            raise ValueError(
                "perception.need_band_cutoffs must be four strictly increasing "
                "values strictly inside (min_value, max_value)"
            )
        for name in (
            "visible_weakness_health_below",
            "visible_dehydration_hydration_below",
            "visible_fatigue_stamina_below",
        ):
            if getattr(self.perception, name) > hi:
                raise ValueError(f"perception.{name} must be within need bounds")
        for name in ("urgent_satiety_below", "urgent_hydration_below", "urgent_stamina_below"):
            if getattr(self.agents, name) > hi:
                raise ValueError(f"agents.{name} must be within need bounds")
        for tree in self.world.fruit_trees:
            if tree.regrow_phase_offset_ticks >= self.fruit.regrow_ticks:
                raise ValueError(f"{tree.id}: phase offset must be in 0..regrow_ticks-1")
        resident_ids = [r.id for r in self.residents]
        _unique(resident_ids, "resident IDs")
        _unique([t.id for t in self.world.fruit_trees], "fruit tree IDs")
        _unique([c.id for c in self.world.cues], "cue IDs")
        _unique([tuple(r.position) for r in self.residents], "resident spawn positions")
        _unique([tuple(t.position) for t in self.world.fruit_trees], "fruit tree positions")
        _unique([tuple(c.position) for c in self.world.cues], "cue positions")
        if self.canteen.initial_owner_id not in resident_ids:
            raise ValueError("canteen.initial_owner_id must be a configured resident")
        return self


# ---------------------------------------------------------------------------
# Canonical identities (Interface Contract §6.3)
# ---------------------------------------------------------------------------


def canonical_json_bytes(value: Any) -> bytes:
    """Canonical JSON: sorted keys, no whitespace, UTF-8, no NaN."""
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def config_hash(config: EffectiveConfig) -> str:
    return hashlib.sha256(canonical_json_bytes(config.model_dump(mode="json"))).hexdigest()


def map_bytes_from_rows(rows: list[str]) -> bytes:
    return "".join(row + "\n" for row in rows).encode("utf-8")


def map_hash(rows: list[str]) -> str:
    return hashlib.sha256(map_bytes_from_rows(rows)).hexdigest()


# ---------------------------------------------------------------------------
# Map grammar and position checks (World Rules §1.2)
# ---------------------------------------------------------------------------

MAP_SYMBOLS = frozenset("~.,W^SCFM")
IMPASSABLE_SYMBOLS = frozenset("~^S")


def parse_map_bytes(raw: bytes) -> list[str]:
    """Decode the ``.map`` grammar: UTF-8 without BOM, LF-terminated rows."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("map must not start with a BOM")
    if b"\r" in raw:
        raise ValueError("map must use LF line endings, not CRLF/CR")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("map must be UTF-8") from exc
    if not text.endswith("\n"):
        raise ValueError("every map row, including the last, ends with LF")
    return text[:-1].split("\n")


def check_map(config: EffectiveConfig, rows: list[str]) -> None:
    width, height = config.map.width, config.map.height
    if len(rows) != height:
        raise ValueError(f"map must have exactly map.height={height} rows, got {len(rows)}")
    for y, row in enumerate(rows):
        bad = sorted({ch for ch in row if ch not in MAP_SYMBOLS})
        if bad:
            raise ValueError(f"map row {y} has disallowed characters {bad!r}")
        if len(row) != width:
            raise ValueError(f"map row {y} must have width {width}, got {len(row)}")

    def symbol_at(pos: list[int], what: str) -> str:
        x, y = pos
        if not (x < width and y < height):
            raise ValueError(f"{what} {pos} is outside the map")
        return rows[y][x]

    def positions_of(symbol: str) -> list[tuple[int, int]]:
        return [(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == symbol]

    for symbol in "SCM":
        if len(positions_of(symbol)) != 1:
            raise ValueError(f"map must contain exactly one {symbol!r}")
    if symbol_at(config.world.spring, "world.spring") != "S":
        raise ValueError("world.spring must match the map's S")
    if symbol_at(config.world.initial_cave, "world.initial_cave") != "C":
        raise ValueError("world.initial_cave must match the map's C")
    if len(config.world.cues) != 1:
        raise ValueError("exactly one damp_moss cue must match the map's single M")
    for cue in config.world.cues:
        if symbol_at(cue.position, f"cue {cue.id}") != "M":
            raise ValueError(f"cue {cue.id} must be on the map's M")
    trees = {tuple(t.position) for t in config.world.fruit_trees}
    if set(positions_of("F")) != trees:
        raise ValueError("map F tiles must match [[world.fruit_trees]] one-to-one")
    for resident in config.residents:
        if symbol_at(resident.position, f"resident {resident.id}") in IMPASSABLE_SYMBOLS:
            raise ValueError(f"resident {resident.id} spawns on an impassable tile")
    border = rows[0] + rows[-1] + "".join(row[0] + row[-1] for row in rows)
    if set(border) != {"~"}:
        raise ValueError("the map border must be ocean '~'")


class WorldContent(ContentModel):
    """Validated content plus canonical identities; never built from unchecked data."""

    config: EffectiveConfig
    map_rows: list[str]
    config_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    map_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _verified(self) -> WorldContent:
        check_map(self.config, self.map_rows)
        if self.config_hash != config_hash(self.config):
            raise ValueError("config_hash does not match the canonical config")
        if self.map_hash != map_hash(self.map_rows):
            raise ValueError("map_hash does not match the canonical map bytes")
        return self


def build_world_content(config_data: Mapping[str, Any], map_raw: bytes) -> WorldContent:
    """Validate a parsed TOML mapping and raw map bytes into ``WorldContent``."""
    config = EffectiveConfig.model_validate(config_data)
    rows = parse_map_bytes(map_raw)
    return WorldContent(
        config=config, map_rows=rows, config_hash=config_hash(config), map_hash=map_hash(rows)
    )
