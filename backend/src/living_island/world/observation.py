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

Content ([CR-002]): ``begin_observation_tick`` receives the verified ``WorldContent`` and the
accumulator keeps a private deep copy; ``observe_step`` and ``finish_observation_tick`` read
content only from the accumulator, so later changes to the caller's object have no effect.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from living_island.world.content import WorldContent, config_hash, map_hash
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
# Derived tile views
# ---------------------------------------------------------------------------

# Immutable, shared TileView objects per map, keyed only by a map hash that
# ``begin_observation_tick`` has just recomputed from the private copy's rows and verified
# against the world identity. This caches derived data only (never content).
_TILE_VIEWS: dict[str, tuple[TileView, ...]] = {}


def _tile_views(smap: StaticMap, verified_map_hash: str) -> tuple[TileView, ...]:
    key = verified_map_hash
    views = _TILE_VIEWS.get(key)
    if views is None:
        views = tuple(
            TileView(position=smap.coord(i), terrain=smap.terrain(i % smap.width, i // smap.width))
            for i in range(smap.width * smap.height)
        )
        _TILE_VIEWS[key] = views
    return views


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


@dataclass(frozen=True)
class _KnownIndex:
    """Novelty lookups derived once from the immutable tick-start baseline.

    Every value is a frozenset or a read-only mapping, so nothing here can be changed after
    construction (WR §5.1 step 6: compare against receipts at the start of the tick).
    """

    ids: Mapping[str, frozenset[str]]
    triples: Mapping[str, frozenset[_Triple]]
    cue_detail: Mapping[str, Mapping[str, str]]


def _build_known(baseline: tuple[ExposureReceipts, ...]) -> _KnownIndex:
    return _KnownIndex(
        ids=MappingProxyType(
            {r.resident_id: frozenset(e.entity_id for e in r.entities) for r in baseline}
        ),
        triples=MappingProxyType(
            {
                r.resident_id: frozenset(
                    (e.entity_id, e.entity_type, e.position.x, e.position.y) for e in r.entities
                )
                for r in baseline
            }
        ),
        cue_detail=MappingProxyType(
            {
                r.resident_id: MappingProxyType(
                    {c.cue_id: c.detail_level for c in r.cue_detail_seen}
                )
                for r in baseline
            }
        ),
    )


_NO_IDS: frozenset[str] = frozenset()
_NO_TRIPLES: frozenset[_Triple] = frozenset()
_NO_CUES: Mapping[str, str] = MappingProxyType({})


class WorkingAccumulator(ObservationAccumulator):
    """``ObservationAccumulator`` plus the private per-tick working data of P1-02."""

    def __init__(
        self,
        completed_tick: int,
        receipt_baseline: tuple[ExposureReceipts, ...],
        private_content: WorldContent,
    ):
        """Takes ownership of ``private_content``, already deep-copied and hash-verified."""
        super().__init__(completed_tick, receipt_baseline)
        self._content = private_content
        self._smap = StaticMap.from_content(private_content)
        self._tile_views = _tile_views(self._smap, private_content.map_hash)
        self._steps: dict[str, _ActorSteps] = {}
        self._known = _build_known(self._receipt_baseline)  # from the private baseline copy


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


def begin_observation_tick(
    state: WorldState, completed_tick: int, content: WorldContent
) -> ObservationAccumulator:
    """Open a tick: freeze the tick-start receipt baseline and keep verified content.

    [CR-002] The content is deep-copied first. The copy's canonical config and map hashes are
    recomputed from its data and must equal its declared hashes and the world state's
    identity, before the map is built or any cache is read. A mismatch raises; there is no
    fallback. The caller's object is never read again.
    """
    if completed_tick < 0:
        raise ValueError("completed_tick must be nonnegative")
    private = content.model_copy(deep=True)
    if config_hash(private.config) != private.config_hash:
        raise ValueError("content config does not match its declared config_hash (stale content)")
    if map_hash(private.map_rows) != private.map_hash:
        raise ValueError("content map does not match its declared map_hash (stale content)")
    if (private.config_hash, private.map_hash) != (state.config_hash, state.map_hash):
        raise ValueError("content hashes do not match the world state's config_hash/map_hash")
    return WorkingAccumulator(completed_tick, tuple(state.exposure_receipts_by_resident), private)


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
    smap = acc._smap
    if not smap.in_bounds(position.x, position.y):
        raise ValueError("observed position is outside the map")
    work = acc._steps.setdefault(actor_id, _ActorSteps())
    if step_index != work.last_step + 1:
        raise ValueError(
            f"step_index must be consecutive from 1: expected {work.last_step + 1}, "
            f"got {step_index}"
        )
    sight = sample_sight(smap, acc._content.config, state, actor_id, position, acc.completed_tick)
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
    smap, config = acc._smap, acc._content.config
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
        work = acc._steps.get(actor_id) or _ActorSteps()

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

        # Exposures for the receipts. Cues are ordinary entities and arrive through
        # ``sight.entities``. The actor's own identity and carried canteen are exposed at the
        # boundary (Interface Contract §2.1).
        sighted: set[_Triple] = set(work.exposures)
        sighted.update(_triple(e) for e in end.entities)
        own: set[_Triple] = {(actor_id, "resident", resident.position.x, resident.position.y)}
        inventory = own_inventory(state, resident)
        if inventory.canteen_id is not None:
            own.add((inventory.canteen_id, "canteen", resident.position.x, resident.position.y))

        known_ids = acc._known.ids.get(actor_id, _NO_IDS)
        known_triples = acc._known.triples.get(actor_id, _NO_TRIPLES)
        known_cues = acc._known.cue_detail.get(actor_id, _NO_CUES)

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

        # NEW_SIGHT: the first exposure of an entity ID (seen, or the inventory canteen), or
        # the first distant->near cue upgrade, against the tick-start receipts. Self is never
        # counted. The initial scan seeds receipts without an interrupt.
        if acc.completed_tick > 0:
            novel_entity = any(t[0] not in known_ids for t in sighted)
            novel_inventory = (
                inventory.canteen_id is not None and inventory.canteen_id not in known_ids
            )
            novel_cue = any(
                c.detail_level == "near" and known_cues.get(cid) != "near"
                for cid, c in cues.items()
            )
            if novel_entity or novel_inventory or novel_cue:
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
                visible_tiles=[acc._tile_views[i] for i in end.tile_indices],
                visible_entities=[_entity_to_visible(e) for e in end.entities],
                transient_sightings=transient,
                explored_static_tiles=[acc._tile_views[i] for i in explored_after],
                environmental_cues=[_cue_to_protocol(c) for _, c in sorted(cues.items())],
            )
        )

    return ObservationBatch(
        physical_samples_by_actor=samples,
        new_static_tiles_by_actor=new_tiles,
        exposure_receipt_updates=receipt_updates,
        new_sight_actor_ids=new_sight_ids,
    )
