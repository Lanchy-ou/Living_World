"""Verify authored ScriptFixtures and expose only actor-local runtime inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from living_island.agents.types import ActorScript, ScriptFixture
from living_island.world.content import EffectiveConfig

from ._codec import PersistenceError, decode_model, digest, encode, read_bytes, verify_identity
from ._files import atomic_create

SCRIPT_FILENAME = "script.json"


@dataclass(frozen=True)
class LoadedScript:
    path: Path
    sha256: str
    _fixture: ScriptFixture

    def for_actor(self, actor_id: str) -> ActorScript:
        for actor in self._fixture.actors:
            if actor.actor_id == actor_id:
                return actor.model_copy(deep=True)
        raise PersistenceError(self.path, "actors", f"no script for {actor_id!r}")

    def retain(self, directory: Path) -> None:
        path = directory / SCRIPT_FILENAME
        raw = encode(self._fixture, path)
        verify_identity(path, "script_sha256", digest(raw), self.sha256)
        atomic_create(path, raw)


def load_script(
    path: Path, config: EffectiveConfig, *, expected_sha256: str | None = None
) -> LoadedScript:
    """Validate the authored JSON and hash its canonical parsed ScriptFixture."""
    fixture = decode_model(
        read_bytes(path),
        ScriptFixture,
        path,
        canonical=False,
        version_field="script_schema_version",
    )
    identity = digest(encode(fixture, path))
    if expected_sha256 is not None:
        verify_identity(path, "script_sha256", identity, expected_sha256)
    if {actor.actor_id for actor in fixture.actors} != {
        resident.id for resident in config.residents
    }:
        raise PersistenceError(
            path, "actors", "expected exactly one script per configured resident"
        )
    for index, actor in enumerate(fixture.actors):
        for plan_index, plan in enumerate(actor.plans):
            if len(plan) > config.agents.max_plan_actions:
                raise PersistenceError(
                    path, f"actors.{index}.plans.{plan_index}", "exceeds max_plan_actions"
                )
    return LoadedScript(path, identity, fixture)
