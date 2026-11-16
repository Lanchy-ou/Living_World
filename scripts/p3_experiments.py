"""Offline P3 validation, evaluation, inspection and recorded no-call proofs.

This entry point does not enroll, read credentials or open live authorities.
Missing evidence is reported as missing; no successful-subset gate is applied.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.p2_experiments import _limits_of, load_case  # noqa: E402
from scripts.p3_trials import CaseReceipt, _world  # noqa: E402

from living_island.agents.llm.fallback import FrozenRuleFallbackAdapter  # noqa: E402
from living_island.agents.p3.types import ContextProfile  # noqa: E402
from living_island.analysis.compare import death_categories, run_scalars  # noqa: E402
from living_island.analysis.metrics import compute_run  # noqa: E402
from living_island.analysis.p3 import (  # noqa: E402
    RULE_TREE,
    AllocationEvidence,
    allocation_accounting,
    evaluate_cognition,
    matched_comparison,
    physical_metrics,
)
from living_island.analysis.validity import assess_validity as evaluate_legacy  # noqa: E402
from living_island.contract.p3_inspection import canonical_bytes, canonical_sha256  # noqa: E402
from living_island.contract.p3_save import ImplementationPin, TrialRegistration  # noqa: E402
from living_island.persistence.content import load_run_content  # noqa: E402
from living_island.persistence.p3_inspection import (  # noqa: E402
    GitSourceReader,
    VerifiedInspection,
    export_inspection,
    resolve_selector,
    verify_inspection_source,
)
from living_island.persistence.trace import load_trace  # noqa: E402
from living_island.sim.p3 import reexecute_p3  # noqa: E402
from living_island.sim.runner import reexecute  # noqa: E402
from living_island.world.content import build_world_content  # noqa: E402


class RaisingSentinel:
    """Every attempted provider or authority operation raises and is counted."""

    def __init__(self) -> None:
        self.accesses = 0

    def __getattr__(self, name: str) -> Any:
        self.accesses += 1
        raise AssertionError(f"offline proof attempted external access: {name}")


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={repository.as_posix()}", *arguments],
            cwd=repository,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError("historical Git identity check refused") from exc


def _inventory(repository: Path, commit: str) -> list[str]:
    return (
        _git(
            repository,
            "ls-tree",
            "-r",
            "--name-only",
            commit,
            "--",
            "backend/src",
            "scripts",
            "backend/pyproject.toml",
            "backend/uv.lock",
        )
        .decode()
        .splitlines()
    )


def registration_source(
    registration: TrialRegistration, repository: Path, reader: GitSourceReader
) -> None:
    """Verify historical registration pins without substituting current worktree files."""
    if _inventory(repository, registration.implementation_commit) != [
        p.path for p in registration.implementation_pins
    ]:
        raise ValueError(
            "registration does not pin the complete historical implementation inventory"
        )
    for pin in [*registration.implementation_pins, *registration.input_pins]:
        if sha256(reader(registration.implementation_commit, pin.path)).hexdigest() != pin.sha256:
            raise ValueError(f"historical source pin mismatch: {pin.path}")
    world = tomllib.loads(
        reader(registration.world_pin_commit, registration.world_config_path).decode("utf-8")
    )
    world["meta"]["seed"] = registration.cases[0].seed
    content = build_world_content(
        world, reader(registration.world_pin_commit, registration.world_map_path)
    )
    if (content.config_hash, content.map_hash) != (
        registration.world_config_sha256,
        registration.world_map_sha256,
    ):
        raise ValueError("historical world pin differs from effective registered inputs")


def recorded_proof(
    verified: VerifiedInspection,
    source: Path,
    output: Path,
    *,
    repository: Path,
    ancestors: tuple[Path, ...],
    reader: GitSourceReader,
) -> dict[str, Any]:
    provider, authority = RaisingSentinel(), RaisingSentinel()
    profile = ContextProfile.model_validate_json(verified.final.inputs["context-profile.json"])
    implementation = ImplementationPin.model_validate_json(
        verified.final.inputs["implementation.json"]
    )
    selector = resolve_selector(
        verified.registration, implementation, profile, repository=repository, source_reader=reader
    )
    configs = verified.final.save.agent_state.runtime_states
    fallback = FrozenRuleFallbackAdapter(configs[0].policy_config.fallback_config)
    result = reexecute_p3(
        source,
        output,
        provider=provider,
        allocation_store=authority,
        fallback=fallback,
        source_reader=reader,
        ancestors=ancestors,
        selector=selector,
        selector_sha256=None if selector is None else selector.implementation_sha256,
    )
    if result.trace != verified.trace:
        raise ValueError("recorded proof trace differs from source equality targets")
    if provider.accesses or authority.accesses:
        raise ValueError("recorded proof accessed an external port")
    return {
        "status": "PASS",
        "provider_accesses": provider.accesses,
        "authority_accesses": authority.accesses,
        "trace_sha256": sha256((result.output / "decision-trace-p3.json").read_bytes()).hexdigest(),
        "final_world_sha256": verified.trace.final_world_sha256,
        "final_runtime_states_sha256": verified.trace.final_runtime_states_sha256,
        "final_budget_sha256": verified.trace.final_budget_sha256,
        "log_prefixes": [p.model_dump(mode="json") for p in verified.trace.log_prefixes],
    }


def _receipt(
    path: Path,
    registration: TrialRegistration,
    case_id: str,
    repository: Path,
    registration_path: Path,
    reader: GitSourceReader,
) -> CaseReceipt:
    receipt = CaseReceipt.model_validate_json(path.read_bytes())
    if (receipt.case_id, receipt.registration_sha256, receipt.status) != (
        case_id,
        canonical_sha256(registration),
        "complete",
    ):
        raise ValueError("missing or incomplete matching case receipt")
    _git(
        repository,
        "merge-base",
        "--is-ancestor",
        registration.implementation_commit,
        receipt.executed_commit,
    )
    for candidate in [
        *path.parent.glob("*.json"),
        *(path.parent / "lineage" / case_id).rglob("previous.json"),
    ]:
        if candidate == path:
            continue
        raw = json.loads(candidate.read_bytes())
        if not isinstance(raw, dict) or raw.get("receipt_schema_version") != "0.1":
            continue
        other = CaseReceipt.model_validate(raw)
        if (other.registration_sha256, other.case_id, other.status) == (
            receipt.registration_sha256,
            case_id,
            "complete",
        ) and (
            other.trace_sha256 != receipt.trace_sha256
            or other.allocation_key != receipt.allocation_key
        ):
            raise ValueError("competing completed receipt lineages for one allocation")
    relative = registration_path.resolve().relative_to(repository.resolve()).as_posix()
    archived = TrialRegistration.model_validate_json(reader(receipt.registration_commit, relative))
    if archived != registration:
        raise ValueError("receipt registration commit does not contain the exact registration")
    if _inventory(repository, receipt.executed_commit) != [
        p.path for p in registration.implementation_pins
    ]:
        raise ValueError("receipt executed source inventory drift")
    for pin in registration.implementation_pins:
        if sha256(reader(receipt.executed_commit, pin.path)).hexdigest() != pin.sha256:
            raise ValueError("receipt executed source differs from registered implementation")
    return receipt


def _control(
    case: Any, receipt: CaseReceipt, proof: Path | None, repository: Path
) -> dict[str, Any]:
    source = Path(receipt.run_directory)
    policy = case.policy_config
    parameters = policy.rule_params
    if (
        policy.policy_id != "rule-based-v0"
        or policy.script_sha256 is not None
        or policy.source_trace_sha256 is not None
        or parameters is None
        or (
            parameters.canteen_use,
            parameters.cue_use,
            parameters.fruit_carry_target,
            parameters.failed_target_retry_ticks,
        )
        != ("enabled", "enabled", 2, 36)
        or any(case.caps.model_dump().values())
        or receipt.allocation_key is not None
    ):
        raise ValueError("matched control must use the frozen base rule identity and zero caps")
    expected_world = _world(repository, case.seed)
    actual_world = load_trace(source).content
    if (actual_world.config_hash, actual_world.map_hash) != (
        expected_world.config_hash,
        expected_world.map_hash,
    ):
        raise ValueError("matched control does not use the frozen M6 world inputs")
    loaded = load_case(
        source,
        cli_exit_code=receipt.exit_code,
        expected_policy_config_sha256=canonical_sha256(case.policy_config),
    )
    validity = evaluate_legacy(replace(loaded.inputs, expected_ticks=case.ticks))
    if not validity.valid or loaded.data is None or loaded.inputs.tick0 is None:
        raise ValueError(f"invalid matched legacy control: {asdict(validity)}")
    for state in loaded.inputs.tick0.agent_state.runtime_states:
        if state.policy_config != case.policy_config:
            raise ValueError("matched control policy differs from registered frozen policy")
    tree = (
        _git(
            repository,
            "rev-parse",
            f"{receipt.executed_commit}:backend/src/living_island/agents/rule_based",
        )
        .decode()
        .strip()
    )
    if tree != RULE_TREE:
        raise ValueError("matched control source is not the frozen P2 rule tree")
    if sha256((source / "decision-trace.json").read_bytes()).hexdigest() != receipt.trace_sha256:
        raise ValueError("matched control trace differs from receipt")
    if actual_world.config.meta.seed != case.seed:
        raise ValueError("matched control seed differs")
    if proof is not None:
        reexecute(source, proof)
    run = compute_run(loaded.data)
    return {
        "technical": "PASS" if proof is not None else "FAIL",
        "case_id": case.case_id,
        "seed": case.seed,
        "ticks": case.ticks,
        "rule_tree": tree,
        "world_inputs": [loaded.inputs.trace.config_hash, loaded.inputs.trace.map_hash],
        "scalars": run_scalars(run),
        "physical": asdict(run),
        "death_categories": death_categories(loaded.data, run),
        "missing_sources": [] if proof is not None else ["PV-06 recorded proof"],
    }


def evaluate_registration(
    registration_path: Path,
    receipts: Path,
    *,
    repository: Path,
    output: Path | None,
    ancestors: tuple[Path, ...] = (),
) -> dict[str, Any]:
    reader = GitSourceReader(repository)
    registration = TrialRegistration.model_validate_json(registration_path.read_bytes())
    registration_source(registration, repository, reader)
    results: dict[str, dict[str, Any]] = {}
    allocations = []
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
    for case in [*registration.cases, *registration.controls]:
        try:
            receipt = _receipt(
                receipts / f"{case.case_id}.json",
                registration,
                case.case_id,
                repository,
                registration_path,
                reader,
            )
            source = Path(receipt.run_directory)
            if case in registration.controls:
                results[case.case_id] = _control(
                    case,
                    receipt,
                    None if output is None else output / f"{case.case_id}-recorded",
                    repository,
                )
                continue
            verified = verify_inspection_source(
                source,
                source / "replay.json",
                repository=repository,
                ancestors=ancestors,
                source_reader=reader,
            )
            if verified.registration != registration or verified.trace.final_tick != case.ticks:
                raise ValueError("case registration/horizon differs from verified source")
            if (
                receipt.allocation_key != verified.final.save.run_budget.allocation_key
                or receipt.trace_sha256 != sha256(verified.trace_bytes).hexdigest()
            ):
                raise ValueError("receipt allocation/trace differs from committed lineage")
            expected_key = canonical_sha256(
                {"registration_sha256": canonical_sha256(registration), "case_id": case.case_id}
            )
            if receipt.allocation_key != expected_key:
                raise ValueError("receipt selects a different registered case")
            metrics = evaluate_cognition(
                verified.decisions,
                verified.samples,
                llm_actor_ids=case.llm_actor_ids,
                expected_tick=case.ticks,
                recovery_debits=verified.final.save.run_budget.recovery_debits,
            )
            content = load_run_content(
                source,
                expected_config_hash=verified.trace.config_hash,
                expected_map_hash=verified.trace.map_hash,
            )
            physical = physical_metrics(
                verified.replay, [d.record for d in verified.decisions], _limits_of(content)
            )
            item = {
                "technical": metrics["technical"],
                "case_id": case.case_id,
                "seed": case.seed,
                "ticks": case.ticks,
                "world_inputs": [verified.trace.config_hash, verified.trace.map_hash],
                "receipt": receipt.model_dump(mode="json"),
                "cognitive": metrics,
                "physical": physical["metrics"],
                "scalars": physical["scalars"],
                "missing_sources": [],
                "PV-06": "NOT_RUN",
                "PV-07": "NOT_RUN",
            }
            allocations.append(
                AllocationEvidence(
                    canonical_sha256(registration),
                    case.case_id,
                    registration.purpose,
                    case.seed,
                    case.caps,
                    tuple(verified.final.save.allocation_entries),
                    receipt.trace_sha256,
                )
            )
            if output is not None:
                index_dir = output / f"{case.case_id}-inspection"
                export_inspection(verified, index_dir)
                item["inspection_index_sha256"] = sha256(
                    (index_dir / "index.json").read_bytes()
                ).hexdigest()
                item["PV-07"] = "HEADLESS_PASS_UI_PENDING"
                item["recorded_proof"] = recorded_proof(
                    verified,
                    source,
                    output / f"{case.case_id}-recorded",
                    repository=repository,
                    ancestors=ancestors,
                    reader=reader,
                )
                item["PV-06"] = "PASS"
            else:
                item["technical"] = "FAIL"
                item["missing_sources"] = ["PV-06 recorded proof", "PV-07 inspection"]
            if (
                registration.purpose in ("smoke", "acceptance")
                and metrics["metrics"]["v05"] != "PASS"
            ):
                item["technical"] = "FAIL"
            results[case.case_id] = item
        except (OSError, ValueError) as exc:
            results[case.case_id] = {
                "technical": "FAIL",
                "case_id": case.case_id,
                "missing_sources": [str(exc)],
                "metrics": None,
            }
    accounting = allocation_accounting(allocations)
    comparison = (
        matched_comparison(registration, results) if registration.purpose == "acceptance" else None
    )
    passed = (
        all(r["technical"] == "PASS" for r in results.values())
        and accounting["technical"] == "PASS"
    )
    if comparison is not None:
        passed = passed and comparison["technical"] == "PASS"
    return {
        "report_schema_version": "0.1",
        "registration_sha256": canonical_sha256(registration),
        "technical": "PASS" if passed else "FAIL",
        "owner_acceptance": "NOT_REQUESTED",
        "m10_status": "NOT_EVALUATED",
        "technical_scope": "Offline source, recorded proof and headless inspection; UI pending.",
        "cases_expected": len(registration.cases) + len(registration.controls),
        "cases": results,
        "accounting": accounting,
        "comparison": comparison,
        "live_provider_calls": 0,
        "live_authority_accesses": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "report"):
        command = commands.add_parser(name)
        command.add_argument("--registration", type=Path, required=True)
        command.add_argument("--receipts", type=Path, required=True)
        command.add_argument("--ancestor", type=Path, action="append", default=[])
        if name == "report":
            command.add_argument("--out", type=Path, required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--source-run", type=Path, required=True)
    inspect.add_argument("--replay", type=Path)
    inspect.add_argument("--ancestor", type=Path, action="append", default=[])
    inspect.add_argument("--out", type=Path, required=True)
    inspect.add_argument("--recorded-out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            reader = GitSourceReader(args.repository)
            verified = verify_inspection_source(
                args.source_run,
                args.replay or args.source_run / "replay.json",
                repository=args.repository,
                ancestors=tuple(args.ancestor),
                source_reader=reader,
            )
            index = export_inspection(verified, args.out)
            result: dict[str, Any] = {
                "status": "PASS",
                "index_sha256": canonical_sha256(index),
                "samples": len(index.samples),
                "decisions": len(index.decisions),
            }
            if args.recorded_out is not None:
                result["recorded_proof"] = recorded_proof(
                    verified,
                    args.source_run,
                    args.recorded_out,
                    repository=args.repository,
                    ancestors=tuple(args.ancestor),
                    reader=reader,
                )
        else:
            result = evaluate_registration(
                args.registration,
                args.receipts,
                repository=args.repository,
                output=getattr(args, "out", None),
                ancestors=tuple(args.ancestor),
            )
            result["command"] = [
                sys.executable,
                str(Path(__file__).resolve()),
                *(sys.argv[1:] if argv is None else argv),
            ]
            if args.command == "report":
                (args.out / "report.json").write_bytes(canonical_bytes(result))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result.get("technical") == "FAIL" else 0
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": str(exc),
                    "live_provider_calls": 0,
                    "live_authority_accesses": 0,
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
