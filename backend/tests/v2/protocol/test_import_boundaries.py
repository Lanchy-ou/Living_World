"""Exercise the actual import-linter configuration in an isolated source tree."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_protocol_import_boundaries(tmp_path):
    backend = Path(__file__).resolve().parents[3]
    package = tmp_path / "living_island"
    shutil.copytree(
        backend / "src" / "living_island", package, ignore=shutil.ignore_patterns("__pycache__")
    )
    env = {**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"}

    def lint():
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "from importlinter.cli import lint_imports_command; lint_imports_command()",
                "--no-cache",
                "--config",
                str(backend / "pyproject.toml"),
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )

    agent_probe = package / "agents" / "wap_import_probe.py"
    memory_probe = package / "memory" / "wap_import_probe.py"
    permitted = "from living_island.world.v2.protocol import TurnSubmission\n"
    agent_probe.write_text(permitted, encoding="utf-8")
    memory_probe.write_text(permitted, encoding="utf-8")
    passed = lint()
    assert passed.returncode == 0, passed.stdout + passed.stderr

    world_v2 = package / "world" / "v2"
    internal = world_v2 / "wap_internal.py"
    internal.write_text(
        "from living_island.world.content import canonical_json_bytes\n", encoding="utf-8"
    )
    v1_import = lint()
    assert v1_import.returncode == 1, v1_import.stdout + v1_import.stderr
    output = " ".join(v1_import.stdout.split())
    assert "world.v2 does not import v1 world modules BROKEN" in output
    assert "living_island.world.v2.wap_internal -> living_island.world.content" in output

    # Use a new v2 internal module to prove the contract protects future modules too.
    internal.write_text("VALUE = 1\n", encoding="utf-8")
    agent_probe.write_text(
        "from living_island.world.v2.wap_internal import VALUE\n", encoding="utf-8"
    )
    with (world_v2 / "protocol.py").open("a", encoding="utf-8") as protocol_file:
        protocol_file.write("\nfrom living_island.world.v2.wap_internal import VALUE\n")

    failed = lint()
    assert failed.returncode == 1, failed.stdout + failed.stderr
    output = " ".join(failed.stdout.split())
    assert "living_island.agents.wap_import_probe -> living_island.world.v2.wap_internal" in output
    assert "living_island.world.v2.protocol -> living_island.world.v2.wap_internal" in output
    internal.write_text("from living_island.analysis import canon\n", encoding="utf-8")
    impure = lint()
    assert impure.returncode == 1, impure.stdout + impure.stderr
    assert "world.v2 imports no other living_island subpackage BROKEN" in impure.stdout
