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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.p2_experiments import _limits_of, load_case  # noqa: E402
from scripts.p3_trials import CaseReceipt, _world  # noqa: E402

from living_island.agents.llm.fallback import FrozenRuleFallbackAdapter  # noqa: E402
from living_island.agents.p3.types import CaseAllocationP3, ContextProfile  # noqa: E402
from living_island.analysis.compare import death_categories, run_scalars  # noqa: E402
from living_island.analysis.metrics import compute_run  # noqa: E402
from living_island.analysis.p3 import (  # noqa: E402
    RULE_TREE,
    AllocationEvidence,
    ExpectedAllocation,
    VerifiedIssuance,
    allocation_accounting,
    evaluate_cognition,
    matched_comparison,
    physical_metrics,
)
from living_island.analysis.validity import assess_validity as evaluate_legacy  # noqa: E402
from living_island.contract.p3_inspection import canonical_bytes, canonical_sha256  # noqa: E402
from living_island.contract.p3_save import ImplementationPin, TrialRegistration  # noqa: E402
from living_island.persistence._codec import decode_model  # noqa: E402
from living_island.persistence.content import load_run_content  # noqa: E402
from living_island.persistence.p3 import read_checkpoint_p3  # noqa: E402
from living_island.persistence.p3_allocation import (  # noqa: E402
    _ORIGINAL_SMOKE_CASE,
    _ORIGINAL_SMOKE_CHARGED,
    _ORIGINAL_SMOKE_REGISTRATION,
    _PRIOR_REPLACEMENT_CHARGED,
    _PRIOR_REPLACEMENT_REGISTRATION,
    REPLACEMENT_SMOKE_CAPS,
    REPLACEMENT_SMOKE_CASE,
    U4_SMOKE_CAPS,
    U4_SMOKE_CASE,
    _Pilot,
    _ReplacementSmoke,
)
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


class _ArchiveModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ArchiveArtifact(_ArchiveModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ArchiveRun(_ArchiveModel):
    directory: str
    original_run_directory: str
    ancestors: list[str]


class ArchiveCase(_ArchiveModel):
    case_id: str
    receipts: list[str]
    runs: list[ArchiveRun]


class ArchiveRegistration(_ArchiveModel):
    registration: str
    repository_path: str
    cases: list[ArchiveCase]


class ArchiveReplacement(_ArchiveModel):
    record: str
    guard: str


class EvidenceManifest(_ArchiveModel):
    evidence_manifest_version: Literal["0.1"]
    artifacts: list[ArchiveArtifact]
    registrations: list[ArchiveRegistration] = Field(min_length=1)
    pilot: str | None
    cr007: ArchiveReplacement | None
    cr008: ArchiveReplacement | None
    allocations: list[str]


def _relative_member(value: str) -> Path:
    # POSIX-only archive members also reject Windows drives and UNC spellings.
    if not value or "\\" in value or ":" in value or value.startswith("/"):
        raise ValueError("archive member must be a relative POSIX path")
    if any(ord(c) < 32 or c in '<>"|?*' for c in value):
        raise ValueError("archive member is not a portable locator")
    if any(part in ("", ".", "..") or part.endswith((".", " ")) for part in value.split("/")):
        raise ValueError("archive member traversal or empty component")
    return Path(*value.split("/"))


class ArchiveReader:
    """Read an explicitly supplied immutable archive; embedded paths stay inert."""

    def __init__(self, path: Path, trusted_digest: str | None):
        raw = path.read_bytes()
        self.manifest = decode_model(raw, EvidenceManifest, path)
        self.digest = sha256(raw).hexdigest()
        self.trusted = trusted_digest is not None
        if trusted_digest is not None and trusted_digest != self.digest:
            raise ValueError("external owner-approved evidence digest mismatch")
        self.base = path.resolve().parent
        self.members: dict[str, ArchiveArtifact] = {}
        resolved_members: set[Path] = set()
        portable_names: set[str] = set()
        file_ids: set[tuple[int, int]] = set()
        for artifact in self.manifest.artifacts:
            if artifact.path in self.members:
                raise ValueError("duplicate archive artifact locator")
            resolved = self.locate(artifact.path)
            info = resolved.stat()
            identity = (info.st_dev, info.st_ino)
            if (
                resolved in resolved_members
                or artifact.path.casefold() in portable_names
                or identity in file_ids
            ):
                raise ValueError("duplicate resolved archive member/alias")
            resolved_members.add(resolved)
            portable_names.add(artifact.path.casefold())
            file_ids.add(identity)
            self.members[artifact.path] = artifact
            self.read(artifact.path)
        for entry in self.manifest.registrations:
            _relative_member(entry.repository_path)
            self.file(entry.registration)
            for case in entry.cases:
                if len(case.receipts) != len(set(case.receipts)):
                    raise ValueError("duplicate case receipt locator")
                for receipt in case.receipts:
                    self.file(receipt)
                for run in case.runs:
                    self.run(run)
        for name in [self.manifest.pilot, *self.manifest.allocations]:
            if name is not None:
                self.file(name)
        for link in (self.manifest.cr007, self.manifest.cr008):
            if link is not None:
                self.file(link.record)
                self.file(link.guard)

    def locate(self, member: str) -> Path:
        relative = _relative_member(member)
        path = self.base
        for part in relative.parts:
            path = path / part
            if path.is_symlink() or path.is_junction():
                raise ValueError("archive member symlink/junction is not permitted")
        resolved = path.resolve(strict=True)
        if resolved == self.base or self.base not in resolved.parents:
            raise ValueError("archive member escapes its root (including symlinks)")
        return resolved

    def file(self, member: str) -> Path:
        if member not in self.members:
            raise ValueError(f"missing hashed archive member:{member}")
        path = self.locate(member)
        if not path.is_file():
            raise ValueError("archive artifact is not a file")
        return path

    def read(self, member: str) -> bytes:
        raw = self.file(member).read_bytes()
        if sha256(raw).hexdigest() != self.members[member].sha256:
            raise ValueError(f"archive artifact hash mismatch:{member}")
        return raw

    def model[T: BaseModel](self, member: str, model: type[T]) -> T:
        return decode_model(self.read(member), model, self.file(member))

    def tree(self, member: str) -> Path:
        directory = self.locate(member)
        if not directory.is_dir():
            raise ValueError("archive run locator is not a directory")
        for path in directory.rglob("*"):
            relative = path.relative_to(self.base).as_posix()
            self.locate(relative)
            if path.is_file():
                self.read(relative)
        return directory

    def run(self, run: ArchiveRun) -> tuple[Path, tuple[Path, ...]]:
        directory = self.tree(run.directory)
        ancestors = []
        if len(run.ancestors) != len(set(run.ancestors)):
            raise ValueError("duplicate ancestor locator")
        for member in run.ancestors:
            ancestor = self.file(member)
            self.tree(_relative_member(member).parent.as_posix())
            ancestors.append(ancestor)
        return directory, tuple(ancestors)


def _snapshot_charged(snapshot: CaseAllocationP3) -> tuple[int, int, int, int]:
    entries = snapshot.entries
    return (
        len(entries),
        sum(e.debit.input_charged if e.debit else e.reservation.input_reserved for e in entries),
        sum(e.debit.output_charged if e.debit else e.reservation.output_reserved for e in entries),
        sum(e.debit.money_charged if e.debit else e.reservation.money_reserved for e in entries),
    )


def _completed_predecessor(snapshot: CaseAllocationP3) -> None:
    if (
        snapshot.status != "complete"
        or snapshot.head is None
        or snapshot.head.checkpoint_tick != 24
        or snapshot.head.reservation_cursor != len(snapshot.entries)
        or snapshot.prepared_head is not None
        or snapshot.pending_recovery_sha256 is not None
        or any(e.debit is None or e.state == "reserved" for e in snapshot.entries)
    ):
        raise ValueError("replacement predecessor must be settled and complete at tick24")


def archive_issuance(
    archive: ArchiveReader,
) -> tuple[VerifiedIssuance | None, dict[str, list[CaseAllocationP3]]]:
    """Verify frozen issuance snapshots without constructing or opening an authority."""
    manifest = archive.manifest
    snapshots: dict[str, list[CaseAllocationP3]] = {}
    for member in manifest.allocations:
        snapshot = archive.model(member, CaseAllocationP3)
        copies = snapshots.setdefault(snapshot.allocation_key, [])
        for other in copies:
            if (other.registration_sha256, other.case_id, other.caps) != (
                snapshot.registration_sha256,
                snapshot.case_id,
                snapshot.caps,
            ):
                raise ValueError("conflicting allocation snapshot identities")
            if other.status == snapshot.status == "complete" and other != snapshot:
                raise ValueError("competing completed allocation snapshots")
            for first, second in zip(other.entries, snapshot.entries, strict=False):
                if first != second:
                    raise ValueError("conflicting copied reservation evidence")
        if snapshot not in copies:
            copies.append(snapshot)
    if manifest.pilot is None:
        if manifest.cr007 is not None or manifest.cr008 is not None:
            raise ValueError("replacement evidence requires its pilot snapshot")
        return None, snapshots
    pilot = archive.model(manifest.pilot, _Pilot)
    bindings = {}
    slots: dict[str, list[str]] = {}
    for slot in pilot.slots:
        name = f"{slot.purpose}:{slot.seed}"
        slots[name] = []
        if slot.binding is not None:
            if slot.binding.state != "issued":
                raise ValueError("pilot binding has not reached issued state")
            bindings[slot.binding.allocation_key] = slot.binding
            slots[name].append(slot.binding.allocation_key)
    smoke = slots["smoke:1292387875"]
    for ordinal, link, case_id, caps in (
        (1, manifest.cr007, REPLACEMENT_SMOKE_CASE, REPLACEMENT_SMOKE_CAPS),
        (2, manifest.cr008, U4_SMOKE_CASE, U4_SMOKE_CAPS),
    ):
        if link is None:
            continue
        if len(smoke) != ordinal:
            raise ValueError("replacement chain is missing its approved predecessor")
        record = archive.model(link.record, _ReplacementSmoke)
        guard = archive.model(link.guard, _ReplacementSmoke)
        if record != guard or record.binding.state != "issued":
            raise ValueError("replacement issued record/guard mismatch")
        previous_key = smoke[-1]
        matching = [
            row
            for row in snapshots.get(previous_key, [])
            if canonical_sha256(row) == record.original_allocation_sha256
        ]
        if len(matching) != 1:
            raise ValueError("missing exact replacement predecessor snapshot/hash")
        previous = matching[0]
        _completed_predecessor(previous)
        expected_registration = (
            _ORIGINAL_SMOKE_REGISTRATION if ordinal == 1 else _PRIOR_REPLACEMENT_REGISTRATION
        )
        expected_case = _ORIGINAL_SMOKE_CASE if ordinal == 1 else REPLACEMENT_SMOKE_CASE
        expected_charged = (
            tuple(_ORIGINAL_SMOKE_CHARGED.values()) if ordinal == 1 else _PRIOR_REPLACEMENT_CHARGED
        )
        if (previous.registration_sha256, previous.case_id, _snapshot_charged(previous)) != (
            expected_registration,
            expected_case,
            expected_charged,
        ):
            raise ValueError(
                "replacement predecessor differs from frozen approved identity/charges"
            )
        binding = record.binding
        if (
            record.authority_root != pilot.authority_root
            or record.original_allocation_key != previous_key
            or binding.case_id != case_id
            or binding.caps != caps
            or binding.registration_sha256 == previous.registration_sha256
            or binding.allocation_key in bindings
            or any(b.registration_sha256 == binding.registration_sha256 for b in bindings.values())
        ):
            raise ValueError("replacement authorization identity/caps mismatch")
        bindings[binding.allocation_key] = binding
        smoke.append(binding.allocation_key)
    for key, binding in bindings.items():
        for snapshot in snapshots.get(key, []):
            if (snapshot.registration_sha256, snapshot.case_id, snapshot.caps) != (
                binding.registration_sha256,
                binding.case_id,
                binding.caps,
            ):
                raise ValueError("issued binding differs from archived allocation")
    issuance = (
        VerifiedIssuance(archive.digest, tuple((slot, tuple(keys)) for slot, keys in slots.items()))
        if archive.trusted
        else None
    )
    return issuance, snapshots


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
    *,
    registration_relative: str | None = None,
    receipt_candidates: list[Path] | None = None,
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
    candidates = (
        receipt_candidates
        if receipt_candidates is not None
        else [
            *path.parent.glob("*.json"),
            *(path.parent / "lineage" / case_id).rglob("previous.json"),
        ]
    )
    for candidate in candidates:
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
    relative = (
        registration_relative
        or registration_path.resolve().relative_to(repository.resolve()).as_posix()
    )
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
    case: Any,
    receipt: CaseReceipt,
    proof: Path | None,
    repository: Path,
    *,
    source: Path | None = None,
) -> dict[str, Any]:
    source = Path(receipt.run_directory) if source is None else source
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
    archive: ArchiveReader | None = None,
    archive_entry: ArchiveRegistration | None = None,
    allocation_sink: list[AllocationEvidence] | None = None,
    verified_sink: dict[str, VerifiedInspection] | None = None,
) -> dict[str, Any]:
    reader = GitSourceReader(repository)
    registration = TrialRegistration.model_validate_json(registration_path.read_bytes())
    registration_source(registration, repository, reader)
    results: dict[str, dict[str, Any]] = {}
    allocations = []
    expected = [
        ExpectedAllocation(
            canonical_sha256(registration), case.case_id, registration.purpose, case.seed, case.caps
        )
        for case in registration.cases
    ]
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
    for case in [*registration.cases, *registration.controls]:
        try:
            if archive is None:
                receipt_path = receipts / f"{case.case_id}.json"
                candidates = None
                relative = None
                archive_runs = []
            else:
                assert archive_entry is not None
                members = [c for c in archive_entry.cases if c.case_id == case.case_id]
                if not members:
                    raise ValueError("missing archived case/receipt/run evidence")
                receipt_names = list(dict.fromkeys(n for c in members for n in c.receipts))
                candidates = [archive.file(n) for n in receipt_names]
                retained = [archive.model(n, CaseReceipt) for n in receipt_names]
                if any(
                    (r.registration_sha256, r.case_id)
                    != (canonical_sha256(registration), case.case_id)
                    for r in retained
                ):
                    raise ValueError("foreign receipt in archived case")
                complete = [i for i, r in enumerate(retained) if r.status == "complete"]
                if not complete:
                    raise ValueError("missing or incomplete matching case receipt")
                receipt_path = candidates[complete[0]]
                relative = archive_entry.repository_path
                archive_runs = [r for c in members for r in c.runs]
            receipt = _receipt(
                receipt_path,
                registration,
                case.case_id,
                repository,
                registration_path,
                reader,
                registration_relative=relative,
                receipt_candidates=candidates,
            )
            if archive is None:
                source = Path(receipt.run_directory)
                case_ancestors = ancestors
            else:
                matching_runs = [
                    r for r in archive_runs if r.original_run_directory == receipt.run_directory
                ]
                if not matching_runs:
                    raise ValueError("missing explicit archived completed run locator")
                source, case_ancestors = archive.run(matching_runs[0])
                trace_name = (
                    "decision-trace.json"
                    if case in registration.controls
                    else "decision-trace-p3.json"
                )
                for run in matching_runs:
                    copied, _ = archive.run(run)
                    if (
                        sha256((copied / trace_name).read_bytes()).hexdigest()
                        != receipt.trace_sha256
                    ):
                        raise ValueError("competing completed archived run lineages")
            if case in registration.controls:
                results[case.case_id] = _control(
                    case,
                    receipt,
                    None if output is None else output / f"{case.case_id}-recorded",
                    repository,
                    source=source,
                )
                continue
            verified = verify_inspection_source(
                source,
                source / "replay.json",
                repository=repository,
                ancestors=case_ancestors,
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
            if verified_sink is not None:
                prior = verified_sink.get(expected_key)
                if prior is not None and (
                    prior.trace_bytes != verified.trace_bytes
                    or prior.final.raw != verified.final.raw
                ):
                    raise ValueError("competing completed source lineages across registrations")
                verified_sink[expected_key] = verified
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
                    ancestors=case_ancestors,
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
    if allocation_sink is not None:
        allocation_sink.extend(allocations)
    accounting = allocation_accounting(allocations, expected=expected)
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


def evaluate_archive(
    manifest_path: Path, *, trusted_owner_digest: str | None, repository: Path, output: Path | None
) -> dict[str, Any]:
    archive = ArchiveReader(manifest_path, trusted_owner_digest)
    issuance, snapshots = archive_issuance(archive)
    reader = GitSourceReader(repository)
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
    expected: dict[str, ExpectedAllocation] = {}
    case_info: dict[str, Any] = {}
    allocations: list[AllocationEvidence] = []
    verified: dict[str, VerifiedInspection] = {}
    reports = []
    errors: list[str] = []
    run_locators = [
        run for entry in archive.manifest.registrations for case in entry.cases for run in case.runs
    ]
    for index, entry in enumerate(archive.manifest.registrations):
        registration = archive.model(entry.registration, TrialRegistration)
        digest = canonical_sha256(registration)
        case_ids = {case.case_id for case in [*registration.cases, *registration.controls]}
        if any(case.case_id not in case_ids for case in entry.cases):
            raise ValueError("archive contains an unregistered case")
        for case in registration.cases:
            item = ExpectedAllocation(
                digest, case.case_id, registration.purpose, case.seed, case.caps
            )
            prior = expected.setdefault(item.allocation_key, item)
            if prior != item:
                raise ValueError("conflicting archived registration case identity")
            case_info[item.allocation_key] = case
        try:
            if registration.purpose in ("development", "acceptance"):
                raise ValueError(
                    "P305-U1_REQUIRED: registration0.1 matrix is unsupported; "
                    "split registrations cannot substitute"
                )
            report = evaluate_registration(
                archive.file(entry.registration),
                archive.base,
                repository=repository,
                output=None if output is None else output / f"registration-{index:04d}",
                archive=archive,
                archive_entry=entry,
                allocation_sink=allocations,
                verified_sink=verified,
            )
            # Issuance and charge completeness are evaluated once across the whole
            # supplied archive, never independently as fresh per-registration grants.
            report.pop("accounting")
            report["technical"] = (
                "PASS"
                if all(row["technical"] == "PASS" for row in report["cases"].values())
                else "FAIL"
            )
            reports.append(report)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            reports.append(
                {
                    "registration_sha256": digest,
                    "technical": "FAIL",
                    "cases_expected": len(case_ids),
                    "cases": {
                        case_id: {
                            "technical": "FAIL",
                            "case_id": case_id,
                            "metrics": None,
                            "missing_sources": [str(exc)],
                        }
                        for case_id in sorted(case_ids)
                    },
                }
            )
    # The complete pilot inventory determines every issued obligation, including
    # bindings whose registration or execution artifacts were omitted.
    binding_by_key = {}
    if archive.manifest.pilot is not None:
        pilot = archive.model(archive.manifest.pilot, _Pilot)
        for slot in pilot.slots:
            if slot.binding is not None:
                binding_by_key[slot.binding.allocation_key] = (
                    slot.purpose,
                    slot.seed,
                    slot.binding,
                )
        for link in (archive.manifest.cr007, archive.manifest.cr008):
            if link is not None:
                binding = archive.model(link.record, _ReplacementSmoke).binding
                binding_by_key[binding.allocation_key] = ("smoke", 1292387875, binding)
        for key, (purpose, seed, binding) in binding_by_key.items():
            item = ExpectedAllocation(
                binding.registration_sha256, binding.case_id, purpose, seed, binding.caps
            )
            if key in expected and expected[key] != item:
                raise ValueError("issued binding differs from registered case")
            if key not in expected:
                errors.append(f"missing issued registration/case:{key}")
                expected[key] = item
            if key not in snapshots:
                errors.append(f"missing issued allocation snapshot:{key}")
    for key, copies in snapshots.items():
        item = expected.get(key)
        if item is None:
            raise ValueError("allocation snapshot has no registered or issued case")
        if item.purpose == "fake" and key in binding_by_key:
            raise ValueError("fake case cannot consume a live slot")
        for snapshot in copies:
            if (snapshot.registration_sha256, snapshot.case_id, snapshot.caps) != (
                item.registration_sha256,
                item.case_id,
                item.caps,
            ):
                raise ValueError("allocation snapshot differs from expected case")
            source_verified = verified.get(key)
            complete_trace = None
            try:
                if snapshot.head is None:
                    raise ValueError("allocation snapshot has no committed head")
                matches = [
                    run
                    for run in run_locators
                    if run.original_run_directory == snapshot.head.run_directory
                ]
                if not matches:
                    raise ValueError("missing explicit archive locator for allocation head")
                for run in matches:
                    directory, ancestors = archive.run(run)
                    path = directory / f"checkpoint-{snapshot.head.checkpoint_tick:010d}.json"
                    checkpoint = read_checkpoint_p3(path, ancestors=ancestors, source_reader=reader)
                    head = snapshot.head
                    if (
                        sha256(checkpoint.raw).hexdigest() != head.checkpoint_sha256
                        or checkpoint.save.input_manifest_sha256 != head.input_manifest_sha256
                        or checkpoint.save.run_budget.allocation_key != key
                        or checkpoint.save.run_budget.caps != snapshot.caps
                        or len(checkpoint.save.allocation_entries) != head.reservation_cursor
                        or snapshot.entries[: head.reservation_cursor]
                        != checkpoint.save.allocation_entries
                    ):
                        raise ValueError("archived allocation head/entries differ from checkpoint")
                if snapshot.status == "complete":
                    case = case_info.get(key)
                    if (
                        case is None
                        or snapshot.head.checkpoint_tick != case.ticks
                        or snapshot.prepared_head is not None
                        or snapshot.pending_recovery_sha256 is not None
                        or snapshot.head.reservation_cursor != len(snapshot.entries)
                    ):
                        raise ValueError(
                            "completed allocation differs from registered horizon/settlement"
                        )
                    if source_verified is None:
                        raise ValueError(
                            "complete snapshot lacks source-verified receipt/run lineage"
                        )
                    if (
                        snapshot.head.checkpoint_sha256
                        != sha256(source_verified.final.raw).hexdigest()
                        or snapshot.entries != source_verified.final.save.allocation_entries
                    ):
                        raise ValueError("competing completed allocation/source lineages")
                    complete_trace = sha256(source_verified.trace_bytes).hexdigest()
                else:
                    errors.append(f"incomplete archived allocation:{key}")
            except (OSError, ValueError) as exc:
                errors.append(f"allocation {key}: {exc}")
            allocations.append(
                AllocationEvidence(
                    item.registration_sha256,
                    item.case_id,
                    item.purpose,
                    item.seed,
                    item.caps,
                    tuple(snapshot.entries),
                    complete_trace,
                )
            )
    accounting = allocation_accounting(
        allocations, expected=list(expected.values()), issuance=issuance
    )
    if errors:
        accounting["technical"] = accounting["arithmetic_status"] = "FAIL"
        accounting["errors"].extend(errors)
        accounting["cost_ceiling_micro_cny"] = None
        accounting["evidence_complete"] = False
    passed = accounting["technical"] == "PASS" and all(r["technical"] == "PASS" for r in reports)
    return {
        "report_schema_version": "0.1",
        "technical": "PASS" if passed else "FAIL",
        "owner_acceptance": "NOT_REQUESTED",
        "m10_status": "NOT_EVALUATED",
        "evidence_manifest_sha256": archive.digest,
        "trust_anchor": {
            "expected_owner_approved_sha256": trusted_owner_digest,
            "status": "MATCHED_EXTERNAL_DIGEST" if archive.trusted else "MISSING",
            "assumption": (
                "Operator supplies an independently obtained owner-approved manifest digest; "
                "the archive does not authenticate itself or create any grant."
            ),
        },
        "registrations": reports,
        "allocations_expected": len(expected),
        "accounting": accounting,
        "live_provider_calls": 0,
        "live_authority_accesses": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "report"):
        command = commands.add_parser(name)
        choice = command.add_mutually_exclusive_group(required=True)
        choice.add_argument("--registration", type=Path)
        choice.add_argument(
            "--evidence-manifest",
            type=Path,
            help="Closed relative-path archive manifest for cross-registration offline accounting",
        )
        command.add_argument("--receipts", type=Path)
        command.add_argument(
            "--trusted-owner-evidence-sha256",
            help=(
                "Independently obtained owner-approved digest of the whole canonical manifest; "
                "no default, no self-authentication or grant creation"
            ),
        )
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
            if args.evidence_manifest is not None:
                if args.receipts is not None or args.ancestor:
                    raise ValueError("archive members supply explicit receipts and ancestors")
                result = evaluate_archive(
                    args.evidence_manifest,
                    trusted_owner_digest=args.trusted_owner_evidence_sha256,
                    repository=args.repository,
                    output=getattr(args, "out", None),
                )
            else:
                if args.receipts is None:
                    raise ValueError("--receipts is required with --registration")
                if args.trusted_owner_evidence_sha256 is not None:
                    raise ValueError("external digest requires --evidence-manifest")
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
                    **(
                        {
                            "accounting": {
                                "technical": "FAIL",
                                "arithmetic_status": "FAIL",
                                "issuance_proof": "MISSING",
                                "cost_ceiling_micro_cny": None,
                                "known_subtotal_micro_cny": 0,
                                "evidence_complete": False,
                                "missing_sources": [str(exc)],
                            }
                        }
                        if args.command in ("validate", "report")
                        else {}
                    ),
                    "live_provider_calls": 0,
                    "live_authority_accesses": 0,
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
