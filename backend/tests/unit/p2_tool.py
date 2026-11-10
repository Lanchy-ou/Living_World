"""Load ``scripts/p2_experiments.py`` as a module and build throwaway git repos for its tests."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "p2_experiments.py"
SCRIPT_FIXTURE = "backend/tests/fixtures/p2/p1-scripted.script.json"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("p2_experiments", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["p2_experiments"] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return done.stdout.decode().strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


_TEMPLATE: tuple[Path, str] | None = None


def make_repo(root: Path) -> tuple[Path, str]:
    """A throwaway repo with the default world, a script fixture and an S1-style fixture.

    The repo is built once per process and copied for every call (a git init per test is slow).
    """
    global _TEMPLATE
    if _TEMPLATE is None:
        template, commit = _build_repo(Path(tempfile.mkdtemp(prefix="p2tool-")))
        _TEMPLATE = (template, commit)
    template, commit = _TEMPLATE
    repo = root / "repo"
    shutil.copytree(template, repo)
    return repo, commit


def _build_repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    (repo / "content" / "worlds").mkdir(parents=True)
    (repo / "content" / "scenarios" / "s1-spring-visible").mkdir(parents=True)
    (repo / "backend" / "tests" / "fixtures" / "p2").mkdir(parents=True)
    for name in ("default.toml", "default-island.map"):
        shutil.copy(REPO / "content" / "worlds" / name, repo / "content" / "worlds" / name)
    text = (REPO / "content" / "worlds" / "default.toml").read_text(encoding="utf-8")
    fixture = text.replace(
        'layout_file = "default-island.map"', 'layout_file = "../../worlds/default-island.map"'
    )
    assert fixture != text
    (repo / "content" / "scenarios" / "s1-spring-visible" / "orig.toml").write_text(
        fixture, encoding="utf-8", newline="\n"
    )
    shutil.copy(REPO / SCRIPT_FIXTURE, repo / SCRIPT_FIXTURE)
    (repo / ".gitignore").write_text("runs/\n", encoding="utf-8")
    git(repo, "init", "-q")
    return repo, commit_all(repo, "initial content")


def registry_for(pin: str) -> dict[tuple[str, str], object]:
    """S2 ``orig`` pinned at ``pin``, plus the S1 fixture (its only commit)."""
    Revision = tool.Revision  # noqa: N806
    return {
        ("s2-default", "orig"): Revision("s2-default", "orig", "content/worlds/default.toml", pin),
        ("s1-spring-visible", "orig"): Revision(
            "s1-spring-visible", "orig", "content/scenarios/s1-spring-visible/orig.toml", None
        ),
    }


def inprocess(args: Sequence[str], repo: Path) -> object:
    """Run the simulation CLI in this process from ``repo`` (a ``Runner`` for fast tests)."""
    from living_island.sim.cli import main

    previous = os.getcwd()
    os.chdir(repo)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            code = main(list(args))
    finally:
        os.chdir(previous)
    return tool.CliResult(code, sink.getvalue())
