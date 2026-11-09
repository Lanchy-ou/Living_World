"""Authoritative, backend-private world state (Interface Contract §2.1).

``WorldState`` is owned by the world engine. It is never sent to residents or the
frontend wholesale. Unlike protocol DTOs these models are mutable so the engine can
update its own instance; published snapshots are deep copies (plan §2.1).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from living_island.world.protocol import (
    ActionIntent,
    Coord,
    CueDetailLevel,
    EntityType,
    NonNegInt,
    require_sorted_unique,
)

# Xorshift32 state is a nonzero unsigned 32-bit integer (World Rules §5.6).
RngState = Annotated[int, Field(ge=1, le=0xFFFFFFFF)]


class StateModel(BaseModel):
    """Base for world state: strict types and unknown fields rejected."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class ResidentPhysicalState(StateModel):
    id: str
    position: Coord
    alive: bool
    satiety: NonNegInt
    hydration: NonNegInt
    stamina: NonNegInt
    health: NonNegInt
    fruit_count: NonNegInt


class FruitNodeState(StateModel):
    id: str
    position: Coord
    stock: NonNegInt
    regrow_phase_offset_ticks: NonNegInt


class CueState(StateModel):
    id: str
    kind: str
    position: Coord


class GroundFruitPile(StateModel):
    position: Coord
    # Zero-quantity piles are removed (Interface Contract §2.2).
    quantity: Annotated[int, Field(ge=1)]


class UniqueCanteenState(StateModel):
    id: str
    holder_id: str | None
    ground_position: Coord | None
    servings: NonNegInt

    @model_validator(mode="after")
    def _one_place(self) -> UniqueCanteenState:
        if (self.holder_id is None) == (self.ground_position is None):
            raise ValueError("the canteen is in exactly one place: a holder or a ground tile")
        return self


class CorpseState(StateModel):
    id: str
    resident_id: str
    position: Coord
    death_tick: NonNegInt


class DialogueSessionState(StateModel):
    pair_ids: Annotated[list[str], Field(min_length=2, max_length=2)]
    turn_count: NonNegInt
    last_utterance_tick: NonNegInt
    cooldown_until_tick: NonNegInt

    @model_validator(mode="after")
    def _pair(self) -> DialogueSessionState:
        if self.pair_ids[0] >= self.pair_ids[1]:
            raise ValueError("pair_ids are two distinct IDs in ascending order")
        return self


class ActiveAction(StateModel):
    """The complete immutable intent plus its progress."""

    intent: ActionIntent
    tick_started: NonNegInt
    elapsed_ticks: NonNegInt
    remaining_ticks: NonNegInt | None
    route: list[Coord] | None
    route_cursor: NonNegInt | None
    pending_failure_code: str | None


class ExploredTiles(StateModel):
    resident_id: str
    tile_indices: list[NonNegInt]

    @model_validator(mode="after")
    def _sorted(self) -> ExploredTiles:
        if any(a >= b for a, b in zip(self.tile_indices, self.tile_indices[1:], strict=False)):
            raise ValueError("tile_indices must be ascending and duplicate-free")
        return self


class ReceiptEntity(StateModel):
    entity_id: str
    entity_type: EntityType
    position: Coord


class CueDetailReceipt(StateModel):
    cue_id: str
    detail_level: CueDetailLevel


def check_receipt_order(entities: list[ReceiptEntity], cues: list[CueDetailReceipt]) -> None:
    """Receipt entities sort by (entity_id, y, x) uniquely; cue details by cue ID."""
    keys = [(e.entity_id, e.position.y, e.position.x) for e in entities]
    if any(a >= b for a, b in zip(keys, keys[1:], strict=False)):
        raise ValueError("receipt entities must be sorted by (entity_id,y,x) and unique")
    require_sorted_unique([c.cue_id for c in cues], "cue_detail_seen")


class ExposureReceipts(StateModel):
    resident_id: str
    entities: list[ReceiptEntity]
    cue_detail_seen: list[CueDetailReceipt]

    @model_validator(mode="after")
    def _sorted(self) -> ExposureReceipts:
        check_receipt_order(self.entities, self.cue_detail_seen)
        return self


class RuleOverrides(StateModel):
    """Runtime rule edits are disabled in P1: the only valid value is ``{}``."""


class WorldState(StateModel):
    schema_version: str
    world_id: str
    run_id: str
    tick: NonNegInt
    config_hash: str
    map_hash: str
    static_map_ref: str
    residents: list[ResidentPhysicalState]
    fruit_nodes: list[FruitNodeState]
    cave: Coord
    spring: Coord
    cues: list[CueState]
    ground_fruit: list[GroundFruitPile]
    lifetime_fruit_regrown: NonNegInt
    lifetime_fruit_consumed: NonNegInt
    unique_canteen: UniqueCanteenState
    corpses: list[CorpseState]
    dialogue_sessions: list[DialogueSessionState]
    active_actions: list[ActiveAction]
    explored_tiles_by_resident: list[ExploredTiles]
    exposure_receipts_by_resident: list[ExposureReceipts]
    resolution_rng_state_uint32: RngState
    next_event_seq_in_tick: NonNegInt
    event_log_cursor: NonNegInt
    rule_overrides: RuleOverrides

    @model_validator(mode="after")
    def _canonical_order(self) -> WorldState:
        require_sorted_unique([r.id for r in self.residents], "residents")
        require_sorted_unique([n.id for n in self.fruit_nodes], "fruit_nodes")
        require_sorted_unique([c.id for c in self.corpses], "corpses")
        require_sorted_unique([c.id for c in self.cues], "cues")
        require_sorted_unique(
            [g.resident_id for g in self.explored_tiles_by_resident], "explored_tiles_by_resident"
        )
        require_sorted_unique(
            [g.resident_id for g in self.exposure_receipts_by_resident],
            "exposure_receipts_by_resident",
        )
        piles = [(p.position.y, p.position.x) for p in self.ground_fruit]
        if any(a >= b for a, b in zip(piles, piles[1:], strict=False)):
            raise ValueError("ground_fruit must be sorted by (y,x), one pile per tile")
        pairs = [tuple(s.pair_ids) for s in self.dialogue_sessions]
        if any(a >= b for a, b in zip(pairs, pairs[1:], strict=False)):
            raise ValueError("dialogue_sessions must be sorted by pair_ids and unique")
        keys = [(a.intent.actor_id, a.intent.intent_id) for a in self.active_actions]
        if any(a >= b for a, b in zip(keys, keys[1:], strict=False)):
            raise ValueError("active_actions must be sorted by (actor_id,intent_id)")
        if len({k[0] for k in keys}) != len(keys):
            raise ValueError("at most one active action per actor")
        return self
