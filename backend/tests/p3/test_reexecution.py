"""P3 coordinator, checkpoint continuation and no-external-access replay vectors."""

from __future__ import annotations

import base64
import json
import shutil
from hashlib import sha256

import pytest
from test_persistence import SOURCE, retained_fixture
from world_builders import tiny_content

from living_island.agents.p3.cognition import validate_proposal
from living_island.agents.p3.types import DecisionProposal, ProviderResult, WireRequest
from living_island.contract.p3_save import ActorPolicyConfig, TrialRegistration
from living_island.memory.p3_types import RetrievalResult, canonical_bytes
from living_island.persistence.p3_allocation import AllocationStore, initialize_fake
from living_island.sim.p3 import reexecute_p3, resume_p3, run_p3
from living_island.sim.runner import checkpoint_filename
from living_island.world.content import build_world_content, map_bytes_from_rows

WAIT = {"action_type": "wait", "target": None, "parameters": {}, "reason": None}


class Sentinel:
    def __getattribute__(self, name):
        raise AssertionError(f"replay touched external object: {name}")


class LocalProvider:
    """A deterministic local port fake; no P3-04 implementation is imported."""

    def __init__(self, *, actions=None, malformed=False, fail_after=None):
        self.actions = actions
        self.malformed = malformed
        self.fail_after = fail_after
        self.calls = []

    def prepare(self, request):
        return WireRequest(
            wire_schema_version="0.1",
            method="POST",
            origin="https://api.deepseek.com",
            path="/responses",
            content_type="application/json",
            body_base64=base64.b64encode(canonical_bytes(request)).decode("ascii"),
        )

    def count_input_tokens(self, request, wire):
        return 100

    def complete(self, request, wire, timeout_ms):
        if self.fail_after == len(self.calls):
            raise RuntimeError("injected process interruption during provider call")
        self.calls.append((request, wire, timeout_ms))
        user = json.loads(request.messages[1].content)
        current = user["context"]["goals"]["current"]
        actions = [WAIT] if self.actions is None else self.actions(user)
        proposal = {
            "proposal_schema_version": "0.1",
            "actions": actions,
            "cognitive_delta": {
                "delta_schema_version": "0.1",
                "goal_change": {
                    "operation": "continue",
                    "expected_goal_id": None if current is None else current["goal_id"],
                    "proposal": None,
                },
            },
        }
        text = "{malformed" if self.malformed else canonical_bytes(proposal).decode("utf-8")
        body = text.encode("utf-8")
        return ProviderResult(
            provider_result_version="0.1",
            outcome="response",
            raw_response=text,
            raw_body_base64=base64.b64encode(body).decode("ascii"),
            observed_body_bytes=len(body),
            response_complete=True,
            response_text=text,
            provider_request_id="fake-request",
            token_input=80,
            token_output=10,
            latency_ms=7,
            provider_error_code=None,
        )


class LocalFallback:
    def __init__(self, policies):
        self.policies = policies
        self.calls = 0

    def decide(self, request, state):
        self.calls += 1
        current = request.context.goals.current
        proposal = DecisionProposal.model_validate(
            {
                "proposal_schema_version": "0.1",
                "actions": [WAIT],
                "cognitive_delta": {
                    "delta_schema_version": "0.1",
                    "goal_change": {
                        "operation": "continue",
                        "expected_goal_id": None if current is None else current.goal_id,
                        "proposal": None,
                    },
                },
            }
        )
        plan, _ = validate_proposal(proposal, request, self.policies[request.actor_id])
        return plan, state.model_copy(
            update={"mode": "fallback", "last_fallback_ordinal": request.decision_ordinal}
        )


def setup_case(tmp_path, *, horizon=5, policy="llm-v0", fixture_profile=False):
    content = tiny_content(
        [
            "~~~~~~~~~~~",
            "~.SC......~",
            "~.MF......~",
            "~.........~",
            "~.........~",
            "~.........~",
            "~~~~~~~~~~~",
        ],
        {"ella": (2, 3), "ryan": (8, 4)},
        day_radius_tiles=10,
    )
    config = content.config.model_dump()
    config["map"]["walk_cost_budget_per_tick"] = 2
    content = build_world_content(config, map_bytes_from_rows(content.map_rows))
    files, reader = retained_fixture(content, policy, horizon, fixture_profile=fixture_profile)
    registration = TrialRegistration.model_validate_json(files["trial-registration.json"])
    case = registration.cases[0]
    root = tmp_path / "authority"
    initialize_fake(root)
    store = AllocationStore(root, mode="fake")
    store.enroll_fake(sha256(files["trial-registration.json"]).hexdigest(), case.case_id, case.caps)
    policies = {
        item["actor_id"]: ActorPolicyConfig.model_validate(item).config
        for item in json.loads(files["p3-policy-configs.json"])
    }
    return content, files, case.case_id, store, reader, LocalFallback(policies)


def execute(tmp_path, *, ticks=None, provider=None, horizon=5, policy="llm-v0", fault=None):
    content, files, case, store, reader, fallback = setup_case(
        tmp_path, horizon=horizon, policy=policy
    )
    provider = LocalProvider() if provider is None else provider
    result = run_p3(
        content,
        files,
        case,
        tmp_path / "run",
        allocation_store=store,
        provider=provider,
        fallback=fallback,
        source_reader=reader,
        ticks=ticks,
        clock_ms=lambda: 0,
        fault=fault,
    )
    return result, store, reader, provider, fallback


def test_full_replay_preserves_all_five_logs_and_checkpoint_without_external_access(tmp_path):
    original, store, reader, provider, _ = execute(tmp_path)
    assert provider.calls and original.trace is not None
    authority_before = {
        p: p.read_bytes() for p in (tmp_path / "authority").rglob("*") if p.is_file()
    }
    replay = reexecute_p3(
        original.output,
        tmp_path / "replayed",
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
        source_reader=reader,
    )
    assert replay.checkpoint == original.checkpoint
    assert replay.trace == original.trace
    for prefix in original.checkpoint.log_prefixes:
        assert (replay.output / prefix.name).read_bytes() == (
            original.output / prefix.name
        ).read_bytes()
    assert authority_before == {p: p.read_bytes() for p in authority_before}
    with pytest.raises(ValueError, match="CLOSED|COMPLETE|STALE"):
        resume_p3(
            replay.output / checkpoint_filename(5),
            tmp_path / "cannot-live-replay",
            allocation_store=store,
            provider=Sentinel(),
            fallback=Sentinel(),
            source_reader=reader,
        )


def test_current_head_continuation_preserves_active_and_queued_intents(tmp_path):
    def actions(user):
        if user["request"]["decision_ordinal"] == 0:
            return [
                {
                    "action_type": "move_to",
                    "target": {"kind": "tile", "position": {"x": 6, "y": 4}},
                    "parameters": {},
                    "reason": None,
                },
                WAIT,
            ]
        return [WAIT]

    full, _, full_reader, _, _ = execute(
        tmp_path / "full", provider=LocalProvider(actions=actions), horizon=6
    )
    prefix, store, reader, provider, fallback = execute(
        tmp_path / "split", ticks=1, provider=LocalProvider(actions=actions), horizon=6
    )
    assert prefix.checkpoint.world.active_actions
    assert prefix.checkpoint.agent_state.queued_plans
    before = {p: p.read_bytes() for p in prefix.output.iterdir() if p.is_file()}
    continued = resume_p3(
        prefix.output / checkpoint_filename(1),
        tmp_path / "tail",
        allocation_store=store,
        provider=provider,
        fallback=fallback,
        source_reader=reader,
        clock_ms=lambda: 0,
    )
    assert continued.checkpoint == full.checkpoint
    assert {p: p.read_bytes() for p in before} == before
    replay = reexecute_p3(
        continued.output,
        tmp_path / "replayed-suffix",
        ancestors=continued.ancestors,
        source_reader=reader,
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
    )
    assert replay.checkpoint == full.checkpoint
    recorded_continuation = reexecute_p3(
        full.output,
        tmp_path / "recorded-checkpoint",
        source_reader=full_reader,
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
        start_checkpoint=full.output / checkpoint_filename(1),
    )
    assert recorded_continuation.checkpoint == full.checkpoint


def test_fallback_world_facts_preserve_provenance_and_rule_control_has_none(tmp_path):
    failed, _, reader, provider, fallback = execute(
        tmp_path / "failed", provider=LocalProvider(malformed=True), horizon=2
    )
    assert len(provider.calls) == fallback.calls * 2
    events = [json.loads(row) for row in (failed.output / "events.jsonl").read_bytes().splitlines()]
    facts = [row for row in events if row["type"] == "agent_fallback_used"]
    assert len(facts) == failed.checkpoint.decision_record_cursor
    assert all(row["payload"]["reason"] == "PARSE_ERROR" for row in facts)
    assert [row["actor_id"] for row in facts[:2]] == ["ella", "ryan"]
    replay = reexecute_p3(
        failed.output,
        tmp_path / "fallback-replay",
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
        source_reader=reader,
    )
    assert replay.checkpoint == failed.checkpoint
    control, _, _, _, _ = execute(
        tmp_path / "control", provider=Sentinel(), policy="rule-based-v0", horizon=2
    )
    assert control.checkpoint.llm_record_cursor == 0
    assert b"agent_fallback_used" not in (control.output / "events.jsonl").read_bytes()


def test_interrupted_call_requires_offline_recovery_and_replay_never_touches_authority(tmp_path):
    content, files, case, store, reader, fallback = setup_case(tmp_path, horizon=4)
    provider = LocalProvider(fail_after=0)
    with pytest.raises(RuntimeError, match="interruption"):
        run_p3(
            content,
            files,
            case,
            tmp_path / "interrupted",
            allocation_store=store,
            provider=provider,
            fallback=fallback,
            source_reader=reader,
            clock_ms=lambda: 0,
        )
    checkpoint = tmp_path / "interrupted" / checkpoint_filename(0)
    with pytest.raises(ValueError, match="INTERRUPTED_CALL_RECOVERY_REQUIRED"):
        resume_p3(
            checkpoint,
            tmp_path / "refused",
            allocation_store=store,
            provider=Sentinel(),
            fallback=fallback,
            source_reader=reader,
        )
    assert not (tmp_path / "refused").exists()
    recovered = resume_p3(
        checkpoint,
        tmp_path / "recovered",
        allocation_store=store,
        provider=Sentinel(),
        fallback=fallback,
        source_reader=reader,
        offline_recovery=True,
        clock_ms=lambda: 0,
    )
    assert recovered.checkpoint.run_budget.attempts_charged == 1
    assert len(recovered.checkpoint.run_budget.recovery_debits) == 1
    assert recovered.checkpoint.llm_record_cursor == 0
    assert not recovered.checkpoint.live_enabled
    decisions = [
        json.loads(row)
        for row in (recovered.output / "decisions-p3.jsonl").read_bytes().splitlines()
    ]
    assert all(row["detail_code"] == "RECOVERY_OFFLINE" for row in decisions)
    replay = reexecute_p3(
        recovered.output,
        tmp_path / "offline-replay",
        ancestors=recovered.ancestors,
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
        source_reader=reader,
    )
    assert replay.checkpoint == recovered.checkpoint


def test_copied_and_stale_heads_cannot_resume_or_issue_a_second_grant(tmp_path):
    prefix, store, reader, provider, fallback = execute(tmp_path, ticks=0, horizon=2)
    copied = tmp_path / "copied"
    shutil.copytree(prefix.output, copied)
    with pytest.raises(ValueError, match="STALE"):
        resume_p3(
            copied / checkpoint_filename(0),
            tmp_path / "copy-resume",
            allocation_store=store,
            provider=Sentinel(),
            fallback=Sentinel(),
            source_reader=reader,
            ticks=0,
        )
    assert not (tmp_path / "copy-resume").exists()
    resumed = resume_p3(
        prefix.output / checkpoint_filename(0),
        tmp_path / "new-head",
        allocation_store=store,
        provider=provider,
        fallback=fallback,
        source_reader=reader,
        ticks=0,
    )
    assert resumed.checkpoint == prefix.checkpoint
    with pytest.raises(ValueError, match="STALE"):
        resume_p3(
            prefix.output / checkpoint_filename(0),
            tmp_path / "stale-resume",
            allocation_store=store,
            provider=Sentinel(),
            fallback=Sentinel(),
            source_reader=reader,
            ticks=0,
        )
    assert not (tmp_path / "stale-resume").exists()


def test_partial_unbacked_dispatch_and_invalid_later_checkpoint_fail_closed(tmp_path):
    prefix, store, reader, _, fallback = execute(tmp_path, ticks=0, horizon=2)
    checkpoint = prefix.output / checkpoint_filename(0)
    dispatch_path = prefix.output / "llm-dispatches.jsonl"
    with dispatch_path.open("ab") as stream:
        stream.write(b"{")
    for offline in (False, True):
        with pytest.raises(ValueError):
            resume_p3(
                checkpoint,
                tmp_path / f"refused-{offline}",
                allocation_store=store,
                provider=Sentinel(),
                fallback=fallback,
                source_reader=reader,
                offline_recovery=offline,
                ticks=0,
            )
        assert not (tmp_path / f"refused-{offline}").exists()
    (prefix.output / checkpoint_filename(1)).write_bytes(b"{corrupt")
    with pytest.raises(ValueError):
        resume_p3(
            checkpoint,
            tmp_path / "later-corrupt",
            allocation_store=store,
            provider=Sentinel(),
            fallback=fallback,
            source_reader=reader,
            ticks=0,
        )
    assert not (tmp_path / "later-corrupt").exists()


def test_pending_offline_recovery_reopens_once_then_saved_offline_mode_persists(tmp_path):
    content, files, case, store, reader, fallback = setup_case(tmp_path, horizon=2)
    with pytest.raises(RuntimeError):
        run_p3(
            content,
            files,
            case,
            tmp_path / "interrupted",
            allocation_store=store,
            provider=LocalProvider(fail_after=0),
            fallback=fallback,
            source_reader=reader,
            clock_ms=lambda: 0,
        )
    source = tmp_path / "interrupted" / checkpoint_filename(0)

    def crash(stage):
        if stage == "checkpoint:prepared":
            raise OSError("crash after durable recovery preparation")

    with pytest.raises(OSError, match="crash"):
        resume_p3(
            source,
            tmp_path / "failed-recovery",
            allocation_store=store,
            provider=Sentinel(),
            fallback=fallback,
            source_reader=reader,
            offline_recovery=True,
            ticks=0,
            fault=crash,
        )
    retained_origin = (tmp_path / "failed-recovery" / "resume-origin-p3.json").read_bytes()
    recovered = resume_p3(
        source,
        tmp_path / "recovered",
        allocation_store=store,
        provider=Sentinel(),
        fallback=fallback,
        source_reader=reader,
        offline_recovery=True,
        ticks=1,
        clock_ms=lambda: 0,
    )
    assert (recovered.output / "resume-origin-p3.json").read_bytes() == retained_origin
    assert recovered.checkpoint.run_budget.attempts_charged == 1
    continued = resume_p3(
        recovered.output / checkpoint_filename(1),
        tmp_path / "offline-suffix",
        allocation_store=store,
        provider=Sentinel(),
        fallback=fallback,
        source_reader=reader,
        ancestors=recovered.ancestors,
        clock_ms=lambda: 0,
    )
    assert not continued.checkpoint.live_enabled
    assert continued.checkpoint.run_budget == recovered.checkpoint.run_budget
    replay = reexecute_p3(
        continued.output,
        tmp_path / "multi-origin-replay",
        ancestors=continued.ancestors,
        source_reader=reader,
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
    )
    assert replay.checkpoint == continued.checkpoint


class RecentOnlyFixture:
    retrieval_profile = "recent-only-fixture-v0"
    implementation_sha256 = sha256(SOURCE).hexdigest()

    def retrieve(self, state, query):
        records = sorted(state.records, key=lambda record: record.sequence, reverse=True)
        return RetrievalResult(
            ranked_experience_ids=[record.experience_id for record in records],
            selected_records=records[:16],
        )


def test_alternate_strategy_records_its_actual_id_and_replays_its_own_rank(tmp_path):
    content, files, case, store, reader, fallback = setup_case(
        tmp_path, horizon=2, fixture_profile=True
    )
    selector = RecentOnlyFixture()
    original = run_p3(
        content,
        files,
        case,
        tmp_path / "alternate",
        allocation_store=store,
        provider=LocalProvider(),
        fallback=fallback,
        source_reader=reader,
        selector=selector,
        selector_sha256=selector.implementation_sha256,
        clock_ms=lambda: 0,
    )
    contexts = [
        json.loads(row) for row in (original.output / "contexts-p3.jsonl").read_bytes().splitlines()
    ]
    assert contexts
    for context in contexts:
        manifest = context["assembly"]["manifest"]
        assert manifest["retrieval_profile"] == "recent-only-fixture-v0"
        assert manifest["context_profile_id"] == "p3-context-recent-only-fixture-v0"
        sequences = [
            record["sequence"] for record in context["request"]["context"]["recalled_experience"]
        ]
        assert sequences == sorted(sequences, reverse=True)
    replay = reexecute_p3(
        original.output,
        tmp_path / "alternate-replay",
        source_reader=reader,
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
        selector=RecentOnlyFixture(),
        selector_sha256=selector.implementation_sha256,
    )
    assert replay.checkpoint == original.checkpoint
    with pytest.raises(ValueError):
        reexecute_p3(
            original.output,
            tmp_path / "wrong-selector",
            source_reader=reader,
            provider=Sentinel(),
            fallback=Sentinel(),
            allocation_store=Sentinel(),
        )
