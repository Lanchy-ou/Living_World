import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_mm13_audit_is_unreachable_from_resident_readers(tmp_path):
    backend = Path(__file__).resolve().parents[3]
    package = tmp_path / "living_island"
    shutil.copytree(
        backend / "src/living_island", package, ignore=shutil.ignore_patterns("__pycache__")
    )
    env = {**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"}

    def lint():
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from importlinter.cli import lint_imports_command; lint_imports_command()",
                "--no-cache",
                "--config",
                str(backend / "pyproject.toml"),
                "--contract",
                "resident-audit-isolation",
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        return result.returncode, " ".join((result.stdout + result.stderr).split())

    status, report = lint()
    assert status == 0, report
    # Use a read-capable dependency so each probe exercises a transitive edge.
    helper = package / "audit_probe.py"
    helper.write_text(
        "from living_island.persistence.v2.audit import AuditReader\n", encoding="utf-8"
    )
    for module in (
        "agents.v2.context",
        "agents.v2.recall",
        "memory.v2",
        "sim.v2.harness.consolidation",
    ):
        probe = package.joinpath(*module.split("."), "probe.py")
        probe.write_text("from living_island.audit_probe import AuditReader\n", encoding="utf-8")
        status, report = lint()
        assert status == 1, report
        assert f"living_island.{module}.probe -> living_island.audit_probe" in report
        assert "living_island.audit_probe -> living_island.persistence.v2.audit" in report
        probe.write_text("", encoding="utf-8")
