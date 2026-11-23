"""Compose starter content with its registered v1 base and initial island setup."""

from dataclasses import dataclass
from pathlib import Path

from living_island.sim.v2.compat import BoundCompatPack, CompatManifest, load_compat_pack
from living_island.world.protocol import TERRAIN_BY_SYMBOL
from living_island.world.space import OPAQUE_SYMBOLS
from living_island.world.v2.engine import (
    ClockConfig,
    CueSetup,
    DialogueConfig,
    MapConfig,
    ResidentSetup,
    SensesConfig,
    WorldSetup,
)
from living_island.world.v2.protocol import Coord
from living_island.world.v2.rules import Pack, Vocabulary, load_pack


@dataclass(frozen=True)
class StarterScenario:
    pack: Pack
    setup: WorldSetup
    manifest: CompatManifest


def _setup(base: BoundCompatPack, pack: Pack) -> WorldSetup:
    config = base.config
    layout = config["map"]
    clock = config["time"]
    senses = config["perception"]
    social = config["social"]
    return WorldSetup(
        world_id=config["meta"]["world_id"],
        run_id=config["meta"]["run_id"],
        seed=base.manifest.seed,
        config_hash=base.manifest.effective_config_sha256,
        map_hash=base.manifest.map_sha256,
        static_map_ref=layout["layout_file"],
        pack_ids=pack.pack_ids,
        terrain=MapConfig(
            rows=tuple(tuple(TERRAIN_BY_SYMBOL[c] for c in row) for row in base.map_rows),
            step_costs={
                terrain: layout[f"step_cost_{terrain}"]
                for terrain in TERRAIN_BY_SYMBOL.values()
                if f"step_cost_{terrain}" in layout
            },
            walk_budget=layout["walk_cost_budget_per_tick"],
            opaque_terrains=frozenset(TERRAIN_BY_SYMBOL[c] for c in OPAQUE_SYMBOLS),
        ),
        clock=ClockConfig(
            tick_minutes=clock["tick_minutes"],
            start_minute=60 * clock["start_hour"],
            day_start_minute=60 * clock["day_start_hour"],
            day_end_minute=60 * clock["day_end_hour"],
        ),
        senses=SensesConfig(
            day_radius=senses["day_radius_tiles"],
            night_radius=senses["night_radius_tiles"],
            hearing_radius=senses["hearing_radius_tiles"],
            cue_detail_radius=senses["cue_detail_radius_tiles"],
            visible_weakness_below=senses["visible_weakness_health_below"],
            visible_dehydration_below=senses["visible_dehydration_hydration_below"],
            visible_fatigue_below=senses["visible_fatigue_stamina_below"],
        ),
        dialogue=DialogueConfig(
            max_turns=social["max_dialogue_turns"],
            gap_ticks=social["dialogue_gap_ticks"],
            cooldown_ticks=social["dialogue_cooldown_ticks"],
        ),
        residents=tuple(
            ResidentSetup(id=r["id"], position=Coord(x=r["position"][0], y=r["position"][1]))
            for r in config["residents"]
        ),
        cues=tuple(
            CueSetup(**{**cue, "position": Coord(x=cue["position"][0], y=cue["position"][1])})
            for cue in config["world"]["cues"]
        ),
    )


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
    return StarterScenario(pack, _setup(base, pack), base.manifest)
