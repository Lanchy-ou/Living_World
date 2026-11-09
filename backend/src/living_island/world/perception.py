"""Physical sampling: what one resident sees from one position (World Rules §5.1, §5.2).

Pure functions from (static map, config, world state, observer position, completed tick) to
immutable sight records. Descriptors (need bands, signs, fruit bands, quantities, cue text)
are captured at sampling time and never refreshed from live state later. This module has no
knowledge of exposure receipts or batching; see ``receipts.py`` and ``observation.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from living_island.world.content import EffectiveConfig
from living_island.world.protocol import (
    Coord,
    CueDetailLevel,
    EntityType,
    FruitBand,
    NeedBand,
    OwnCondition,
    OwnInventory,
    VisibleSign,
)
from living_island.world.space import StaticMap, sight_radius, visible_tile_indices
from living_island.world.state import ResidentPhysicalState, WorldState


@dataclass(frozen=True)
class EntityView:
    """An entity and the descriptor values captured when it was seen."""

    entity_id: str
    entity_type: EntityType
    position: Coord
    observable_signs: tuple[VisibleSign, ...]
    fruit_band: FruitBand | None
    quantity: int | None


@dataclass(frozen=True)
class CueView:
    """A cue as exposed at one detail level (``near`` carries the direction)."""

    cue_id: str
    position: Coord
    detail_level: CueDetailLevel
    physical_description: str
    direction: str | None


@dataclass(frozen=True)
class Sight:
    """One sample: visible tile indices (ascending), entities and cues sorted by ID."""

    tile_indices: tuple[int, ...]
    entities: tuple[EntityView, ...]
    cues: tuple[CueView, ...]


# ---------------------------------------------------------------------------
# Descriptors (Interface Contract §2.5)
# ---------------------------------------------------------------------------


def need_band(value: int, cutoffs: list[int]) -> NeedBand:
    """Five-level band: ``[min,a)`` critical up to ``[d,max]`` strong (IC §2.5)."""
    a, b, c, d = cutoffs
    if value < a:
        return "critical"
    if value < b:
        return "low"
    if value < c:
        return "moderate"
    if value < d:
        return "good"
    return "strong"


def fruit_band(config: EffectiveConfig, stock: int) -> FruitBand:
    if stock <= 0:
        return "empty"
    return "few" if stock <= config.perception.fruit_few_max else "many"


def visible_signs(
    config: EffectiveConfig, resident: ResidentPhysicalState
) -> tuple[VisibleSign, ...]:
    """Observable signs of another resident, in canonical order ``weak, dehydrated, fatigued``."""
    p = config.perception
    signs: list[VisibleSign] = []
    if resident.health < p.visible_weakness_health_below:
        signs.append("weak")
    if resident.hydration < p.visible_dehydration_hydration_below:
        signs.append("dehydrated")
    if resident.stamina < p.visible_fatigue_stamina_below:
        signs.append("fatigued")
    return tuple(signs)


def own_condition(config: EffectiveConfig, resident: ResidentPhysicalState) -> OwnCondition:
    cut = config.perception.need_band_cutoffs
    return OwnCondition(
        satiety=need_band(resident.satiety, cut),
        hydration=need_band(resident.hydration, cut),
        stamina=need_band(resident.stamina, cut),
        health=need_band(resident.health, cut),
    )


def own_inventory(state: WorldState, resident: ResidentPhysicalState) -> OwnInventory:
    """Exact own inventory; the canteen appears only for its holder."""
    canteen = state.unique_canteen
    held = canteen.holder_id == resident.id
    return OwnInventory(
        fruit_count=resident.fruit_count,
        canteen_id=canteen.id if held else None,
        canteen_servings=canteen.servings if held else None,
    )


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def ground_fruit_id(position: Coord) -> str:
    """Spatial handle of a ground fruit pile (Interface Contract §2.2)."""
    return f"ground_fruit@{position.x},{position.y}"


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def sample_sight(
    smap: StaticMap,
    config: EffectiveConfig,
    state: WorldState,
    actor_id: str,
    position: Coord,
    completed_tick: int,
) -> Sight:
    """Everything ``actor_id`` sees from ``position`` using the completed tick's clock.

    Other living residents, corpses, fruit trees (stock band only), ground fruit piles
    (exact quantity), a ground canteen and cues are entities. The observer is excluded. A cue
    also carries a detail record: ``distant`` with the generic description, or ``near`` (within
    ``cue_detail_radius_tiles`` and in sight) with the detailed description and direction.
    Static terrain is not remembered here; remote live stock is never read for unseen tiles.
    """
    radius = sight_radius(config, completed_tick)
    tiles = visible_tile_indices(smap, position.x, position.y, radius)
    visible = set(tiles)

    def seen(at: Coord) -> bool:
        return smap.in_bounds(at.x, at.y) and smap.index(at.x, at.y) in visible

    entities: list[EntityView] = []
    for r in state.residents:
        if r.alive and r.id != actor_id and seen(r.position):
            entities.append(
                EntityView(r.id, "resident", r.position, visible_signs(config, r), None, None)
            )
    for corpse in state.corpses:
        if seen(corpse.position):
            entities.append(EntityView(corpse.id, "corpse", corpse.position, (), None, None))
    for node in state.fruit_nodes:
        if seen(node.position):
            band = fruit_band(config, node.stock)
            entities.append(EntityView(node.id, "fruit_tree", node.position, (), band, None))
    for pile in state.ground_fruit:
        if seen(pile.position):
            entities.append(
                EntityView(
                    ground_fruit_id(pile.position),
                    "ground_fruit",
                    pile.position,
                    (),
                    None,
                    pile.quantity,
                )
            )
    canteen = state.unique_canteen
    if canteen.ground_position is not None and seen(canteen.ground_position):
        entities.append(EntityView(canteen.id, "canteen", canteen.ground_position, (), None, None))

    descriptions = {c.id: c for c in config.world.cues}
    cues: list[CueView] = []
    for cue in state.cues:
        if not seen(cue.position):
            continue
        # A cue is also an ordinary entity (WR §4.1, IC §2.5); its detail stays in ``cues``.
        entities.append(EntityView(cue.id, "cue", cue.position, (), None, None))
        spec = descriptions[cue.id]
        if manhattan(position, cue.position) <= config.perception.cue_detail_radius_tiles:
            cues.append(
                CueView(cue.id, cue.position, "near", spec.near_description, spec.direction)
            )
        else:
            cues.append(CueView(cue.id, cue.position, "distant", spec.visible_description, None))
    cues.sort(key=lambda c: c.cue_id)
    entities.sort(key=lambda e: e.entity_id)
    return Sight(tuple(tiles), tuple(entities), tuple(cues))
