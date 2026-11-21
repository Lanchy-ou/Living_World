"""Validated, task-local extensions of the shared engine-test fixture."""

from pathlib import Path

import pytest


@pytest.fixture
def process_world(tmp_path: Path, pack, setup):
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.items import tile_of
    from living_island.world.v2.engine.state import Exposure
    from living_island.world.v2.rules import load_pack

    def make(*, archetypes="", rules="", instances="", world_limit=100):
        extension = tmp_path / "process_test"
        extension.mkdir()
        (extension / "pack.toml").write_text(
            f"""
pack_id = "process_test"
pack_version = "0.1"
extends = "engine_core"
vocabulary_version = "vocab/0.1"
vocabulary_hash = "{pack.vocabulary.vocabulary_hash}"

[limits]
replace = true
max_entity_units_world = {world_limit}
max_entities_per_tile = 10
""",
            encoding="utf8",
        )
        for name, content in (
            ("archetypes", archetypes),
            ("rules", rules),
            ("instances", instances),
        ):
            (extension / f"{name}.toml").write_text(content, encoding="utf8")
        content = load_pack(extension, pack.vocabulary)
        world = initialize(
            content, setup.model_copy(update={"pack_ids": (*setup.pack_ids, content.pack_id)})
        )
        state = world.state
        for actor_id in state.residents:
            state.explored_tiles_by_resident[actor_id] = set(
                range(state.static_map.width * len(state.static_map.rows))
            )
            receipt = state.exposure_receipts_by_resident[actor_id]
            for entity in state.entities.values():
                receipt.entities[entity.entity_id] = Exposure(
                    entity.entity_id, tile_of(state, entity.place), entity.archetype_id
                )
            state.visible_entities_by_resident[actor_id] = set(receipt.entities)
        return world

    return make
