"""P3 optional inspection retains frozen legacy contracts and metric definitions."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
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
sys.path.insert(0, str(ROOT))
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


def test_edge_fixture_dead_cursors_and_zero_call_decisions():
    manifest = json.loads((FIXTURES / "ui-edge-manifest.json").read_bytes())
    for path, digest in manifest["files"].items():
        assert sha256((FIXTURES / path).read_bytes()).hexdigest() == digest
    replay = ReplayBundle.model_validate_json((FIXTURES / manifest["replay"]).read_bytes())
    index = P3InspectionIndex.model_validate_json((FIXTURES / "ui-edge/index.json").read_bytes())
    assert len(index.samples) == 15 and len(index.decisions) == 3
    assert not any(resident.alive for resident in replay.frames[-1].residents)
    for ref in index.decisions:
        decision = DecisionInspection.model_validate_json(
            (FIXTURES / "ui-edge" / ref.shard.file).read_bytes()
        )
        assert decision.record.policy_id == decision.record.effective_policy_id == "rule-based-v0"
        assert decision.calls == decision.dispatches == decision.record.call_ids == []
    for ref in index.samples:
        sample = ResidentInspection.model_validate_json(
            (FIXTURES / "ui-edge" / ref.shard.file).read_bytes()
        )
        if ref.tick > 1:
            assert sample.latest_perception_tick == 0
            assert sample.latest_decision_id.endswith(":000000")


@pytest.mark.parametrize("name", ["ui", "ui-edge"])
def test_source_archive_reproduces_committed_inspection(tmp_path, name):
    import tarfile

    from living_island.persistence.p3_inspection import export_inspection, verify_inspection_source

    manifest = json.loads((FIXTURES / f"{name}-manifest.json").read_bytes())
    archive = FIXTURES / f"{name}-source.tar.gz"
    assert sha256(archive.read_bytes()).hexdigest() == manifest["source_archive_sha256"]
    source = tmp_path / "source"
    source.mkdir()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            assert member.isfile() and Path(member.name).name == member.name
            stream = tar.extractfile(member)
            assert stream is not None
            (source / member.name).write_bytes(stream.read())
    verified = verify_inspection_source(source, source / "replay.json", repository=ROOT)
    output = tmp_path / "inspection"
    export_inspection(verified, output)
    for path in output.iterdir():
        assert path.read_bytes() == (FIXTURES / name / path.name).read_bytes()


@pytest.mark.parametrize("name, deaths", [("ui", 0), ("ui-edge", 3)])
def test_physical_adapter_uses_frozen_metrics_and_objective_events(name, deaths):
    import tarfile
    from dataclasses import replace

    from living_island.analysis.data import RunLimits
    from living_island.analysis.p3 import physical_metrics

    index = P3InspectionIndex.model_validate_json((FIXTURES / name / "index.json").read_bytes())
    replay = ReplayBundle.model_validate_json((FIXTURES / name / "replay.json").read_bytes())
    records = [
        DecisionInspection.model_validate_json(
            (FIXTURES / name / ref.shard.file).read_bytes()
        ).record
        for ref in index.decisions
    ]
    with tarfile.open(FIXTURES / f"{name}-source.tar.gz", "r:gz") as tar:
        stream = tar.extractfile("config.json")
        assert stream is not None
        config = json.loads(stream.read())
    limits = RunLimits(
        min_value=config["needs"]["min_value"],
        hydration_gain_per_serving=config["needs"]["hydration_gain_per_serving"],
        canteen_capacity=config["canteen"]["capacity_servings"],
        max_stock_per_tree=config["fruit"]["max_stock_per_tree"],
        slot_capacity=config["inventory"]["slot_capacity"],
        tick_minutes=config["time"]["tick_minutes"],
    )
    result = physical_metrics(replay, records, limits)
    assert result["scalars"]["deaths"] == deaths
    assert result["scalars"]["given_count"] == sum(e.type == "item_given" for e in replay.events)
    assert (
        "a1" in result["metrics"]
        and "repeats" in result["metrics"]
        and "unresolved" in result["metrics"]
    )
    with pytest.raises(ValueError, match="physical invariants"):
        physical_metrics(replay, records, replace(limits, max_stock_per_tree=-1))


def test_actual_short_legacy_control_loader_and_recorded_proof(tmp_path):
    from scripts.p3_experiments import _control
    from scripts.p3_trials import CaseReceipt, git

    from living_island.contract.p3_inspection import BudgetCaps
    from living_island.contract.p3_save import ControlCase
    from living_island.persistence.checkpoints import read_checkpoint
    from living_island.persistence.trace import load_trace
    from living_island.sim.cli import main

    source = tmp_path / "short-control"
    assert (
        main(
            [
                "run",
                "--config",
                str(ROOT / "content/worlds/default.toml"),
                "--ticks",
                "4",
                "--policy",
                "rule-based",
                "--out",
                str(source),
                "--export-replay",
            ]
        )
        == 0
    )
    content = load_trace(source).content
    checkpoint = read_checkpoint(source / "checkpoint-0000000000.json", content)
    policy = checkpoint.agent_state.runtime_states[0].policy_config
    case = ControlCase(
        case_id=f"short.control.s{policy.seed}",
        paired_case_id=f"short.s{policy.seed}",
        seed=policy.seed,
        ticks=4,
        policy_config=policy,
        caps=BudgetCaps(attempts=0, input_tokens=0, output_tokens=0, micro_cny=0),
    )
    head = git(ROOT, "rev-parse", "HEAD").decode().strip()
    receipt = CaseReceipt(
        receipt_schema_version="0.1",
        registration_sha256="a" * 64,
        registration_commit=head,
        executed_commit=head,
        case_id=case.case_id,
        command=["offline-short-control"],
        status="complete",
        exit_code=0,
        trace_sha256=sha256((source / "decision-trace.json").read_bytes()).hexdigest(),
        failure=None,
        run_directory=str(source),
        allocation_key=None,
    )
    before = {p.name: sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}
    result = _control(case, receipt, tmp_path / "recorded-control", ROOT)
    assert result["technical"] == "PASS" and result["ticks"] == 4
    assert result["rule_tree"] == "837f2f90f6b242477e43c25aec9b359ec51ba331"
    assert before == {
        p.name: sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()
    }
    with pytest.raises(ValueError, match="invalid matched legacy control"):
        _control(case.model_copy(update={"ticks": 5}), receipt, None, ROOT)
    altered = policy.model_copy(update={"policy_id": "random-v0"})
    with pytest.raises(ValueError, match="frozen base rule identity"):
        _control(case.model_copy(update={"policy_config": altered}), receipt, None, ROOT)
    with pytest.raises(ValueError, match="trace differs"):
        _control(case, receipt.model_copy(update={"trace_sha256": "f" * 64}), None, ROOT)
    with pytest.raises(ValueError, match="frozen M6 world"):
        _control(case.model_copy(update={"seed": case.seed + 1}), receipt, None, ROOT)
