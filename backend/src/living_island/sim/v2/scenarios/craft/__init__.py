"""One registered island and three packet-driven residents for CT-05/06/16."""

from living_island.sim.v2 import cli
from living_island.sim.v2.scenarios.starter import load_starter_pack
from living_island.world.v2.engine import ResidentSetup, World, initialize
from living_island.world.v2.protocol import Coord
from living_island.world.v2.rules import load_vocabulary

from .route import START

SEED = 201486072


def opening() -> tuple[World, str, str]:
    story = load_starter_pack(
        cli.ROOT / "content/worlds/default.toml",
        cli.PACK.with_name("starter-v1"),
        load_vocabulary(cli.VOCABULARY),
        map_path=cli.ROOT / "content/worlds/default-island.map",
        seed=SEED,
    )
    residents = tuple(
        ResidentSetup(id=actor, position=Coord(x=x, y=y)) for actor, (x, y) in START.items()
    )
    setup = story.setup.model_copy(update={"residents": residents, "run_id": f"craft-{SEED}"})
    return (
        initialize(story.pack, setup),
        story.manifest.config_blob_sha256,
        story.manifest.map_blob_sha256,
    )
