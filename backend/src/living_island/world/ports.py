"""Frozen world integration ports (implementation plan §2.1).

Signatures are normative for P1. Bodies arrive later: observation in P1-02, the engine in
P1-04. Only engine ports mutate world state.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import model_validator

from living_island.world.content import WorldContent
from living_island.world.facts import EventType, TypedEventPayload, WorldEvent
from living_island.world.protocol import (
    ActionIntent,
    BoundaryPerceptionDelivery,
    Coord,
    EnvironmentalCue,
    NonNegInt,
    OwnCondition,
    OwnInventory,
    ProtocolModel,
    TileView,
    TransientSighting,
    VisibleEntity,
    check_physical_view_order,
    require_sorted_unique,
)
from living_island.world.state import (
    CueDetailReceipt,
    ExposureReceipts,
    ReceiptEntity,
    WorldState,
    check_receipt_order,
)

# ---------------------------------------------------------------------------
# Observation results
# ---------------------------------------------------------------------------


class ObservationSample(ProtocolModel):
    """Every Perception field except ``heard_utterances`` and ``last_action_feedback``."""

    schema_version: str
    actor_id: str
    tick: NonNegInt
    own_condition: OwnCondition
    own_position: Coord
    own_inventory: OwnInventory
    visible_tiles: list[TileView]
    visible_entities: list[VisibleEntity]
    transient_sightings: list[TransientSighting]
    explored_static_tiles: list[TileView]
    environmental_cues: list[EnvironmentalCue]

    @model_validator(mode="after")
    def _ordering(self) -> ObservationSample:
        check_physical_view_order(
            self.actor_id,
            self.visible_entities,
            self.transient_sightings,
            self.environmental_cues,
        )
        return self


class ExposureReceiptUpdate(ProtocolModel):
    """New receipt entries for one actor, using the Interface Contract §2.1 entry types."""

    actor_id: str
    entities: list[ReceiptEntity]
    cue_detail_seen: list[CueDetailReceipt]

    @model_validator(mode="after")
    def _sorted(self) -> ExposureReceiptUpdate:
        check_receipt_order(self.entities, self.cue_detail_seen)
        return self


class NewStaticTiles(ProtocolModel):
    actor_id: str
    tile_indices: list[NonNegInt]

    @model_validator(mode="after")
    def _sorted(self) -> NewStaticTiles:
        idx = self.tile_indices
        if any(a >= b for a, b in zip(idx, idx[1:], strict=False)):
            raise ValueError("tile_indices must be ascending and duplicate-free")
        return self


class ObservationBatch(ProtocolModel):
    """Frozen result of one tick's observation; every array sorts by actor ID."""

    physical_samples_by_actor: list[ObservationSample]
    new_static_tiles_by_actor: list[NewStaticTiles]
    exposure_receipt_updates: list[ExposureReceiptUpdate]
    new_sight_actor_ids: list[str]

    @model_validator(mode="after")
    def _sorted(self) -> ObservationBatch:
        require_sorted_unique(
            [s.actor_id for s in self.physical_samples_by_actor], "physical_samples_by_actor"
        )
        require_sorted_unique(
            [t.actor_id for t in self.new_static_tiles_by_actor], "new_static_tiles_by_actor"
        )
        require_sorted_unique(
            [u.actor_id for u in self.exposure_receipt_updates], "exposure_receipt_updates"
        )
        require_sorted_unique(self.new_sight_actor_ids, "new_sight_actor_ids")
        return self


class ObservationAccumulator:
    """Per-tick observation buffer owned by P1-02.

    Holds the completed-tick number (its clock/radius applies to every sample) and an
    immutable copy of the tick-start exposure receipts used for novelty. Per-actor step
    samples, unions and highest cue detail are private P1-02 attributes. Observe calls
    modify only this accumulator, never ``WorldState``.
    """

    def __init__(self, completed_tick: int, receipt_baseline: tuple[ExposureReceipts, ...]):
        self._completed_tick = completed_tick
        self._receipt_baseline = tuple(r.model_copy(deep=True) for r in receipt_baseline)

    @property
    def completed_tick(self) -> int:
        return self._completed_tick

    @property
    def receipt_baseline(self) -> tuple[ExposureReceipts, ...]:
        """An isolated deep copy on every access; the private baseline never changes."""
        return tuple(r.model_copy(deep=True) for r in self._receipt_baseline)


def begin_observation_tick(
    state: WorldState, completed_tick: int, content: WorldContent
) -> ObservationAccumulator:
    # Imported here: observation.py builds the models defined above (P1-02).
    from living_island.world import observation

    return observation.begin_observation_tick(state, completed_tick, content)


def observe_step(
    acc: ObservationAccumulator,
    state: WorldState,
    actor_id: str,
    position: Coord,
    step_index: int,
) -> None:
    from living_island.world import observation

    observation.observe_step(acc, state, actor_id, position, step_index)


def finish_observation_tick(acc: ObservationAccumulator, state: WorldState) -> ObservationBatch:
    from living_island.world import observation

    return observation.finish_observation_tick(acc, state)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class WorldTickCommit(ProtocolModel):
    """Immutable copies of one committed boundary, never references to engine objects."""

    snapshot: WorldState
    events: list[WorldEvent]
    pending_deliveries: list[BoundaryPerceptionDelivery]


class WorldEngine(Protocol):
    """One engine instance owns all world mutations (implemented in P1-04)."""

    def initial_commit(self) -> WorldTickCommit:
        """Fresh initialization only: tick zero."""
        raise NotImplementedError

    def begin_tick(self) -> None:
        """Open the next-tick buffer and reset seq before phase 1."""
        raise NotImplementedError

    def start_intent(self, intent: ActionIntent) -> None:
        """Queue an intent to start in phase 2; no early physical effect."""
        raise NotImplementedError

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
        """Allocate the next event ID now; reject forward causal references."""
        raise NotImplementedError

    def advance_tick(self) -> WorldTickCommit:
        raise NotImplementedError


def create_engine(content: WorldContent, restored_world: WorldState | None) -> WorldEngine:
    raise NotImplementedError("P1-04")
