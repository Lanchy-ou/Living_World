"""Run paired compatibility cases and publish the CT-06 prerequisite."""

from collections.abc import Iterator
from dataclasses import asdict
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from living_island.persistence.v2.journal import store_once
from living_island.persistence.v2.manifest import Digest
from living_island.sim.equivalence.projection import read_projection
from living_island.sim.v2 import cli
from living_island.world.v2.protocol import ProtocolModel
from living_island.world.v2.rules.schema import content_hash

from ..receipts import CasePlan, Evidence, Inputs, file_digest
from ..runtime import Scenario, run_or_resume
from .comparison import TraceBoundary, TraceComparison, compare_traces
from .fixtures import CalibrationCase, calibration_cases, generic_failure_difference
from .pins import EquivalenceCase, EquivalencePin, calibration_pins, read_equivalence
from .recording import Mode, scenario, verified_trace

MODES: tuple[Mode, Mode] = ("bridge", "visible")


class ArmReceipt(ProtocolModel):
    inputs: Inputs
    evidence_path: str
    evidence_sha256: Digest


class PairResult(ProtocolModel):
    case: str
    residents: tuple[str, ...]
    fixture_sha256: Digest
    restore_after: int | None
    en08_projection_sha256: Digest | None
    arms: dict[Mode, ArmReceipt]
    comparison: TraceComparison


def record_pair(
    out: Path, case: CalibrationCase, revision: str, en08: EquivalenceCase | None = None
) -> PairResult:
    directory = out / case.name
    inputs = directory / "config"
    prepared = case.prepare(inputs)
    actors = tuple(actor.id for actor in prepared.config.residents)
    fixture_hash = file_digest(case.fixture_input)
    oracle = read_projection(case.archive) if case.archive is not None else None
    if oracle is not None:
        source = oracle.source
        actual = asdict(prepared.bound.manifest)
        if (oracle.case, oracle.config, source.model_dump(include=set(actual))) != (
            case.name,
            case.config,
            actual,
        ):
            raise ValueError(f"{case.name}: fixture source/config/map does not match setup")
        if en08 is not None and (
            en08.source != source or en08.rule_library_hash != prepared.bound.pack.rule_library_hash
        ):
            raise ValueError(f"{case.name}: EN-08 source or rule library differs from setup")

    plan = CasePlan(
        revision=revision,
        runner="CT-04/PR-07",
        controller=content_hash(prepared.policy_config.model_dump(mode="json")),
        setup=fixture_hash,
        observer="CT-20/1",
        arm="bridge",
        case_index=0,
        horizon=case.end - case.start,
        checkpoint_every=24,
    )
    evidence: dict[Mode, Evidence] = {}
    arms: dict[Mode, ArmReceipt] = {}
    for index, mode in enumerate(MODES):
        arm = directory / mode
        arm_plan = plan.model_copy(update={"arm": mode, "case_index": index})

        def setup(mode: Mode = mode, arm: Path = arm) -> Scenario:
            return scenario(case.prepare(inputs), mode, arm / "trace")

        # Each specified fixture cut reopens its saved policy and pending delivery once.
        record = partial(run_or_resume, arm, arm_plan, setup)
        progress = record(pause_after=lambda tick: tick == case.restore_after)
        if progress.evidence is None:
            progress = record()
        assert progress.evidence is not None
        evidence[mode] = progress.evidence
        path = arm / "evidence.json"
        arms[mode] = ArmReceipt(
            inputs=Inputs.model_validate_json((arm / "inputs.json").read_bytes()),
            evidence_path=path.relative_to(out).as_posix(),
            evidence_sha256=file_digest(path),
        )

    def trace(mode: Mode) -> Iterator[TraceBoundary]:
        return verified_trace(directory / mode / "trace", evidence[mode])

    result = compare_traces(
        case.seed,
        case.start,
        plan.horizon,
        actors,
        trace("bridge"),
        trace("visible"),
        oracle=oracle,
        en08_sha256=None if en08 is None else en08.v2_projection_sha256,
    )
    if result.status == "equal" and oracle is None:
        difference = generic_failure_difference(next(trace("visible")))
        if difference is not None:
            result = result.model_copy(update={"status": "different", "difference": difference})
    pair = PairResult(
        case=case.name,
        residents=actors,
        fixture_sha256=fixture_hash,
        arms=arms,
        comparison=result,
        restore_after=case.restore_after,
        en08_projection_sha256=None if en08 is None else en08.v2_projection_sha256,
    )
    store_once(directory / "comparison.json", cli.report_bytes(pair.model_dump(mode="json")))
    return pair


class CalibrationReceipt(ProtocolModel):
    version: Literal["ct20/1"] = "ct20/1"
    status: Literal["equal", "different", "incomplete"]
    en08: EquivalencePin
    executable: dict[str, str]
    cases: tuple[PairResult, ...]
    missing_cases: tuple[str, ...]


def run(out: Path, en08_directory: Path) -> CalibrationReceipt:
    en08, equivalence = read_equivalence(en08_directory)
    pins = calibration_pins()
    cases = sorted(calibration_cases(out / "config"), key=lambda case: case.script is None)
    fixtures = {case.name: file_digest(case.fixture_input) for case in cases}
    registration = {"en08": en08.model_dump(), "executable": pins, "fixtures": fixtures}
    store_once(out / "registration.json", cli.report_bytes(registration))
    pairs: list[PairResult] = []
    status: Literal["equal", "different", "incomplete"] = "equal"
    for case in cases:
        reference = equivalence[case.name] if case.script is None else None
        pair = record_pair(out, case, content_hash(pins), reference)
        pairs.append(pair)
        status = pair.comparison.status
        if status != "equal":
            break
    receipt = CalibrationReceipt(
        status=status,
        en08=en08,
        executable=pins,
        cases=tuple(pairs),
        missing_cases=tuple(case.name for case in cases[len(pairs) :]),
    )
    store_once(out / "receipt.json", cli.report_bytes(receipt.model_dump(mode="json")))
    return receipt


def require_calibration(
    directory: Path, *, en08_revision: str, receipt_sha256: str
) -> CalibrationReceipt:
    """CT-06 calls this before each round with the reviewed digest and verified EN-08 revision."""
    path = directory / "receipt.json"
    if file_digest(path) != receipt_sha256:
        raise ValueError(f"{path}: reviewed CT-05 receipt digest differs")
    receipt = CalibrationReceipt.model_validate_json(path.read_bytes())
    if receipt.en08.revision != en08_revision or calibration_pins() != receipt.executable:
        raise ValueError(
            "recalibrate: EN-08 revision, implementation, policy or fixture pins changed"
        )
    with TemporaryDirectory() as scratch:
        required = {
            case.name: file_digest(case.fixture_input) for case in calibration_cases(Path(scratch))
        }
    matched = {
        row.case: row.fixture_sha256 for row in receipt.cases if row.comparison.status == "equal"
    }
    if (
        receipt.status != "equal"
        or receipt.missing_cases
        or matched != required
        or len(receipt.cases) != len(required)
    ):
        raise ValueError("recalibrate: fixture or seed coverage is incomplete or different")
    return receipt
