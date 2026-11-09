"""Builders for P1-02 tests: default and tiny worlds, plus fresh ``WorldState`` objects."""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

from living_island.persistence.content import load_world_content
from living_island.world.content import (
    EffectiveConfig,
    WorldContent,
    build_world_content,
    map_bytes_from_rows,
)
from living_island.world.observation import register_content
from living_island.world.protocol import Coord
from living_island.world.space import StaticMap
from living_island.world.state import WorldState

WORLDS = Path(__file__).resolve().parents[3] / "content" / "worlds"


def default_content() -> WorldContent:
    content = load_world_content(WORLDS / "default.toml")
    register_content(content)
    return content


def static_map(rows: list[str]) -> StaticMap:
    """A bare ``StaticMap`` over arbitrary rows (default costs; no border/marker rules)."""
    base = default_content().config
    config: EffectiveConfig = base.model_copy(
        update={
            "map": base.map.model_copy(update={"width": len(rows[0]), "height": len(rows)}),
        }
    )
    return StaticMap(config, rows)


def tiny_content(
    rows: list[str],
    residents: dict[str, tuple[int, int]],
    **perception: int,
) -> WorldContent:
    """Validated content over custom ``rows`` (must satisfy the map grammar).

    Spring, cave, moss cue and fruit trees are derived from the ``S``, ``C``, ``M`` and ``F``
    symbols; ``residents`` lists the residents (subset of ella/ryan/mia) with positions.
    """
    with (WORLDS / "default.toml").open("rb") as f:
        data: dict[str, Any] = tomllib.load(f)
    data = copy.deepcopy(data)
    data["map"]["width"] = len(rows[0])
    data["map"]["height"] = len(rows)

    def find(symbol: str) -> list[list[int]]:
        return [[x, y] for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == symbol]

    data["world"]["spring"] = find("S")[0]
    data["world"]["initial_cave"] = find("C")[0]
    data["world"]["cues"][0]["position"] = find("M")[0]
    data["world"]["fruit_trees"] = [
        {"id": f"fruit_{i + 1:02d}", "position": pos, "regrow_phase_offset_ticks": 0}
        for i, pos in enumerate(find("F"))
    ]
    by_id = {r["id"]: r for r in data["residents"]}
    data["residents"] = [{**by_id[rid], "position": list(pos)} for rid, pos in residents.items()]
    data["canteen"]["initial_owner_id"] = next(iter(residents))
    data["perception"].update(perception)
    content = build_world_content(data, map_bytes_from_rows(rows))
    register_content(content)
    return content


def fresh_state(content: WorldContent) -> WorldState:
    """A tick-zero world state: initial needs, trees at initial stock, canteen with its owner."""
    cfg = content.config
    return WorldState.model_validate(
        {
            "schema_version": cfg.meta.schema_version,
            "world_id": cfg.meta.world_id,
            "run_id": cfg.meta.run_id,
            "tick": 0,
            "config_hash": content.config_hash,
            "map_hash": content.map_hash,
            "static_map_ref": cfg.map.layout_file,
            "residents": [
                {
                    "id": r.id,
                    "position": {"x": r.position[0], "y": r.position[1]},
                    "alive": True,
                    "satiety": cfg.needs.initial_satiety,
                    "hydration": cfg.needs.initial_hydration,
                    "stamina": cfg.needs.initial_stamina,
                    "health": cfg.needs.initial_health,
                    "fruit_count": 0,
                }
                for r in sorted(cfg.residents, key=lambda r: r.id)
            ],
            "fruit_nodes": [
                {
                    "id": t.id,
                    "position": {"x": t.position[0], "y": t.position[1]},
                    "stock": cfg.fruit.initial_stock_per_tree,
                    "regrow_phase_offset_ticks": t.regrow_phase_offset_ticks,
                }
                for t in sorted(cfg.world.fruit_trees, key=lambda t: t.id)
            ],
            "cave": {"x": cfg.world.initial_cave[0], "y": cfg.world.initial_cave[1]},
            "spring": {"x": cfg.world.spring[0], "y": cfg.world.spring[1]},
            "cues": [
                {
                    "id": c.id,
                    "kind": c.kind,
                    "position": {"x": c.position[0], "y": c.position[1]},
                }
                for c in sorted(cfg.world.cues, key=lambda c: c.id)
            ],
            "ground_fruit": [],
            "lifetime_fruit_regrown": 0,
            "lifetime_fruit_consumed": 0,
            "unique_canteen": {
                "id": cfg.canteen.unique_item_id,
                "holder_id": cfg.canteen.initial_owner_id,
                "ground_position": None,
                "servings": cfg.canteen.initial_servings,
            },
            "corpses": [],
            "dialogue_sessions": [],
            "active_actions": [],
            "explored_tiles_by_resident": [
                {"resident_id": r.id, "tile_indices": []}
                for r in sorted(cfg.residents, key=lambda r: r.id)
            ],
            "exposure_receipts_by_resident": [
                {"resident_id": r.id, "entities": [], "cue_detail_seen": []}
                for r in sorted(cfg.residents, key=lambda r: r.id)
            ],
            "resolution_rng_state_uint32": cfg.meta.seed,
            "next_event_seq_in_tick": 0,
            "event_log_cursor": 0,
            "rule_overrides": {},
        }
    )


def place(state: WorldState, resident_id: str, x: int, y: int) -> None:
    for r in state.residents:
        if r.id == resident_id:
            r.position = Coord(x=x, y=y)
            return
    raise KeyError(resident_id)


def resident(state: WorldState, resident_id: str) -> Any:
    return next(r for r in state.residents if r.id == resident_id)
