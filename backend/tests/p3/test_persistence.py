"""P3 retained-input, snapshot, journal and committed-prefix verification."""

from __future__ import annotations

import copy
import json
from hashlib import sha256
from pathlib import Path

import pytest
from world_builders import tiny_content

from living_island.agents.p3.cognition import initial_goal_state
from living_island.agents.p3.prompts import RESIDENT_TEMPLATE, build_model_action_contract
from living_island.agents.p3.types import (
    BudgetLedgerP3,
    ContextProfile,
    IdentitySource,
    P3PolicyConfig,
    P3PolicyPrivateState,
    ProfileDocument,
    ResidentCognitiveState,
    ResidentIdentity,
    ResidentRuntimeStateP3,
)
from living_island.agents.types import RuleStateV0_1
from living_island.contract.p3_save import AgentStateP3, SavePackageP3
from living_island.contract.save import DeliveryCursor
from living_island.memory.experience import initial_experience
from living_island.memory.p3_types import canonical_bytes, canonical_sha256
from living_island.persistence.p3 import (
    LOG_NAMES,
    MANIFEST_NAME,
    P3Journal,
    complete_origin,
    load_trace_p3,
    prepare_continuation,
    publish_checkpoint,
    read_checkpoint_p3,
    read_inputs,
    retain_inputs,
    write_trace_p3,
)
from living_island.world.content import map_bytes_from_rows
from living_island.world.ports import create_engine

COMMIT = "982988ab9b87856dd62fe4cced426971b33b22df"
SOURCE = b"fixture implementation bytes\n"


def retained_fixture(content, policy="llm-v0", horizon=3, *, fixture_profile=False):
    """Return approved fake retained bytes and a pinned source reader for integration tests."""
    cfg = content.config
    identities, sources, templates = [], [], []
    profile = ContextProfile(
        context_profile_schema_version="0.1",
        context_profile_id="p3-context-recent-only-fixture-v0"
        if fixture_profile
        else "p3-context-v0",
        retrieval_profile="recent-only-fixture-v0" if fixture_profile else "recent-relevant-v0",
        projection_profile="p3-context-v0",
    )
    action = build_model_action_contract()
    for resident in sorted(cfg.residents, key=lambda r: r.id):
        source = IdentitySource(
            actor_id=resident.id,
            display_name=resident.name,
            profile=ProfileDocument(
                profile_schema_version="0.1",
                profile_id=resident.profile_id,
                values=["Observe carefully."],
            ),
            initial_direction=resident.initial_goal,
        )
        identity = ResidentIdentity(
            identity_schema_version="0.1",
            actor_id=resident.id,
            display_name=source.display_name,
            profile_id=source.profile.profile_id,
            values=source.profile.values,
            initial_direction=source.initial_direction,
            source_sha256=canonical_sha256(source),
        )
        sources.append(source)
        identities.append(identity)
        common = dict(
            seed=cfg.meta.seed,
            max_plan_actions=cfg.agents.max_plan_actions,
            map_width=cfg.map.width,
            map_height=cfg.map.height,
        )
        template = dict(
            config_schema_version="0.2",
            policy_id=policy,
            **common,
            identity_sha256=canonical_sha256(identity),
            prompt_version="p3-resident/0.1",
            prompt_sha256=sha256(RESIDENT_TEMPLATE).hexdigest(),
            action_schema_version="p3-actions/0.1",
            action_schema_sha256=canonical_sha256(action),
            context_profile_id=profile.context_profile_id,
            adapter_id="fake",
            adapter_version="0.1",
            model_id="fake-model",
            provider_settings=dict(
                api="deepseek-responses",
                reasoning_effort="none",
                store=False,
                tools=[],
                background=False,
                stream=False,
                input_counter_id="fake-counter",
                input_counter_version="0.1",
            ),
            limits=dict(
                profile_id="p3-bounded-v0.1",
                max_attempts=2,
                attempt_timeout_ms=30000,
                decision_timeout_ms=60000,
                retry_delay_ms=0,
                max_input_tokens=32768,
                max_output_tokens=2048,
                max_request_bytes=131072,
                max_response_bytes=262144,
            ),
            pricing=dict(
                currency="CNY",
                date="2026-11-12",
                source_url="https://example.test/fake",
                input_micro_cny_per_million_tokens=0,
                output_micro_cny_per_million_tokens=0,
            ),
            fallback_config=dict(
                policy_id="rule-based-v0",
                **common,
                script_sha256=None,
                source_trace_sha256=None,
                rule_params=dict(
                    rule_params_version="0.1",
                    canteen_use="enabled",
                    cue_use="enabled",
                    fruit_carry_target=2,
                    failed_target_retry_ticks=36,
                ),
            ),
        )
        templates.append(dict(actor_id=resident.id, config=template))
    file_pin = dict(path="backend/src/fixture.py", sha256=sha256(SOURCE).hexdigest())
    caps = dict(attempts=100, input_tokens=1000000, output_tokens=1000000, micro_cny=0)
    registration = dict(
        registration_schema_version="0.1",
        registration_id="fixture",
        purpose="fake",
        revision=1,
        implementation_commit=COMMIT,
        implementation_pins=[file_pin],
        world_pin_commit=COMMIT,
        world_config_path="content/worlds/default.toml",
        world_map_path="content/worlds/default.map",
        world_config_sha256=content.config_hash,
        world_map_sha256=content.map_hash,
        input_pins=[file_pin],
        cases=[
            dict(
                case_id=f"fixture.s{cfg.meta.seed}",
                seed=cfg.meta.seed,
                ticks=horizon,
                llm_actor_ids=[item.actor_id for item in identities] if policy == "llm-v0" else [],
                policy_templates=templates,
                caps=caps,
            )
        ],
        controls=[],
        aggregate_caps=caps,
        fake_fixture_id="p3-persistence",
    )
    registration_hash = canonical_sha256(registration)
    policies = [
        dict(
            actor_id=item["actor_id"],
            config={**item["config"], "trial_registration_sha256": registration_hash},
        )
        for item in templates
    ]
    implementation = dict(
        implementation_pin_version="0.1",
        code_commit=COMMIT,
        modules=[
            dict(role=role, files=[file_pin])
            for role in ("adapter", "counter", "goal", "runtime", "schema", "selector")
        ],
    )
    files = {
        "config.json": canonical_bytes(cfg),
        "map.txt": map_bytes_from_rows(content.map_rows),
        "identities.json": canonical_bytes([item.model_dump(mode="json") for item in identities]),
        "identity-sources.json": canonical_bytes(
            [item.model_dump(mode="json") for item in sources]
        ),
        "p3-policy-configs.json": canonical_bytes(policies),
        "prompt.txt": RESIDENT_TEMPLATE,
        "action-schema.json": canonical_bytes(action),
        "context-profile.json": canonical_bytes(profile),
        "trial-registration.json": canonical_bytes(registration),
        "implementation.json": canonical_bytes(implementation),
    }

    def source_reader(commit, path):
        assert commit == COMMIT and path == file_pin["path"]
        return SOURCE

    return files, source_reader


def initial_checkpoint(directory: Path, *, policy="llm-v0", fixture_profile=False):
    content = tiny_content(["~~~~~~~", "~.SC..~", "~.MF..~", "~~~~~~~"], {"ella": (1, 1)})
    files, reader = retained_fixture(content, policy, fixture_profile=fixture_profile)
    manifest = retain_inputs(
        directory, files, run_id=content.config.meta.run_id, source_reader=reader
    )
    journal = P3Journal(directory, content.config.meta.run_id)
    boundary = create_engine(content, None).initial_commit()
    journal.append_events(boundary.events)
    states = []
    for item, identity_data in zip(
        json.loads(files["p3-policy-configs.json"]),
        json.loads(files["identities.json"]),
        strict=True,
    ):
        config = P3PolicyConfig.model_validate(item["config"])
        identity = ResidentIdentity.model_validate(identity_data)
        states.append(
            ResidentRuntimeStateP3(
                runtime_schema_version="0.2",
                actor_id=item["actor_id"],
                policy_config=config,
                next_decision_ordinal=0,
                latest_perception_tick=-1,
                cognitive_state=ResidentCognitiveState(
                    cognitive_schema_version="0.1",
                    actor_id=item["actor_id"],
                    identity=identity,
                    experience=initial_experience(item["actor_id"]),
                    goals=initial_goal_state(),
                ),
                policy_private=P3PolicyPrivateState(
                    private_schema_version="0.1",
                    mode="llm" if policy == "llm-v0" else "fallback",
                    fallback_state=RuleStateV0_1(
                        rule_state_version="0.1",
                        commitment=None,
                        issued_intents=[],
                        failed_targets=[],
                        cue_impressions=[],
                        canteen_capacity=None,
                    ),
                    last_fallback_ordinal=None,
                ),
            )
        )
    registration = json.loads(files["trial-registration.json"])
    allocation_key = canonical_sha256(
        {
            "registration_sha256": canonical_sha256(registration),
            "case_id": registration["cases"][0]["case_id"],
        }
    )
    ledger = BudgetLedgerP3(
        budget_schema_version="0.1",
        allocation_key=allocation_key,
        caps=registration["cases"][0]["caps"],
        attempts_charged=0,
        input_charged=0,
        output_charged=0,
        money_charged=0,
        unknown_usage_count=0,
        recovery_debits=[],
    )
    save = SavePackageP3(
        save_schema_version="0.2",
        world=boundary.snapshot,
        agent_state=AgentStateP3(
            profiles=[],
            goal_states=[],
            personal_memories=[],
            relationships=[],
            queued_plans=[],
            deferred_decision_triggers=[],
            delivered_perception_ticks=[
                DeliveryCursor(actor_id=state.actor_id, last_observed_tick=-1) for state in states
            ],
            runtime_states=states,
        ),
        event_cursor=len(boundary.events),
        llm_record_cursor=0,
        decision_record_cursor=0,
        context_record_cursor=0,
        dispatch_record_cursor=0,
        pending_perception_deliveries=boundary.pending_deliveries,
        canonical_config_hash=content.config_hash,
        canonical_map_hash=content.map_hash,
        input_manifest_sha256=canonical_sha256(manifest),
        log_prefixes=journal.prefixes(),
        run_budget=ledger,
        allocation_entries=[],
        live_enabled=True,
    )
    path = directory / "checkpoint-0000000000.json"
    publish_checkpoint(path, save, journal)
    return read_checkpoint_p3(path, source_reader=reader), reader, journal


def test_tick_zero_round_trip_preserves_exact_pending_packet_and_inputs(tmp_path):
    verified, reader, journal = initial_checkpoint(tmp_path)
    assert verified.save.agent_state.runtime_states[0].latest_perception_tick == -1
    assert verified.save.pending_perception_deliveries[0].observed_tick == 0
    assert verified.logs == journal.raw_prefixes()
    assert verified.raw == canonical_bytes(verified.save)
    assert (
        read_inputs(
            tmp_path, expected_hash=verified.save.input_manifest_sha256, source_reader=reader
        )
        == verified.inputs
    )


@pytest.mark.parametrize("name", LOG_NAMES)
def test_corrupt_or_missing_committed_prefix_refuses_even_at_zero_cursor(tmp_path, name):
    verified, reader, _ = initial_checkpoint(tmp_path)
    path = tmp_path / name
    if verified.logs[name]:
        path.write_bytes(verified.logs[name][:-1])
    else:
        path.unlink()
    with pytest.raises(ValueError):
        read_checkpoint_p3(tmp_path / "checkpoint-0000000000.json", source_reader=reader)


def test_ordinary_tails_do_not_become_committed_prefixes(tmp_path):
    verified, reader, _ = initial_checkpoint(tmp_path)
    for name in LOG_NAMES:
        with (tmp_path / name).open("ab") as stream:
            stream.write(b'{"partial":')
    after = read_checkpoint_p3(tmp_path / "checkpoint-0000000000.json", source_reader=reader)
    assert after == verified


def test_retained_input_and_archived_source_corruption_refuse(tmp_path):
    verified, reader, _ = initial_checkpoint(tmp_path)
    with pytest.raises(ValueError, match="archived implementation"):
        read_checkpoint_p3(tmp_path / "checkpoint-0000000000.json")
    with pytest.raises(ValueError, match="pinned"):
        read_checkpoint_p3(
            tmp_path / "checkpoint-0000000000.json", source_reader=lambda *_: b"mutated"
        )
    (tmp_path / "prompt.txt").write_bytes(b"mutated")
    with pytest.raises(ValueError, match="hash"):
        read_inputs(tmp_path, source_reader=reader)
    assert verified.inputs["prompt.txt"] == RESIDENT_TEMPLATE


def test_clean_continuation_is_suffix_only_and_requires_verified_ancestor(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "continuation"
    verified, reader, _ = initial_checkpoint(source)
    origin = prepare_continuation(source, verified, destination)
    assert origin == complete_origin(verified)
    journal = P3Journal(destination, verified.save.world.run_id, prior_raw=verified.logs)
    publish_checkpoint(
        destination / "checkpoint-0000000000.json", verified.save, journal, origins=[origin]
    )
    assert all((destination / name).read_bytes() == b"" for name in LOG_NAMES)
    with pytest.raises(ValueError, match="ancestor"):
        read_checkpoint_p3(destination / "checkpoint-0000000000.json", source_reader=reader)
    restored = read_checkpoint_p3(
        destination / "checkpoint-0000000000.json",
        ancestors=(source / "checkpoint-0000000000.json",),
        source_reader=reader,
    )
    assert restored.logs == verified.logs and restored.save == verified.save


def test_invalid_input_rejected_before_output_creation(tmp_path):
    content = tiny_content(["~~~~~~~", "~.SC..~", "~.MF..~", "~~~~~~~"], {"ella": (1, 1)})
    files, reader = retained_fixture(content)
    files = copy.deepcopy(files)
    files["unexpected.json"] = b"{}"
    target = tmp_path / "new"
    with pytest.raises(ValueError):
        retain_inputs(target, files, run_id=content.config.meta.run_id, source_reader=reader)
    assert not target.exists()


def test_fixture_retrieval_strategy_retains_actual_identifier(tmp_path):
    verified, reader, _ = initial_checkpoint(tmp_path, fixture_profile=True)
    profile = json.loads(verified.inputs["context-profile.json"])
    assert profile["retrieval_profile"] == "recent-only-fixture-v0"
    assert read_inputs(tmp_path, source_reader=reader) == verified.inputs


def test_trace_has_full_snapshot_hashes_and_refuses_incomplete_horizon(tmp_path):
    verified, reader, _ = initial_checkpoint(tmp_path)
    trace_path = tmp_path / "decision-trace-p3.json"
    with pytest.raises(ValueError, match="horizon"):
        write_trace_p3(trace_path, verified, final_tick=1)
    assert not trace_path.exists()
    trace = write_trace_p3(trace_path, verified, final_tick=0)
    assert load_trace_p3(trace_path, source_reader=reader) == (trace, verified)


def test_snapshot_rejects_unknown_version_placeholders_and_cursor_forgery(tmp_path):
    verified, reader, _ = initial_checkpoint(tmp_path)
    for update in (
        {"save_schema_version": "0.3"},
        {"decision_record_cursor": 1},
        {"live_enabled": 1},
    ):
        with pytest.raises(ValueError):
            SavePackageP3.model_validate({**verified.save.model_dump(), **update})
    data = verified.save.model_dump()
    data["agent_state"]["personal_memories"] = [{"invented": "legacy"}]
    with pytest.raises(ValueError):
        SavePackageP3.model_validate(data)
    assert (tmp_path / MANIFEST_NAME).read_bytes()
