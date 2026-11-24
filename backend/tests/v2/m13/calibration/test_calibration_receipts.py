"""Admission of EN-08 evidence and the reviewed CT-06 prerequisite."""

import json
from dataclasses import replace

import pytest


@pytest.fixture
def en08_report(tmp_path):
    from living_island.sim.v2 import cli
    from living_island.sim.v2.scenarios.calibration import pins
    from living_island.sim.v2.scenarios.receipts import file_digest

    revision = pins.git("rev-parse", "HEAD")
    directory = tmp_path / f"acceptance-{revision}"
    (directory / "cases").mkdir(parents=True)
    rows = []
    digest = "8" * 64
    for name in cli.matrix_names():
        if name.startswith("acceptance-"):
            source = {
                "v1_source_commit": revision,
                "config_blob_sha256": digest,
                "effective_config_sha256": digest,
                "map_blob_sha256": digest,
                "map_sha256": digest,
                "seed": int(name.rsplit("-", 1)[1]),
            }
            row = {
                "case": name,
                "config": "production",
                "policy": "base",
                "source": source,
                "projection_sha256": file_digest(cli.FIXTURES / "matrix" / f"{name}.json.gz"),
                "rule_library_hash": digest,
                "matched_boundaries": 1009,
                "difference": None,
                "v2_projection_sha256": digest,
                "packet_receipt_sha256": digest,
                "declared_exceptions": dict.fromkeys(cli.EXCEPTION_NAMES, 0),
            }
            (directory / "cases" / f"{name}.json").write_bytes(cli.report_bytes(row))
            rows.append(row)
    scope = {"through": 1008, "git": pins._trees(revision, pins._PR07_SCOPE)}
    (directory / "scope.json").write_bytes(cli.report_bytes(scope))
    (directory / "report.json").write_bytes(cli.report_bytes(rows))
    return directory


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("scope", "scope differs"),
        ("implementation", "inputs differ"),
        ("missing seed", "coverage: missing"),
        ("duplicate seed", "extra"),
        ("partial", "matched_boundaries"),
        ("case receipt", "aggregate report"),
        ("oracle digest", "archived projection differs"),
    ],
)
def test_en08_refuses_unverified_inputs(en08_report, change, message, monkeypatch):
    from living_island.sim.v2 import cli
    from living_island.sim.v2.scenarios.calibration import pins

    report = en08_report / "report.json"
    rows = json.loads(report.read_bytes())
    row = rows[0]
    case = en08_report / "cases" / f"{row['case']}.json"
    if change == "scope":
        path = en08_report / "scope.json"
        scope = json.loads(path.read_bytes())
        scope["git"]["backend/src"] = "0" * 40
        path.write_bytes(cli.report_bytes(scope))
    elif change == "implementation":
        trees = pins._trees

        def changed(revision, paths):
            current = trees(revision, paths)
            if revision == "HEAD":
                current["backend/uv.lock"] = "0" * 40
            return current

        monkeypatch.setattr(pins, "_trees", changed)
    elif change == "missing seed":
        rows.pop()
    elif change == "duplicate seed":
        rows.append(row)
    elif change == "partial":
        row["matched_boundaries"] = 1008
    elif change == "case receipt":
        case.write_bytes(cli.report_bytes({**row, "packet_receipt_sha256": "0" * 64}))
    else:
        row["projection_sha256"] = "0" * 64
        case.write_bytes(cli.report_bytes(row))
    report.write_bytes(cli.report_bytes(rows))
    with pytest.raises(ValueError, match=message):
        pins.read_equivalence(en08_report)


def test_en08_absent_or_ambiguous_requires_locator(en08_report, tmp_path):
    from living_island.sim.v2.scenarios.calibration.pins import find_evidence

    assert find_evidence(tmp_path) == en08_report
    with pytest.raises(ValueError, match="found 0"):
        find_evidence(tmp_path / "absent")
    another = tmp_path / ("acceptance-" + "7" * 40)
    another.mkdir()
    (another / "report.json").write_bytes(b"[]")
    with pytest.raises(ValueError, match="found 2"):
        find_evidence(tmp_path)


@pytest.mark.parametrize("changed", ["fixture", "en08"])
def test_case_refuses_wrong_archived_input_before_recording(tmp_path, en08_report, changed):
    from living_island.sim.v2.scenarios.calibration import campaign
    from living_island.sim.v2.scenarios.calibration.pins import read_equivalence

    cases = campaign.calibration_cases(tmp_path / "config")
    case = next(case for case in cases if case.name == "wap23-reply-first-reply")
    reference = None
    if changed == "fixture":
        case = replace(case, name="wrong-fixture")
        message = "does not match setup"
    else:
        _, rows = read_equivalence(en08_report)
        reference = next(iter(rows.values()))
        message = "EN-08 source or rule library"
    with pytest.raises(ValueError, match=message):
        campaign.record_pair(tmp_path, case, "test", reference)
    assert not (tmp_path / case.name / "bridge").exists()


def test_ct06_admits_reviewed_complete_receipt_and_refuses_changed_inputs(
    tmp_path, en08_report, monkeypatch
):
    from living_island.sim.v2 import cli
    from living_island.sim.v2.scenarios.calibration import campaign
    from living_island.sim.v2.scenarios.receipts import file_digest

    # Exercise the normal campaign handoff at the one-tick DL-25 horizon.
    # The long acceptance registry stays in the offline command.
    registered = campaign.calibration_cases(tmp_path / "config")
    short = next(case for case in registered if case.archive is None)
    monkeypatch.setattr(campaign, "calibration_cases", lambda _: (short,))
    directory = tmp_path / "calibration"
    receipt = campaign.run(directory, en08_report)
    path = directory / "receipt.json"
    revision = receipt.en08.revision
    digest = file_digest(path)
    assert receipt.status == "equal" and receipt.cases[0].comparison.compared_boundaries == 1
    assert campaign.run(directory, en08_report) == receipt
    assert (
        campaign.require_calibration(directory, en08_revision=revision, receipt_sha256=digest)
        == receipt
    )
    # Rebuild the verdict from another directory without executing matched arms.
    with monkeypatch.context() as patch:
        patch.setattr(campaign, "run_or_resume", lambda *a, **kw: pytest.fail("reran matched arm"))
        reused = campaign.run(tmp_path / "rework", en08_report, reuse=(directory,))
    assert reused.cases[0].comparison == receipt.cases[0].comparison
    assert (
        reused.cases[0].arms["bridge"].evidence_sha256
        == receipt.cases[0].arms["bridge"].evidence_sha256
    )
    with pytest.raises(ValueError, match="digest differs"):
        campaign.require_calibration(directory, en08_revision=revision, receipt_sha256="0" * 64)
    with pytest.raises(ValueError, match="pins changed"):
        campaign.require_calibration(directory, en08_revision="0" * 40, receipt_sha256=digest)
    pair = receipt.cases[0]
    partial_pair = pair.model_copy(update={"arms": {"visible": pair.arms["visible"]}})
    partial = receipt.model_copy(update={"cases": (partial_pair,)})
    path.write_bytes(cli.report_bytes(partial.model_dump(mode="json")))
    with pytest.raises(ValueError, match="coverage"):
        campaign.require_calibration(
            directory, en08_revision=revision, receipt_sha256=file_digest(path)
        )


def test_parallel_calibration_preserves_serial_receipt(tmp_path, en08_report, monkeypatch):
    from living_island.sim.v2.scenarios.calibration import campaign

    names = ("wap23-reply-first-reply", "dl25-generic-act-no-item")
    register = campaign.calibration_cases

    def register_short_cases(directory):
        registered = {c.name: c for c in register(directory)}
        return tuple(registered[n] for n in names)

    monkeypatch.setattr(campaign, "calibration_cases", register_short_cases)
    serial, parallel = tmp_path / "serial", tmp_path / "parallel"
    receipt = campaign.run(serial, en08_report)
    assert receipt.status == "equal" and tuple(c.case for c in receipt.cases) == names
    for workers in (2, 1):
        assert campaign.run(parallel, en08_report, jobs=workers) == receipt
        assert (parallel / "receipt.json").read_bytes() == (serial / "receipt.json").read_bytes()
    for workers in (0, 5):
        with pytest.raises(ValueError, match="jobs"):
            campaign.run(parallel, en08_report, jobs=workers)

    blocked = tmp_path / "blocked"
    case = register_short_cases(blocked / "config")[0]
    held = blocked / case.name / "config" / f".{case.config}.toml.lock"
    held.parent.mkdir(parents=True)
    held.touch()
    with pytest.raises(ValueError, match="writer lock exists"):
        campaign.run(blocked, en08_report, jobs=2)
