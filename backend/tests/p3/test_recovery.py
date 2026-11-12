"""Durable reservation joins, immutable recovery evidence and process crash boundaries."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from test_persistence import initial_checkpoint

from living_island.agents.p3.context import assemble_context
from living_island.agents.p3.prompts import RESIDENT_TEMPLATE, render_provider_request
from living_island.agents.p3.types import (
    AllocationEntry,
    AllocationHead,
    AttemptDispatch,
    CallDebit,
    CallReservation,
    CaseAllocationP3,
    ContextProfile,
    ContextRecordP3,
    DecisionRequestP3,
    LLMCallRecordP3,
    ProviderResult,
    WireRequest,
    build_call_id,
)
from living_island.contract.p3_save import SavePackageP3
from living_island.memory.experience import ingest_experience
from living_island.memory.p3_types import build_decision_id, canonical_bytes, canonical_sha256
from living_island.persistence.p3 import (
    ORIGIN_NAME,
    P3Journal,
    build_recovery_origin,
    candidate_allocation_entries,
    prepare_continuation,
    publish_checkpoint,
    read_checkpoint_p3,
    verify_recovery_evidence,
)


def attempt(checkpoint):
    save = checkpoint.save
    runtime = save.agent_state.runtime_states[0]
    packet = save.pending_perception_deliveries[0]
    cognitive = runtime.cognitive_state.model_copy(
        update={
            "experience": ingest_experience(
                runtime.cognitive_state.experience, packet, run_id=save.world.run_id
            )
        }
    )
    profile = ContextProfile.model_validate_json(checkpoint.inputs["context-profile.json"])
    assembly = assemble_context(packet.perception, cognitive, profile)
    request = DecisionRequestP3(
        request_schema_version="0.2",
        actor_id=runtime.actor_id,
        tick=0,
        decision_ordinal=0,
        triggers=[],
        context=assembly.context,
    )
    provider = render_provider_request(assembly, request, runtime.policy_config, RESIDENT_TEMPLATE)
    decision_id = build_decision_id(save.world.run_id, runtime.actor_id, 0)
    context = ContextRecordP3(
        context_record_version="0.1",
        run_id=save.world.run_id,
        decision_id=decision_id,
        request=request,
        assembly=assembly,
        provider_request=provider,
    )
    body = canonical_bytes(provider)
    wire = WireRequest(
        wire_schema_version="0.1",
        method="POST",
        origin="https://api.deepseek.com",
        path="/responses",
        content_type="application/json",
        body_base64=base64.b64encode(body).decode(),
    )
    reservation = CallReservation(
        allocation_key=save.run_budget.allocation_key,
        reservation_ordinal=0,
        call_id=build_call_id(decision_id, 0),
        input_reserved=100,
        output_reserved=2048,
        money_reserved=0,
    )
    dispatch = AttemptDispatch(
        dispatch_schema_version="0.1",
        run_id=save.world.run_id,
        decision_id=decision_id,
        call_id=reservation.call_id,
        actor_id=runtime.actor_id,
        tick=0,
        decision_ordinal=0,
        attempt_index=0,
        request_sha256=canonical_sha256(request),
        context_sha256=assembly.context_sha256,
        projection_sha256=assembly.projection_sha256,
        provider_request_sha256=canonical_sha256(provider),
        provider_request=provider,
        wire_request=wire,
        wire_body_sha256=sha256(body).hexdigest(),
        allocation_key=reservation.allocation_key,
        reservation_ordinal=0,
        prompt_version=runtime.policy_config.prompt_version,
        action_schema_version=runtime.policy_config.action_schema_version,
        adapter_id=runtime.policy_config.adapter_id,
        adapter_version=runtime.policy_config.adapter_version,
        model_id=runtime.policy_config.model_id,
        input_reserved=100,
        output_reserved=2048,
        money_reserved=0,
    )
    debit = CallDebit(
        call_id=reservation.call_id,
        input_reserved=100,
        output_reserved=2048,
        money_reserved=0,
        input_reported=None,
        output_reported=None,
        input_charged=100,
        output_charged=2048,
        money_charged=0,
        usage_unknown=True,
    )
    result = ProviderResult(
        provider_result_version="0.1",
        outcome="timeout",
        raw_response=None,
        raw_body_base64=None,
        observed_body_bytes=0,
        response_complete=False,
        response_text=None,
        provider_request_id=None,
        token_input=None,
        token_output=None,
        latency_ms=30000,
        provider_error_code=None,
    )
    call = LLMCallRecordP3(
        call_schema_version="0.1",
        run_id=save.world.run_id,
        decision_id=decision_id,
        call_id=reservation.call_id,
        actor_id=runtime.actor_id,
        tick=0,
        decision_ordinal=0,
        attempt_index=0,
        dispatch_sha256=canonical_sha256(dispatch),
        result=result,
        parsed_proposal=None,
        validation_error="TIMEOUT",
        detail_code=None,
        debit=debit,
    )
    entry = AllocationEntry(
        reservation=reservation,
        provider_request_sha256=dispatch.provider_request_sha256,
        wire_body_sha256=dispatch.wire_body_sha256,
        state="reserved",
        debit=None,
        terminal_call_sha256=None,
    )
    return context, dispatch, call, entry


def authority_for(checkpoint, source, entries):
    save = checkpoint.save
    registration = json.loads(checkpoint.inputs["trial-registration.json"])
    return CaseAllocationP3(
        allocation_schema_version="0.1",
        allocation_key=save.run_budget.allocation_key,
        registration_sha256=canonical_sha256(registration),
        case_id=registration["cases"][0]["case_id"],
        caps=save.run_budget.caps,
        generation=2,
        status="running",
        head=AllocationHead(
            checkpoint_sha256=sha256(checkpoint.raw).hexdigest(),
            checkpoint_tick=0,
            input_manifest_sha256=save.input_manifest_sha256,
            run_directory=str(source.resolve()),
            reservation_cursor=0,
        ),
        prepared_head=None,
        pending_recovery_sha256=None,
        entries=entries,
    )


def test_journal_refuses_dispatch_without_durable_reservation(tmp_path):
    checkpoint, _, _ = initial_checkpoint(tmp_path / "source")
    context, dispatch, _, _ = attempt(checkpoint)
    journal = P3Journal(tmp_path / "tail", checkpoint.save.world.run_id)
    journal.stage_context(context)
    with pytest.raises(ValueError, match="reservation"):
        journal.before_call(context, dispatch)
    assert (tmp_path / "tail" / "llm-dispatches.jsonl").read_bytes() == b""


def test_journal_orders_reservation_context_dispatch_terminal_and_settlement(tmp_path):
    checkpoint, _, _ = initial_checkpoint(tmp_path / "source")
    context, dispatch, call, entry = attempt(checkpoint)
    observed = []
    directory = tmp_path / "tail"

    def verify(record):
        observed.append(record)
        assert (directory / "contexts-p3.jsonl").read_bytes() == canonical_bytes(context) + b"\n"
        assert (directory / "llm-dispatches.jsonl").read_bytes() == b""

    journal = P3Journal(directory, checkpoint.save.world.run_id, reservation_lookup=verify)
    journal.stage_context(context)
    journal.before_call(context, dispatch)
    journal.after_call(call)
    assert observed == [dispatch]
    settled = candidate_allocation_entries([entry], journal.raw_prefixes())
    assert settled[0].state == "settled" and settled[0].terminal_call_sha256 == canonical_sha256(
        call
    )
    with pytest.raises(ValueError, match="duplicate"):
        journal.after_call(call)
    with pytest.raises(ValueError, match="once"):
        journal.stage_context(context)


@pytest.mark.parametrize("tail_kind", ["reservation", "partial_dispatch", "dispatch", "terminal"])
def test_recovery_charges_each_authority_reservation_once_and_retains_evidence(tmp_path, tail_kind):
    source, target = tmp_path / "source", tmp_path / "recovery"
    checkpoint, reader, _ = initial_checkpoint(source)
    _, dispatch, call, entry = attempt(checkpoint)
    artifacts = checkpoint.logs.copy()
    if tail_kind == "partial_dispatch":
        artifacts["llm-dispatches.jsonl"] += canonical_bytes(dispatch)[:101]
    if tail_kind in ("dispatch", "terminal"):
        artifacts["llm-dispatches.jsonl"] += canonical_bytes(dispatch) + b"\n"
    if tail_kind == "terminal":
        artifacts["llm-calls.jsonl"] += canonical_bytes(call) + b"\n"
    authority = authority_for(checkpoint, source, [entry])
    origin, evidence = build_recovery_origin(checkpoint, authority, artifacts)
    assert origin.recovery_entries[0].reservation == entry.reservation
    assert origin.recovery_debits == [call.debit]
    assert origin.recovery_debits[0].usage_unknown
    prepare_continuation(source, checkpoint, target, offline_origin=origin, evidence=evidence)
    assert verify_recovery_evidence(target, origin, checkpoint) == evidence
    ledger = checkpoint.save.run_budget.model_dump()
    ledger.update(
        attempts_charged=1,
        input_charged=100,
        output_charged=2048,
        unknown_usage_count=1,
        recovery_debits=origin.recovery_debits,
    )
    recovered = SavePackageP3.model_validate(
        {
            **checkpoint.save.model_dump(),
            "allocation_entries": origin.recovery_entries,
            "run_budget": ledger,
            "live_enabled": False,
        }
    )
    journal = P3Journal(target, checkpoint.save.world.run_id, prior_raw=checkpoint.logs)
    publish_checkpoint(target / "checkpoint-0000000000.json", recovered, journal, origins=[origin])
    verified = read_checkpoint_p3(
        target / "checkpoint-0000000000.json",
        ancestors=(source / "checkpoint-0000000000.json",),
        source_reader=reader,
    )
    assert verified.save.run_budget.attempts_charged == 1
    assert verified.save.llm_record_cursor == 0
    assert verified.origins == (origin,)
    with pytest.raises(ValueError, match="fresh"):
        prepare_continuation(source, checkpoint, target, offline_origin=origin, evidence=evidence)
    assert sha256((target / ORIGIN_NAME).read_bytes()).hexdigest() == canonical_sha256(origin)


def test_recovery_refuses_unowned_dispatch_conflicting_hash_and_missing_evidence(tmp_path):
    source = tmp_path / "source"
    checkpoint, _, _ = initial_checkpoint(source)
    _, dispatch, _, entry = attempt(checkpoint)
    artifacts = {**checkpoint.logs, "llm-dispatches.jsonl": canonical_bytes(dispatch) + b"\n"}
    with pytest.raises(ValueError, match="no authority"):
        build_recovery_origin(checkpoint, authority_for(checkpoint, source, []), artifacts)
    conflict = entry.model_copy(update={"wire_body_sha256": "0" * 64})
    with pytest.raises(ValueError, match="conflicts"):
        build_recovery_origin(checkpoint, authority_for(checkpoint, source, [conflict]), artifacts)
    origin, evidence = build_recovery_origin(
        checkpoint, authority_for(checkpoint, source, [entry]), artifacts
    )
    target = tmp_path / "target"
    prepare_continuation(source, checkpoint, target, offline_origin=origin, evidence=evidence)
    evidence_path = target / "recovery-evidence" / f"{origin.orphan_artifacts[0].sha256}.bin"
    evidence_path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash"):
        verify_recovery_evidence(target, origin, checkpoint)


@pytest.mark.parametrize(
    "stage",
    [
        "checkpoint:logs_flushed",
        "checkpoint:prepared",
        "checkpoint:before_write",
        "checkpoint:after_write",
        "checkpoint:after_fsync",
        "checkpoint:after_publish",
        "checkpoint:finalized",
    ],
)
def test_real_process_exit_during_checkpoint_publication_has_only_complete_snapshot(
    tmp_path, stage
):
    source = tmp_path / "source"
    checkpoint, reader, _ = initial_checkpoint(source)
    target = tmp_path / "crash"
    script = """
import os, sys
from pathlib import Path
from test_persistence import initial_checkpoint
from living_island.persistence.p3 import P3Journal, publish_checkpoint
target, stage = Path(sys.argv[1]), sys.argv[2]
checkpoint, reader, journal = initial_checkpoint(target / 'base')
publication = target / 'publication'
publication.mkdir()
for name, raw in checkpoint.inputs.items():
    (publication / name).write_bytes(raw)
manifest = 'input-manifest-p3.json'
(publication / manifest).write_bytes((target / 'base' / manifest).read_bytes())
journal = P3Journal(publication, checkpoint.save.world.run_id)
for name, raw in checkpoint.logs.items():
    journal.append_recorded(name, raw)
def fault(point):
    if point == stage:
        os._exit(79)
publish_checkpoint(
    publication / 'checkpoint-0000000000.json', checkpoint.save, journal, fault=fault
)
"""
    environment = os.environ.copy()
    backend = Path(__file__).resolve().parents[2]
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(backend / "src"), str(backend / "tests" / "p3"), str(backend / "tests" / "unit")]
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(target), stage],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 79, result.stderr
    path = target / "publication" / "checkpoint-0000000000.json"
    if stage in ("checkpoint:after_publish", "checkpoint:finalized"):
        actual = read_checkpoint_p3(path, source_reader=reader)
        assert actual.raw == checkpoint.raw
    else:
        assert not path.exists()


@pytest.mark.parametrize(
    "stage",
    [
        "contexts-p3.jsonl:before_write",
        "contexts-p3.jsonl:after_write",
        "contexts-p3.jsonl:after_fsync",
        "llm-dispatches.jsonl:before_write",
        "llm-dispatches.jsonl:after_write",
        "llm-dispatches.jsonl:after_fsync",
        "llm-calls.jsonl:before_write",
        "llm-calls.jsonl:after_write",
        "llm-calls.jsonl:after_fsync",
    ],
)
def test_each_staged_write_failure_cannot_publish_a_checkpoint(tmp_path, stage):
    checkpoint, _, _ = initial_checkpoint(tmp_path / "source")
    context, dispatch, call, _ = attempt(checkpoint)

    def fault(point):
        if point == stage:
            raise OSError("injected crash")

    journal = P3Journal(
        tmp_path / "tail",
        checkpoint.save.world.run_id,
        reservation_lookup=lambda _: None,
        fault=fault,
    )
    with pytest.raises(OSError, match="injected"):
        journal.stage_context(context)
        journal.before_call(context, dispatch)
        journal.after_call(call)
    with pytest.raises(ValueError, match="failed"):
        journal.flush()
    assert not (tmp_path / "tail" / "checkpoint-0000000000.json").exists()


def test_recovery_rejects_malformed_complete_tail_instead_of_silently_dropping_spend(tmp_path):
    checkpoint, _, _ = initial_checkpoint(tmp_path / "source")
    _, _, _, entry = attempt(checkpoint)
    artifacts = checkpoint.logs.copy()
    artifacts["llm-dispatches.jsonl"] = b'{"unknown":"complete record"}\n'
    with pytest.raises(ValueError, match="unverifiable"):
        build_recovery_origin(
            checkpoint, authority_for(checkpoint, tmp_path / "source", [entry]), artifacts
        )


def test_partial_dispatch_without_an_unmatched_reservation_refuses_recovery(tmp_path):
    source = tmp_path / "source"
    checkpoint, _, _ = initial_checkpoint(source)
    _, dispatch, _, entry = attempt(checkpoint)
    for entries, raw in (([], b"{"), ([entry], canonical_bytes(dispatch) + b"\n{")):
        artifacts = {**checkpoint.logs, "llm-dispatches.jsonl": raw}
        with pytest.raises(ValueError, match="no corresponding"):
            build_recovery_origin(checkpoint, authority_for(checkpoint, source, entries), artifacts)


def test_terminal_tick_usage_and_reservation_forgeries_refuse_before_logging(tmp_path):
    checkpoint, _, _ = initial_checkpoint(tmp_path / "source")
    context, dispatch, call, _ = attempt(checkpoint)
    journal = P3Journal(
        tmp_path / "tail", checkpoint.save.world.run_id, reservation_lookup=lambda _: None
    )
    journal.stage_context(context)
    journal.before_call(context, dispatch)
    with pytest.raises(ValueError, match="metadata"):
        journal.after_call(call.model_copy(update={"tick": 1}))
    forged = call.debit.model_copy(update={"input_reserved": 99})
    with pytest.raises(ValueError, match="evidence"):
        journal.after_call(call.model_copy(update={"debit": forged}))
    assert (tmp_path / "tail" / "llm-calls.jsonl").read_bytes() == b""


def test_recovery_evidence_cannot_replace_committed_physical_prefix(tmp_path):
    source = tmp_path / "source"
    checkpoint, _, _ = initial_checkpoint(source)
    _, _, _, entry = attempt(checkpoint)
    artifacts = {**checkpoint.logs, "events.jsonl": b""}
    with pytest.raises(ValueError, match="committed physical"):
        build_recovery_origin(checkpoint, authority_for(checkpoint, source, [entry]), artifacts)
