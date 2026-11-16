"""P3-06 three-primary offline decisions, private contexts, and replay."""

from __future__ import annotations

import json
from hashlib import sha256

from test_one_resident import (
    MappedProvider,
    assert_replay,
    mechanic_world,
    own_goal,
    proposal,
    rows,
    slice_inputs,
)

from living_island.agents.llm.fallback import FrozenRuleFallbackAdapter
from living_island.agents.p3.types import BudgetCaps, P3PolicyConfig
from living_island.memory.p3_types import canonical_bytes
from living_island.persistence.p3_allocation import AllocationStore, initialize_fake
from living_island.sim.p3 import run_p3

ACTORS = ("ella", "mia", "ryan")
WAIT = {"action_type": "wait", "target": None, "parameters": {}, "reason": None}


def three_primary_inputs(*, horizon: int = 3):
    """Derive all-primary fake inputs without changing the pinned source modules."""
    content = mechanic_world(radius=20)
    files, reader, case, _ = slice_inputs(content, horizon=horizon, attempts=48)
    registration = json.loads(files["trial-registration.json"])
    registered_case = registration["cases"][0]
    registered_case["llm_actor_ids"] = list(ACTORS)
    for row in registered_case["policy_templates"]:
        row["config"]["policy_id"] = "llm-v0"
    files["trial-registration.json"] = canonical_bytes(registration)
    registration_hash = sha256(files["trial-registration.json"]).hexdigest()
    configs = [
        {
            "actor_id": row["actor_id"],
            "config": {**row["config"], "trial_registration_sha256": registration_hash},
        }
        for row in registered_case["policy_templates"]
    ]
    files["p3-policy-configs.json"] = canonical_bytes(configs)
    fallback = FrozenRuleFallbackAdapter(
        P3PolicyConfig.model_validate(configs[0]["config"]).fallback_config
    )
    return content, files, reader, registered_case, fallback


def test_three_primary_decisions_are_canonical_and_replay_without_external_access(tmp_path):
    content, files, reader, case, fallback = three_primary_inputs()

    def choose(user, _index):
        actor = user["request"]["actor_id"]
        current = user["context"]["goals"]["current"]
        if current is None:
            return proposal(
                actions=[WAIT],
                operation="revise",
                goal=own_goal(f"{actor} waits for one boundary.", WAIT),
            )
        return proposal(current["goal_id"], actions=[WAIT])

    provider = MappedProvider(choose)
    authority = tmp_path / "authority"
    initialize_fake(authority)
    allocation = AllocationStore(authority, mode="fake")
    allocation.enroll_fake(
        sha256(files["trial-registration.json"]).hexdigest(),
        case["case_id"],
        BudgetCaps.model_validate(case["caps"]),
    )
    result = run_p3(
        content,
        files,
        case["case_id"],
        tmp_path / "run",
        allocation_store=allocation,
        provider=provider,
        fallback=fallback,
        source_reader=reader,
        clock_ms=lambda: 0,
    )
    decisions = rows(result, "decisions-p3.jsonl")
    contexts = rows(result, "contexts-p3.jsonl")
    assert len(decisions) == len(provider.transport.calls) == len(contexts) == 3 * case["ticks"]
    assert [row["actor_id"] for row in decisions] == list(ACTORS) * case["ticks"]
    assert all(row["policy_id"] == row["effective_policy_id"] == "llm-v0" for row in decisions)
    for context in contexts:
        request = context["request"]
        owner = request["actor_id"]
        assert request["context"]["identity"]["actor_id"] == owner
        assert all(
            record["owner_id"] == owner for record in request["context"]["recalled_experience"]
        )
    assert {state.actor_id for state in result.checkpoint.agent_state.runtime_states} == set(ACTORS)
    assert all(
        state.next_decision_ordinal == case["ticks"]
        for state in result.checkpoint.agent_state.runtime_states
    )
    goals = {
        state.actor_id: state.cognitive_state.goals.current
        for state in result.checkpoint.agent_state.runtime_states
    }
    assert {goal.goal_id for goal in goals.values()} == {f"{actor}:g000000" for actor in ACTORS}
    assert all(goal.status == "observed_complete" for goal in goals.values())
    assert all(
        goal.evidence.owned_intent.intent.actor_id == actor
        and goal.evidence.feedback.status == "success"
        for actor, goal in goals.items()
    )
    before = {
        path.relative_to(authority): path.read_bytes()
        for path in authority.rglob("*")
        if path.is_file()
    }
    replay = assert_replay(tmp_path / "replay", result, reader)
    assert replay.checkpoint.agent_state == result.checkpoint.agent_state
    assert before == {
        path.relative_to(authority): path.read_bytes()
        for path in authority.rglob("*")
        if path.is_file()
    }
