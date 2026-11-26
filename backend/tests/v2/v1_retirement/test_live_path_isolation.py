"""EV-07: the current v2 entry points run without loading the retired v1 engine."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

import living_island

RETIRED = (
    "living_island.sim.cli",
    "living_island.sim.equivalence.v1_extract",
    "living_island.sim.p3",
    "living_island.sim.runner",
    "living_island.world.engine",
)

# The source packages of the import-linter contract for the live v2 path.
LIVE_PATH_SOURCES = (
    "agents/v2",
    "analysis/v2",
    "memory/v2",
    "persistence/v2",
    "sim/v2/cli.py",
    "sim/v2/compat",
    "sim/v2/harness",
)

_MARKER = "RETIRED_LOADED="


def _loaded_after(probe: str) -> str:
    # A fresh interpreter, so modules imported by other tests cannot mask a load.
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout
    (line,) = [x for x in out.splitlines() if x.startswith(_MARKER)]
    return line.removeprefix(_MARKER)


def _report() -> str:
    return f"print({_MARKER!r} + ','.join(m for m in {RETIRED!r} if m in sys.modules))\n"


@pytest.mark.parametrize(
    "entry",
    [
        "living_island.sim.v2.cli",
        "living_island.sim.v2.harness.live_resident",
        "living_island.sim.v2.harness.provider_check",
        "living_island.sim.v2.harness.replay",
    ],
)
def test_v2_entry_point_import_does_not_load_the_v1_engine(entry: str) -> None:
    probe = f"import importlib, sys\nimportlib.import_module({entry!r})\n" + _report()
    assert _loaded_after(probe) == ""


@pytest.mark.parametrize(
    "entry",
    [
        "living_island.sim.v2.cli",
        "living_island.sim.v2.harness.live_resident",
        "living_island.sim.v2.harness.provider_check",
    ],
)
def test_v2_launch_does_not_load_the_v1_engine(entry: str) -> None:
    # Runs the module's __main__ block as `python -m <entry> --help` would.
    probe = (
        "import runpy, sys\n"
        f"sys.argv = [{entry!r}, '--help']\n"
        "try:\n"
        f"    runpy.run_module({entry!r}, run_name='__main__', alter_sys=True)\n"
        "except SystemExit as stop:\n"
        "    assert stop.code in (0, None), stop.code\n"
    ) + _report()
    assert _loaded_after(probe) == ""


def test_live_v2_path_has_no_dynamic_imports() -> None:
    # import-linter sees every static import, including function bodies and
    # __main__ blocks. Dynamic imports would bypass it, so the live path has none.
    root = Path(living_island.__file__).parent
    dynamic = re.compile(r"\bimportlib\b|\b__import__\b|\brunpy\b")
    files = [
        f
        for src in LIVE_PATH_SOURCES
        for f in ([root / src] if src.endswith(".py") else sorted((root / src).rglob("*.py")))
    ]
    assert files
    offenders = [
        str(f.relative_to(root)) for f in files if dynamic.search(f.read_text(encoding="utf-8"))
    ]
    assert offenders == []
