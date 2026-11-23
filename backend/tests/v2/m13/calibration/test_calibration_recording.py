"""The archived successful accept saves a one-intent tail before its give."""

import sqlite3
from contextlib import closing
from shutil import copytree

import pytest


def test_ct20_resumes_mid_queue_and_consumes_the_give_once(recorded_mid_queue):
    from living_island.sim.v2.scenarios.calibration.recording import verified_trace
    from living_island.sim.v2.scenarios.receipts import Evidence, timing

    case, base, pair, direct = recorded_mid_queue
    assert pair.comparison.status == "equal", pair.comparison.difference
    receipt = pair.arms["visible"]
    path = base / receipt.evidence_path
    resumed = Evidence.model_validate_json(path.read_bytes())
    uri = (path.parent / "progress.sqlite").as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        paused, finished = timing(db, receipt.inputs.plan, case.end - case.start, True).attempts
    assert paused.status == "paused" and paused.last_checkpoint_tick == case.restore_after
    assert finished.resumed_tick == case.restore_after == 2
    assert resumed.final_snapshot_sha256 == direct.final_snapshot_sha256
    assert resumed.observer == direct.observer and resumed.prefix_sha256 == direct.prefix_sha256

    rows = list(verified_trace(path.parent / "trace", resumed))
    before, after, following = [rows[tick].actors["ryan"] for tick in (1, 2, 3)]
    assert [(intent.action_type, intent.intent_id) for intent in before.queue] == [
        ("give", "ryan:p000001:i1")
    ]
    assert after.queue == () and after.decision is None
    assert [
        row.tick
        for row in rows
        for turn in row.submissions
        if turn.actor_id == "ryan"
        and turn.action.kind == "intent"
        and turn.action.intent.action == "give"
    ] == [2]
    assert following.decision.triggers == ["PLAN_FINISHED"]
    assert following.decision.plan.intents[0].action_type == "gather"


def test_verified_trace_refuses_changed_observation(recorded_mid_queue, tmp_path):
    from living_island.sim.v2.scenarios.calibration.recording import verified_trace

    case, base, _, direct = recorded_mid_queue
    first = f"{case.start}.json"
    (tmp_path / first).write_bytes((base / "direct/trace" / first).read_bytes() + b"\n")
    with pytest.raises(ValueError, match="calibration observation digest differs at tick 0"):
        next(verified_trace(tmp_path, direct))


@pytest.mark.parametrize("changed", ["missing", "policy", "restore"])
def test_run_affected_arm_when_prior_evidence_cannot_supply_it(recorded_mid_queue, changed):
    from living_island.sim.v2.scenarios.calibration.reuse import reusable_evidence

    case, base, pair, _ = recorded_mid_queue
    inputs = pair.arms["visible"].inputs
    if changed == "policy":
        inputs = inputs.model_copy(
            update={"plan": inputs.plan.model_copy(update={"controller": "changed"})}
        )
    arm = base / ("absent" if changed == "missing" else "direct")
    cut = case.restore_after if changed == "restore" else None
    pack = case.prepare(base / "source").bound.pack
    assert reusable_evidence(arm, inputs, pack, restore_after=cut) is None


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        ("checkpoint-index", "checkpoints do not cover the requested horizon"),
        ("published-evidence", "prior evidence differs from the verified CT-04 handoff"),
    ],
)
def test_reuse_refuses_altered_completed_arm(recorded_mid_queue, tmp_path, damage, reason):
    from living_island.sim.v2.scenarios.calibration.reuse import reusable_evidence

    case, base, pair, _ = recorded_mid_queue
    arm = copytree(base / "direct", tmp_path / "prior")
    inputs = pair.arms["visible"].inputs
    if damage == "checkpoint-index":
        with closing(sqlite3.connect(arm / "progress.sqlite")) as db:
            db.execute("UPDATE checkpoints SET tick=tick+1 WHERE tick=?", (case.end,))
            db.commit()
    else:
        evidence = arm / "evidence.json"
        evidence.write_bytes(evidence.read_bytes() + b"\n")
    pack = case.prepare(base / "source").bound.pack
    with pytest.raises(ValueError, match=reason):
        reusable_evidence(arm, inputs, pack)
