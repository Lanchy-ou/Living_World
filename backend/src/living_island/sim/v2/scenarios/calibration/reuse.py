"""Read an earlier CT-04 handoff when its complete case inputs still match."""

import gzip
import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from living_island.sim.v2 import cli
from living_island.world.v2.rules import Pack
from living_island.world.v2.rules.schema import canonical_json_bytes

from ..receipts import CaseReceipt, Evidence, Inputs, checkpoints, file_digest
from ..runtime import _verified_evidence


def reusable_evidence(
    arm: Path, expected: Inputs, pack: Pack, *, restore_after: int | None = None
) -> Evidence | None:
    """Return a verified prior handoff, or a cache miss for an absent or changed case."""
    name = str(expected.plan.case_index)
    if not (arm / "cases" / f"{name}.json").is_file():
        return None
    archive = arm / "inputs" / f"{name}.json.gz"
    receipt = CaseReceipt.model_validate(cli.run_recorded(archive, arm, expected.plan.horizon))
    raw = gzip.decompress(archive.read_bytes())
    if raw != canonical_json_bytes(expected.model_dump(mode="json")):
        return None
    uri = (arm / "progress.sqlite").resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        points = checkpoints(db)
        if (
            restore_after is not None
            and db.execute(
                "SELECT 1 FROM attempts WHERE resumed_tick = ? LIMIT 1", (restore_after,)
            ).fetchone()
            is None
        ):
            # A direct control has identical simulation inputs but cannot witness a restore.
            return None
    end = expected.opening_tick + expected.plan.horizon
    if not points or (points[0].tick, points[-1].tick) != (expected.opening_tick, end):
        raise ValueError(f"{arm}: prior checkpoints do not cover the requested horizon")
    observed = _verified_evidence(arm, expected, pack, points)
    digest = sha256(canonical_json_bytes(observed.model_dump(mode="json"))).hexdigest()
    if (
        observed.final_tick != end
        or observed.inputs_sha256 != sha256(raw).hexdigest()
        or (receipt.evidence_path, receipt.timing_db) != ("evidence.json", "progress.sqlite")
        or receipt.evidence_sha256 != digest
        or file_digest(arm / "evidence.json") != digest
    ):
        raise ValueError(f"{arm}: prior evidence differs from the verified CT-04 handoff")
    return observed
