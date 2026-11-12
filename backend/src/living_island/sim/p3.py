"""Opt-in P3 coordination; legacy simulation entry points remain unchanged."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pydantic import TypeAdapter

from living_island.agents.p3.ports import (
    AttemptJournalPort,
    DecisionBudgetPort,
    FallbackAdapter,
    ProviderAdapter,
    ResidentRuntimeP3,
)
from living_island.agents.p3.runtime import create_p3_runtime
from living_island.agents.p3.types import (
    AllocationEntry,
    AllocationHead,
    AttemptDispatch,
    BudgetCaps,
    BudgetLedgerP3,
    CallDebit,
    CallReservation,
    ContextProfile,
    ContextRecordP3,
    DecisionRecordP3,
    LLMCallRecordP3,
    P3PolicyConfig,
    ResidentIdentity,
)
from living_island.agents.policies.recorded import ReplayDiverged
from living_island.contract.p3_save import (
    LOG_NAMES,
    ActorPolicyConfig,
    AgentStateP3,
    DecisionTraceP3,
    ImplementationPin,
    LogPrefix,
    ResumeOriginP3,
    SavePackageP3,
    TrialCase,
    TrialRegistration,
)
from living_island.contract.save import DeliveryCursor
from living_island.memory.p3_types import RetrievalSelector, canonical_bytes, canonical_sha256
from living_island.persistence.content import load_run_content
from living_island.persistence.p3 import (
    P3Journal,
    SourceReader,
    VerifiedP3Checkpoint,
    build_recovery_origin,
    candidate_allocation_entries,
    checkpoint_verifier,
    decode_records,
    load_trace_p3,
    prepare_continuation,
    publish_checkpoint,
    read_checkpoint_p3,
    retain_inputs,
    validate_inputs,
    verify_later_checkpoints,
    write_trace_p3,
)
from living_island.persistence.p3_allocation import AllocationStore, CaseAllocationSession
from living_island.sim.ports import BoundaryObserver
from living_island.sim.runner import checkpoint_filename
from living_island.world.content import WorldContent
from living_island.world.facts import AgentFallbackUsedPayload, WorldEvent
from living_island.world.ports import WorldEngine, WorldTickCommit, create_engine
from living_island.world.protocol import (
    DECISION_TRIGGERS,
    ActionIntent,
    ActionPlan,
    DecisionTrigger,
    DeferredDecisionTriggers,
    format_delivery_id,
)
from living_island.world.state import WorldState

Fault = Callable[[str], None]


@dataclass(frozen=True)
class P3RunResult:
    """The verified last boundary; a trace exists only at the registered horizon."""

    checkpoint: SavePackageP3
    output: Path
    ancestors: tuple[Path, ...]
    trace: DecisionTraceP3 | None

    @property
    def world(self) -> WorldState:
        return self.checkpoint.world.model_copy(deep=True)


@dataclass(frozen=True)
class _Inputs:
    files: Mapping[str, bytes]
    policies: Mapping[str, P3PolicyConfig]
    identities: Mapping[str, ResidentIdentity]
    profile: ContextProfile
    registration: TrialRegistration
    case: TrialCase
    allocation_key: str

    @classmethod
    def parse(cls, files: Mapping[str, bytes], case_id: str) -> _Inputs:
        policies = TypeAdapter(list[ActorPolicyConfig]).validate_json(
            files["p3-policy-configs.json"]
        )
        identities = TypeAdapter(list[ResidentIdentity]).validate_json(files["identities.json"])
        registration = TrialRegistration.model_validate_json(files["trial-registration.json"])
        cases = [case for case in registration.cases if case.case_id == case_id]
        if len(cases) != 1:
            raise ValueError("P3 case must belong to its retained registration")
        return cls(
            dict(files),
            {row.actor_id: row.config for row in policies},
            {row.actor_id: row for row in identities},
            ContextProfile.model_validate_json(files["context-profile.json"]),
            registration,
            cases[0],
            canonical_sha256(
                {
                    "registration_sha256": sha256(files["trial-registration.json"]).hexdigest(),
                    "case_id": case_id,
                }
            ),
        )

    def check_selector(
        self, selector: RetrievalSelector | None, selector_sha256: str | None
    ) -> None:
        if selector is None:
            if selector_sha256 is not None:
                raise ValueError("selector hash requires an injected selector")
            return
        pin = ImplementationPin.model_validate_json(self.files["implementation.json"])
        files = next(module.files for module in pin.modules if module.role == "selector")
        if selector_sha256 not in {item.sha256 for item in files}:
            raise ValueError("injected selector must identify its retained defining source")


def _ledger(key: str, caps: BudgetCaps, entries: Sequence[AllocationEntry]) -> BudgetLedgerP3:
    debits: list[CallDebit] = []
    recovery: list[CallDebit] = []
    for entry in entries:
        if entry.debit is None or entry.state == "reserved":
            raise ValueError("unresolved reservation cannot enter a committed budget mirror")
        debits.append(entry.debit)
        if entry.state == "recovery":
            recovery.append(entry.debit)
    return BudgetLedgerP3(
        budget_schema_version="0.1",
        allocation_key=key,
        caps=caps,
        attempts_charged=len(debits),
        input_charged=sum(d.input_charged for d in debits),
        output_charged=sum(d.output_charged for d in debits),
        money_charged=sum(d.money_charged for d in debits),
        unknown_usage_count=sum(d.usage_unknown for d in debits),
        recovery_debits=recovery,
    )


def _head(checkpoint: VerifiedP3Checkpoint, directory: Path) -> AllocationHead:
    save = checkpoint.save
    return AllocationHead(
        checkpoint_sha256=sha256(checkpoint.raw).hexdigest(),
        checkpoint_tick=save.world.tick,
        input_manifest_sha256=save.input_manifest_sha256,
        run_directory=str(directory.resolve()),
        reservation_cursor=len(save.allocation_entries),
    )


def _roster(
    inputs: _Inputs,
    run_id: str,
    *,
    provider: ProviderAdapter,
    fallback: FallbackAdapter,
    budget: DecisionBudgetPort,
    journal: AttemptJournalPort,
    live_enabled: bool,
    restored: SavePackageP3 | None = None,
    records: Sequence[DecisionRecordP3] | None = None,
    contexts: Sequence[ContextRecordP3] | None = None,
    selector: RetrievalSelector | None = None,
    selector_sha256: str | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> dict[str, ResidentRuntimeP3]:
    states = (
        {} if restored is None else {s.actor_id: s for s in restored.agent_state.runtime_states}
    )
    result: dict[str, ResidentRuntimeP3] = {}
    for actor in sorted(inputs.policies):
        own_records = None if records is None else [r for r in records if r.actor_id == actor]
        own_contexts = (
            None if contexts is None else [c for c in contexts if c.request.actor_id == actor]
        )
        clock_options = {} if clock_ms is None else {"clock_ms": clock_ms}
        result[actor] = create_p3_runtime(
            actor,
            inputs.policies[actor],
            inputs.identities[actor],
            states.get(actor),
            live_enabled=live_enabled,
            provider=provider,
            budget=budget,
            attempts=journal,
            fallback=fallback,
            own_records=own_records,
            own_contexts=own_contexts,
            run_id=run_id,
            context_profile=inputs.profile,
            purpose="fake" if inputs.registration.purpose == "fake" else "live",
            selector=selector,
            selector_sha256=selector_sha256,
            template=inputs.files["prompt.txt"],
            **clock_options,
        )
    return result


def _length(start: int, ticks: int | None, horizon: int) -> int:
    count = horizon - start if ticks is None else ticks
    if type(count) is not int or count < 0 or start + count > horizon:
        raise ValueError("P3 length must stay inside its registered horizon")
    return count


def _fresh_output(path: Path) -> Path:
    output = path.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("P3 output must be a fresh directory")
    return output


def _finish(
    save: SavePackageP3,
    output: Path,
    ancestors: tuple[Path, ...],
    source_reader: SourceReader,
    horizon: int,
) -> P3RunResult:
    verified = read_checkpoint_p3(
        output / checkpoint_filename(save.world.tick),
        ancestors=ancestors,
        source_reader=source_reader,
    )
    trace = None
    if save.world.tick == horizon:
        trace = write_trace_p3(output / "decision-trace-p3.json", verified, final_tick=horizon)
    return P3RunResult(verified.save, output, ancestors, trace)


def _drive_live(
    loop: P3BoundaryLoop,
    count: int,
    output: Path,
    journal: P3Journal,
    session: CaseAllocationSession,
    *,
    inputs_hash: str,
    inputs: _Inputs,
    live_enabled: bool,
    origins: Sequence[ResumeOriginP3],
    fault: Fault | None,
    observer: BoundaryObserver | None,
) -> SavePackageP3:
    def publish() -> SavePackageP3:
        entries = candidate_allocation_entries(session.snapshot().entries, journal.raw_prefixes())
        ledger = _ledger(inputs.allocation_key, inputs.case.caps, entries)
        if ledger != session.export_ledger():
            raise ValueError("staged budget debits differ from verified terminal evidence")
        save = loop.checkpoint(
            input_manifest_sha256=inputs_hash,
            log_prefixes=journal.prefixes(),
            run_budget=ledger,
            allocation_entries=entries,
            live_enabled=live_enabled,
        )
        return publish_checkpoint(
            output / checkpoint_filename(save.world.tick),
            save,
            journal,
            authority=session,
            final=save.world.tick == inputs.case.ticks,
            fault=fault,
            origins=origins,
        )

    # Tick zero, a clean continuation, and a recovery import all acquire a durable
    # current head before any subsequent decision can reserve or dispatch.
    save = publish()
    for _ in range(count):
        boundary, records = loop.advance()
        journal.append_events(boundary.events)
        journal.append_decisions(records)
        save = publish()
        if observer is not None:
            observer(boundary.snapshot.model_copy(deep=True), tuple(boundary.events))
    return save


def run_p3(
    content: WorldContent,
    input_files: Mapping[str, bytes],
    case_id: str,
    output: Path,
    *,
    allocation_store: AllocationStore,
    provider: ProviderAdapter,
    fallback: FallbackAdapter,
    source_reader: SourceReader,
    ticks: int | None = None,
    selector: RetrievalSelector | None = None,
    selector_sha256: str | None = None,
    clock_ms: Callable[[], int] | None = None,
    fault: Fault | None = None,
    on_boundary_committed: BoundaryObserver | None = None,
) -> P3RunResult:
    """Execute an already enrolled case with explicitly injected provider ports.

    Enrollment is separate and create-once. Neither an output directory nor a
    checkpoint can initialize an allocation or expand its registered capacity.
    """
    inputs = _Inputs.parse(input_files, case_id)
    validate_inputs(input_files, run_id=content.config.meta.run_id, source_reader=source_reader)
    inputs.check_selector(selector, selector_sha256)
    if (
        sha256(input_files["config.json"]).hexdigest() != content.config_hash
        or sha256(input_files["map.txt"]).hexdigest() != content.map_hash
        or inputs.case.seed != content.config.meta.seed
    ):
        raise ValueError("P3 world does not match its retained registered inputs")
    count = _length(0, ticks, inputs.case.ticks)
    output = _fresh_output(output)
    pricing = next(iter(inputs.policies.values())).pricing
    verifier = checkpoint_verifier(source_reader=source_reader, horizon=inputs.case.ticks)
    with allocation_store.open_case(inputs.allocation_key, pricing, None, verifier) as session:
        if session.snapshot().caps != inputs.case.caps:
            raise ValueError("enrolled capacity differs from the registered case")
        output.mkdir(parents=True, exist_ok=True)
        manifest = retain_inputs(
            output, input_files, run_id=content.config.meta.run_id, source_reader=source_reader
        )
        journal = P3Journal(
            output,
            content.config.meta.run_id,
            reservation_lookup=session.verify_reservation,
            fault=fault,
        )
        runtimes = _roster(
            inputs,
            content.config.meta.run_id,
            provider=provider,
            fallback=fallback,
            budget=session,
            journal=journal,
            live_enabled=True,
            selector=selector,
            selector_sha256=selector_sha256,
            clock_ms=clock_ms,
        )
        loop = P3BoundaryLoop(create_engine(content, None), runtimes, session)
        journal.append_events(loop.boundary.events)
        save = _drive_live(
            loop,
            count,
            output,
            journal,
            session,
            inputs_hash=canonical_sha256(manifest),
            inputs=inputs,
            live_enabled=True,
            origins=(),
            fault=fault,
            observer=on_boundary_committed,
        )
        return _finish(save, output, (), source_reader, inputs.case.ticks)


def _dispatch_tail(source: Path, checkpoint: VerifiedP3Checkpoint) -> bool:
    prior = 0
    if checkpoint.origins:
        prior = next(
            p.records
            for p in checkpoint.origins[-1].log_prefixes
            if p.name == "llm-dispatches.jsonl"
        )
    count = checkpoint.save.dispatch_record_cursor - prior
    raw = (source / "llm-dispatches.jsonl").read_bytes()
    committed = b"".join(raw.splitlines(keepends=True)[:count])
    return raw != committed


def resume_p3(
    checkpoint: Path,
    output: Path,
    *,
    allocation_store: AllocationStore,
    provider: ProviderAdapter,
    fallback: FallbackAdapter,
    source_reader: SourceReader,
    ancestors: tuple[Path, ...] = (),
    ticks: int | None = None,
    offline_recovery: bool = False,
    selector: RetrievalSelector | None = None,
    selector_sha256: str | None = None,
    clock_ms: Callable[[], int] | None = None,
    fault: Fault | None = None,
    on_boundary_committed: BoundaryObserver | None = None,
) -> P3RunResult:
    """Continue the current authority head; interrupted spend requires offline mode."""
    checkpoint = checkpoint.resolve()
    source = checkpoint.parent
    verify_later_checkpoints(checkpoint, ancestors=ancestors, source_reader=source_reader)
    verified = read_checkpoint_p3(checkpoint, ancestors=ancestors, source_reader=source_reader)
    registration = TrialRegistration.model_validate_json(verified.inputs["trial-registration.json"])
    case_id = next(
        case.case_id
        for case in registration.cases
        if canonical_sha256(
            {
                "registration_sha256": sha256(
                    verified.inputs["trial-registration.json"]
                ).hexdigest(),
                "case_id": case.case_id,
            }
        )
        == verified.save.run_budget.allocation_key
    )
    inputs = _Inputs.parse(verified.inputs, case_id)
    inputs.check_selector(selector, selector_sha256)
    count = _length(verified.save.world.tick, ticks, inputs.case.ticks)
    output = _fresh_output(output)
    if output == source or source in output.parents:
        raise ValueError("P3 continuation must be separate from its source")
    content = load_run_content(
        source,
        expected_config_hash=verified.save.canonical_config_hash,
        expected_map_hash=verified.save.canonical_map_hash,
    )
    new_ancestors = (checkpoint, *ancestors)
    verifier = checkpoint_verifier(
        ancestors=new_ancestors, source_reader=source_reader, horizon=inputs.case.ticks
    )
    pricing = next(iter(inputs.policies.values())).pricing
    offline_mode = offline_recovery or not verified.save.live_enabled
    with allocation_store.open_case(
        inputs.allocation_key,
        pricing,
        _head(verified, source),
        verifier,
        offline_recovery=offline_mode,
    ) as session:
        dispatch_tail = _dispatch_tail(source, verified)
        if dispatch_tail and not offline_mode:
            raise ValueError("INTERRUPTED_CALL_RECOVERY_REQUIRED: dispatch bytes beyond checkpoint")
        origin: ResumeOriginP3 | None = None
        evidence: Mapping[str, bytes] = {}
        if offline_mode and (
            verified.save.live_enabled
            or session.pending_recovery() is not None
            or len(session.snapshot().entries) > len(verified.save.allocation_entries)
            or dispatch_tail
        ):
            pending = session.pending_recovery()
            if pending is None:
                artifacts = {name: (source / name).read_bytes() for name in LOG_NAMES}
                origin, evidence = build_recovery_origin(verified, session.snapshot(), artifacts)
                session.latch_recovery(canonical_bytes(origin), evidence, origin.recovery_entries)
            else:
                origin = ResumeOriginP3.model_validate_json(pending)
                evidence = session.recovery_evidence()
        origin = prepare_continuation(
            source, verified, output, offline_origin=origin, evidence=evidence
        )
        live_enabled = verified.save.live_enabled and session.snapshot().status != "offline_only"
        journal = P3Journal(
            output,
            content.config.meta.run_id,
            prior_raw=verified.logs,
            reservation_lookup=session.verify_reservation,
            fault=fault,
        )
        runtimes = _roster(
            inputs,
            content.config.meta.run_id,
            provider=provider,
            fallback=fallback,
            budget=session,
            journal=journal,
            live_enabled=live_enabled,
            restored=verified.save,
            selector=selector,
            selector_sha256=selector_sha256,
            clock_ms=clock_ms,
        )
        history = decode_records(verified.logs["events.jsonl"], WorldEvent, source / "events.jsonl")
        loop = P3BoundaryLoop(
            create_engine(content, verified.save.world, history), runtimes, session, verified.save
        )
        save = _drive_live(
            loop,
            count,
            output,
            journal,
            session,
            inputs_hash=verified.save.input_manifest_sha256,
            inputs=inputs,
            live_enabled=live_enabled,
            origins=(*verified.origins, origin),
            fault=fault,
            observer=on_boundary_committed,
        )
        return _finish(save, output, new_ancestors, source_reader, inputs.case.ticks)


class _RecordedBudget:
    """A local audit mirror, deliberately unable to access or reserve real capacity."""

    def __init__(self, final: SavePackageP3, initial: SavePackageP3 | None = None) -> None:
        self._final = final
        self.entries = (
            [] if initial is None else [e.model_copy(deep=True) for e in initial.allocation_entries]
        )
        self._decisions: set[str] = set()

    def admit(
        self,
        call_id: str,
        input_tokens: int,
        output_tokens: int,
        provider_request_sha256: str,
        wire_body_sha256: str,
    ) -> CallReservation | None:
        raise ReplayDiverged("recorded replay attempted budget admission")

    def commit(self, decision_id: str, debits: list[CallDebit]) -> None:
        if decision_id in self._decisions:
            raise ReplayDiverged("recorded decision committed twice")
        for debit in debits:
            index = len(self.entries)
            if index >= len(self._final.allocation_entries):
                raise ReplayDiverged("recorded debit exceeds retained allocation entries")
            entry = self._final.allocation_entries[index]
            if (
                entry.state != "settled"
                or entry.debit != debit
                or not debit.call_id.startswith(decision_id + ":")
            ):
                raise ReplayDiverged("recorded debit differs from retained allocation entry")
            self.entries.append(entry.model_copy(deep=True))
        self._decisions.add(decision_id)

    def import_origin(self, origin: ResumeOriginP3) -> None:
        for entry in origin.recovery_entries:
            index = len(self.entries)
            if (
                entry.reservation.reservation_ordinal != index
                or index >= len(self._final.allocation_entries)
                or entry != self._final.allocation_entries[index]
            ):
                raise ReplayDiverged(
                    "recovery import is repeated or differs from recorded allocation"
                )
            self.entries.append(entry.model_copy(deep=True))

    def ledger(self) -> BudgetLedgerP3:
        return _ledger(
            self._final.run_budget.allocation_key, self._final.run_budget.caps, self.entries
        )


class _RecordedAudit:
    def __init__(self, source: VerifiedP3Checkpoint, start: SavePackageP3 | None) -> None:
        self.records = decode_records(
            source.logs["decisions-p3.jsonl"], DecisionRecordP3, Path("decisions-p3.jsonl")
        )
        self.contexts = decode_records(
            source.logs["contexts-p3.jsonl"], ContextRecordP3, Path("contexts-p3.jsonl")
        )
        self.events = decode_records(source.logs["events.jsonl"], WorldEvent, Path("events.jsonl"))
        self._event_rows = source.logs["events.jsonl"].splitlines(keepends=True)
        self._decision_rows = source.logs["decisions-p3.jsonl"].splitlines(keepends=True)
        self._event_cursor = 0 if start is None else start.event_cursor
        self._decision_cursor = 0 if start is None else start.decision_record_cursor
        self._audit_rows: dict[str, dict[str, list[bytes]]] = {}
        for name, model in (
            ("contexts-p3.jsonl", ContextRecordP3),
            ("llm-dispatches.jsonl", AttemptDispatch),
            ("llm-calls.jsonl", LLMCallRecordP3),
        ):
            by_decision: dict[str, list[bytes]] = {}
            for row, raw in zip(
                decode_records(source.logs[name], model, Path(name)),
                source.logs[name].splitlines(keepends=True),
                strict=True,
            ):
                assert isinstance(row, (ContextRecordP3, AttemptDispatch, LLMCallRecordP3))
                by_decision.setdefault(row.decision_id, []).append(raw)
            self._audit_rows[name] = by_decision

    def append(
        self, journal: P3Journal, commit: WorldTickCommit, records: Sequence[DecisionRecordP3]
    ) -> None:
        end = self._event_cursor + len(commit.events)
        if commit.events != list(self.events[self._event_cursor : end]):
            raise ReplayDiverged(f"event bytes differ at tick {commit.snapshot.tick}")
        journal.append_recorded(
            "events.jsonl", b"".join(self._event_rows[self._event_cursor : end])
        )
        self._event_cursor = end
        for record in records:
            if (
                self._decision_cursor >= len(self.records)
                or record != self.records[self._decision_cursor]
            ):
                raise ReplayDiverged("decision row differs from the recorded source")
            for name in ("contexts-p3.jsonl", "llm-dispatches.jsonl", "llm-calls.jsonl"):
                journal.append_recorded(
                    name, b"".join(self._audit_rows[name].get(record.decision_id, []))
                )
            journal.append_recorded(
                "decisions-p3.jsonl", self._decision_rows[self._decision_cursor]
            )
            self._decision_cursor += 1

    def finish(self) -> None:
        if self._event_cursor != len(self.events) or self._decision_cursor != len(self.records):
            raise ReplayDiverged("recorded replay left unconsumed decisions or events")


def _retained_evidence(origin: ResumeOriginP3, directories: Sequence[Path]) -> dict[str, bytes]:
    evidence: dict[str, bytes] = {}
    for item in origin.orphan_artifacts:
        matches = [
            directory / "recovery-evidence" / f"{item.sha256}.bin" for directory in directories
        ]
        raw = next((path.read_bytes() for path in matches if path.is_file()), None)
        if raw is None or sha256(raw).hexdigest() != item.sha256:
            raise ReplayDiverged("retained recovery evidence missing or corrupt")
        evidence[item.name] = raw
    return evidence


def reexecute_p3(
    source: Path,
    output: Path,
    *,
    provider: ProviderAdapter,
    fallback: FallbackAdapter,
    source_reader: SourceReader,
    allocation_store: object | None = None,
    ancestors: tuple[Path, ...] = (),
    start_checkpoint: Path | None = None,
    selector: RetrievalSelector | None = None,
    selector_sha256: str | None = None,
    on_boundary_committed: BoundaryObserver | None = None,
) -> P3RunResult:
    """Replay immutable records, with no access to the injected authority or provider.

    The destination is a container of standard suffix-only run segments, one per
    retained origin. The result identifies its final segment and ancestor locators.
    A checkpoint resume consumes only decisions after that verified boundary.
    """
    source = source.resolve()
    try:
        trace, final = load_trace_p3(
            source / "decision-trace-p3.json", ancestors=ancestors, source_reader=source_reader
        )
        initial = (
            None
            if start_checkpoint is None
            else read_checkpoint_p3(
                start_checkpoint, ancestors=ancestors, source_reader=source_reader
            )
        )
        if initial is not None:
            if initial.inputs != final.inputs or initial.save.world.tick > final.save.world.tick:
                raise ReplayDiverged("replay checkpoint is not part of the recorded input lineage")
            for prefix in initial.save.log_prefixes:
                raw = b"".join(final.logs[prefix.name].splitlines(keepends=True)[: prefix.records])
                if raw != initial.logs[prefix.name]:
                    raise ReplayDiverged("replay checkpoint prefixes differ from the source trace")
        registration = TrialRegistration.model_validate_json(
            final.inputs["trial-registration.json"]
        )
        case_id = next(
            case.case_id
            for case in registration.cases
            if canonical_sha256(
                {
                    "registration_sha256": sha256(
                        final.inputs["trial-registration.json"]
                    ).hexdigest(),
                    "case_id": case.case_id,
                }
            )
            == final.save.run_budget.allocation_key
        )
        inputs = _Inputs.parse(final.inputs, case_id)
        inputs.check_selector(selector, selector_sha256)
        if trace.final_tick != inputs.case.ticks:
            raise ReplayDiverged("trace does not reach its registered horizon")
        content = load_run_content(
            source,
            expected_config_hash=final.save.canonical_config_hash,
            expected_map_hash=final.save.canonical_map_hash,
        )
        output = _fresh_output(output)
        if output == source or source in output.parents:
            raise ReplayDiverged("replay destination must be separate from source")
        directory = output / "segment-0000"
        origins: list[ResumeOriginP3] = []
        replay_ancestors: tuple[Path, ...] = ()
        restored = None if initial is None else initial.save
        if initial is None:
            directory.mkdir(parents=True)
            retain_inputs(directory, final.inputs, run_id=trace.run_id, source_reader=source_reader)
            journal = P3Journal(directory, trace.run_id)
        else:
            assert start_checkpoint is not None
            origin = prepare_continuation(start_checkpoint.parent, initial, directory)
            origins = [*initial.origins, origin]
            replay_ancestors = (start_checkpoint.resolve(), *ancestors)
            journal = P3Journal(directory, trace.run_id, prior_raw=initial.logs)
        mirror = _RecordedBudget(final.save, restored)
        audit = _RecordedAudit(final, restored)
        live_enabled = True if restored is None else restored.live_enabled

        def build_loop(save: SavePackageP3 | None) -> P3BoundaryLoop:
            runtimes = _roster(
                inputs,
                trace.run_id,
                provider=provider,
                fallback=fallback,
                budget=mirror,
                journal=journal,
                live_enabled=live_enabled,
                restored=save,
                records=audit.records,
                contexts=audit.contexts,
                selector=selector,
                selector_sha256=selector_sha256,
            )
            history = () if save is None else audit.events[: save.event_cursor]
            return P3BoundaryLoop(
                create_engine(content, None if save is None else save.world, history),
                runtimes,
                mirror,
                save,
            )

        loop = build_loop(restored)
        if restored is None:
            audit.append(journal, loop.boundary, [])

        def publish() -> SavePackageP3:
            save = loop.checkpoint(
                input_manifest_sha256=final.save.input_manifest_sha256,
                log_prefixes=journal.prefixes(),
                run_budget=mirror.ledger(),
                allocation_entries=mirror.entries,
                live_enabled=live_enabled,
            )
            return publish_checkpoint(
                directory / checkpoint_filename(save.world.tick), save, journal, origins=origins
            )

        pending_origins = list(final.origins)
        if initial is not None:
            inherited = {canonical_sha256(origin) for origin in initial.origins}
            pending_origins = [
                origin for origin in pending_origins if canonical_sha256(origin) not in inherited
            ]
            if any(origin.checkpoint_tick < initial.save.world.tick for origin in pending_origins):
                raise ReplayDiverged("checkpoint skipped a required recovery origin")
        segment = 0
        save = publish()
        while True:
            while pending_origins and pending_origins[0].checkpoint_tick == save.world.tick:
                origin = pending_origins.pop(0)
                if canonical_sha256(save) != origin.checkpoint_sha256:
                    raise ReplayDiverged("replay state differs at an origin boundary")
                previous_path = directory / checkpoint_filename(save.world.tick)
                previous = read_checkpoint_p3(
                    previous_path, ancestors=replay_ancestors, source_reader=source_reader
                )
                segment += 1
                directory = output / f"segment-{segment:04d}"
                evidence = _retained_evidence(origin, [source, *(p.parent for p in ancestors)])
                prepare_continuation(
                    previous_path.parent,
                    previous,
                    directory,
                    offline_origin=origin,
                    evidence=evidence,
                )
                replay_ancestors = (previous_path, *replay_ancestors)
                origins.append(origin)
                mirror.import_origin(origin)
                if origin.recovery_mode == "offline":
                    live_enabled = False
                journal = P3Journal(directory, trace.run_id, prior_raw=previous.logs)
                loop = build_loop(save)
                save = publish()
            if save.world.tick == trace.final_tick:
                break
            boundary, records = loop.advance()
            audit.append(journal, boundary, records)
            save = publish()
            if on_boundary_committed is not None:
                on_boundary_committed(
                    boundary.snapshot.model_copy(deep=True), tuple(boundary.events)
                )
        audit.finish()
        if pending_origins or canonical_bytes(save) != final.raw:
            raise ReplayDiverged("final recorded world/runtime/budget/checkpoint bytes differ")
        result = _finish(save, directory, replay_ancestors, source_reader, trace.final_tick)
        if result.trace != trace:
            raise ReplayDiverged("final replay trace differs from source")
        return result
    except (OSError, ValueError) as exc:
        if isinstance(exc, ReplayDiverged):
            raise
        raise ReplayDiverged(str(exc)) from exc


class P3BoundaryLoop:
    """Commit each resident decision once, then publish a pre-ingest world boundary.

    A failed interval poisons this coordinator. Durable recovery uses its previous
    checkpoint; it must never rewind IO or re-enter an already dispatched decision.
    """

    def __init__(
        self,
        engine: WorldEngine,
        runtimes: Mapping[str, ResidentRuntimeP3],
        budget: DecisionBudgetPort,
        restored: SavePackageP3 | None = None,
    ) -> None:
        self._engine = engine
        self._runtimes = dict(runtimes)
        self._budget = budget
        self._commit = (
            engine.initial_commit()
            if restored is None
            else WorldTickCommit(
                snapshot=restored.world,
                events=[],
                pending_deliveries=restored.pending_perception_deliveries,
            ).model_copy(deep=True)
        )
        actors = {r.id for r in self._commit.snapshot.residents}
        if set(self._runtimes) != actors or any(
            runtime.export_state().actor_id != actor for actor, runtime in self._runtimes.items()
        ):
            raise ValueError("P3 requires exactly one matching runtime per resident")
        self._cursors = dict.fromkeys(self._runtimes, -1)
        self._deferred: dict[str, set[DecisionTrigger]] = {actor: set() for actor in self._runtimes}
        self._queued: dict[str, ActionPlan] = {}
        self._at_boundary = True
        self._decision_cursor = 0
        if restored is not None:
            self._decision_cursor = restored.decision_record_cursor
            self._cursors = {
                c.actor_id: c.last_observed_tick
                for c in restored.agent_state.delivered_perception_ticks
            }
            saved = {s.actor_id: s for s in restored.agent_state.runtime_states}
            if any(self._runtimes[a].export_state() != saved[a] for a in actors):
                raise ValueError("runtime restoration differs from the checkpoint")
            living = {r.id for r in restored.world.residents if r.alive}
            for plan in restored.agent_state.queued_plans:
                if plan.actor_id not in living or plan.actor_id in self._queued:
                    raise ValueError("invalid restored P3 queue")
                self._queued[plan.actor_id] = plan.model_copy(deep=True)
            for item in restored.agent_state.deferred_decision_triggers:
                if item.actor_id not in living:
                    raise ValueError("invalid restored deferred triggers")
                self._deferred[item.actor_id].update(item.reasons)

    @property
    def boundary(self) -> WorldTickCommit:
        return self._commit.model_copy(deep=True)

    @property
    def decision_record_cursor(self) -> int:
        return self._decision_cursor

    def checkpoint(
        self,
        *,
        input_manifest_sha256: str,
        log_prefixes: Sequence[LogPrefix],
        run_budget: BudgetLedgerP3,
        allocation_entries: Sequence[AllocationEntry],
        live_enabled: bool,
    ) -> SavePackageP3:
        if not self._at_boundary:
            raise ValueError("checkpoint requires a completed pre-ingest P3 boundary")
        prefixes = {p.name: p.records for p in log_prefixes}
        world = self._commit.snapshot
        return SavePackageP3(
            save_schema_version="0.2",
            world=world,
            agent_state=AgentStateP3(
                profiles=[],
                goal_states=[],
                personal_memories=[],
                relationships=[],
                queued_plans=[self._queued[a] for a in sorted(self._queued)],
                deferred_decision_triggers=[
                    DeferredDecisionTriggers(
                        actor_id=a,
                        reasons=[r for r in DECISION_TRIGGERS if r in self._deferred[a]],
                    )
                    for a in sorted(self._deferred)
                    if self._deferred[a]
                ],
                delivered_perception_ticks=[
                    DeliveryCursor(actor_id=a, last_observed_tick=t)
                    for a, t in sorted(self._cursors.items())
                ],
                runtime_states=[self._runtimes[a].export_state() for a in sorted(self._runtimes)],
            ),
            event_cursor=world.event_log_cursor,
            llm_record_cursor=prefixes["llm-calls.jsonl"],
            decision_record_cursor=self._decision_cursor,
            context_record_cursor=prefixes["contexts-p3.jsonl"],
            dispatch_record_cursor=prefixes["llm-dispatches.jsonl"],
            pending_perception_deliveries=self._commit.pending_deliveries,
            canonical_config_hash=world.config_hash,
            canonical_map_hash=world.map_hash,
            input_manifest_sha256=input_manifest_sha256,
            log_prefixes=list(log_prefixes),
            run_budget=run_budget,
            allocation_entries=list(allocation_entries),
            live_enabled=live_enabled,
        ).model_copy(deep=True)

    def advance(self) -> tuple[WorldTickCommit, list[DecisionRecordP3]]:
        if not self._at_boundary:
            raise ValueError("P3 simulation stopped inside an incomplete interval")
        self._at_boundary = False
        self._engine.begin_tick()
        self._ingest()
        records, starts = self._schedule()
        for intent in starts:
            self._engine.start_intent(intent)
        self._commit = self._engine.advance_tick()
        for resident in self._commit.snapshot.residents:
            if not resident.alive:
                self._queued.pop(resident.id, None)
                self._deferred[resident.id].clear()
        for packet in self._commit.pending_deliveries:
            feedback = packet.perception.last_action_feedback
            if feedback is not None and feedback.status != "success":
                self._queued.pop(packet.actor_id, None)
        self._decision_cursor += len(records)
        self._at_boundary = True
        return self.boundary, records

    def _ingest(self) -> None:
        world = self._commit.snapshot
        living = sorted(r.id for r in world.residents if r.alive)
        if [p.actor_id for p in self._commit.pending_deliveries] != living:
            raise ValueError("expected one pending P3 packet per living resident")
        for packet in self._commit.pending_deliveries:
            actor = packet.actor_id
            if (
                packet.delivery_id != format_delivery_id(world.run_id, world.tick, actor)
                or packet.observed_tick != world.tick
                or self._cursors[actor] != world.tick - 1
            ):
                raise ValueError("pending P3 delivery identity/cursor mismatch")
            self._runtimes[actor].ingest(packet)
            self._cursors[actor] = packet.observed_tick
            self._deferred[actor].update(packet.decision_triggers)
            feedback = packet.perception.last_action_feedback
            if feedback is not None and feedback.status == "success" and actor not in self._queued:
                self._deferred[actor].add("PLAN_FINISHED")

    def _schedule(self) -> tuple[list[DecisionRecordP3], list[ActionIntent]]:
        world = self._commit.snapshot
        active = {a.intent.actor_id for a in world.active_actions}
        records: list[DecisionRecordP3] = []
        starts: list[ActionIntent] = []
        for actor in sorted(self._runtimes):
            if actor in active or self._cursors[actor] != world.tick:
                continue
            deferred = self._deferred[actor]
            if world.tick == 0 or deferred:
                self._queued.pop(actor, None)
                triggers = [r for r in DECISION_TRIGGERS if r in deferred] if world.tick else []
                runtime = self._runtimes[actor]
                request = runtime.make_request(world.tick, triggers)
                record = runtime.decide(request)
                # This changes only the run mirror; settlement awaits checkpoint publication.
                self._budget.commit(record.decision_id, record.budget_debits)
                runtime.commit_decision(record)
                self._queued[actor] = record.plan.model_copy(deep=True)
                records.append(record)
                deferred.clear()
                if record.policy_id == "llm-v0" and record.substituted:
                    self._fallback_fact(record)
            plan = self._queued.pop(actor)
            intent, *remaining = plan.intents
            starts.append(intent)
            if remaining:
                self._queued[actor] = plan.model_copy(update={"intents": remaining}, deep=True)
        return records, starts

    def _fallback_fact(self, record: DecisionRecordP3) -> None:
        reason = {
            "TIMEOUT": "TIMEOUT",
            "PARSE_ERROR": "PARSE_ERROR",
            "INVALID_PLAN": "PARSE_ERROR",
            "INVALID_DELTA": "PARSE_ERROR",
            "INVALID_CONTEXT": "BUDGET",
            "BUDGET": "BUDGET",
            "PROVIDER_ERROR": "PROVIDER_ERROR",
        }.get(record.error_kind or "")
        if reason is None:
            raise ValueError("unpublishable P3 fallback error")
        self._engine.append_fact(
            "agent_fallback_used",
            record.actor_id,
            None,
            None,
            record.llm_call_id,
            [],
            AgentFallbackUsedPayload.model_validate(
                {
                    "resident_id": record.actor_id,
                    "reason": reason,
                    "fallback_policy_id": record.effective_policy_id,
                }
            ),
        )
