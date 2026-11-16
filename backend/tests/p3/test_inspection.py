"""P3 inspection schema, lineage and offline export integration tests."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest
from test_extension_ports import ROOT, _three_actor_case, fixture_provider, fixture_selector

from living_island.contract.p3_inspection import (
    DecisionInspection,
    P3InspectionIndex,
    ResidentInspection,
    canonical_bytes,
)
from living_island.persistence.p3_inspection import export_inspection, verify_inspection_source
from living_island.sim.p3 import export_p3_replay, run_p3


@pytest.fixture(scope="module")
def inspected(tmp_path_factory):
    root = tmp_path_factory.mktemp("inspection")
    content, files, case, store, reader, fallback = _three_actor_case(root, fixture=True, horizon=2)
    source = root / "source"
    run_p3(
        content,
        files,
        case,
        source,
        allocation_store=store,
        provider=fixture_provider("recent-only", 1, horizon=2),
        fallback=fallback,
        source_reader=reader,
        selector=fixture_selector(),
        selector_sha256=fixture_selector().implementation_sha256,
    )
    replay = root / "replay.json"
    export_p3_replay(source, replay, source_reader=reader)
    verified = verify_inspection_source(source, replay, repository=ROOT, source_reader=reader)
    return root, source, replay, reader, verified


def test_export_exact_deterministic_shards_and_complete_samples(inspected):
    root, source, replay, reader, verified = inspected
    before = {
        p.relative_to(source): sha256(p.read_bytes()).hexdigest()
        for p in source.rglob("*")
        if p.is_file()
    }
    first, second = root / "export-a", root / "export-b"
    index = export_inspection(verified, first)
    assert export_inspection(verified, second) == index
    assert len(index.samples) == 9
    assert len(index.decisions) == len(verified.decisions)
    assert (first / "trace.json").read_bytes() == (source / "decision-trace-p3.json").read_bytes()
    assert index.replay_sha256 == sha256(replay.read_bytes()).hexdigest()
    for file in first.iterdir():
        assert file.read_bytes() == (second / file.name).read_bytes()
        if file.name != "trace.json":
            assert not file.read_bytes().endswith(b"\n")
    for ref in index.decisions:
        raw = (first / ref.shard.file).read_bytes()
        assert sha256(raw).hexdigest() == ref.shard.sha256
        shard = DecisionInspection.model_validate_json(raw)
        assert shard.context.assembly.manifest.retrieval_profile == "recent-only-fixture-v0"
    for ref in index.samples:
        sample = ResidentInspection.model_validate_json((first / ref.shard.file).read_bytes())
        assert sample.latest_perception_tick < sample.tick
        if ref.tick == 0:
            assert sample.latest_decision_id is None
            assert sample.recent_experience == []
        else:
            assert len(sample.recent_experience) == min(8, sample.retained_record_count)
    assert before == {
        p.relative_to(source): sha256(p.read_bytes()).hexdigest()
        for p in source.rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError, match="fresh"):
        export_inspection(verified, first)


@pytest.mark.parametrize(
    "mutation",
    ["version", "missing", "duplicate", "foreign", "filename", "ordinal", "huge-horizon"],
)
def test_index_refuses_corrupt_membership(inspected, mutation):
    root, _, _, _, verified = inspected
    index = export_inspection(verified, root / f"mutation-{mutation}").model_dump(mode="json")
    if mutation == "huge-horizon":
        index["final_tick"] = 10**18
    elif mutation == "version":
        index["inspection_schema_version"] = "9"
    elif mutation == "missing":
        index["samples"].pop()
    elif mutation == "duplicate":
        index["samples"].append(index["samples"][0])
    elif mutation == "foreign":
        index["decisions"][0]["actor_id"] = "other"
    elif mutation == "filename":
        index["samples"][0]["shard"]["file"] = "../bad.json"
    else:
        index["decisions"][0]["ordinal"] = True
    with pytest.raises(ValueError):
        P3InspectionIndex.model_validate(index)


def test_unrelated_replay_refuses(inspected):
    root, source, replay, reader, _ = inspected
    data = json.loads(replay.read_bytes())
    data["config_hash"] = "f" * 64
    wrong = root / "wrong-replay.json"
    wrong.write_bytes(canonical_bytes(data))
    with pytest.raises(ValueError, match="config_hash|run/config/map"):
        verify_inspection_source(source, wrong, repository=ROOT, source_reader=reader)


def test_exact_shard_limit(monkeypatch, inspected):
    import living_island.persistence.p3_inspection as exporter

    shard = inspected[-1].decisions[0]
    size = len(canonical_bytes(shard))
    monkeypatch.setattr(exporter, "SHARD_LIMIT", size)
    assert len(exporter.checked_shard_bytes(shard)) == size
    monkeypatch.setattr(exporter, "SHARD_LIMIT", size - 1)
    with pytest.raises(ValueError, match="V-06"):
        exporter.checked_shard_bytes(shard)


def test_recorded_proof_has_zero_external_access(inspected):
    from scripts.p3_experiments import recorded_proof

    from living_island.persistence.p3_inspection import GitSourceReader

    root, source, _, _, verified = inspected
    proof = recorded_proof(
        verified,
        source,
        root / "recorded",
        repository=ROOT,
        ancestors=(),
        reader=GitSourceReader(ROOT),
    )
    assert proof["status"] == "PASS"
    assert proof["provider_accesses"] == proof["authority_accesses"] == 0


def test_source_child_destination_refuses(inspected):
    _, source, _, _, verified = inspected
    with pytest.raises(ValueError, match="source directory"):
        export_inspection(verified, source / "inspection")
    assert not (source / "inspection").exists()


def test_replay_clock_mismatch_refuses(inspected):
    root, source, replay, reader, _ = inspected
    data = json.loads(replay.read_bytes())
    data["clock"]["start_hour"] = (data["clock"]["start_hour"] + 1) % 24
    altered = root / "wrong-clock.json"
    altered.write_bytes(canonical_bytes(data))
    with pytest.raises(ValueError, match="metadata"):
        verify_inspection_source(source, altered, repository=ROOT, source_reader=reader)


def test_default_selector_installed_source_mismatch_refuses(inspected, tmp_path):
    from living_island.agents.p3.types import ContextProfile
    from living_island.contract.p3_save import ImplementationPin
    from living_island.persistence.p3_inspection import resolve_selector

    verified = inspected[-1]
    pin = ImplementationPin.model_validate_json(verified.final.inputs["implementation.json"])
    profile = ContextProfile(
        context_profile_schema_version="0.1",
        context_profile_id="p3-context-v0",
        retrieval_profile="recent-relevant-v0",
        projection_profile="p3-context-v0",
    )
    with pytest.raises((ValueError, OSError)):
        resolve_selector(
            verified.registration, pin, profile, repository=tmp_path, source_reader=inspected[3]
        )


def test_actual_v06_two_mebibytes_and_one_byte_over(monkeypatch, inspected):
    import living_island.persistence.p3_inspection as exporter

    shard = inspected[-1].decisions[0]
    exact = b"x" * 2_097_152
    monkeypatch.setattr(exporter, "canonical_bytes", lambda model: exact)
    assert exporter.checked_shard_bytes(shard) == exact
    monkeypatch.setattr(exporter, "canonical_bytes", lambda model: exact + b"x")
    with pytest.raises(ValueError, match="2097153 > 2097152"):
        exporter.checked_shard_bytes(shard)


@pytest.mark.parametrize("kind", ["index", "decision", "sample"])
def test_unknown_inspection_fields_refuse(inspected, kind):
    root, _, _, _, verified = inspected
    if kind == "index":
        model = export_inspection(verified, root / "unknown-fields")
    elif kind == "decision":
        model = verified.decisions[0]
    else:
        model = verified.samples[0]
    raw = model.model_dump(mode="json")
    raw["undeclared"] = "refuse"
    with pytest.raises(ValueError):
        type(model).model_validate(raw)


def test_recent_suffix_over_eight_refuses(inspected):
    sample = next(s for s in inspected[-1].samples if len(s.recent_experience) == 8)
    assert sample.retained_record_count > 8
    assert sample.recent_experience[-1].sequence == sample.next_sequence - 1
    raw = sample.model_dump(mode="json")
    raw["recent_experience"].append(raw["recent_experience"][-1])
    with pytest.raises(ValueError, match="count"):
        ResidentInspection.model_validate(raw)


def test_missing_boundary_and_orphan_tail_refuse_without_source_repair(inspected, tmp_path):
    import shutil

    _, source, replay, reader, _ = inspected
    incomplete = tmp_path / "incomplete"
    shutil.copytree(source, incomplete)
    missing = incomplete / "checkpoint-0000000001.json"
    missing.unlink()  # One explicit fixture file; no recursive deletion.
    with pytest.raises((OSError, ValueError)):
        verify_inspection_source(incomplete, replay, repository=ROOT, source_reader=reader)
    assert not missing.exists()
    orphan = tmp_path / "orphan"
    shutil.copytree(source, orphan)
    calls = orphan / "llm-calls.jsonl"
    original = calls.read_bytes()
    calls.write_bytes(original + original.splitlines(keepends=True)[-1])
    with pytest.raises(ValueError, match="orphan.*extra_records=1"):
        verify_inspection_source(orphan, replay, repository=ROOT, source_reader=reader)
    assert calls.read_bytes() == original + original.splitlines(keepends=True)[-1]


def test_decision_call_hash_or_missing_reference_refuses(inspected):
    shard = inspected[-1].decisions[0]
    raw = shard.model_dump(mode="json")
    raw["calls"][0]["dispatch_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="hash"):
        DecisionInspection.model_validate(raw)
    raw = shard.model_dump(mode="json")
    raw["calls"] = []
    with pytest.raises(ValueError, match="call chain"):
        DecisionInspection.model_validate(raw)


def test_cli_inspect_and_missing_case_report_are_offline(inspected, tmp_path, capsys, monkeypatch):
    from scripts import p3_trials
    from scripts.p3_experiments import main

    root, source, replay, _, _ = inspected

    def forbidden(*args, **kwargs):
        raise AssertionError("offline command touched live authority")

    monkeypatch.setattr(p3_trials, "_live_store", forbidden)
    monkeypatch.setattr(p3_trials, "live_locations", forbidden)
    assert (
        main(
            [
                "--repository",
                str(ROOT),
                "inspect",
                "--source-run",
                str(source),
                "--replay",
                str(replay),
                "--out",
                str(root / "cli-inspection"),
            ]
        )
        == 0
    )
    exported = json.loads(capsys.readouterr().out)
    assert exported["samples"] == 9
    registration = p3_trials.build_registration(
        ROOT,
        p3_trials.git(ROOT, "rev-parse", "HEAD").decode().strip(),
        purpose="fake",
        registration_id="p307-missing-case",
    )
    path = tmp_path / "registration.json"
    path.write_bytes(canonical_bytes(registration))
    for command in ("validate", "report"):
        args = [
            "--repository",
            str(ROOT),
            command,
            "--registration",
            str(path),
            "--receipts",
            str(tmp_path / "no-receipts"),
        ]
        if command == "report":
            args += ["--out", str(tmp_path / "report")]
        assert main(args) == 1
        report = json.loads(capsys.readouterr().out)
        assert report["technical"] == "FAIL"
        assert report["cases_expected"] == 1
        assert report["cases"][registration.cases[0].case_id]["metrics"] is None
        assert report["live_provider_calls"] == report["live_authority_accesses"] == 0


def test_same_boundary_continuations_use_nearest_first_locators(tmp_path):
    from living_island.sim.p3 import resume_p3

    content, files, case, store, reader, fallback = _three_actor_case(
        tmp_path, fixture=True, horizon=2
    )
    provider = fixture_provider("recent-only", 1, horizon=2)
    selector = fixture_selector()
    kwargs = {
        "allocation_store": store,
        "provider": provider,
        "fallback": fallback,
        "source_reader": reader,
        "selector": selector,
        "selector_sha256": selector.implementation_sha256,
    }
    original = run_p3(content, files, case, tmp_path / "original", ticks=1, **kwargs)
    origin = original.output / "checkpoint-0000000001.json"
    middle = resume_p3(origin, tmp_path / "middle", ticks=0, **kwargs)
    middle_path = middle.output / origin.name
    nearest = resume_p3(
        middle_path, tmp_path / "nearest", ticks=0, ancestors=middle.ancestors, **kwargs
    )
    near_path = nearest.output / origin.name
    assert origin.read_bytes() == middle_path.read_bytes() == near_path.read_bytes()
    final = resume_p3(near_path, tmp_path / "final", ticks=1, ancestors=nearest.ancestors, **kwargs)
    replay = tmp_path / "continued-replay.json"
    export_p3_replay(final.output, replay, ancestors=final.ancestors, source_reader=reader)
    verified = verify_inspection_source(
        final.output, replay, repository=ROOT, ancestors=final.ancestors, source_reader=reader
    )
    assert len(verified.samples) == 9
    assert all(s.latest_perception_tick == s.tick - 1 for s in verified.samples)
    index = export_inspection(verified, tmp_path / "inspection")
    assert len(index.samples) == 9


def test_cli_refuses_competing_completed_receipts_before_artifact_use(tmp_path):
    from scripts import p3_trials
    from scripts.p3_experiments import _receipt

    from living_island.persistence.p3_inspection import GitSourceReader

    head = p3_trials.git(ROOT, "rev-parse", "HEAD").decode().strip()
    registration = p3_trials.build_registration(
        ROOT, head, purpose="fake", registration_id="p307-receipts"
    )
    case_id = registration.cases[0].case_id
    from living_island.contract.p3_inspection import canonical_sha256

    registration_hash = canonical_sha256(registration)
    receipt = {
        "receipt_schema_version": "0.1",
        "registration_sha256": registration_hash,
        "registration_commit": head,
        "executed_commit": head,
        "case_id": case_id,
        "command": ["offline-fixture"],
        "status": "complete",
        "exit_code": 0,
        "trace_sha256": "a" * 64,
        "failure": None,
        "run_directory": str(tmp_path / "absent-source"),
        "allocation_key": canonical_sha256(
            {"registration_sha256": registration_hash, "case_id": case_id}
        ),
    }
    primary = tmp_path / f"{case_id}.json"
    primary.write_bytes(canonical_bytes(receipt))
    (tmp_path / "competing.json").write_bytes(
        canonical_bytes({**receipt, "trace_sha256": "b" * 64})
    )
    with pytest.raises(ValueError, match="competing completed receipt"):
        _receipt(
            primary,
            registration,
            case_id,
            ROOT,
            tmp_path / "registration.json",
            GitSourceReader(ROOT),
        )


ACCOUNTING_FIXTURE = ROOT / "backend/tests/fixtures/p3/evaluation/accounting"


def accounting_archive(tmp_path):
    """Relocate an actual committed four-tick fake run; never read live authority."""
    import tarfile
    from pathlib import Path

    from scripts.p3_trials import CaseReceipt, git

    from living_island.contract.p3_inspection import canonical_sha256

    archive = tmp_path / "archive"
    source = archive / "source"
    source.mkdir(parents=True)
    provenance = json.loads((ACCOUNTING_FIXTURE / "provenance.json").read_bytes())
    for name, digest in provenance["files"].items():
        assert sha256((ACCOUNTING_FIXTURE / name).read_bytes()).hexdigest() == digest
    with tarfile.open(ACCOUNTING_FIXTURE / "source.tar.gz", "r:gz") as tar:
        for member in tar.getmembers():
            assert member.isfile() and Path(member.name).name == member.name
            stream = tar.extractfile(member)
            assert stream is not None
            (source / member.name).write_bytes(stream.read())
    for name in ("registration.json", "fake-allocation.json", "unissued-pilot.json"):
        (archive / name).write_bytes((ACCOUNTING_FIXTURE / name).read_bytes())
    registration = json.loads((archive / "registration.json").read_bytes())
    snapshot = json.loads((archive / "fake-allocation.json").read_bytes())
    relative = (ACCOUNTING_FIXTURE / "registration.json").relative_to(ROOT).as_posix()
    commit = git(ROOT, "log", "-1", "--format=%H", "--", relative).decode().strip()
    receipt = CaseReceipt(
        receipt_schema_version="0.1",
        registration_sha256=canonical_sha256(registration),
        registration_commit=commit,
        executed_commit=provenance["implementation_commit"],
        case_id=registration["cases"][0]["case_id"],
        command=["retained-offline-perf-fixture"],
        status="complete",
        exit_code=0,
        trace_sha256=sha256((source / "decision-trace-p3.json").read_bytes()).hexdigest(),
        failure=None,
        run_directory=provenance["original_run_directory"],
        allocation_key=snapshot["allocation_key"],
    )
    (archive / "receipt.json").write_bytes(canonical_bytes(receipt))
    manifest = {
        "evidence_manifest_version": "0.1",
        "artifacts": [],
        "registrations": [
            {
                "registration": "registration.json",
                "repository_path": relative,
                "cases": [
                    {
                        "case_id": receipt.case_id,
                        "receipts": ["receipt.json"],
                        "runs": [
                            {
                                "directory": "source",
                                "original_run_directory": receipt.run_directory,
                                "ancestors": [],
                            }
                        ],
                    }
                ],
            }
        ],
        "pilot": "unissued-pilot.json",
        "cr007": None,
        "cr008": None,
        "allocations": ["fake-allocation.json"],
    }
    path = archive / "manifest.json"
    rewrite_manifest(path, manifest)
    return path, manifest


def rewrite_manifest(path, manifest):
    manifest["artifacts"] = [
        {
            "path": p.relative_to(path.parent).as_posix(),
            "sha256": sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(path.parent.rglob("*"))
        if p.is_file() and p != path
    ]
    path.write_bytes(canonical_bytes(manifest))
    return sha256(path.read_bytes()).hexdigest()


def archive_sentinels(monkeypatch):
    from scripts import p3_trials

    from living_island.agents.llm import provider
    from living_island.persistence import p3_allocation
    from living_island.sim import p3

    def denied(*args, **kwargs):
        raise AssertionError("offline archive touched a provider/live authority/lock/grant")

    for name in ("live_locations", "_live_store", "initialize_authority", "enroll_registration"):
        monkeypatch.setattr(p3_trials, name, denied)
    for name in ("AllocationStore", "_ProcessLock", "initialize_pilot"):
        monkeypatch.setattr(p3_allocation, name, denied)
    monkeypatch.setattr(p3, "AllocationStore", denied)
    monkeypatch.setattr(provider.DeepSeekResponsesAdapter, "complete", denied)


def test_actual_archived_fake_report_external_anchor_and_source_preservation(
    tmp_path, monkeypatch, capsys
):
    from scripts.p3_experiments import main

    path, manifest = accounting_archive(tmp_path)
    archive_sentinels(monkeypatch)
    before = {
        p.relative_to(path.parent): p.read_bytes() for p in path.parent.rglob("*") if p.is_file()
    }
    digest = sha256(path.read_bytes()).hexdigest()
    assert (
        main(
            [
                "report",
                "--evidence-manifest",
                str(path),
                "--trusted-owner-evidence-sha256",
                digest,
                "--out",
                str(tmp_path / "report"),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert json.loads((tmp_path / "report/report.json").read_bytes()) == report
    assert report["technical"] == report["accounting"]["technical"] == "PASS"
    assert report["accounting"]["issuance_proof"] == "VERIFIED_ARCHIVE"
    assert report["accounting"]["cost_ceiling_micro_cny"] == 0
    assert all(s["issuance_status"] == "UNISSUED" for s in report["accounting"]["slots"])
    assert report["accounting"]["allocations"][0]["charged"]["attempts"] == 12
    assert report["live_authority_accesses"] == report["live_provider_calls"] == 0
    assert (
        next(iter(report["registrations"][0]["cases"].values()))["recorded_proof"][
            "provider_accesses"
        ]
        == 0
    )
    assert before == {
        p.relative_to(path.parent): p.read_bytes() for p in path.parent.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-anchor",
        "missing-anchor",
        "changed-bytes",
        "version",
        "duplicate-json",
        "extra-field",
        "missing-registration",
        "missing-receipt",
        "missing-checkpoint",
        "missing-allocation",
        "early-end",
        "receipt-conflict",
    ],
)
def test_archive_refuses_incomplete_or_untrusted_evidence(tmp_path, monkeypatch, capsys, mutation):
    from scripts.p3_experiments import main

    path, manifest = accounting_archive(tmp_path)
    archive_sentinels(monkeypatch)
    anchor = sha256(path.read_bytes()).hexdigest()
    if mutation == "wrong-anchor":
        anchor = "0" * 64
    elif mutation == "changed-bytes":
        (path.parent / "source/prompt.txt").write_bytes(b"changed")
    elif mutation == "version":
        manifest["evidence_manifest_version"] = "9.9"
        anchor = rewrite_manifest(path, manifest)
    elif mutation == "extra-field":
        manifest["self_approved_digest"] = anchor
        anchor = rewrite_manifest(path, manifest)
    elif mutation == "duplicate-json":
        path.write_bytes(b'{"evidence_manifest_version":"0.1",' + path.read_bytes()[1:])
        anchor = sha256(path.read_bytes()).hexdigest()
    elif mutation.startswith("missing-") and mutation != "missing-anchor":
        target = {
            "missing-registration": "registration.json",
            "missing-receipt": "receipt.json",
            "missing-checkpoint": "source/checkpoint-0000000004.json",
            "missing-allocation": "fake-allocation.json",
        }[mutation]
        (
            path.parent / target
        ).unlink()  # One explicit fixture file, never a source or recursive deletion.
    elif mutation == "early-end":
        value = json.loads((path.parent / "receipt.json").read_bytes())
        value.update(status="failed", exit_code=1, trace_sha256=None, failure="early end")
        (path.parent / "receipt.json").write_bytes(canonical_bytes(value))
        anchor = rewrite_manifest(path, manifest)
    elif mutation == "receipt-conflict":
        value = json.loads((path.parent / "receipt.json").read_bytes())
        value["trace_sha256"] = "0" * 64
        (path.parent / "fork.json").write_bytes(canonical_bytes(value))
        manifest["registrations"][0]["cases"][0]["receipts"].append("fork.json")
        anchor = rewrite_manifest(path, manifest)
    args = ["validate", "--evidence-manifest", str(path)]
    if mutation != "missing-anchor":
        args += ["--trusted-owner-evidence-sha256", anchor]
    assert main(args) == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out or captured.err)
    assert report.get("technical", report.get("status")) == "FAIL"
    assert report["accounting"]["technical"] == "FAIL"
    assert report["accounting"]["cost_ceiling_micro_cny"] is None


@pytest.mark.parametrize(
    "member",
    [
        "../escape",
        "/absolute",
        "D:/drive",
        "//host/share",
        "source\\prompt.txt",
        "source/../prompt.txt",
        "source//prompt.txt",
        "source/prompt.txt.",
        "source/prompt.txt ",
    ],
)
def test_archive_unsafe_locator_refused(tmp_path, member):
    from scripts.p3_experiments import ArchiveReader

    path, manifest = accounting_archive(tmp_path)
    manifest["artifacts"][0]["path"] = member
    path.write_bytes(canonical_bytes(manifest))
    with pytest.raises((ValueError, OSError)):
        ArchiveReader(path, sha256(path.read_bytes()).hexdigest())


def test_archive_alias_and_unlisted_ancestor_refused(tmp_path):
    from scripts.p3_experiments import ArchiveReader

    path, manifest = accounting_archive(tmp_path)
    row = next(a for a in manifest["artifacts"] if a["path"] == "receipt.json")
    manifest["artifacts"].append({**row, "path": "RECEIPT.json"})
    path.write_bytes(canonical_bytes(manifest))
    with pytest.raises((ValueError, OSError)):
        ArchiveReader(path, sha256(path.read_bytes()).hexdigest())
    manifest["artifacts"].pop()
    manifest["registrations"][0]["cases"][0]["runs"][0]["ancestors"] = ["../escape.json"]
    path.write_bytes(canonical_bytes(manifest))
    with pytest.raises(ValueError):
        ArchiveReader(path, sha256(path.read_bytes()).hexdigest())


def test_missing_paid_case_never_reports_passing_zero_cost(tmp_path, monkeypatch, capsys):
    from scripts.p3_experiments import main

    archive_sentinels(monkeypatch)
    registration = ROOT / "content/experiments/p3/development/p3-smoke-r1.json"
    assert (
        main(
            [
                "validate",
                "--registration",
                str(registration),
                "--receipts",
                str(tmp_path / "absent"),
            ]
        )
        == 1
    )
    report = json.loads(capsys.readouterr().out)
    accounting = report["accounting"]
    assert accounting["technical"] == accounting["arithmetic_status"] == "FAIL"
    assert accounting["issuance_proof"] == "MISSING"
    assert accounting["cost_ceiling_micro_cny"] is None
    assert accounting["known_subtotal_micro_cny"] == 0
    assert accounting["allocations"][0]["charged"] is None
    assert accounting["allocations"][0]["missing_sources"]
    assert all(s["issuance_status"] == "UNKNOWN" for s in accounting["slots"])


@pytest.mark.parametrize(
    "mutation",
    [
        "head-hash",
        "head-manifest",
        "head-original-path",
        "head-cursor",
        "entry-debit",
        "incomplete",
        "receipt-allocation",
    ],
)
def test_archive_snapshot_receipt_checkpoint_bridge(tmp_path, monkeypatch, mutation):
    from scripts.p3_experiments import evaluate_archive

    path, manifest = accounting_archive(tmp_path)
    archive_sentinels(monkeypatch)
    snapshot_path = path.parent / "fake-allocation.json"
    snapshot = json.loads(snapshot_path.read_bytes())
    if mutation == "head-hash":
        snapshot["head"]["checkpoint_sha256"] = "0" * 64
    elif mutation == "head-manifest":
        snapshot["head"]["input_manifest_sha256"] = "0" * 64
    elif mutation == "head-original-path":
        snapshot["head"]["run_directory"] = "Z:/never-follow-this-authority-path"
    elif mutation == "head-cursor":
        snapshot["head"]["reservation_cursor"] -= 1
    elif mutation == "entry-debit":
        snapshot["entries"][-1]["debit"]["input_charged"] += 1
    elif mutation == "incomplete":
        snapshot["status"] = "running"
    else:
        receipt_path = path.parent / "receipt.json"
        receipt = json.loads(receipt_path.read_bytes())
        receipt["allocation_key"] = "0" * 64
        receipt_path.write_bytes(canonical_bytes(receipt))
    snapshot_path.write_bytes(canonical_bytes(snapshot))
    digest = rewrite_manifest(path, manifest)
    try:
        report = evaluate_archive(path, trusted_owner_digest=digest, repository=ROOT, output=None)
    except ValueError as exc:
        assert "conflicting copied reservation" in str(exc)
    else:
        assert report["technical"] == report["accounting"]["technical"] == "FAIL"
        assert report["accounting"]["cost_ceiling_micro_cny"] is None
        assert report["accounting"]["errors"]


def test_archive_output_and_duplicate_registration_refused(tmp_path):
    from scripts.p3_experiments import evaluate_archive

    path, manifest = accounting_archive(tmp_path)
    with pytest.raises(ValueError, match="outside the immutable archive"):
        evaluate_archive(
            path,
            trusted_owner_digest=sha256(path.read_bytes()).hexdigest(),
            repository=ROOT,
            output=path.parent / "report",
        )
    manifest["registrations"].append(manifest["registrations"][0])
    digest = rewrite_manifest(path, manifest)
    with pytest.raises(ValueError, match="duplicate archived registration"):
        evaluate_archive(path, trusted_owner_digest=digest, repository=ROOT, output=None)


def test_archive_directory_link_escape_refused(tmp_path):
    import os
    import subprocess

    from scripts.p3_experiments import ArchiveReader

    path, manifest = accounting_archive(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_bytes(b"outside")
    link = path.parent / "linked"
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    manifest["artifacts"].append(
        {"path": "linked/secret.json", "sha256": sha256(b"outside").hexdigest()}
    )
    path.write_bytes(canonical_bytes(manifest))
    with pytest.raises(ValueError, match="symlink/junction"):
        ArchiveReader(path, sha256(path.read_bytes()).hexdigest())


def test_missing_registration_path_has_unknown_total(tmp_path, capsys):
    from scripts.p3_experiments import main

    assert (
        main(
            [
                "validate",
                "--registration",
                str(tmp_path / "missing.json"),
                "--receipts",
                str(tmp_path / "missing-receipts"),
            ]
        )
        == 1
    )
    report = json.loads(capsys.readouterr().err)
    assert report["accounting"]["technical"] == "FAIL"
    assert report["accounting"]["cost_ceiling_micro_cny"] is None
