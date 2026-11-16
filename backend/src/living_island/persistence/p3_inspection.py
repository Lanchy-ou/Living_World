"""Authority-free verification and deterministic P3 inspection export.

The reader verifies complete committed boundaries and replays only pure cognitive
reducers. It never opens allocation authority, dispatches, or writes source files.
"""

from __future__ import annotations

import importlib.util
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cache
from hashlib import sha256
from pathlib import Path

from living_island.agents.p3.cognition import (
    advance_goal_evidence,
    apply_goal_change,
    attached_goal_id,
)
from living_island.agents.p3.context import assemble_context
from living_island.agents.p3.types import ContextProfile
from living_island.contract.p3_inspection import (
    RECENT_LIMIT,
    SHARD_LIMIT,
    AttemptDispatch,
    ContextRecordP3,
    DecisionInspection,
    DecisionRecordP3,
    InspectionActor,
    InspectionDecisionRef,
    InspectionSampleRef,
    LLMCallRecordP3,
    P3InspectionIndex,
    ResidentInspection,
    ResidentRuntimeStateP3,
    ShardRef,
    canonical_bytes,
    canonical_sha256,
    decision_filename,
    sample_filename,
)
from living_island.contract.p3_save import DecisionTraceP3, ImplementationPin, TrialRegistration
from living_island.contract.projections import project_frame
from living_island.contract.replay import ReplayBundle
from living_island.events import WorldEvent
from living_island.memory.experience import capture_accepted_decision, ingest_experience
from living_island.memory.p3_types import RetrievalSelector
from living_island.persistence.content import load_run_content
from living_island.persistence.p3 import (
    SourceReader,
    VerifiedP3Checkpoint,
    _VerificationSession,
    decode_records,
    git_source_reader,
    load_trace_p3,
    read_checkpoint_p3,
)

SELECTOR_HELPER = "backend/tests/fixtures/p3/extensions/recent_only.py"
SELECTOR_DEPENDENCIES = (
    "backend/src/living_island/memory/p3_types.py",
    "backend/src/living_island/memory/retrieval.py",
)


class GitSourceReader:
    """Cache immutable Git blobs across all boundaries of an export."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()
        self._read = cache(git_source_reader(self.repository))

    def __call__(self, commit: str, path: str) -> bytes:
        return self._read(commit, path)


def resolve_selector(
    registration: TrialRegistration,
    implementation: ImplementationPin,
    profile: ContextProfile,
    *,
    repository: Path,
    source_reader: SourceReader,
) -> RetrievalSelector | None:
    """Resolve only the reviewed fixed helper, never a registered executable path."""
    module = next(m for m in implementation.modules if m.role == "selector")
    pins = {pin.path: pin.sha256 for pin in module.files}
    inputs = {pin.path: pin.sha256 for pin in registration.input_pins}
    registered = {
        p.path: p.sha256 for p in [*registration.implementation_pins, *registration.input_pins]
    }
    pure_dependencies = (
        *SELECTOR_DEPENDENCIES,
        "backend/src/living_island/agents/p3/context.py",
        "backend/src/living_island/agents/p3/cognition.py",
        "backend/src/living_island/memory/experience.py",
    )
    for path in pure_dependencies:
        source = source_reader(implementation.code_commit, path)
        digest = sha256(source).hexdigest()
        if registered.get(path) != digest or (repository / path).read_bytes() != source:
            raise ValueError(
                "installed pure assembly implementation differs from registered source"
            )
        if path in SELECTOR_DEPENDENCIES and pins.get(path) != digest:
            raise ValueError("selector role lacks its exact production dependency pins")
    if profile.retrieval_profile == "recent-relevant-v0":
        return None
    if registration.purpose != "fake" or registration.fake_fixture_id != "vf-20":
        raise ValueError("alternate selector requires the registered VF-20 fake fixture")
    for path in (SELECTOR_HELPER, *SELECTOR_DEPENDENCIES):
        source = source_reader(implementation.code_commit, path)
        digest = sha256(source).hexdigest()
        if pins.get(path) != digest or inputs.get(path) != digest:
            raise ValueError("alternate selector requires exact helper and dependency pins")
        if (repository / path).read_bytes() != source:
            raise ValueError("installed fixed selector differs from source-pinned implementation")
    spec = importlib.util.spec_from_file_location(
        "p3_inspection_recent_only", repository / SELECTOR_HELPER
    )
    if spec is None or spec.loader is None:
        raise ValueError("fixed selector helper unavailable")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    selector: RetrievalSelector = helper.RecentOnlySelector(pins[SELECTOR_HELPER])
    return selector


@dataclass(frozen=True)
class VerifiedInspection:
    source_directories: tuple[Path, ...]
    trace: DecisionTraceP3
    trace_bytes: bytes
    registration: TrialRegistration
    replay: ReplayBundle
    replay_bytes: bytes
    final: VerifiedP3Checkpoint
    decisions: tuple[DecisionInspection, ...]
    samples: tuple[ResidentInspection, ...]


def _segments(
    source: Path, final: VerifiedP3Checkpoint, ancestors: tuple[Path, ...]
) -> list[tuple[Path, int, int]]:
    remaining = list(ancestors)
    current = source / f"checkpoint-{final.save.world.tick:010d}.json"
    lineage: list[tuple[Path, int]] = []
    for origin in reversed(final.origins):
        matches = [
            p
            for p in remaining
            if p.resolve() != current.resolve()
            and sha256(p.read_bytes()).hexdigest() == origin.checkpoint_sha256
        ]
        if not matches:
            raise ValueError("inspection requires every verified nearest-first origin locator")
        current = matches[0]
        remaining = [p for p in remaining if p != current]
        lineage.append((current.parent, origin.checkpoint_tick))
    segments = []
    start = 0
    for directory, tick in reversed(lineage):
        segments.append((directory, start, tick))
        start = tick
    segments.append((source, start, final.save.world.tick))
    return segments


def _advance(
    checkpoint: VerifiedP3Checkpoint,
    decisions: list[DecisionInspection],
    profile: ContextProfile,
    selector: RetrievalSelector | None,
    fake: bool,
) -> dict[str, ResidentRuntimeStateP3]:
    states = {s.actor_id: s for s in checkpoint.save.agent_state.runtime_states}
    by_actor = {d.record.actor_id: d for d in decisions}
    for delivery in checkpoint.save.pending_perception_deliveries:
        state = states[delivery.actor_id]
        cognitive = state.cognitive_state
        goals = advance_goal_evidence(
            delivery,
            cognitive.experience.intent_refs,
            cognitive.goals,
            run_id=checkpoint.save.world.run_id,
        )
        experience = ingest_experience(
            cognitive.experience, delivery, run_id=checkpoint.save.world.run_id
        )
        cognitive = cognitive.model_copy(update={"goals": goals, "experience": experience})
        state = state.model_copy(
            update={"cognitive_state": cognitive, "latest_perception_tick": delivery.observed_tick}
        )
        shard = by_actor.pop(delivery.actor_id, None)
        if shard is not None:
            record = shard.record
            if canonical_sha256(state) != record.state_before_sha256:
                raise ValueError("decision before-state does not match delivered cognitive input")
            assembly = assemble_context(
                delivery.perception,
                cognitive,
                profile,
                purpose="recorded-fake" if fake else "live",
                selector=selector,
                selector_sha256=None if selector is None else selector.implementation_sha256,
            )
            if assembly != shard.context.assembly:
                raise ValueError("source-pinned assembly differs from committed complete context")
            goals = apply_goal_change(
                goals, record.accepted_delta.goal_change, actor_id=record.actor_id, tick=record.tick
            )
            experience = capture_accepted_decision(
                experience,
                record.run_id,
                record.decision_id,
                record.decision_ordinal,
                record.plan,
                attached_goal_id(goals),
                max_plan_actions=state.policy_config.max_plan_actions,
            )
            cognitive = cognitive.model_copy(update={"goals": goals, "experience": experience})
            state = state.model_copy(
                update={
                    "cognitive_state": cognitive,
                    "next_decision_ordinal": state.next_decision_ordinal + 1,
                    "policy_private": record.policy_private_after,
                }
            )
            if canonical_sha256(state) != record.state_after_sha256:
                raise ValueError("decision after-state differs from accepted transaction")
        states[state.actor_id] = state
    if by_actor:
        raise ValueError("decision has no own committed delivery")
    return states


def verify_inspection_source(
    source: Path,
    replay_path: Path,
    *,
    repository: Path,
    ancestors: tuple[Path, ...] = (),
    source_reader: SourceReader | None = None,
) -> VerifiedInspection:
    source = source.resolve()
    verification = _VerificationSession()
    reader = cache(source_reader or GitSourceReader(repository))
    trace_path = source / "decision-trace-p3.json"
    trace_bytes = trace_path.read_bytes()
    trace, final = load_trace_p3(
        trace_path, ancestors=ancestors, source_reader=reader, verification=verification
    )
    for name, committed in final.logs.items():
        actual = (source / name).read_bytes()
        # Continuations store only a suffix, whose start is fixed by the nearest origin.
        inherited = (
            0
            if not final.origins
            else next(p.records for p in final.origins[-1].log_prefixes if p.name == name)
        )
        suffix = b"".join(committed.splitlines(keepends=True)[inherited:])
        if actual != suffix:
            extra = max(0, actual.count(b"\n") - suffix.count(b"\n"))
            raise ValueError(f"uncommitted/orphan source tail: {name}; extra_records={extra}")
    registration = TrialRegistration.model_validate_json(final.inputs["trial-registration.json"])
    profile = ContextProfile.model_validate_json(final.inputs["context-profile.json"])
    implementation = ImplementationPin.model_validate_json(final.inputs["implementation.json"])
    selector = resolve_selector(
        registration, implementation, profile, repository=repository, source_reader=reader
    )
    replay_bytes = replay_path.read_bytes()
    replay = ReplayBundle.model_validate_json(replay_bytes)
    if (replay.run_id, replay.config_hash, replay.map_hash, replay.frames[-1].tick) != (
        trace.run_id,
        trace.config_hash,
        trace.map_hash,
        trace.final_tick,
    ):
        raise ValueError("replay run/config/map/horizon differs from committed source")
    content = load_run_content(
        source, expected_config_hash=trace.config_hash, expected_map_hash=trace.map_hash
    )
    config = content.config
    if (
        replay.world_id != config.meta.world_id
        or replay.map.rows != list(content.map_rows)
        or replay.map.width != config.map.width
        or replay.map.height != config.map.height
        or replay.condition_bounds.min_value != config.needs.min_value
        or replay.condition_bounds.max_value != config.needs.max_value
        or any(
            getattr(replay.clock, name) != getattr(config.time, name)
            for name in ("tick_minutes", "start_hour", "day_start_hour", "day_end_hour")
        )
    ):
        raise ValueError("replay metadata differs from retained effective world configuration")
    records = decode_records(
        final.logs["decisions-p3.jsonl"], DecisionRecordP3, source, verification=verification
    )
    contexts = decode_records(
        final.logs["contexts-p3.jsonl"], ContextRecordP3, source, verification=verification
    )
    dispatches = decode_records(
        final.logs["llm-dispatches.jsonl"], AttemptDispatch, source, verification=verification
    )
    calls = decode_records(
        final.logs["llm-calls.jsonl"], LLMCallRecordP3, source, verification=verification
    )
    events = decode_records(
        final.logs["events.jsonl"], WorldEvent, source, verification=verification
    )
    if list(events) != replay.events:
        raise ValueError("replay objective events differ from committed prefix")
    by_dispatch = {d.call_id: d for d in dispatches}
    by_call = {c.call_id: c for c in calls}
    outcomes: dict[str, list[str]] = defaultdict(list)
    for event in events:
        if event.intent_id is not None:
            outcomes[event.intent_id].append(event.event_id)
    event_order = {e.event_id: i for i, e in enumerate(events)}
    decisions = tuple(
        DecisionInspection(
            inspection_schema_version="0.1",
            record=record,
            context=context,
            dispatches=[by_dispatch[c] for c in record.call_ids],
            calls=[by_call[c] for c in record.call_ids],
            outcome_event_ids=sorted(
                (event for intent in record.plan.intents for event in outcomes[intent.intent_id]),
                key=event_order.__getitem__,
            ),
        )
        for record, context in zip(records, contexts, strict=True)
    )
    by_tick: dict[int, list[DecisionInspection]] = defaultdict(list)
    for decision in decisions:
        by_tick[decision.record.tick].append(decision)
    actors = [s.actor_id for s in final.save.agent_state.runtime_states]
    if [r.id for r in replay.residents] != actors:
        raise ValueError("replay roster differs from retained runtime identities")
    identities = {
        s.actor_id: s.cognitive_state.identity for s in final.save.agent_state.runtime_states
    }
    if any(r.display_name != identities[r.id].display_name for r in replay.residents):
        raise ValueError("replay names differ from retained identities")
    segments = _segments(source, final, ancestors)
    final_lines = {name: raw.splitlines(keepends=True) for name, raw in final.logs.items()}
    counts = Counter(e.tick for e in events)
    event_cursor = 0
    latest: dict[str, str | None] = dict.fromkeys(actors)
    expected_states: dict[str, ResidentRuntimeStateP3] | None = None
    samples: list[ResidentInspection] = []
    for tick in range(trace.final_tick + 1):
        directory = next(d for d, lower, upper in reversed(segments) if lower <= tick <= upper)
        checkpoint = read_checkpoint_p3(
            directory / f"checkpoint-{tick:010d}.json",
            ancestors=ancestors,
            source_reader=reader,
            verification=verification,
        )
        if checkpoint.inputs != final.inputs:
            raise ValueError("boundary inputs differ from completed lineage")
        for prefix in checkpoint.save.log_prefixes:
            if checkpoint.logs[prefix.name] != b"".join(final_lines[prefix.name][: prefix.records]):
                raise ValueError("boundary prefix is outside completed lineage")
        event_cursor += counts[tick]
        if checkpoint.save.event_cursor != event_cursor:
            raise ValueError("boundary event cursor differs from committed event order")
        if project_frame(checkpoint.save.world, counts[tick]) != replay.frames[tick]:
            raise ValueError("replay frame differs from exact committed boundary")
        states = checkpoint.save.agent_state.runtime_states
        if [s.actor_id for s in states] != actors:
            raise ValueError("boundary actor roster changed")
        if expected_states is not None and expected_states != {s.actor_id: s for s in states}:
            raise ValueError("saved runtime differs from pure delivered/accepted transition")
        for state in states:
            cognitive = state.cognitive_state
            if cognitive.identity != identities[state.actor_id]:
                raise ValueError("boundary identity changed")
            experience = cognitive.experience
            if tick == 0 and (
                experience.next_sequence
                or cognitive.goals.next_goal_sequence
                or state.next_decision_ordinal
                or state.latest_perception_tick != -1
            ):
                raise ValueError("tick-zero cognition must be initial")
            samples.append(
                ResidentInspection(
                    inspection_schema_version="0.1",
                    tick=tick,
                    actor_id=state.actor_id,
                    latest_perception_tick=state.latest_perception_tick,
                    identity=cognitive.identity,
                    goals=cognitive.goals,
                    recent_experience=experience.records[-RECENT_LIMIT:],
                    retained_record_count=len(experience.records),
                    next_sequence=experience.next_sequence,
                    latest_decision_id=latest[state.actor_id],
                    state_sha256=canonical_sha256(state),
                )
            )
        if tick < trace.final_tick:
            expected_states = _advance(
                checkpoint, by_tick[tick], profile, selector, registration.purpose == "fake"
            )
            for decision in by_tick[tick]:
                latest[decision.record.actor_id] = decision.record.decision_id
    return VerifiedInspection(
        tuple(dict.fromkeys([source, *(p.parent.resolve() for p in ancestors)])),
        trace,
        trace_bytes,
        registration,
        replay,
        replay_bytes,
        final,
        decisions,
        tuple(samples),
    )


def checked_shard_bytes(shard: DecisionInspection | ResidentInspection) -> bytes:
    raw = canonical_bytes(shard)
    if len(raw) > SHARD_LIMIT:
        raise ValueError(f"inspection shard exceeds V-06: {len(raw)} > {SHARD_LIMIT}")
    return raw


def export_inspection(verified: VerifiedInspection, output: Path) -> P3InspectionIndex:
    """Publish index last; every shard is checked before creating the fresh directory."""
    resolved = output.resolve()
    if any(
        resolved == source or source in resolved.parents for source in verified.source_directories
    ):
        raise ValueError("inspection output must not modify any source directory")
    if output.exists():
        raise ValueError("inspection output must be a fresh directory")
    files: dict[str, bytes] = {}
    decisions = []
    samples = []
    for shard in verified.decisions:
        record = shard.record
        name = decision_filename(record.decision_id)
        raw = checked_shard_bytes(shard)
        files[name] = raw
        decisions.append(
            InspectionDecisionRef(
                decision_id=record.decision_id,
                actor_id=record.actor_id,
                tick=record.tick,
                ordinal=record.decision_ordinal,
                shard=ShardRef(file=name, sha256=sha256(raw).hexdigest()),
            )
        )
    for sample in verified.samples:
        name = sample_filename(sample.tick, sample.actor_id)
        raw = checked_shard_bytes(sample)
        files[name] = raw
        samples.append(
            InspectionSampleRef(
                actor_id=sample.actor_id,
                tick=sample.tick,
                shard=ShardRef(file=name, sha256=sha256(raw).hexdigest()),
            )
        )
    index = P3InspectionIndex(
        inspection_schema_version="0.1",
        run_id=verified.trace.run_id,
        config_hash=verified.trace.config_hash,
        map_hash=verified.trace.map_hash,
        final_tick=verified.trace.final_tick,
        replay_sha256=sha256(verified.replay_bytes).hexdigest(),
        trace_sha256=sha256(verified.trace_bytes).hexdigest(),
        registration_sha256=canonical_sha256(verified.registration),
        actors=[
            InspectionActor(actor_id=s.actor_id, identity=s.identity)
            for s in verified.samples
            if s.tick == 0
        ],
        decisions=decisions,
        samples=samples,
    )
    files["trace.json"] = verified.trace_bytes
    files["registration.json"] = canonical_bytes(verified.registration)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as stream:
            stream.write(raw)
    with (output / "index.json").open("xb") as stream:
        stream.write(canonical_bytes(index))
    return index
