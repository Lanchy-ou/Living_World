"""Atomic SavePackage storage and pre-ingest checkpoint history checks."""

from __future__ import annotations

from pathlib import Path

from living_island.contract.save import SavePackage
from living_island.world.content import WorldContent, config_hash, map_hash

from ._codec import (
    PersistenceError,
    decode_model,
    encode,
    read_bytes,
    require_version,
    verify_identity,
)
from ._files import atomic_create


def _decode_checkpoint(path: Path, raw: bytes) -> SavePackage:
    save = decode_model(raw, SavePackage, path, version_field="save_schema_version")
    require_version(path, "world.schema_version", save.world.schema_version)
    _verify_history(path, save)
    return save


def _verify_history(path: Path, save: SavePackage) -> None:
    """Check the ingest cutoff and at most one committed decision per ingested tick."""
    deaths: dict[str, int] = {}
    for corpse in save.world.corpses:
        if corpse.resident_id in deaths:
            raise PersistenceError(
                path, "world.corpses", f"duplicate death for {corpse.resident_id}"
            )
        deaths[corpse.resident_id] = corpse.death_tick

    for resident, runtime in zip(
        save.world.residents, save.agent_state.runtime_states, strict=True
    ):
        actor = resident.id
        latest = runtime.latest_perception_tick
        if not resident.alive:
            death = deaths.get(actor)
            if death is None or not 1 <= death <= save.world.tick:
                raise PersistenceError(
                    path, "world.corpses.death_tick", f"invalid death for {actor}"
                )
            if latest != death - 1:
                raise PersistenceError(
                    path, "latest_perception_tick", f"{actor} must end at {death - 1} before death"
                )
        if runtime.next_decision_ordinal > latest + 1:
            raise PersistenceError(
                path,
                "next_decision_ordinal",
                f"{actor} has more decisions than ingested boundaries",
            )


def _verify_content(path: Path, save: SavePackage, content: WorldContent) -> None:
    verify_identity(
        path, "canonical_config_hash", save.canonical_config_hash, config_hash(content.config)
    )
    verify_identity(path, "canonical_map_hash", save.canonical_map_hash, map_hash(content.map_rows))
    config = content.config
    world = save.world
    for field, actual, expected in (
        ("world.run_id", world.run_id, config.meta.run_id),
        ("world.world_id", world.world_id, config.meta.world_id),
        ("world.static_map_ref", world.static_map_ref, config.map.layout_file),
    ):
        verify_identity(path, field, actual, expected)
    if {r.id for r in world.residents} != {r.id for r in config.residents}:
        raise PersistenceError(path, "world.residents", "must match the configured residents")
    for runtime in save.agent_state.runtime_states:
        policy = runtime.policy_config
        for field, actual_int, expected_int in (
            ("seed", policy.seed, config.meta.seed),
            ("max_plan_actions", policy.max_plan_actions, config.agents.max_plan_actions),
            ("map_width", policy.map_width, config.map.width),
            ("map_height", policy.map_height, config.map.height),
        ):
            if actual_int != expected_int:
                raise PersistenceError(
                    path, f"policy_config.{field}", f"{runtime.actor_id} must use {expected_int}"
                )


def read_checkpoint(path: Path, content: WorldContent) -> SavePackage:
    """Verify a checkpoint against independently validated retained run content."""
    save = _decode_checkpoint(path, read_bytes(path))
    _verify_content(path, save, content)
    return save


def write_checkpoint(path: Path, save: SavePackage) -> None:
    """Publish a new pre-ingest checkpoint without replacing an existing save."""
    raw = encode(save, path)
    _decode_checkpoint(path, raw)
    atomic_create(path, raw)
