"""Target keys, back-off table and local-entry limits (Rule Policy §2, §5, §7.1)."""

from __future__ import annotations

from living_island.agents.types import SelfTarget, TargetKey
from living_island.world.protocol import (
    Coord,
    EntityTarget,
    ResidentTarget,
    TileTarget,
)

# A target key is (kind rank, y, x, id); tuple order is the canonical order of §2:
# self < tile (y, x) < entity (id) < resident (id).
Key = tuple[int, int, int, str]

SELF: Key = (0, 0, 0, "")

LOCAL_CODES = frozenset({"OBSERVED_EMPTY", "REFUSED", "REQUESTED"})
LOCAL_ENTRY_LIMIT = 64

# Rule Policy §5 table: action -> failure code -> back-off key source.
# "target" is the reference's own target; "self" is the policy-local self key.
BACKOFF: dict[str, dict[str, str]] = {
    "move_to": {"INVALID_TARGET": "target", "PATH_BLOCKED": "target", "NO_PATH": "target"},
    "gather": {
        "OUT_OF_REACH": "target",
        "RESOURCE_TAKEN": "target",
        "INVALID_TARGET": "target",
        "INVENTORY_FULL": "self",
    },
    "pick_up": {
        "ITEM_TAKEN": "target",
        "OUT_OF_REACH": "target",
        "INVALID_TARGET": "target",
        "INVENTORY_FULL": "self",
    },
    "give": {"OUT_OF_REACH": "target", "INVENTORY_FULL": "target", "INVALID_TARGET": "target"},
    "talk": {
        "INVALID_TARGET": "target",
        "OUT_OF_HEARING": "target",
        "INVALID_SPEECH_ACT": "target",
        "INVALID_REPLY": "target",
        "DIALOGUE_LIMIT": "target",
    },
    "fill_canteen": {"NO_ITEM": "target", "OUT_OF_REACH": "target", "INVALID_TARGET": "target"},
}


def tile_key(x: int, y: int) -> Key:
    return (1, y, x, "")


def entity_key(entity_id: str) -> Key:
    return (2, 0, 0, entity_id)


def resident_key(resident_id: str) -> Key:
    return (3, 0, 0, resident_id)


def key_of_target(target: TargetKey | None) -> Key | None:
    match target:
        case None:
            return None
        case SelfTarget():
            return SELF
        case TileTarget(position=position):
            return tile_key(position.x, position.y)
        case EntityTarget(id=entity_id):
            return entity_key(entity_id)
        case ResidentTarget(id=resident_id):
            return resident_key(resident_id)
    raise ValueError("unknown target key")


def target_of_key(key: Key) -> TargetKey:
    rank, y, x, ident = key
    if rank == 0:
        return SelfTarget(kind="self")
    if rank == 1:
        return TileTarget(kind="tile", position=Coord(x=x, y=y))
    if rank == 2:
        return EntityTarget(kind="entity", id=ident)
    return ResidentTarget(kind="resident", id=ident)
