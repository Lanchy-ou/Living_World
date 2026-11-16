"""P3 optional inspection retains frozen legacy contracts and metric definitions."""

from __future__ import annotations

import ast
import json
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from living_island.contract.p3_inspection import (
    DecisionInspection,
    P3InspectionIndex,
    ResidentInspection,
)
from living_island.contract.replay import ReplayBundle

ROOT = Path(__file__).resolve().parents[3]
BASELINE = "34df3deb2abbf816926de89a7e3187aa0ec587b4"
FIXTURES = ROOT / "backend/tests/fixtures/p3/evaluation"


def blob(path):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "show", f"{BASELINE}:{path}"], cwd=ROOT
    )


@pytest.mark.parametrize(
    "path",
    [
        "backend/src/living_island/analysis/metrics.py",
        "backend/src/living_island/analysis/data.py",
        "backend/src/living_island/analysis/compare.py",
        "backend/src/living_island/analysis/validity.py",
        "scripts/p2_experiments.py",
        "scripts/gen_types.py",
        "backend/src/living_island/contract/replay.py",
        "frontend/src/api/generated/replay.schema.json",
        "frontend/src/api/generated/replay.ts",
    ],
)
def test_frozen_p2_analysis_and_legacy_contract_bytes_unchanged(path):
    assert (ROOT / path).read_bytes() == blob(path)


def test_pure_analysis_has_no_forbidden_direct_imports():
    path = ROOT / "backend/src/living_island/analysis/p3.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = (
        "living_island.agents.p3",
        "living_island.memory",
        "living_island.persistence",
        "living_island.sim",
        "living_island.world",
    )
    imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(module.startswith(forbidden) for module in imported if module)


def test_committed_ui_fixture_membership_hashes_and_legacy_optional_import():
    manifest = json.loads((FIXTURES / "ui-manifest.json").read_bytes())
    for path, digest in manifest["files"].items():
        assert sha256((FIXTURES / path).read_bytes()).hexdigest() == digest
    replay = ReplayBundle.model_validate_json((FIXTURES / manifest["replay"]).read_bytes())
    index = P3InspectionIndex.model_validate_json((FIXTURES / "ui/index.json").read_bytes())
    assert index.run_id == replay.run_id
    assert index.replay_sha256 == sha256((FIXTURES / manifest["replay"]).read_bytes()).hexdigest()
    assert len(index.samples) == 3 * 5
    samples = [
        ResidentInspection.model_validate_json((FIXTURES / "ui" / r.shard.file).read_bytes())
        for r in index.samples
    ]
    decisions = [
        DecisionInspection.model_validate_json((FIXTURES / "ui" / r.shard.file).read_bytes())
        for r in index.decisions
    ]
    assert any(c.debit.usage_unknown for d in decisions for c in d.calls)
    assert any(
        s.actor_id == "ryan" and s.tick == 2 and s.latest_decision_id.endswith(":000000")
        for s in samples
    )
    ella = [d for d in decisions if d.record.actor_id == "ella"]
    assert ella[1].context.request.context.goals.current.status == "observed_complete"
    assert ella[1].record.accepted_delta.goal_change.operation == "revise"
    assert ella[2].record.accepted_delta.goal_change.operation == "abandon"
    assert any("<img" in json.dumps(d.model_dump(mode="json")) for d in decisions)
    assert not hasattr(replay, "inspection_schema_version")
