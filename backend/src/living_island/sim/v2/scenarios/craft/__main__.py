"""Record or reopen the continuous starter crafting demonstration."""

import argparse
import subprocess
from pathlib import Path

from living_island.persistence.v2.journal import store_once
from living_island.sim.v2 import cli
from living_island.sim.v2.scenarios import runtime
from living_island.sim.v2.scenarios.receipts import CasePlan, file_digest
from living_island.world.v2.rules.schema import canonical_json_bytes, content_hash

from . import SEED, opening
from .index import Story
from .observer import Frame, observe
from .script import CraftScript

# The last of the six unclamped shelter sleep ticks on the declared itinerary.
FINAL_TICK = 126


def run(directory: Path) -> None:
    root = Path(__file__).parent
    world, config, island = opening()
    scenario = runtime.Scenario(world, config, island, runtime.scripted(CraftScript), observe)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=cli.ROOT, text=True
    ).strip()
    plan = CasePlan(
        revision=revision,
        runner=file_digest(Path(runtime.__file__)),
        controller=content_hash([file_digest(root / f) for f in ("script.py", "route.py")]),
        setup=file_digest(root / "__init__.py"),
        observer=file_digest(root / "observer.py"),
        arm="craft",
        case_index=0,
        horizon=FINAL_TICK,
        checkpoint_every=12,
    )
    progress = runtime.run_or_resume(directory, plan, lambda: scenario)
    evidence = progress.evidence
    assert evidence is not None
    story = Story(
        (Frame.model_validate(value) for value in evidence.observer.values()), world.pack.source
    )
    index = {
        "revision": revision,
        "seed": SEED,
        "run_id": world.run_id,
        "pack": world.pack.source.pack_hash,
        "tick_range": [0, evidence.final_tick],
        "receipt": "cases/0.json",
        "receipt_sha256": file_digest(directory / "cases/0.json"),
        "evidence": "evidence.json",
        "evidence_sha256": file_digest(directory / "evidence.json"),
        "packet_locator": "packets/{tick}.json (final pending delivery in the last checkpoint)",
        "story": story.craft(),
        "vine_comparison": story.binding("bind_snaps", "strong"),
        "benefits": story.benefits(),
    }
    path = directory / "index.json"
    store_once(path, canonical_json_bytes(index))
    print(f"{path} SHA-256 {file_digest(path)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    run(parser.parse_args().out)
