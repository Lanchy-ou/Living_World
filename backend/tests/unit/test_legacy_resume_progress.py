"""Legacy checkpoints retain exactly the committed plan's actual remaining work."""

import json

import pytest
from test_engine_actions import content_with
from test_sim_boundaries import template
from test_sim_runs import _actor, _checkpoint, _script

from living_island.agents.policies._plans import WAIT
from living_island.persistence._codec import PersistenceError
from living_island.sim.runner import resume, run
from living_island.world.content import canonical_json_bytes
from living_island.world.protocol import Coord, TileTarget


def _altered_checkpoint(tmp_path, source, tick, change):
    data = json.loads(_checkpoint(source, tick).read_bytes())
    change(data)
    path = tmp_path / "altered.json"
    path.write_bytes(canonical_json_bytes(data))
    return path


@pytest.mark.parametrize(
    "defect", ["intent", "plan-id", "created-at", "truncated", "missing", "consumed", "duplicate"]
)
def test_resume_rejects_changed_or_incomplete_queue_before_creating_output(tmp_path, defect):
    content = content_with({"ella": (2, 3)})
    script = _script(tmp_path / "script.json", content, [_actor(plans=[[WAIT] * 3])])
    source, target = tmp_path / "source", tmp_path / "target"
    run(content, 1, source, script=script)

    def change(data):
        queued = data["agent_state"]["queued_plans"]
        plan = queued[0]
        if defect == "intent":
            plan["intents"][0]["action_type"] = "eat"
        elif defect == "plan-id":
            plan["plan_id"] = "ella:p000099"
            for index, intent in enumerate(plan["intents"], 1):
                intent.update(plan_id=plan["plan_id"], intent_id=f"{plan['plan_id']}:i{index}")
        elif defect == "created-at":
            plan["created_at_tick"] += 1
        elif defect == "truncated":
            plan["intents"].pop(0)
        elif defect == "missing":
            queued.clear()
        elif defect == "consumed":
            record = json.loads((source / "decisions.jsonl").read_bytes().splitlines()[0])
            plan["intents"] = record["plan"]["intents"]
        else:
            queued.append(plan.copy())

    checkpoint = _altered_checkpoint(tmp_path, source, 1, change)
    with pytest.raises(PersistenceError, match="queued_plans"):
        resume(checkpoint, source, 1, target)
    assert not target.exists()
    assert not list(tmp_path.glob(".target.resume-*"))


@pytest.mark.parametrize(
    "defect",
    ["intent", "consumed", "unstarted", "missing", "elapsed", "remaining", "started", "route"],
)
def test_resume_rejects_active_intent_or_progress_tampering(tmp_path, defect):
    content = content_with(
        {"ella": (6, 4)},
        map={"walk_cost_budget_per_tick": 2},
        perception={"day_radius_tiles": 10},
    )
    move = template("move_to", TileTarget(kind="tile", position=Coord(x=2, y=4)))
    script = _script(tmp_path / "script.json", content, [_actor(plans=[[WAIT, move, WAIT]])])
    source, target = tmp_path / "source", tmp_path / "target"
    run(content, 2, source, script=script)

    def change(data):
        actions = data["world"]["active_actions"]
        action = actions[0]
        if defect == "intent":
            action["intent"]["target"]["position"]["x"] += 1
        elif defect in ("consumed", "unstarted"):
            record = json.loads((source / "decisions.jsonl").read_bytes().splitlines()[0])
            action["intent"] = record["plan"]["intents"][0 if defect == "consumed" else 2]
        elif defect == "missing":
            actions.clear()
        elif defect == "elapsed":
            action["elapsed_ticks"] += 1
        elif defect == "remaining":
            action["remaining_ticks"] = 3
        elif defect == "started":
            action["tick_started"] -= 1
        else:
            action["route_cursor"] += 1

    checkpoint = _altered_checkpoint(tmp_path, source, 2, change)
    with pytest.raises(PersistenceError, match="active_actions"):
        resume(checkpoint, source, 1, target)
    assert not target.exists()
    assert not list(tmp_path.glob(".target.resume-*"))


@pytest.mark.parametrize(
    "plans",
    [
        [[WAIT, WAIT, WAIT]],
        [[template("sleep")]],
        [[template("sleep"), WAIT]],
        [[template("eat"), WAIT]],
        [[WAIT], [WAIT, WAIT]],
    ],
    ids=["queue", "active-without-queue", "active-with-queue", "failure", "replacement"],
)
def test_legal_plan_progress_resumes_at_every_boundary(tmp_path, plans):
    content = content_with({"ella": (2, 3)}, actions={"sleep_ticks": 3})
    script = _script(tmp_path / "script.json", content, [_actor(plans=plans)])
    source = tmp_path / "source"
    full = run(content, 5, source, script=script, checkpoint_every=1)
    for tick in range(6):
        continued = resume(_checkpoint(source, tick), source, 5 - tick, tmp_path / f"tail-{tick}")
        assert continued.world == full.world


def test_dead_actor_discards_unstarted_queue_and_still_resumes(tmp_path):
    content = content_with({"ella": (2, 3)}, needs={"initial_health": 1, "initial_hydration": 0})
    script = _script(tmp_path / "script.json", content, [_actor(plans=[[WAIT, WAIT]])])
    source = tmp_path / "source"
    full = run(content, 3, source, script=script, checkpoint_every=1)
    resumed = resume(_checkpoint(source, 1), source, 2, tmp_path / "tail")
    assert resumed.world == full.world


@pytest.mark.parametrize("case", ["interrupted", "deferred", "pending-failure"])
def test_trigger_and_failure_boundaries_preserve_legacy_queue_timing(tmp_path, case):
    content = content_with(
        {"ella": (2, 3)},
        actions={"wait_ticks": 3, "sleep_ticks": 3, "invalid_attempt_ticks": 3},
        needs={"initial_hydration": 3001, "hydration_decay_per_tick": 1},
        agents={"urgent_hydration_below": 3000},
    )
    first = {"interrupted": "sleep", "deferred": "wait", "pending-failure": "eat"}[case]
    script = _script(tmp_path / "script.json", content, [_actor(plans=[[template(first), WAIT]])])
    source = tmp_path / "source"
    full = run(content, 5, source, script=script, checkpoint_every=1)
    saved = json.loads(_checkpoint(source, 1).read_bytes())
    assert bool(saved["agent_state"]["queued_plans"]) == (case != "interrupted")
    if case == "deferred":
        later = json.loads(_checkpoint(source, 2).read_bytes())
        assert later["agent_state"]["deferred_decision_triggers"][0]["reasons"] == ["URGENT_NEED"]
        assert later["agent_state"]["queued_plans"] == saved["agent_state"]["queued_plans"]
    if case == "pending-failure":
        assert saved["world"]["active_actions"][0]["pending_failure_code"] == "NO_ITEM"
    for tick in range(1, 5):
        resumed = resume(_checkpoint(source, tick), source, 5 - tick, tmp_path / f"tail-{tick}")
        assert resumed.world == full.world


def test_queue_from_superseded_decision_is_rejected(tmp_path):
    content = content_with({"ella": (2, 3)})
    script = _script(tmp_path / "script.json", content, [_actor(plans=[[WAIT], [WAIT, WAIT]])])
    source = tmp_path / "source"
    run(content, 2, source, script=script)

    def change(data):
        old = json.loads((source / "decisions.jsonl").read_bytes().splitlines()[0])
        data["agent_state"]["queued_plans"] = [old["plan"]]

    checkpoint = _altered_checkpoint(tmp_path, source, 2, change)
    with pytest.raises(PersistenceError, match="queued_plans"):
        resume(checkpoint, source, 1, tmp_path / "tail")
