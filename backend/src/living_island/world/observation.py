"""Bodies of the observation ports (implementation plan §2.1, World Rules §5.1 steps 5-7).

``begin_observation_tick`` / ``observe_step`` / ``finish_observation_tick`` accumulate per
actor, over one completed tick:

* the union of tiles seen (explored footprint growth),
* the last intermediate sighting of every entity (transient sightings),
* the highest cue detail seen,
* every exposure for the private receipts.

Observe calls modify only the accumulator, never ``WorldState`` (receipts and footprints are
applied by the engine in phase 6). Novelty compares against the immutable tick-start receipt
baseline held by the accumulator. Descriptors are captured when seen. Hearing and action
feedback are not assembled here (P1-04).

Content binding: the frozen port signatures carry no map or config, so content is looked up
by the ``(config_hash, map_hash)`` identity stored in ``WorldState``. The engine (or a test)
calls ``register_content`` once per verified ``WorldContent`` (open question OQ-009).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from living_island.world.content import WorldContent
from living_island.world.perception import (
    CueView,
    EntityView,
    Sight,
    own_condition,
    own_inventory,
    sample_sight,
)
from living_island.world.ports import (
    ExposureReceiptUpdate,
    NewStaticTiles,
    ObservationAccumulator,
    ObservationBatch,
    ObservationSample,
)
from living_island.world.protocol import (
    Coord,
    EntityType,
    EnvironmentalCue,
    TileView,
    TransientSighting,
    VisibleEntity,
)
from living_island.world.receipts import merge_tile_indices
from living_island.world.space import StaticMap
from living_island.world.state import (
    CueDetailReceipt,
    ExposureReceipts,
    ReceiptEntity,
    ResidentPhysicalState,
    WorldState,
)

# ---------------------------------------------------------------------------
# Content binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoundContent:
    """Verified content plus its derived static map and shared immutable tile views."""

    content: WorldContent
    smap: StaticMap
    tile_views: tuple[TileView, ...]


_BOUND: dict[tuple[str, str], BoundContent] = {}


def register_content(content: WorldContent) -> None:
    """Make verified content available to the observation ports by its hashes (idempotent)."""
    key = (content.config_hash, content.map_hash)
    if key in _BOUND:
        return
    smap = StaticMap.from_content(content)
    views = tuple(
        TileView(
            position=smap.coord(i),
            terrain=smap.terrain(i % smap.width, i // smap.width),
        )
        for i in range(smap.width * smap.height)
    )
    _BOUND[key] = BoundContent(content, smap, views)


def bound_content_for(state: WorldState) -> BoundContent:
    try:
        return _BOUND[(state.config_hash, state.map_hash)]
    except KeyError:
        raise ValueError(
            "world content for this state's config_hash/map_hash is not registered; "
            "call register_content(content) first"
        ) from None


# ---------------------------------------------------------------------------
# Accumulator
# ---------------------------------------------------------------------------

_Triple = tuple[str, EntityType, int, int]  # (entity_id, entity_type, x, y)


def _triple(view: EntityView) -> _Triple:
    return (view.entity_id, view.entity_type, view.position.x, view.position.y)


@dataclass
class _ActorSteps:
    last_step: int = 0
    tiles: set[int] = field(default_factory=set)
    # entity_id -> (step_index, descriptor captured at that step); last step wins.
    last_seen: dict[str, tuple[int, EntityView]] = field(default_factory=dict)
    exposures: set[_Triple] = field(default_factory=set)
    cues: dict[str, CueView] = field(default_factory=dict)  # highest detail seen


class WorkingAccumulator(ObservationAccumulator):
    """``ObservationAccumulator`` plus the private per-tick working data of P1-02."""

    def __init__(
        self,
        completed_tick: int,
        receipt_baseline: tuple[ExposureReceipts, ...],
        bound: BoundContent,
    ):
        super().__init__(completed_tick, receipt_baseline)
        self.bound = bound
        self.steps: dict[str, _ActorSteps] = {}
        baseline = self._receipt_baseline  # private immutable copy; never mutated
        self.known_ids = {r.resident_id: {e.entity_id for e in r.entities} for r in baseline}
        self.known_triples: dict[str, set[_Triple]] = {
            r.resident_id: {
                (e.entity_id, e.entity_type, e.position.x, e.position.y) for e in r.entities
            }
            for r in baseline
        }
        self.known_cue_detail: dict[str, dict[str, str]] = {
            r.resident_id: {c.cue_id: c.detail_level for c in r.cue_detail_seen} for r in baseline
        }


def _record_cues(into: dict[str, CueView], cues: tuple[CueView, ...]) -> None:
    """Keep the highest detail per cue; near beats distant (WR §5.1 step 6)."""
    for cue in cues:
        have = into.get(cue.cue_id)
        if have is None or (have.detail_level == "distant" and cue.detail_level == "near"):
            into[cue.cue_id] = cue


def _living(state: WorldState, actor_id: str) -> ResidentPhysicalState:
    for r in state.residents:
        if r.id == actor_id:
            if not r.alive:
                raise ValueError(f"{actor_id} is dead and cannot observe")
            return r
    raise ValueError(f"unknown resident {actor_id!r}")


def begin_observation_tick(state: WorldState, completed_tick: int) -> ObservationAccumulator:
    """Open a tick: freeze the tick-start receipt baseline and bind the content."""
    if completed_tick < 0:
        raise ValueError("completed_tick must be nonnegative")
    bound = bound_content_for(state)
    return WorkingAccumulator(completed_tick, tuple(state.exposure_receipts_by_resident), bound)


def observe_step(
    acc: ObservationAccumulator,
    state: WorldState,
    actor_id: str,
    position: Coord,
    step_index: int,
) -> None:
    """Sample once after an entered tile; ``step_index`` is the actor's 1-based step."""
    if not isinstance(acc, WorkingAccumulator):
        raise TypeError("accumulator was not created by begin_observation_tick")
    _living(state, actor_id)
    smap = acc.bound.smap
    if not smap.in_bounds(position.x, position.y):
        raise ValueError("observed position is outside the map")
    work = acc.steps.setdefault(actor_id, _ActorSteps())
    if step_index != work.last_step + 1:
        raise ValueError(
            f"step_index must be consecutive from 1: expected {work.last_step + 1}, "
            f"got {step_index}"
        )
    sight = sample_sight(
        smap, acc.bound.content.config, state, actor_id, position, acc.completed_tick
    )
    work.last_step = step_index
    work.tiles.update(sight.tile_indices)
    for view in sight.entities:
        work.last_seen[view.entity_id] = (step_index, view)
        work.exposures.add(_triple(view))
    _record_cues(work.cues, sight.cues)


def _entity_to_visible(view: EntityView) -> VisibleEntity:
    return VisibleEntity(
        entity_id=view.entity_id,
        entity_type=view.entity_type,
        position=view.position,
        observable_signs=list(view.observable_signs),
        fruit_band=view.fruit_band,
        quantity=view.quantity,
    )


def _cue_to_protocol(cue: CueView) -> EnvironmentalCue:
    return EnvironmentalCue(
        cue_id=cue.cue_id,
        position=cue.position,
        detail_level=cue.detail_level,
        physical_description=cue.physical_description,
        direction=cue.direction,
    )


def _explored_set(state: WorldState, actor_id: str) -> set[int]:
    for group in state.explored_tiles_by_resident:
        if group.resident_id == actor_id:
            return set(group.tile_indices)
    return set()


def finish_observation_tick(acc: ObservationAccumulator, state: WorldState) -> ObservationBatch:
    """Freeze the tick: boundary scan for every living resident, then build the batch.

    ``new_static_tiles_by_actor`` and ``exposure_receipt_updates`` list only actors with
    something new; ``physical_samples_by_actor`` covers every living resident. When
    ``completed_tick`` is zero (the initial scan) receipts are seeded and no NEW_SIGHT is
    reported. The caller applies footprints and receipts exactly once (phase 6).
    """
    if not isinstance(acc, WorkingAccumulator):
        raise TypeError("accumulator was not created by begin_observation_tick")
    bound = acc.bound
    smap, config = bound.smap, bound.content.config
    samples: list[ObservationSample] = []
    new_tiles: list[NewStaticTiles] = []
    receipt_updates: list[ExposureReceiptUpdate] = []
    new_sight_ids: list[str] = []

    for resident in state.residents:  # ascending ID by WorldState invariant
        if not resident.alive:
            continue
        actor_id = resident.id
        end: Sight = sample_sight(
            smap, config, state, actor_id, resident.position, acc.completed_tick
        )
        work = acc.steps.get(actor_id) or _ActorSteps()

        # Footprint: static tiles only.
        seen_tiles = set(end.tile_indices) | work.tiles
        explored = _explored_set(state, actor_id)
        added = sorted(seen_tiles - explored)
        explored_after = merge_tile_indices(explored, seen_tiles)

        # Transient sightings: last intermediate sample per ID, minus tick-end visibles.
        end_ids = {e.entity_id for e in end.entities}
        transient = [
            TransientSighting(
                entity_id=v.entity_id,
                entity_type=v.entity_type,
                position=v.position,
                seen_at_step=step,
                observable_signs=list(v.observable_signs),
                fruit_band=v.fruit_band,
                quantity=v.quantity,
            )
            for eid, (step, v) in sorted(work.last_seen.items())
            if eid not in end_ids
        ]

        # Cues: highest detail across steps and the boundary scan.
        cues = dict(work.cues)
        _record_cues(cues, end.cues)

        # Exposures for the receipts. Own identity and carried canteen are exposed at the
        # boundary (Interface Contract §2.1) but are never "sights" for novelty.
        sighted: set[_Triple] = set(work.exposures)
        sighted.update(_triple(e) for e in end.entities)
        sighted.update((c.cue_id, "cue", c.position.x, c.position.y) for c in cues.values())
        own: set[_Triple] = {(actor_id, "resident", resident.position.x, resident.position.y)}
        inventory = own_inventory(state, resident)
        if inventory.canteen_id is not None:
            own.add((inventory.canteen_id, "canteen", resident.position.x, resident.position.y))

        known_ids = acc.known_ids.get(actor_id, set())
        known_triples = acc.known_triples.get(actor_id, set())
        known_cues = acc.known_cue_detail.get(actor_id, {})

        fresh_triples = sorted((sighted | own) - known_triples, key=lambda t: (t[0], t[3], t[2]))
        cue_updates = [
            CueDetailReceipt(cue_id=cid, detail_level=c.detail_level)
            for cid, c in sorted(cues.items())
            if known_cues.get(cid) is None
            or (known_cues[cid] == "distant" and c.detail_level == "near")
        ]
        if fresh_triples or cue_updates:
            receipt_updates.append(
                ExposureReceiptUpdate(
                    actor_id=actor_id,
                    entities=[
                        ReceiptEntity(
                            entity_id=t[0], entity_type=t[1], position=Coord(x=t[2], y=t[3])
                        )
                        for t in fresh_triples
                    ],
                    cue_detail_seen=cue_updates,
                )
            )

        # NEW_SIGHT: first exposure of an entity ID, or first distant->near cue upgrade,
        # against the tick-start receipts. The initial scan seeds without interrupting.
        if acc.completed_tick > 0:
            novel_entity = any(t[0] not in known_ids and t[1] != "cue" for t in sighted)
            novel_cue = any(
                cid not in known_ids or (known_cues.get(cid) != "near" and c.detail_level == "near")
                for cid, c in cues.items()
            )
            if novel_entity or novel_cue:
                new_sight_ids.append(actor_id)

        if added:
            new_tiles.append(NewStaticTiles(actor_id=actor_id, tile_indices=added))

        samples.append(
            ObservationSample(
                schema_version=state.schema_version,
                actor_id=actor_id,
                tick=acc.completed_tick,
                own_condition=own_condition(config, resident),
                own_position=resident.position,
                own_inventory=inventory,
                visible_tiles=[bound.tile_views[i] for i in end.tile_indices],
                visible_entities=[_entity_to_visible(e) for e in end.entities],
                transient_sightings=transient,
                explored_static_tiles=[bound.tile_views[i] for i in explored_after],
                environmental_cues=[_cue_to_protocol(c) for _, c in sorted(cues.items())],
            )
        )

    return ObservationBatch(
        physical_samples_by_actor=samples,
        new_static_tiles_by_actor=new_tiles,
        exposure_receipt_updates=receipt_updates,
        new_sight_actor_ids=new_sight_ids,
    )
