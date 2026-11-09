"""Explored footprints and exposure receipts: merging and authorization (World Rules §2).

Pure functions. Footprints hold static tile indices only; receipts hold exposed entity
references and the highest cue detail, never stock, needs or interpretations. Nothing here
mutates the objects passed in.
"""

from __future__ import annotations

from collections.abc import Iterable

from living_island.world.protocol import Coord, ItemType
from living_island.world.state import CueDetailReceipt, ExposureReceipts, ReceiptEntity


def merge_tile_indices(existing: Iterable[int], new: Iterable[int]) -> list[int]:
    """Union of two footprints as an ascending, duplicate-free list."""
    return sorted(set(existing) | set(new))


def merge_receipts(
    existing: ExposureReceipts,
    entities: Iterable[ReceiptEntity],
    cue_details: Iterable[CueDetailReceipt],
) -> ExposureReceipts:
    """A new receipt group with ``entities`` and ``cue_details`` merged in.

    Entities are unique ``(entity_id, entity_type, position)`` triples sorted by
    ``(entity_id, y, x)``; per cue the highest detail wins (``near`` beats ``distant``).
    """
    by_key: dict[tuple[str, int, int], ReceiptEntity] = {}
    for e in [*existing.entities, *entities]:
        by_key[(e.entity_id, e.position.y, e.position.x)] = e
    cue_level: dict[str, str] = {}
    for c in [*existing.cue_detail_seen, *cue_details]:
        if cue_level.get(c.cue_id) != "near":
            cue_level[c.cue_id] = c.detail_level
    return ExposureReceipts(
        resident_id=existing.resident_id,
        entities=[
            ReceiptEntity(
                entity_id=e.entity_id,
                entity_type=e.entity_type,
                position=Coord(x=e.position.x, y=e.position.y),
            )
            for _, e in sorted(by_key.items())
        ],
        cue_detail_seen=[
            CueDetailReceipt(cue_id=cue_id, detail_level="near" if level == "near" else "distant")
            for cue_id, level in sorted(cue_level.items())
        ],
    )


def receipt_authorizes_entity(receipts: ExposureReceipts, entity_id: str) -> bool:
    """An entity-ID target needs a current or past receipt for that ID (any position)."""
    return any(e.entity_id == entity_id for e in receipts.entities)


def receipt_authorizes_pickup(
    receipts: ExposureReceipts, item_type: ItemType, position: Coord
) -> bool:
    """``pick_up`` needs an item-type receipt at the target tile.

    ``fruit`` is authorized by a ``ground_fruit`` receipt and ``canteen`` by a ``canteen``
    receipt, each at exactly that position.
    """
    entity_type = "ground_fruit" if item_type == "fruit" else "canteen"
    return any(
        e.entity_type == entity_type and e.position.x == position.x and e.position.y == position.y
        for e in receipts.entities
    )
