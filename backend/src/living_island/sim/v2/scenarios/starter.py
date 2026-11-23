"""Compose starter content with its registered v1 base and initial island setup."""

from dataclasses import dataclass
from pathlib import Path

from living_island.sim.v2.cli import build_world_setup
from living_island.sim.v2.compat import CompatManifest, load_compat_pack
from living_island.world.content import EffectiveConfig
from living_island.world.v2.engine import WorldSetup
from living_island.world.v2.rules import Pack, Vocabulary, load_pack


@dataclass(frozen=True)
class StarterScenario:
    pack: Pack
    setup: WorldSetup
    manifest: CompatManifest


def load_starter_pack(
    config_path: Path,
    directory: Path,
    vocabulary: Vocabulary,
    *,
    map_path: Path | None = None,
    seed: int | None = None,
) -> StarterScenario:
    """Bind the base once to admitted bytes, then validate the overlay on those values."""
    base = load_compat_pack(
        config_path, directory.parent / "compat-v1", vocabulary, map_path=map_path, seed=seed
    )
    pack = load_pack(directory, vocabulary, bindings=base.bindings)
    config = EffectiveConfig.model_validate(base.config)
    setup = build_world_setup(base, config, pack_ids=pack.pack_ids)
    return StarterScenario(pack, setup, base.manifest)
