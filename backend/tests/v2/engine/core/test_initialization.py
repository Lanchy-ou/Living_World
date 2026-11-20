"""World setup validation and canonical snapshot hashing."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.world.v2.engine import WorldSetup
    from living_island.world.v2.rules import Pack


@pytest.mark.usefixtures("pack")
def test_initial_snapshot_hash_is_independent_of_python_hash_seed(
    setup: WorldSetup, tmp_path: Path
) -> None:
    script = dedent("""
        import sys
        from pathlib import Path

        from living_island.world.v2.engine import WorldSetup, initialize, perception
        from living_island.world.v2.rules import load_pack, load_vocabulary

        def record_sight(ctx):
            ids = {f"test_entity_{index}" for index in range(24)}
            state = ctx.state
            for resident in state.residents.values():
                state.visible_entities_by_resident[resident.id].update(ids)
                state.exposure_receipts_by_resident[resident.id].item_tiles.update(
                    (key, resident.position) for key in ids
                )
            for _ in ids:
                state.entity_counter.allocate(state.seed)

        perception.build_deliveries = record_sight
        setup = WorldSetup.model_validate_json(sys.stdin.read())
        pack = load_pack(Path(sys.argv[1]), load_vocabulary(Path(sys.argv[2])))
        initialized, *_ = initialize(pack, setup).initial_events
        print(initialized.payload["initial_snapshot_hash"])
        """)
    vocabulary = Path(__file__).resolve().parents[5] / "content/vocabulary/vocab-0.1.toml"
    hashes = [
        subprocess.check_output(
            [sys.executable, "-c", script, str(tmp_path / "engine_core"), str(vocabulary)],
            input=setup.model_dump_json(),
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).strip()
        for seed in ("1", "2")
    ]
    assert re.fullmatch(r"[0-9a-f]{64}", hashes[0])
    assert hashes[0] == hashes[1]


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("resident_collision", "placement 'res_a' collides with a resident ID"),
        ("placement_terrain", "placement 'inst_a' is not on a passable tile"),
        ("unknown_holder", "placement 'inst_a' has no such holder"),
        ("unknown_owner", "placement 'inst_d' has no such owner"),
        ("nonportable", "nonportable placement 'inst_b' has a holder"),
        ("reject_contents", "container rejects placement 'inst_d'"),
        ("misdeclared_contents", "declared contents disagree with placement of 'inst_c'"),
        ("full_container", "container 'inst_c' starts over capacity"),
        ("full_inventory", "resident 'res_a' starts over capacity"),
        ("missing_timing", "lacks engine setting invalid_attempt_ticks"),
        ("missing_world_limit", "lacks engine setting max_entity_units_world"),
        ("missing_tile_limit", "lacks engine setting max_entities_per_tile"),
        ("missing_slots", "lacks engine setting inventory_slots"),
        ("duplicate_pack", "duplicate pack ID"),
        ("duplicate_resident", "duplicate resident ID"),
        ("resident_impassable", "resident 'res_a' must start on a passable tile"),
        ("resident_outside_map", "resident 'res_a' must start on a passable tile"),
        ("duplicate_cue", "cues must have unique IDs and in-map positions"),
        ("cue_outside_map", "cues must have unique IDs and in-map positions"),
        ("clock_tick_length", "tick length must divide a day"),
        ("clock_daylight_order", "daylight must have increasing bounds"),
        ("clock_minute_range", "Input should be less than 1440"),
    ],
)
def test_initialization_refusals(
    case: str, message: str, pack: Pack, setup: WorldSetup, tmp_path: Path
) -> None:
    from living_island.world.v2.engine import WorldSetup, initialize
    from living_island.world.v2.rules import load_pack

    base = tmp_path / "engine-test"
    extension = tmp_path / "engine_core"
    instances = base / "instances.toml"
    manifest = extension / "pack.toml"
    setup_data = setup.model_dump()
    match case:
        case "resident_collision":
            edit(instances, 'id = "inst_a"', 'id = "res_a"')
        case "placement_terrain":
            edit(instances, "tile = [2, 1]", "tile = [0, 0]")
        case "unknown_holder":
            edit(instances, "tile = [2, 1]", 'holder = "unknown"')
        case "unknown_owner":
            edit(
                instances, "at = { tile = [1, 2] }", 'at = { tile = [1, 2] }\nowner_id = "unknown"'
            )
        case "nonportable":
            edit(instances, "tile = [3, 2]", 'holder = "res_a"')
        case "reject_contents":
            edit(instances, "tile = [1, 2]", 'holder = "inst_c"')
        case "misdeclared_contents":
            edit(
                instances, "at = { tile = [2, 2] }", 'at = { tile = [2, 2] }\ncontents = ["inst_a"]'
            )
        case "full_container" | "full_inventory":
            holder = "inst_c" if case == "full_container" else "res_a"
            edit(instances, "tile = [2, 1]", f'holder = "{holder}"')
            edit(instances, "quantity = 2", "quantity = 7")
        case "missing_timing":
            edit(manifest, "invalid_attempt_ticks = 1\n", "")
        case "missing_world_limit":
            edit(manifest, "max_entity_units_world = 32\n", "")
        case "missing_tile_limit":
            edit(manifest, "max_entities_per_tile = 2\n", "")
        case "missing_slots":
            edit(base / "pack.toml", "inventory_slots = 6\n", "")
        case "duplicate_pack":
            setup_data["pack_ids"] = ("engine-test", "engine-test", "engine_core")
        case "duplicate_resident":
            first, _ = setup_data["residents"]
            setup_data["residents"] = (first, first)
        case "resident_impassable":
            setup_data["residents"][0]["position"] = {"x": 0, "y": 0}
        case "resident_outside_map":
            setup_data["residents"][0]["position"] = {"x": -1, "y": 1}
        case "duplicate_cue" | "cue_outside_map":
            cue = {
                "id": "test_cue",
                "kind": "damp_moss",
                "position": {"x": 1, "y": 1},
                "visible_description": "Damp patch",
                "near_description": "Damp ground",
            }
            if case == "duplicate_cue":
                setup_data["cues"] = (cue, cue)
            else:
                setup_data["cues"] = ({**cue, "position": {"x": 100, "y": 1}},)
        case "clock_tick_length":
            setup_data["clock"]["tick_minutes"] = 7
        case "clock_daylight_order":
            setup_data["clock"]["day_start_minute"] = setup_data["clock"]["day_end_minute"]
        case "clock_minute_range":
            setup_data["clock"]["start_minute"] = 1440
        case _:
            raise AssertionError(f"missing setup for {case}")

    # Keep pack loading outside the assertion so each case reaches the engine boundary.
    candidate = load_pack(extension, pack.vocabulary)
    with pytest.raises(ValueError, match=re.escape(message)):
        initialize(candidate, WorldSetup.model_validate(setup_data))


def edit(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    assert source.count(old) == 1
    path.write_text(source.replace(old, new), encoding="utf-8")
