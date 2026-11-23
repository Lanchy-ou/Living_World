"""Bind the M13 comparison to EN-08's completed PR-07 acceptance receipts."""

import subprocess
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from living_island.persistence.v2.manifest import Digest
from living_island.sim.equivalence.projection import Source
from living_island.sim.v2 import cli
from living_island.world.v2.protocol import ProtocolModel
from living_island.world.v2.rules.schema import content_hash

from ..receipts import file_digest

_BASE = "backend/src/living_island/"
_COMPAT = tuple(
    _BASE + path
    for path in (
        "agents/rule_based",
        "agents/runtime.py",
        "agents/types.py",
        "agents/policies",
        "persistence",
        "sim/equivalence",
        "sim/v2/compat",
        "sim/v2/cli.py",
        "sim/v2/runner.py",
        "sim/v2/turns.py",
        "sim/v2/manifest.py",
        "sim/decisions.py",
        "world",
    )
) + (
    "backend/uv.lock",
    "content/packs/compat-v1",
    "content/vocabulary",
)
_COMMON = (*_COMPAT, "backend/tests/fixtures/v1_projection")
_SCENARIOS = _BASE + "sim/v2/scenarios/"
_RUNTIME = (_SCENARIOS + "runtime.py", _SCENARIOS + "receipts.py")
_PR07_SCOPE = ("backend/src", "backend/uv.lock", "backend/tests/fixtures/v1_projection", "content")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cli.ROOT, text=True).strip()


def _trees(revision: str, paths: tuple[str, ...]) -> dict[str, str]:
    ids = git("rev-parse", *(f"{revision}:{path}" for path in paths)).splitlines()
    return dict(zip(paths, ids, strict=True))


def calibration_pins() -> dict[str, str]:
    return _trees("HEAD", (*_COMMON, *_RUNTIME, _SCENARIOS + "calibration"))


def recording_revision() -> str:
    """Pin code that produces an arm. CT-04 Inputs separately bind its fixture and pack."""
    recorder = _SCENARIOS + "calibration/"
    paths = (*_COMPAT, *_RUNTIME, recorder + "recording.py", recorder + "fixtures.py")
    return content_hash(_trees("HEAD", paths))


class EquivalenceCase(ProtocolModel):
    """PR-07's complete success format. Prefixes and differences cannot attest a week."""

    case: str
    config: Literal["production"]
    policy: Literal["base"]
    source: Source
    projection_sha256: Digest
    rule_library_hash: Digest
    difference: None
    matched_boundaries: Literal[1009]
    v2_projection_sha256: Digest
    packet_receipt_sha256: Digest
    declared_exceptions: dict[str, Literal[0]]


class _Scope(ProtocolModel):
    through: Literal[1008]
    git: dict[str, str]


class EquivalencePin(ProtocolModel):
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    report_sha256: Digest
    scope_sha256: Digest


def find_evidence(parent: Path) -> Path:
    candidates = sorted(parent.glob("acceptance-*/report.json"))
    if len(candidates) != 1:
        raise ValueError(f"{parent}: found {len(candidates)} EN-08 reports; select one with --en08")
    return candidates[0].parent


def read_equivalence(directory: Path) -> tuple[EquivalencePin, dict[str, EquivalenceCase]]:
    """Verify the producer's scope, aggregate report and per-seed receipts."""
    report = directory / "report.json"
    scope_path = directory / "scope.json"
    pin = EquivalencePin(
        revision=directory.name.removeprefix("acceptance-"),
        report_sha256=file_digest(report),
        scope_sha256=file_digest(scope_path),
    )
    scope = _Scope.model_validate_json(scope_path.read_bytes())
    if scope.git != _trees(pin.revision, _PR07_SCOPE):
        raise ValueError(f"{scope_path}: PR-07 scope differs from EN-08 revision {pin.revision}")
    expected = _trees(pin.revision, _COMMON)
    current = _trees("HEAD", _COMMON)
    changed = [path for path in expected if expected[path] != current[path]]
    if changed:
        raise ValueError(f"EN-08 executable or calibration inputs differ at {changed}")
    rows = TypeAdapter(list[EquivalenceCase]).validate_json(report.read_bytes())
    names = [name for name in cli.matrix_names() if name.startswith("acceptance-")]
    coverage = Counter(row.case for row in rows)
    wanted = Counter(names)
    if coverage != wanted:
        raise ValueError(
            f"EN-08 coverage: missing {list(wanted - coverage)}, extra {list(coverage - wanted)}"
        )
    for row in rows:
        receipt = directory / "cases" / f"{row.case}.json"
        if EquivalenceCase.model_validate_json(receipt.read_bytes()) != row:
            raise ValueError(f"{receipt}: EN-08 case differs from the aggregate report")
        oracle = cli.FIXTURES / "matrix" / f"{row.case}.json.gz"
        if row.projection_sha256 != file_digest(oracle):
            raise ValueError(f"{oracle}: archived projection differs from EN-08 receipt")
    return pin, {row.case: row for row in rows}
