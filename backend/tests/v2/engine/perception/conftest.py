"""Build small validated maps and content extensions for packet tests."""

import pytest


@pytest.fixture
def make_world(pack, setup, tmp_path):
    from living_island.world.v2.engine import (
        ClockConfig,
        CueSetup,
        MapConfig,
        ResidentSetup,
        SensesConfig,
        initialize,
    )
    from living_island.world.v2.protocol import Coord
    from living_island.world.v2.rules import load_pack

    def make(
        residents,
        *,
        opaque=(),
        radius=4,
        night=None,
        start=360,
        seed=1,
        cues=(),
        settings="",
        rules="",
        instances="",
        archetypes="",
    ):
        extension = tmp_path / f"perception_test_{len(list(tmp_path.glob('perception_test_*')))}"
        extension.mkdir()
        (extension / "pack.toml").write_text(
            f'''
pack_id = "perception_test"
pack_version = "0.1"
extends = "engine_core"
vocabulary_version = "vocab/0.1"
vocabulary_hash = "{pack.vocabulary.vocabulary_hash}"
{settings}
''',
            encoding="utf-8",
        )
        for name, data in (("rules", rules), ("instances", instances), ("archetypes", archetypes)):
            (extension / f"{name}.toml").write_text(data, encoding="utf-8")
        if 'enabled_verbs = ["sleep"]' in settings:
            (extension / "unmatched.toml").write_text(
                '[unmatched.sleep]\nentries = []\ndefault = ["nothing_happens"]\n',
                encoding="utf-8",
            )
        loaded = load_pack(extension, pack.vocabulary)
        return initialize(
            loaded,
            setup.model_copy(
                update={
                    "pack_ids": (*setup.pack_ids, loaded.pack_id),
                    "seed": seed,
                    "terrain": MapConfig(
                        rows=tuple(
                            tuple("woods" if (x, y) in opaque else "grass" for x in range(9))
                            for y in range(6)
                        ),
                        step_costs={"grass": 1, "woods": 2},
                        walk_budget=2,
                        opaque_terrains=frozenset({"woods"}),
                    ),
                    "residents": tuple(
                        ResidentSetup(id=key, position=Coord(x=x, y=y)) for key, x, y in residents
                    ),
                    "clock": ClockConfig(
                        tick_minutes=10,
                        start_minute=start,
                        day_start_minute=360,
                        day_end_minute=1200,
                    ),
                    "senses": SensesConfig(
                        day_radius=radius,
                        night_radius=radius if night is None else night,
                        hearing_radius=2,
                        cue_detail_radius=1,
                        visible_weakness_below=2,
                        visible_dehydration_below=2,
                        visible_fatigue_below=2000,
                    ),
                    "cues": tuple(
                        CueSetup(
                            id=key,
                            kind="landmark",
                            position=Coord(x=x, y=y),
                            visible_description="A sound",
                            near_description="Water",
                            direction="east",
                        )
                        for key, x, y in cues
                    ),
                }
            ),
        )

    return make
