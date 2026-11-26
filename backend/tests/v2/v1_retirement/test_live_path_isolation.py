"""EV-07: the current v2 entry points run without loading the retired v1 engine."""

import subprocess
import sys

import pytest

RETIRED = (
    "living_island.sim.cli",
    "living_island.sim.equivalence.v1_extract",
    "living_island.sim.p3",
    "living_island.sim.runner",
    "living_island.world.engine",
)


@pytest.mark.parametrize(
    "entry",
    [
        "living_island.sim.v2.cli",
        "living_island.sim.v2.harness.live_resident",
        "living_island.sim.v2.harness.provider_check",
        "living_island.sim.v2.harness.replay",
    ],
)
def test_v2_entry_point_does_not_load_the_v1_engine(entry: str) -> None:
    # A fresh interpreter, so modules imported by other tests cannot mask a load.
    probe = (
        "import importlib, sys\n"
        f"importlib.import_module({entry!r})\n"
        f"print(','.join(m for m in {RETIRED!r} if m in sys.modules))\n"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert loaded == ""
