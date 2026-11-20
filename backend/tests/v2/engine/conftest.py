"""Synthetic content and world setup for shared engine tests."""

from __future__ import annotations

import tomllib
from hashlib import sha256
from pathlib import Path
from shutil import copytree
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.world.v2.engine import World, WorldSetup
    from living_island.world.v2.rules import Pack

BACKEND = Path(__file__).resolve().parents[3]
ENGINE_TEST = BACKEND / "tests/fixtures/v2/packs/engine-test"


@pytest.fixture
def pack(tmp_path: Path) -> Pack:
    from living_island.world.v2.rules import load_pack, load_vocabulary

    fixture = tmp_path / "engine-test"
    copytree(ENGINE_TEST, fixture)
    extension = tmp_path / "engine_core"
    extension.mkdir()
    (extension / "pack.toml").write_text(
        """
pack_id = "engine_core"
pack_version = "0.1"
extends = "engine-test"
vocabulary_version = "vocab/0.1"
vocabulary_hash = "57554435492d6f3db83006a4510b292f8b0d1ebc70c3393663fd1a9ad94cf286"

[timing]
replace = true
invalid_attempt_ticks = 1
give_ticks = 3
pick_up_ticks = 1
drop_ticks = 1
wait_ticks = 1
inspect_ticks = 1

[timing.attempt_ticks]
build = 1
combine = 1
fill = 1
gather = 1
rest = 1
strike = 1

[limits]
max_entity_units_world = 32
max_entities_per_tile = 2
""",
        encoding="utf-8",
    )
    (extension / "instances.toml").write_text(
        """
[[instance]]
id = "inst_e"
archetype = "arch_e"
at = { tile = [2, 3] }
""",
        encoding="utf-8",
    )
    vocabulary = load_vocabulary(BACKEND.parent / "content/vocabulary/vocab-0.1.toml")
    return load_pack(extension, vocabulary)


@pytest.fixture
def setup() -> WorldSetup:
    from living_island.world.v2.engine import (
        ClockConfig,
        DialogueConfig,
        MapConfig,
        ResidentSetup,
        SensesConfig,
        WorldSetup,
    )
    from living_island.world.v2.protocol import Coord, Terrain

    raw = (ENGINE_TEST / "world.toml").read_bytes()
    fixture = tomllib.loads(raw.decode())
    name = fixture["map"]["layout_file"]
    layout = (ENGINE_TEST / name).read_bytes()
    terrain: dict[str, Terrain] = {
        "~": "sea",
        ",": "grass",
        ".": "beach",
        "C": "cave",
        "W": "woods",
    }
    return WorldSetup(
        world_id="engine_core",
        run_id="engine_core_test",
        seed=20261108,
        config_hash=sha256(raw).hexdigest(),
        map_hash=sha256(layout).hexdigest(),
        static_map_ref=name,
        pack_ids=("engine-test", "engine_core"),
        terrain=MapConfig(
            rows=tuple(
                tuple(terrain[char] for char in row) for row in layout.decode().splitlines()
            ),
            step_costs={"grass": 1, "beach": 1, "cave": 1, "woods": 2},
            walk_budget=2,
            opaque_terrains=frozenset({"woods"}),
        ),
        clock=ClockConfig(
            tick_minutes=10, start_minute=360, day_start_minute=360, day_end_minute=1200
        ),
        senses=SensesConfig(
            day_radius=4,
            night_radius=2,
            hearing_radius=2,
            cue_detail_radius=1,
            visible_weakness_below=1000,
            visible_dehydration_below=1000,
            visible_fatigue_below=1000,
        ),
        dialogue=DialogueConfig(max_turns=4, gap_ticks=2, cooldown_ticks=2),
        residents=tuple(
            ResidentSetup(id=row["id"], position=Coord(x=row["position"][0], y=row["position"][1]))
            for row in fixture["residents"]
        ),
    )


@pytest.fixture
def world(pack: Pack, setup: WorldSetup) -> World:
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.state import Exposure

    world = initialize(pack, setup)
    state = world.state
    # This fixture supplies already-exposed tiles and receipts at the perception seam.
    for actor in state.residents.values():
        actor_id = actor.id
        smap = state.static_map
        state.explored_tiles_by_resident[actor_id] = set(range(smap.width * len(smap.rows)))
        receipts = state.exposure_receipts_by_resident[actor_id]
        for target in state.residents.values():
            receipts.entities[target.id] = Exposure(target.id, target.position)
        for entity in state.entities.values():
            point = entity.place.position
            receipts.entities[entity.entity_id] = Exposure(
                entity.entity_id, point, entity.archetype_id
            )
            receipts.item_tiles.add((entity.archetype_id, point))
        state.visible_entities_by_resident[actor_id] = set(receipts.entities)
    return world
