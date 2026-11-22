"""Canonical, completed-boundary world snapshots."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from pydantic import BaseModel, TypeAdapter

from ..rules import Pack
from ..rules.schema import canonical_json_bytes
from .state import Library, WorldState
from .validate import EnginePack

if TYPE_CHECKING:
    from .tick import World


_STATE = TypeAdapter(WorldState)


def _set_order(value: object) -> tuple[int, int | bytes]:
    if type(value) is int:
        return (0, value)
    return (1, canonical_json_bytes(value))


def _snapshot_value(value: object) -> object:
    if is_dataclass(value):
        row = {entry.name: getattr(value, entry.name) for entry in fields(value)}
        if isinstance(value, Library):
            # Preserve validation order for additions that depend on an earlier rule.
            row["added_rules"] = tuple(value.added_rules.items())
        return {key: _snapshot_value(item) for key, item in row.items()}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", warnings="error")
    if isinstance(value, dict):
        return {
            ":".join(key) if isinstance(key, tuple) else key: _snapshot_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (set, frozenset)):
        return sorted(map(_snapshot_value, value), key=_set_order)
    if isinstance(value, (tuple, list)):
        return [_snapshot_value(item) for item in value]
    return value


def _encode_state(state: WorldState) -> bytes:
    return canonical_json_bytes(_snapshot_value(state))


def encode_snapshot(world: World) -> bytes:
    """Encode the entire committed world, including pending packet bytes."""
    return _encode_state(world.state)


def snapshot_hash(state: WorldState) -> str:
    return sha256(_encode_state(state)).hexdigest()


def restore_snapshot(data: bytes, pack: Pack, *, pack_ids: tuple[str, ...]) -> World:
    """Restore against the original pack and the additions carried by the snapshot."""
    from .tick import World, prepare_rules

    state = _STATE.validate_json(data, strict=True)
    library = state.library
    if library.vocabulary_hash != pack.vocabulary_hash:
        raise ValueError("snapshot vocabulary hash differs from loaded content")
    if (library.pack_ids, library.pack_hash) != (pack_ids, pack.pack_hash):
        raise ValueError("snapshot pack identity differs from loaded content")
    content, added = prepare_rules(
        EnginePack.from_pack(pack),
        [rule.data for rule in library.added_rules.values()],
        canonical=True,
    )
    if (library.rule_library_hash, library.active_rule_ids) != (
        content.source.rule_library_hash,
        tuple(content.source.rules),
    ):
        raise ValueError("snapshot rule library differs from loaded content and additions")
    library.added_rules = {rule.id: rule for rule in added}
    if _encode_state(state) != data:
        raise ValueError("expected canonical snapshot bytes")
    return World(state, content, ())
