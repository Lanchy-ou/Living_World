"""Executable architectural checks for the pure P3 foundation and inert ports."""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from living_island.agents.p3 import ports

BACKEND = Path(__file__).resolve().parents[2]
SOURCE = BACKEND / "src" / "living_island"


def imports(path: Path) -> set[str]:
    result = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"Use auditable absolute imports: {path}"
            result.add(node.module or "")
    return result


@pytest.mark.parametrize("package", ["memory", "agents/p3"])
def test_pure_modules_never_import_world_internals_or_io(package):
    forbidden = (
        "living_island.sim",
        "living_island.persistence",
        "living_island.contract",
        "anthropic",
        "openai",
        "httpx",
        "requests",
        "socket",
        "urllib",
        "subprocess",
    )
    for path in (SOURCE / package).rglob("*.py"):
        for module in imports(path):
            assert not any(
                module == prefix or module.startswith(prefix + ".") for prefix in forbidden
            )
            if module.startswith("living_island.world"):
                assert module == "living_island.world.protocol" and path.name != "__init__.py"
            if package == "memory":
                assert not module.startswith("living_island.agents")


def test_import_linter_contracts_make_memory_ignore_strict_and_protect_analysis():
    data = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = data["tool"]["importlinter"]["contracts"]
    protocol = next(
        c for c in contracts if c["name"] == "memory sees world only via world.protocol"
    )
    assert protocol["unmatched_ignore_imports_alerting"] == "error"
    memory = next(c for c in contracts if c["name"].startswith("memory is pure:"))
    assert set(memory["forbidden_modules"]) >= {
        "living_island.agents",
        "living_island.sim",
        "living_island.persistence",
        "living_island.contract",
        "anthropic",
        "openai",
        "httpx",
        "requests",
    }
    analysis = next(c for c in contracts if c["source_modules"] == ["living_island.analysis"])
    assert {"living_island.agents.p3", "living_island.agents.llm"} <= set(
        analysis["forbidden_modules"]
    )


@pytest.mark.parametrize(
    "name",
    [
        "ProviderAdapter",
        "DecisionBudgetPort",
        "AttemptJournalPort",
        "FallbackAdapter",
        "ResidentRuntimeP3",
    ],
)
def test_ports_are_noninstantiable_protocols_with_no_runtime_bodies(name):
    protocol = getattr(ports, name)
    assert protocol._is_protocol
    with pytest.raises(TypeError):
        protocol()
    module = ast.parse(inspect.getsource(protocol))
    for method in (node for node in ast.walk(module) if isinstance(node, ast.FunctionDef)):
        assert len(method.body) == 1 and isinstance(method.body[0], ast.Expr)
        assert isinstance(method.body[0].value, ast.Constant)
        assert method.body[0].value.value is Ellipsis


def test_fresh_import_is_inert_and_does_not_load_later_runtime_or_network():
    script = """
import importlib
import sys
for name in (
    'living_island.memory.experience', 'living_island.memory.retrieval',
    'living_island.agents.p3.types', 'living_island.agents.p3.ports',
    'living_island.agents.p3.context', 'living_island.agents.p3.cognition',
    'living_island.agents.p3.prompts', 'living_island.persistence.characters',
):
    importlib.import_module(name)
for name in sys.modules:
    assert not any(name == prefix or name.startswith(prefix + '.') for prefix in (
        'living_island.sim', 'living_island.agents.runtime',
        'living_island.agents.rule_based', 'living_island.agents.llm',
        'anthropic', 'openai', 'httpx', 'requests',
    )), name
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
