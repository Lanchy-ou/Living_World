"""Opt-in P3 durable logs, verified snapshots and authority-free recorded inputs.

Allocation authority is injected only at live publication. Readers never consult it.
Continuation files contain suffixes; explicit ancestor locators supply hash-verified
prefixes. No reader repairs, truncates or rewrites its source artifacts.
"""

from __future__ import annotations

import json
import os
import pickle
import subprocess
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any, Protocol, cast

from pydantic import BaseModel

from living_island.agents.p3.cognition import apply_goal_change, attached_goal_id
from living_island.agents.p3.types import (
    AllocationEntry,
    AllocationHead,
    AttemptDispatch,
    CallDebit,
    CaseAllocationP3,
    ContextProfile,
    ContextRecordP3,
    DecisionRecordP3,
    IdentitySource,
    LLMCallRecordP3,
    ModelActionContract,
    ResidentIdentity,
)
from living_island.contract.p3_save import (
    INPUT_NAMES,
    LOG_NAMES,
    ActorPolicyConfig,
    DecisionTraceP3,
    ImplementationPin,
    LogPrefix,
    NamedHash,
    P3InputManifest,
    ResumeOriginP3,
    SavePackageP3,
    TrialRegistration,
)
from living_island.events import WorldEvent
from living_island.memory.p3_types import (
    AcceptedDecisionData,
    FeedbackData,
    OwnedIntentRef,
    canonical_bytes,
    canonical_sha256,
)
from living_island.world.content import (
    EffectiveConfig,
    check_map,
    config_hash,
    map_bytes_from_rows,
    map_hash,
    parse_map_bytes,
)

from ._codec import PersistenceError, decode_model, digest, read_bytes
from .logs import _events_from_bytes
from .p3_allocation import _replace as _durable_replace

if TYPE_CHECKING:
    from .p3_allocation import VerifiedCheckpoint

MANIFEST_NAME = "p3-inputs.json"
ORIGIN_NAME = "resume-origin-p3.json"
TRACE_NAME = "decision-trace-p3.json"
SourceReader = Callable[[str, str], bytes]
Fault = Callable[[str], None]
MODELS: dict[str, type[BaseModel]] = {
    "contexts-p3.jsonl": ContextRecordP3,
    "decisions-p3.jsonl": DecisionRecordP3,
    "events.jsonl": WorldEvent,
    "llm-calls.jsonl": LLMCallRecordP3,
    "llm-dispatches.jsonl": AttemptDispatch,
}


# Only the existing concrete owner DTOs use the internal serialization fast path.
# Other BaseModel classes (including local classes/custom pickle hooks) preserve
# the original model_copy behavior. No serialized payload enters from a caller.
_SERIALIZED_VERIFICATION_MODELS = frozenset(MODELS.values())


class _VerificationSession:
    """Operation-local successful row decodes, never file or lineage acceptance.

    The 128 MiB bound counts retained canonical row bytes, not Python heap.
    Internally encoded payloads (or fallback graphs) and keys add overhead.
    Reused rows are protected for this operation;
    eviction removes only rows not yet reused. When these cannot make room, new
    rows bypass storage, avoiding a repeated full-prefix scan evicting every hot
    row. Capacity zero affects performance only. No authority state is retained.
    """

    def __init__(self, max_raw_bytes: int = 128 * 1024 * 1024) -> None:
        if type(max_raw_bytes) is not int or max_raw_bytes < 0:
            raise ValueError("verification cache capacity must be a nonnegative integer")
        self.max_raw_bytes = max_raw_bytes
        self._rows: OrderedDict[tuple[type[BaseModel], bytes], bytes | BaseModel] = OrderedDict()
        self._cold: OrderedDict[tuple[type[BaseModel], bytes], None] = OrderedDict()
        self.raw_bytes = 0
        self.peak_raw_bytes = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    @property
    def retained_rows(self) -> int:
        return len(self._rows)

    def decode[T: BaseModel](
        self, raw: bytes, model: type[T], path: Path, *, line: int | None = None
    ) -> T:
        key = (model, raw)
        cached = self._rows.get(key)
        if cached is not None:
            self.hits += 1
            self._cold.pop(key, None)
            if isinstance(cached, bytes):
                try:
                    # These bytes are created only by dumps below, never read
                    # from a source file, accepted from a caller, or persisted.
                    return cast(T, pickle.loads(cached))
                except Exception:
                    # Serialization is an optional optimization. Preserve valid
                    # decodes if a Python/Pydantic compatibility issue arises.
                    # Decoder failures remain current and are not caught here.
                    parsed = decode_model(raw, model, path, line=line)
                    self._rows[key] = parsed.model_copy(deep=True)
                    return parsed
            return cast(T, cached.model_copy(deep=True))
        self.misses += 1
        # Preserve the owner's strict scalar, duplicate-key, version, model and
        # canonical-byte validation. Failures never enter the cache.
        parsed = decode_model(raw, model, path, line=line)
        if self.max_raw_bytes and len(raw) <= self.max_raw_bytes:
            while self.raw_bytes + len(raw) > self.max_raw_bytes:
                if not self._cold:
                    return parsed
                old_key, _ = self._cold.popitem(last=False)
                del self._rows[old_key]
                self.raw_bytes -= len(old_key[1])
                self.evictions += 1
            stored: bytes | BaseModel
            if model in _SERIALIZED_VERIFICATION_MODELS:
                try:
                    stored = pickle.dumps(parsed, protocol=pickle.HIGHEST_PROTOCOL)
                except Exception:
                    stored = parsed.model_copy(deep=True)
            else:
                stored = parsed.model_copy(deep=True)
            self._rows[key] = stored
            self._cold[key] = None
            self.raw_bytes += len(raw)
            self.peak_raw_bytes = max(self.peak_raw_bytes, self.raw_bytes)
        return parsed


class PublicationAuthority(Protocol):
    """The already locked allocation publication seam, not a grant source."""

    def prepare(self, head: AllocationHead, entries: Sequence[AllocationEntry]) -> None: ...
    def finalize(
        self, head: AllocationHead, entries: Sequence[AllocationEntry], *, complete: bool = False
    ) -> None: ...


def _fault(callback: Fault | None, stage: str) -> None:
    if callback is not None:
        callback(stage)


def _flush_directory(path: Path) -> None:
    # Published Windows pathnames use MoveFileExW with WRITE_THROUGH. POSIX also
    # flushes directory entries; directory descriptors are unavailable on Windows.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _create(path: Path, raw: bytes, *, fault: Fault | None = None, stage: str = "file") -> None:
    """Publish one immutable file; an exact interrupted retry is idempotent."""
    if path.exists():
        if read_bytes(path) == raw:
            return
        raise PersistenceError(path, "file", "immutable target already exists with different bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            _fault(fault, f"{stage}:before_write")
            stream.write(raw)
            _fault(fault, f"{stage}:after_write")
            stream.flush()
            os.fsync(stream.fileno())
            _fault(fault, f"{stage}:after_fsync")
        if path.exists():
            raise PersistenceError(path, "file", "target appeared during immutable publication")
        _durable_replace(temporary, path)
        temporary = None
        _flush_directory(path.parent)
        _fault(fault, f"{stage}:after_publish")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def git_source_reader(repository: Path) -> SourceReader:
    """Read exact archived tracked blob bytes; never use mutable installed source."""

    def read(commit: str, path: str) -> bytes:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={repository.resolve().as_posix()}",
                "show",
                f"{commit}:{path}",
            ],
            cwd=repository,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise PersistenceError(
                repository / path, "implementation", "pinned revision/blob is unavailable"
            )
        return result.stdout

    return read


def _json(raw: bytes, path: Path) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if canonical_bytes(value) != raw:
            raise ValueError("expected canonical UTF-8 JSON bytes without LF")
        return value
    except (ValueError, TypeError, UnicodeError) as exc:
        raise PersistenceError(path, "JSON", str(exc)) from exc


def _list[T: BaseModel](raw: bytes, model: type[T], path: Path) -> list[T]:
    try:
        value = _json(raw, path)
        if not isinstance(value, list):
            raise ValueError("expected an array")
        result = [model.model_validate(item, strict=True) for item in value]
    except ValueError as exc:
        raise PersistenceError(path, "records", str(exc)) from exc
    return result


def validate_inputs(
    files: Mapping[str, bytes], *, run_id: str, source_reader: SourceReader
) -> None:
    """Verify all retained bytes, typed identities and registration/policy bindings."""
    if tuple(sorted(files)) != INPUT_NAMES:
        raise ValueError("expected exactly the approved retained input names")
    config = decode_model(files["config.json"], EffectiveConfig, Path("config.json"))
    rows = parse_map_bytes(files["map.txt"])
    check_map(config, rows)
    if map_bytes_from_rows(rows) != files["map.txt"] or config.meta.run_id != run_id:
        raise ValueError("retained world bytes/run identity are not canonical")
    registration = decode_model(
        files["trial-registration.json"], TrialRegistration, Path("trial-registration.json")
    )
    pin = decode_model(files["implementation.json"], ImplementationPin, Path("implementation.json"))
    if pin.code_commit != registration.implementation_commit:
        raise ValueError("implementation revision differs from registration")
    registered_sources: dict[str, str] = {}
    for registered_pin in [*registration.implementation_pins, *registration.input_pins]:
        if (
            registered_pin.path in registered_sources
            and registered_sources[registered_pin.path] != registered_pin.sha256
        ):
            raise ValueError(
                "registration inventories assign conflicting hashes to one source path"
            )
        registered_sources[registered_pin.path] = registered_pin.sha256
    if any(
        registered_sources.get(item.path) != item.sha256
        for module in pin.modules
        for item in module.files
    ):
        raise ValueError("implementation modules must resolve to registered source pins")
    for item in [
        *registration.implementation_pins,
        *registration.input_pins,
        *(item for module in pin.modules for item in module.files),
    ]:
        if digest(source_reader(pin.code_commit, item.path)) != item.sha256:
            raise ValueError(f"pinned implementation/input bytes differ: {item.path}")
    identities = _list(files["identities.json"], ResidentIdentity, Path("identities.json"))
    sources = _list(files["identity-sources.json"], IdentitySource, Path("identity-sources.json"))
    policies = _list(
        files["p3-policy-configs.json"], ActorPolicyConfig, Path("p3-policy-configs.json")
    )
    actor_ids = sorted(resident.id for resident in config.residents)
    for values in (identities, sources, policies):
        if [item.actor_id for item in values] != actor_ids:
            raise ValueError("retained actor inputs must cover every resident in actor order")
    profile = decode_model(
        files["context-profile.json"], ContextProfile, Path("context-profile.json")
    )
    action = decode_model(
        files["action-schema.json"], ModelActionContract, Path("action-schema.json")
    )
    if profile.retrieval_profile == "recent-only-fixture-v0" and registration.purpose != "fake":
        raise ValueError("fixture retrieval strategies require a fake registration")
    cases = [case for case in registration.cases if case.seed == config.meta.seed]
    if len(cases) != 1:
        raise ValueError("retained registration must identify one matching world seed")
    case = cases[0]
    expanded: list[ActorPolicyConfig] = []
    for template in case.policy_templates:
        if set(template) != {"actor_id", "config"} or not isinstance(template["config"], dict):
            raise ValueError("policy template must contain exactly actor_id/config")
        if "trial_registration_sha256" in template["config"]:
            raise ValueError("registration template cannot contain its own registration hash")
        expanded.append(
            ActorPolicyConfig.model_validate(
                {
                    "actor_id": template["actor_id"],
                    "config": {
                        **template["config"],
                        "trial_registration_sha256": digest(files["trial-registration.json"]),
                    },
                }
            )
        )
    if expanded != policies:
        raise ValueError("expanded policies differ from registered templates")
    shared: tuple[Any, ...] | None = None
    for identity, source, policy in zip(identities, sources, policies, strict=True):
        cfg = policy.config
        if identity.source_sha256 != canonical_sha256(
            source
        ) or cfg.identity_sha256 != canonical_sha256(identity):
            raise ValueError("identity source/policy hashes differ")
        resident = next(
            resident for resident in config.residents if resident.id == identity.actor_id
        )
        if (source.display_name, source.profile.profile_id, source.initial_direction) != (
            resident.name,
            resident.profile_id,
            resident.initial_goal,
        ):
            raise ValueError("resolved identity differs from world resident source fields")
        if (cfg.seed, cfg.map_width, cfg.map_height, cfg.max_plan_actions) != (
            config.meta.seed,
            config.map.width,
            config.map.height,
            config.agents.max_plan_actions,
        ):
            raise ValueError("P3 policy world configuration differs")
        if (cfg.policy_id == "llm-v0") != (policy.actor_id in case.llm_actor_ids):
            raise ValueError("registered LLM actor assignment differs")
        if (
            cfg.prompt_sha256,
            cfg.action_schema_sha256,
            cfg.action_schema_version,
            cfg.context_profile_id,
        ) != (
            digest(files["prompt.txt"]),
            digest(files["action-schema.json"]),
            action.action_schema_version,
            profile.context_profile_id,
        ):
            raise ValueError("policy prompt/action/context pins differ from retained bytes")
        current = (
            cfg.prompt_version,
            cfg.adapter_id,
            cfg.adapter_version,
            cfg.model_id,
            cfg.provider_settings,
            cfg.limits,
            cfg.pricing,
        )
        if shared is not None and current != shared:
            raise ValueError("all actors must share registered provider/limits/pricing pins")
        shared = current
        if registration.purpose == "fake" and (
            cfg.pricing.input_micro_cny_per_million_tokens
            or cfg.pricing.output_micro_cny_per_million_tokens
            or case.caps.micro_cny
        ):
            raise ValueError("fake registrations require zero prices and money caps")
    if (
        config_hash(config) != registration.world_config_sha256
        or map_hash(rows) != registration.world_map_sha256
    ):
        raise ValueError("registered world input identities differ")


def retain_inputs(
    directory: Path, files: Mapping[str, bytes], *, run_id: str, source_reader: SourceReader
) -> P3InputManifest:
    validate_inputs(files, run_id=run_id, source_reader=source_reader)
    manifest = P3InputManifest(
        input_manifest_version="0.1",
        run_id=run_id,
        files=[NamedHash(name=name, sha256=digest(files[name])) for name in INPUT_NAMES],
    )
    for name in INPUT_NAMES:
        _create(directory / name, files[name])
    _create(directory / MANIFEST_NAME, canonical_bytes(manifest))
    return manifest


def read_inputs(
    directory: Path, *, expected_hash: str | None = None, source_reader: SourceReader | None = None
) -> dict[str, bytes]:
    raw = read_bytes(directory / MANIFEST_NAME)
    if expected_hash is not None and digest(raw) != expected_hash:
        raise PersistenceError(directory / MANIFEST_NAME, "sha256", "input manifest hash mismatch")
    manifest = decode_model(raw, P3InputManifest, directory / MANIFEST_NAME)
    files = {item.name: read_bytes(directory / item.name) for item in manifest.files}
    for item in manifest.files:
        if digest(files[item.name]) != item.sha256:
            raise PersistenceError(directory / item.name, "sha256", "retained input hash mismatch")
    if source_reader is None:
        raise PersistenceError(
            directory / "implementation.json",
            "source_reader",
            "archived implementation reader is required",
        )
    validate_inputs(files, run_id=manifest.run_id, source_reader=source_reader)
    return files


def decode_records[T: BaseModel](
    raw: bytes, model: type[T], path: Path, *, verification: _VerificationSession | None = None
) -> tuple[T, ...]:
    if raw and not raw.endswith(b"\n"):
        raise PersistenceError(path, "JSONL", "committed records must terminate with LF")
    return tuple(
        (
            decode_model(line, model, path, line=index)
            if verification is None
            else verification.decode(line, model, path, line=index)
        )
        for index, line in enumerate(raw.splitlines(), 1)
    )


class P3Journal:
    """Durably stage context/dispatch/terminal rows; accepted prefixes commit later."""

    def __init__(
        self,
        directory: Path,
        run_id: str,
        *,
        prior_raw: Mapping[str, bytes] | None = None,
        reservation_lookup: Callable[[AttemptDispatch], None] | None = None,
        fault: Fault | None = None,
        verification: _VerificationSession | None = None,
    ):
        self.verification = verification
        self.directory, self.run_id = directory, run_id
        self._raw = {name: (prior_raw or {}).get(name, b"") for name in LOG_NAMES}
        self._reservation_lookup, self._fault = reservation_lookup, fault
        self._failed = False
        for name in LOG_NAMES:
            decode_records(
                self._raw[name], MODELS[name], directory / name, verification=self.verification
            )
            if (directory / name).exists():
                raise PersistenceError(directory / name, "file", "journal suffix must be fresh")
        directory.mkdir(parents=True, exist_ok=True)
        for name in LOG_NAMES:
            _create(directory / name, b"")

    def _append(self, name: str, records: Iterable[BaseModel]) -> None:
        if self._failed:
            raise PersistenceError(self.directory / name, "journal", "previous append failed")
        raw = b"".join(canonical_bytes(record) + b"\n" for record in records)
        parsed = decode_records(
            raw, MODELS[name], self.directory / name, verification=self.verification
        )
        if any(getattr(record, "run_id", self.run_id) != self.run_id for record in parsed):
            raise ValueError("journal record has foreign run identity")
        if not raw:
            return
        try:
            with (self.directory / name).open("ab") as stream:
                _fault(self._fault, f"{name}:before_write")
                stream.write(raw)
                _fault(self._fault, f"{name}:after_write")
                stream.flush()
                os.fsync(stream.fileno())
                _fault(self._fault, f"{name}:after_fsync")
            self._raw[name] += raw
        except BaseException:
            self._failed = True
            raise

    def stage_context(self, record: ContextRecordP3) -> None:
        existing = decode_records(
            self._raw["contexts-p3.jsonl"],
            ContextRecordP3,
            self.directory / "contexts-p3.jsonl",
            verification=self.verification,
        )
        if any(item.decision_id == record.decision_id for item in existing):
            raise ValueError("context may be staged exactly once per decision")
        self._append("contexts-p3.jsonl", [record])

    def before_call(self, context: ContextRecordP3, dispatch: AttemptDispatch) -> None:
        if self._reservation_lookup is None:
            raise ValueError("dispatch requires a locked durable reservation verifier")
        self._reservation_lookup(dispatch)
        contexts = decode_records(
            self._raw["contexts-p3.jsonl"],
            ContextRecordP3,
            self.directory / "contexts-p3.jsonl",
            verification=self.verification,
        )
        if not contexts or contexts[-1] != context:
            raise ValueError("dispatch must follow its durably staged exact context")
        _join_context(context, dispatch)
        existing = decode_records(
            self._raw["llm-dispatches.jsonl"],
            AttemptDispatch,
            self.directory / "llm-dispatches.jsonl",
            verification=self.verification,
        )
        if dispatch.call_id in {item.call_id for item in existing}:
            raise ValueError("duplicate dispatched call")
        earlier = [item for item in existing if item.decision_id == dispatch.decision_id]
        calls = decode_records(
            self._raw["llm-calls.jsonl"],
            LLMCallRecordP3,
            self.directory / "llm-calls.jsonl",
            verification=self.verification,
        )
        if dispatch.attempt_index != len(earlier) or (
            earlier and earlier[-1].call_id not in {call.call_id for call in calls}
        ):
            raise ValueError(
                "dispatch attempts must be serial and contiguous after terminal evidence"
            )
        self._append("llm-dispatches.jsonl", [dispatch])

    def after_call(self, record: LLMCallRecordP3) -> None:
        dispatches = decode_records(
            self._raw["llm-dispatches.jsonl"],
            AttemptDispatch,
            self.directory / "llm-dispatches.jsonl",
            verification=self.verification,
        )
        if (
            not dispatches
            or dispatches[-1].call_id != record.call_id
            or canonical_sha256(dispatches[-1]) != record.dispatch_sha256
        ):
            raise ValueError("terminal call must join its durable dispatch")
        _join_call(dispatches[-1], record)
        calls = decode_records(
            self._raw["llm-calls.jsonl"],
            LLMCallRecordP3,
            self.directory / "llm-calls.jsonl",
            verification=self.verification,
        )
        if record.call_id in {item.call_id for item in calls}:
            raise ValueError("duplicate terminal call")
        self._append("llm-calls.jsonl", [record])

    def append_events(self, events: Iterable[WorldEvent]) -> None:
        self._append("events.jsonl", events)

    def append_decisions(self, records: Iterable[DecisionRecordP3]) -> None:
        self._append("decisions-p3.jsonl", records)

    def append_recorded(self, name: str, raw: bytes) -> None:
        """Copy verified audit bytes without any provider/authority interaction."""
        records = decode_records(
            raw, MODELS[name], self.directory / name, verification=self.verification
        )
        self._append(name, records)

    def flush(self) -> None:
        if self._failed:
            raise ValueError("failed journal cannot establish a checkpoint")
        for name in LOG_NAMES:
            with (self.directory / name).open("ab") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            _fault(self._fault, f"{name}:checkpoint_fsync")
        _flush_directory(self.directory)

    def raw_prefixes(self) -> dict[str, bytes]:
        return self._raw.copy()

    def prefixes(self) -> list[LogPrefix]:
        return [
            LogPrefix(
                name=name, records=self._raw[name].count(b"\n"), sha256=digest(self._raw[name])
            )
            for name in LOG_NAMES
        ]


def _join_context(context: ContextRecordP3, dispatch: AttemptDispatch) -> None:
    request, assembly = context.request, context.assembly
    if (
        dispatch.run_id,
        dispatch.decision_id,
        dispatch.actor_id,
        dispatch.tick,
        dispatch.decision_ordinal,
        dispatch.request_sha256,
        dispatch.context_sha256,
        dispatch.projection_sha256,
        dispatch.provider_request,
    ) != (
        context.run_id,
        context.decision_id,
        request.actor_id,
        request.tick,
        request.decision_ordinal,
        canonical_sha256(request),
        assembly.context_sha256,
        assembly.projection_sha256,
        context.provider_request,
    ):
        raise ValueError("context/dispatch chain differs")


def _join_call(dispatch: AttemptDispatch, call: LLMCallRecordP3) -> None:
    for field in (
        "run_id",
        "decision_id",
        "call_id",
        "actor_id",
        "tick",
        "decision_ordinal",
        "attempt_index",
    ):
        if getattr(dispatch, field) != getattr(call, field):
            raise ValueError("terminal call/dispatch metadata differs")
    debit = call.debit
    if (debit.input_reserved, debit.output_reserved, debit.money_reserved) != (
        dispatch.input_reserved,
        dispatch.output_reserved,
        dispatch.money_reserved,
    ) or (debit.input_reported, debit.output_reported) != (
        call.result.token_input,
        call.result.token_output,
    ):
        raise ValueError("terminal usage/debit/reservation evidence differs")


def _validate_logs(
    save: SavePackageP3,
    logs: Mapping[str, bytes],
    origins: Sequence[ResumeOriginP3],
    *,
    verification: _VerificationSession | None = None,
) -> None:
    """Validate full committed joins and immutable mirrors, independent of authority."""
    contexts = decode_records(
        logs["contexts-p3.jsonl"],
        ContextRecordP3,
        Path("contexts-p3.jsonl"),
        verification=verification,
    )
    decisions = decode_records(
        logs["decisions-p3.jsonl"],
        DecisionRecordP3,
        Path("decisions-p3.jsonl"),
        verification=verification,
    )
    dispatches = decode_records(
        logs["llm-dispatches.jsonl"],
        AttemptDispatch,
        Path("llm-dispatches.jsonl"),
        verification=verification,
    )
    calls = decode_records(
        logs["llm-calls.jsonl"], LLMCallRecordP3, Path("llm-calls.jsonl"), verification=verification
    )
    events = _events_from_bytes(
        Path("events.jsonl"), logs["events.jsonl"], save.world.run_id, (), None
    )
    if len(events) != save.event_cursor or any(event.tick > save.world.tick for event in events):
        raise ValueError("event prefix extends beyond saved boundary")
    if [context.decision_id for context in contexts] != [
        record.decision_id for record in decisions
    ]:
        raise ValueError("contexts and committed decisions must join in order")
    call_ids = [call_id for decision in decisions for call_id in decision.call_ids]
    if (
        [item.call_id for item in dispatches] != call_ids
        or [item.call_id for item in calls] != call_ids
        or len(set(call_ids)) != len(call_ids)
    ):
        raise ValueError(
            "committed call/dispatch references are missing, duplicated or out of order"
        )
    ordinals = {state.actor_id: 0 for state in save.agent_state.runtime_states}
    policies = {state.actor_id: state.policy_config for state in save.agent_state.runtime_states}
    offline_ticks = [
        origin.checkpoint_tick for origin in origins if origin.recovery_mode == "offline"
    ]
    last: tuple[int, str] | None = None
    goal_ids: dict[str, str | None] = {}
    committed_refs: dict[str, OwnedIntentRef] = {}
    for context, decision in zip(contexts, decisions, strict=True):
        if (
            decision.run_id != save.world.run_id
            or decision.actor_id not in ordinals
            or decision.decision_ordinal != ordinals[decision.actor_id]
        ):
            raise ValueError("decision run/actor/ordinal differs from committed sequence")
        key = (decision.tick, decision.actor_id)
        if (last is not None and key <= last) or decision.tick >= save.world.tick:
            raise ValueError("decision boundary ordering differs")
        last = key
        ordinals[decision.actor_id] += 1
        request = context.request
        if (
            decision.run_id,
            decision.actor_id,
            decision.tick,
            decision.decision_ordinal,
            decision.triggers,
        ) != (
            context.run_id,
            request.actor_id,
            request.tick,
            request.decision_ordinal,
            request.triggers,
        ):
            raise ValueError("context/decision request metadata differs")
        if (decision.request_sha256, decision.context_sha256, decision.projection_sha256) != (
            canonical_sha256(context.request),
            context.assembly.context_sha256,
            context.assembly.projection_sha256,
        ):
            raise ValueError("context/decision hashes differ")
        cfg = policies[decision.actor_id]
        goals = apply_goal_change(
            request.context.goals,
            decision.accepted_delta.goal_change,
            actor_id=decision.actor_id,
            tick=decision.tick,
        )
        goal_ids[decision.decision_id] = attached_goal_id(goals)
        for intent in decision.plan.intents:
            committed_refs[intent.intent_id] = OwnedIntentRef(
                intent=intent,
                decision_id=decision.decision_id,
                decision_ordinal=decision.decision_ordinal,
                committed_tick=decision.tick,
                goal_id=goal_ids[decision.decision_id],
            )
        if offline_ticks and decision.tick >= min(offline_ticks) and cfg.policy_id == "llm-v0":
            if (decision.error_kind, decision.detail_code, decision.call_ids) != (
                "PROVIDER_ERROR",
                "RECOVERY_OFFLINE",
                [],
            ):
                raise ValueError(
                    "offline recovery LLM decisions must be call-free recovery fallbacks"
                )
        if decision.policy_id != cfg.policy_id or (
            context.assembly.manifest.context_profile_id != cfg.context_profile_id
            or canonical_sha256(context.request.context.identity) != cfg.identity_sha256
        ):
            raise ValueError("committed context/decision differs from saved policy pins")
    if ordinals != {
        state.actor_id: state.next_decision_ordinal for state in save.agent_state.runtime_states
    }:
        raise ValueError("committed per-resident decision cursors differ")
    contexts_by_id = {context.decision_id: context for context in contexts}
    normal_entries = [entry for entry in save.allocation_entries if entry.state == "settled"]
    if len(normal_entries) != len(calls):
        raise ValueError("every normal allocation entry must join one terminal call")
    debits = [debit for decision in decisions for debit in decision.budget_debits]
    for dispatch, call, entry, debit in zip(dispatches, calls, normal_entries, debits, strict=True):
        _join_context(contexts_by_id[dispatch.decision_id], dispatch)
        _join_call(dispatch, call)
        cfg = policies[dispatch.actor_id]
        if (
            dispatch.adapter_id,
            dispatch.adapter_version,
            dispatch.model_id,
            dispatch.prompt_version,
            dispatch.action_schema_version,
            dispatch.provider_request.settings,
        ) != (
            cfg.adapter_id,
            cfg.adapter_version,
            cfg.model_id,
            cfg.prompt_version,
            cfg.action_schema_version,
            cfg.provider_settings,
        ):
            raise ValueError("dispatch differs from retained policy provider pins")
        price = cfg.pricing
        expected_money_reserved = (
            dispatch.input_reserved * price.input_micro_cny_per_million_tokens + 999999
        ) // 1000000 + (
            dispatch.output_reserved * price.output_micro_cny_per_million_tokens + 999999
        ) // 1000000
        if dispatch.money_reserved != expected_money_reserved:
            raise ValueError("reservation money differs from registered integer pricing")
        expected_input: int | None
        expected_output: int | None
        if debit.usage_unknown:
            expected_input, expected_output = dispatch.input_reserved, dispatch.output_reserved
        else:
            expected_input, expected_output = debit.input_reported, debit.output_reported
        if expected_input is None or expected_output is None:
            raise ValueError("known usage requires both provider token counts")
        if expected_input > dispatch.input_reserved or expected_output > dispatch.output_reserved:
            raise ValueError("provider overrun cannot enter a normal committed checkpoint")
        expected_money = (
            expected_input * price.input_micro_cny_per_million_tokens + 999999
        ) // 1000000 + (
            expected_output * price.output_micro_cny_per_million_tokens + 999999
        ) // 1000000
        if (debit.input_charged, debit.output_charged, debit.money_charged) != (
            expected_input,
            expected_output,
            expected_money,
        ):
            raise ValueError("terminal debit differs from exact registered usage accounting")
        if (
            call.dispatch_sha256 != canonical_sha256(dispatch)
            or call.debit != debit
            or entry.debit != debit
            or entry.terminal_call_sha256 != canonical_sha256(call)
        ):
            raise ValueError("terminal call/decision/allocation mirror differs")
        reservation = entry.reservation
        if (
            reservation.call_id,
            reservation.allocation_key,
            reservation.reservation_ordinal,
            reservation.input_reserved,
            reservation.output_reserved,
            reservation.money_reserved,
            entry.provider_request_sha256,
            entry.wire_body_sha256,
        ) != (
            dispatch.call_id,
            dispatch.allocation_key,
            dispatch.reservation_ordinal,
            dispatch.input_reserved,
            dispatch.output_reserved,
            dispatch.money_reserved,
            dispatch.provider_request_sha256,
            dispatch.wire_body_sha256,
        ):
            raise ValueError("dispatch differs from allocation reservation identity")
    recovery = [entry for origin in origins for entry in origin.recovery_entries]
    if recovery != [entry for entry in save.allocation_entries if entry.state == "recovery"]:
        raise ValueError("checkpoint recovery mirror differs from verified origin ancestry")
    if any(origin.recovery_mode == "offline" for origin in origins) and save.live_enabled:
        raise ValueError("offline recovery cannot re-enable live calls")
    records_by_id = {record.decision_id: record for record in decisions}
    last_by_actor = {record.actor_id: record for record in decisions}
    for runtime in save.agent_state.runtime_states:
        latest = last_by_actor.get(runtime.actor_id)
        refs = runtime.cognitive_state.experience.intent_refs
        if latest is None:
            if refs:
                raise ValueError("runtime references require a committed decision")
        elif refs != [committed_refs[intent.intent_id] for intent in latest.plan.intents]:
            raise ValueError("runtime references must preserve its exact latest committed plan")
        if latest is not None and runtime.policy_private != latest.policy_private_after:
            raise ValueError("runtime private state differs from its latest committed decision")
        for memory in runtime.cognitive_state.experience.records:
            if memory.source.run_id != save.world.run_id:
                raise ValueError("retained experience source belongs to a foreign run")
            if memory.source.source_kind == "decision":
                record = records_by_id.get(memory.source.decision_id)
                data = memory.payload.data
                if record is None or not isinstance(data, AcceptedDecisionData):
                    raise ValueError("retained experience references an uncommitted decision")
                if (
                    memory.owner_id,
                    memory.observed_tick,
                    memory.source.decision_ordinal,
                    data.plan,
                    data.goal_id,
                ) != (
                    record.actor_id,
                    record.tick,
                    record.decision_ordinal,
                    record.plan,
                    goal_ids[record.decision_id],
                ):
                    raise ValueError("accepted-decision memory differs from its committed source")
            data = memory.payload.data
            if isinstance(data, FeedbackData) and data.owned_intent is not None:
                if data.owned_intent != committed_refs.get(data.owned_intent.intent.intent_id):
                    raise ValueError("feedback memory differs from its committed owned intent")
        goal = runtime.cognitive_state.goals.current
        if goal is not None and goal.evidence is not None:
            ref = goal.evidence.owned_intent
            if ref != committed_refs.get(ref.intent.intent_id):
                raise ValueError("goal evidence differs from its committed owned intent")
    living = {resident.id for resident in save.world.residents if resident.alive}
    for plan in save.agent_state.queued_plans:
        latest = last_by_actor.get(plan.actor_id)
        if (
            plan.actor_id not in living
            or latest is None
            or (
                plan.plan_id != latest.plan.plan_id
                or plan.created_at_tick != latest.plan.created_at_tick
                or plan.intents != latest.plan.intents[-len(plan.intents) :]
            )
        ):
            raise ValueError(
                "queued intents must preserve a living resident's committed plan suffix"
            )
    for action in save.world.active_actions:
        latest = last_by_actor.get(action.intent.actor_id)
        if latest is None or action.intent not in latest.plan.intents:
            raise ValueError("active intent must resolve to its owner's latest committed plan")
    if any(entry.actor_id not in living for entry in save.agent_state.deferred_decision_triggers):
        raise ValueError("deferred decision triggers must belong to living residents")
    for resident in save.world.residents:
        runtime = next(
            state for state in save.agent_state.runtime_states if state.actor_id == resident.id
        )
        if runtime.next_decision_ordinal > runtime.latest_perception_tick + 1:
            raise ValueError("decision ordinal exceeds acknowledged perceptions")
        if not resident.alive:
            deaths = [
                event
                for event in events
                if event.type == "resident_died" and event.actor_id == resident.id
            ]
            if len(deaths) != 1 or runtime.latest_perception_tick != deaths[0].tick - 1:
                raise ValueError("dead actor cursor differs from death history")


@dataclass(frozen=True)
class VerifiedP3Checkpoint:
    save: SavePackageP3
    raw: bytes
    logs: dict[str, bytes]
    inputs: dict[str, bytes]
    origins: tuple[ResumeOriginP3, ...]


def _prefix(raw: bytes, count: int, path: Path) -> bytes:
    parts = raw.splitlines(keepends=True)
    if len(parts) < count or any(
        not part.endswith(b"\n") or part.endswith(b"\r\n") for part in parts[:count]
    ):
        raise PersistenceError(
            path, "prefix", "committed prefix is truncated or not complete LF JSONL"
        )
    return b"".join(parts[:count])


def _origin_matches(origin: ResumeOriginP3, checkpoint: VerifiedP3Checkpoint) -> None:
    save = checkpoint.save
    if (
        origin.source_run_id,
        origin.checkpoint_tick,
        origin.checkpoint_sha256,
        origin.log_prefixes,
        origin.source_input_manifest_sha256,
        origin.allocation_key,
    ) != (
        save.world.run_id,
        save.world.tick,
        digest(checkpoint.raw),
        save.log_prefixes,
        save.input_manifest_sha256,
        save.run_budget.allocation_key,
    ):
        raise ValueError("continuation origin differs from its verified source checkpoint")


def read_checkpoint_p3(
    path: Path,
    *,
    source: Path | None = None,
    ancestors: tuple[Path, ...] = (),
    source_reader: SourceReader | None = None,
    verification: _VerificationSession | None = None,
) -> VerifiedP3Checkpoint:
    """Verify a full snapshot and precisely its committed bytes before restoring."""
    directory = path.parent if source is None else source
    raw = read_bytes(path)
    save = decode_model(raw, SavePackageP3, path)
    if path.name != f"checkpoint-{save.world.tick:010d}.json":
        raise ValueError("checkpoint filename must identify its exact saved boundary")
    inputs = read_inputs(
        directory, expected_hash=save.input_manifest_sha256, source_reader=source_reader
    )
    manifest = decode_model(
        read_bytes(directory / MANIFEST_NAME), P3InputManifest, directory / MANIFEST_NAME
    )
    if (
        manifest.run_id != save.world.run_id
        or digest(inputs["config.json"]) != save.canonical_config_hash
        or digest(inputs["map.txt"]) != save.canonical_map_hash
    ):
        raise ValueError("snapshot retained world/input identities differ")
    policies = _list(
        inputs["p3-policy-configs.json"], ActorPolicyConfig, directory / "p3-policy-configs.json"
    )
    if [policy.config for policy in policies] != [
        runtime.policy_config for runtime in save.agent_state.runtime_states
    ]:
        raise ValueError("saved runtime policy differs from retained policy")
    config = decode_model(inputs["config.json"], EffectiveConfig, directory / "config.json")
    if (
        save.world.schema_version,
        save.world.run_id,
        save.world.world_id,
        save.world.static_map_ref,
    ) != ("0.1", config.meta.run_id, config.meta.world_id, config.map.layout_file):
        raise ValueError("saved world identity/version differs from retained content")
    registration = decode_model(
        inputs["trial-registration.json"], TrialRegistration, directory / "trial-registration.json"
    )
    cases = [
        case
        for case in registration.cases
        if canonical_sha256(
            {
                "registration_sha256": digest(inputs["trial-registration.json"]),
                "case_id": case.case_id,
            }
        )
        == save.run_budget.allocation_key
    ]
    if len(cases) != 1 or cases[0].caps != save.run_budget.caps:
        raise ValueError("checkpoint allocation key/caps differ from retained registration")
    prior = {name: b"" for name in LOG_NAMES}
    origins: tuple[ResumeOriginP3, ...] = ()
    origin_path = directory / ORIGIN_NAME
    if origin_path.exists():
        origin = decode_model(read_bytes(origin_path), ResumeOriginP3, origin_path)
        candidates = [
            candidate
            for candidate in ancestors
            if candidate.resolve() != path.resolve()
            and digest(read_bytes(candidate)) == origin.checkpoint_sha256
        ]
        if not candidates:
            raise ValueError("continuation requires a distinct verified source ancestor locator")
        parent = read_checkpoint_p3(
            candidates[0],
            ancestors=tuple(candidate for candidate in ancestors if candidate != candidates[0]),
            source_reader=source_reader,
            verification=verification,
        )
        _origin_matches(origin, parent)
        if parent.inputs != inputs or save.world.tick < parent.save.world.tick:
            raise ValueError("continuation changed retained inputs or moved before source boundary")
        if origin.recovery_mode == "offline" and canonical_sha256(origin) in {
            canonical_sha256(item) for item in parent.origins if item.recovery_mode == "offline"
        }:
            raise ValueError("repeated recovery origin in ancestry")
        verify_recovery_evidence(directory, origin, parent, verification=verification)
        prior, origins = parent.logs, (*parent.origins, origin)
    logs: dict[str, bytes] = {}
    for prefix in save.log_prefixes:
        previous = prior[prefix.name]
        remaining = prefix.records - previous.count(b"\n")
        if remaining < 0:
            raise ValueError("ancestor prefix exceeds checkpoint cursor")
        logs[prefix.name] = previous + _prefix(
            read_bytes(directory / prefix.name), remaining, directory / prefix.name
        )
        if digest(logs[prefix.name]) != prefix.sha256:
            raise PersistenceError(
                directory / prefix.name, "sha256", "committed prefix hash mismatch"
            )
    _validate_logs(save, logs, origins, verification=verification)
    return VerifiedP3Checkpoint(save, raw, logs, inputs, origins)


def verify_later_checkpoints(
    path: Path,
    *,
    ancestors: tuple[Path, ...] = (),
    source_reader: SourceReader,
    verification: _VerificationSession | None = None,
) -> None:
    """Refuse corrupt later publications instead of falling back to an older grant.

    Callers provide ancestor locators nearest first. Identical clean snapshots at
    distinct locators are valid; source hashes identify bytes, not path ownership.
    """
    source = decode_model(read_bytes(path), SavePackageP3, path)
    for candidate in sorted(path.parent.glob("checkpoint-*.json")):
        if candidate.name > path.name:
            later = read_checkpoint_p3(
                candidate,
                ancestors=ancestors,
                source_reader=source_reader,
                verification=verification,
            )
            if later.save.world.tick <= source.world.tick:
                raise ValueError("later checkpoint filename/boundary ordering differs")


def publish_checkpoint(
    path: Path,
    save: SavePackageP3,
    journal: P3Journal,
    *,
    authority: PublicationAuthority | None = None,
    final: bool = False,
    fault: Fault | None = None,
    origins: Sequence[ResumeOriginP3] = (),
) -> SavePackageP3:
    prefixes = journal.prefixes()
    values = save.model_dump(mode="python")
    values.update(
        log_prefixes=prefixes,
        context_record_cursor=prefixes[0].records,
        decision_record_cursor=prefixes[1].records,
        event_cursor=prefixes[2].records,
        llm_record_cursor=prefixes[3].records,
        dispatch_record_cursor=prefixes[4].records,
    )
    candidate = SavePackageP3.model_validate(values)
    _validate_logs(candidate, journal.raw_prefixes(), origins, verification=journal.verification)
    journal.flush()
    _fault(fault, "checkpoint:logs_flushed")
    raw = canonical_bytes(candidate)
    head = AllocationHead(
        checkpoint_sha256=digest(raw),
        checkpoint_tick=candidate.world.tick,
        input_manifest_sha256=candidate.input_manifest_sha256,
        run_directory=str(path.parent.resolve()),
        reservation_cursor=len(candidate.allocation_entries),
    )
    if authority is not None:
        authority.prepare(head, candidate.allocation_entries)
    _fault(fault, "checkpoint:prepared")
    _create(path, raw, fault=fault, stage="checkpoint")
    if authority is not None:
        authority.finalize(head, candidate.allocation_entries, complete=final)
    _fault(fault, "checkpoint:finalized")
    return candidate


def checkpoint_verifier(
    *,
    ancestors: tuple[Path, ...] = (),
    source_reader: SourceReader,
    horizon: int,
    verification: _VerificationSession | None = None,
) -> Callable[[AllocationHead], VerifiedCheckpoint | None]:
    def verify(head: AllocationHead) -> VerifiedCheckpoint | None:
        from .p3_allocation import VerifiedCheckpoint

        path = Path(head.run_directory) / f"checkpoint-{head.checkpoint_tick:010d}.json"
        if not path.exists():
            return None
        checkpoint = read_checkpoint_p3(
            path, ancestors=ancestors, source_reader=source_reader, verification=verification
        )
        if (
            digest(checkpoint.raw) != head.checkpoint_sha256
            or checkpoint.save.input_manifest_sha256 != head.input_manifest_sha256
            or len(checkpoint.save.allocation_entries) != head.reservation_cursor
        ):
            raise ValueError("authority head differs from published checkpoint")
        return VerifiedCheckpoint(
            head,
            checkpoint.save.allocation_entries,
            checkpoint.save.live_enabled,
            checkpoint.save.world.tick == horizon,
        )

    return verify


def complete_origin(checkpoint: VerifiedP3Checkpoint) -> ResumeOriginP3:
    save = checkpoint.save
    return ResumeOriginP3(
        origin_version="0.2",
        source_run_id=save.world.run_id,
        checkpoint_tick=save.world.tick,
        checkpoint_sha256=digest(checkpoint.raw),
        log_prefixes=save.log_prefixes,
        source_input_manifest_sha256=save.input_manifest_sha256,
        recovery_mode="complete",
        allocation_key=save.run_budget.allocation_key,
        orphan_artifacts=[],
        recovery_entries=[],
        recovery_debits=[],
    )


def prepare_continuation(
    source: Path,
    checkpoint: VerifiedP3Checkpoint,
    destination: Path,
    *,
    offline_origin: ResumeOriginP3 | None = None,
    evidence: Mapping[str, bytes] | None = None,
    verification: _VerificationSession | None = None,
) -> ResumeOriginP3:
    """Copy verified immutable input bytes only after complete source verification."""
    src, dst = source.resolve(), destination.resolve()
    if src == dst or src in dst.parents or (destination.exists() and any(destination.iterdir())):
        raise ValueError("continuation destination must be fresh and outside its source")
    origin = complete_origin(checkpoint) if offline_origin is None else offline_origin
    _origin_matches(origin, checkpoint)
    evidence = {} if evidence is None else dict(evidence)
    if {item.name: item.sha256 for item in origin.orphan_artifacts} != {
        name: digest(raw) for name, raw in evidence.items()
    }:
        raise ValueError("origin evidence byte hashes differ")
    if origin.recovery_mode == "offline":
        _verify_recovery_artifacts(origin, evidence, checkpoint, verification=verification)
    destination.mkdir(parents=True, exist_ok=True)
    for name, raw in checkpoint.inputs.items():
        _create(destination / name, raw)
    _create(destination / MANIFEST_NAME, read_bytes(source / MANIFEST_NAME))
    for raw in evidence.values():
        _create(destination / "recovery-evidence" / f"{digest(raw)}.bin", raw)
    _create(destination / ORIGIN_NAME, canonical_bytes(origin))
    return origin


def candidate_allocation_entries(
    entries: Sequence[AllocationEntry],
    logs: Mapping[str, bytes],
    *,
    verification: _VerificationSession | None = None,
) -> list[AllocationEntry]:
    """Join durable terminal evidence to reserved entries without releasing authority."""
    calls = {
        row.call_id: row
        for row in decode_records(
            logs["llm-calls.jsonl"],
            LLMCallRecordP3,
            Path("llm-calls.jsonl"),
            verification=verification,
        )
    }
    result = []
    for entry in entries:
        if entry.state != "reserved":
            result.append(entry)
            continue
        call = calls.get(entry.reservation.call_id)
        if call is None:
            raise ValueError("unresolved reservation cannot enter a normal checkpoint")
        result.append(
            AllocationEntry.model_validate(
                {
                    **entry.model_dump(),
                    "state": "settled",
                    "debit": call.debit,
                    "terminal_call_sha256": canonical_sha256(call),
                }
            )
        )
    return result


def _recovery_entries(
    checkpoint: VerifiedP3Checkpoint,
    authority: CaseAllocationP3,
    artifacts: Mapping[str, bytes],
    *,
    verification: _VerificationSession | None = None,
) -> list[AllocationEntry]:
    head = authority.head
    if (
        head is None
        or head.checkpoint_sha256 != digest(checkpoint.raw)
        or authority.allocation_key != checkpoint.save.run_budget.allocation_key
        or head.reservation_cursor != len(checkpoint.save.allocation_entries)
        or authority.entries[: head.reservation_cursor] != checkpoint.save.allocation_entries
    ):
        raise ValueError("recovery authority does not own the exact source checkpoint")
    if authority.prepared_head is not None or authority.status == "complete":
        raise ValueError("reconcile publication before recovery; completed authority is closed")
    tail = authority.entries[head.reservation_cursor :]
    if not set(LOG_NAMES).issubset(artifacts):
        raise ValueError("recovery must retain every complete physical source log artifact")
    ancestor_counts = (
        {prefix.name: prefix.records for prefix in checkpoint.origins[-1].log_prefixes}
        if checkpoint.origins
        else dict.fromkeys(LOG_NAMES, 0)
    )
    for name in LOG_NAMES:
        committed = b"".join(
            checkpoint.logs[name].splitlines(keepends=True)[ancestor_counts[name] :]
        )
        if not artifacts[name].startswith(committed):
            raise ValueError("recovery artifact conflicts with committed physical source prefix")
    dispatches: dict[str, AttemptDispatch] = {}
    calls: dict[str, LLMCallRecordP3] = {}

    def orphan_rows[T: AttemptDispatch | LLMCallRecordP3](
        name: str, model: type[T]
    ) -> dict[str, T]:
        destination: dict[str, T] = {}
        raw = artifacts.get(name, b"")
        # Evidence contains complete physical source files; committed ancestry may
        # precede a suffix file. Complete valid rows must join authority. A final
        # partial row is conservatively charged from authority reservation data.
        for line in raw.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                break
            try:
                row = (
                    decode_model(line[:-1], model, Path(name))
                    if verification is None
                    else verification.decode(line[:-1], model, Path(name))
                )
            except ValueError as exc:
                raise ValueError("unverifiable complete orphan call/dispatch row") from exc
            if row.call_id in destination:
                raise ValueError("duplicate orphan call identity")
            destination[row.call_id] = row
        return destination

    dispatches = orphan_rows("llm-dispatches.jsonl", AttemptDispatch)
    calls = orphan_rows("llm-calls.jsonl", LLMCallRecordP3)
    known = {entry.reservation.call_id: entry for entry in authority.entries}
    if set(dispatches) - set(known) or set(calls) - set(known):
        raise ValueError("orphan dispatch/call has no authority reservation")
    extra_dispatches = [
        row for row in dispatches.values() if row.reservation_ordinal >= head.reservation_cursor
    ]
    if [row.reservation_ordinal for row in extra_dispatches] != list(
        range(head.reservation_cursor, head.reservation_cursor + len(extra_dispatches))
    ):
        raise ValueError("orphan dispatch order must be the serial authority reservation prefix")
    dispatch_raw = artifacts["llm-dispatches.jsonl"]
    if dispatch_raw and not dispatch_raw.endswith(b"\n") and len(extra_dispatches) >= len(tail):
        raise ValueError(
            "partial orphan dispatch has no corresponding pending authority reservation"
        )
    for call_id, dispatch in dispatches.items():
        entry = known[call_id]
        r = entry.reservation
        if (
            dispatch.allocation_key,
            dispatch.reservation_ordinal,
            dispatch.input_reserved,
            dispatch.output_reserved,
            dispatch.money_reserved,
            dispatch.provider_request_sha256,
            dispatch.wire_body_sha256,
        ) != (
            r.allocation_key,
            r.reservation_ordinal,
            r.input_reserved,
            r.output_reserved,
            r.money_reserved,
            entry.provider_request_sha256,
            entry.wire_body_sha256,
        ):
            raise ValueError("orphan dispatch conflicts with authority reservation")
    for call_id, call in calls.items():
        if call_id not in dispatches or call.dispatch_sha256 != canonical_sha256(
            dispatches[call_id]
        ):
            raise ValueError("orphan terminal call has no exact durable dispatch")
        _join_call(dispatches[call_id], call)
    policies = _list(
        checkpoint.inputs["p3-policy-configs.json"],
        ActorPolicyConfig,
        Path("p3-policy-configs.json"),
    )
    price = policies[0].config.pricing
    result = []
    for entry in tail:
        reservation = entry.reservation
        terminal = calls.get(reservation.call_id)
        reported_input = None if terminal is None else terminal.result.token_input
        reported_output = None if terminal is None else terminal.result.token_output
        input_charged = max(reservation.input_reserved, reported_input or 0)
        output_charged = max(reservation.output_reserved, reported_output or 0)
        money = (input_charged * price.input_micro_cny_per_million_tokens + 999999) // 1000000
        money += (output_charged * price.output_micro_cny_per_million_tokens + 999999) // 1000000
        debit = CallDebit(
            call_id=reservation.call_id,
            input_reserved=reservation.input_reserved,
            output_reserved=reservation.output_reserved,
            money_reserved=reservation.money_reserved,
            input_reported=reported_input,
            output_reported=reported_output,
            input_charged=input_charged,
            output_charged=output_charged,
            money_charged=max(reservation.money_reserved, money),
            usage_unknown=reported_input is None or reported_output is None,
        )
        result.append(
            AllocationEntry(
                reservation=reservation,
                provider_request_sha256=entry.provider_request_sha256,
                wire_body_sha256=entry.wire_body_sha256,
                state="recovery",
                debit=debit,
                terminal_call_sha256=None if terminal is None else canonical_sha256(terminal),
            )
        )
    return result


def build_recovery_origin(
    checkpoint: VerifiedP3Checkpoint,
    authority: CaseAllocationP3,
    artifacts: Mapping[str, bytes],
    *,
    verification: _VerificationSession | None = None,
) -> tuple[ResumeOriginP3, dict[str, bytes]]:
    evidence = {**artifacts, "authority-tail.json": canonical_bytes(authority)}
    entries = _recovery_entries(checkpoint, authority, evidence, verification=verification)
    origin = complete_origin(checkpoint)
    origin = ResumeOriginP3.model_validate(
        {
            **origin.model_dump(),
            "recovery_mode": "offline",
            "orphan_artifacts": [
                NamedHash(name=name, sha256=digest(evidence[name])) for name in sorted(evidence)
            ],
            "recovery_entries": entries,
            "recovery_debits": [entry.debit for entry in entries],
        }
    )
    return origin, evidence


def _verify_recovery_artifacts(
    origin: ResumeOriginP3,
    evidence: Mapping[str, bytes],
    checkpoint: VerifiedP3Checkpoint,
    *,
    verification: _VerificationSession | None = None,
) -> None:
    if origin.recovery_mode == "complete":
        return
    raw = evidence.get("authority-tail.json")
    if raw is None:
        raise ValueError("recovery evidence lacks retained pre-latch authority tail")
    authority = decode_model(raw, CaseAllocationP3, Path("authority-tail.json"))
    entries = _recovery_entries(checkpoint, authority, evidence, verification=verification)
    if entries != origin.recovery_entries:
        raise ValueError("recovery origin entries differ from retained authority/call evidence")


def verify_recovery_evidence(
    directory: Path,
    origin: ResumeOriginP3,
    checkpoint: VerifiedP3Checkpoint,
    *,
    verification: _VerificationSession | None = None,
) -> dict[str, bytes]:
    evidence = {}
    for item in origin.orphan_artifacts:
        path = directory / "recovery-evidence" / f"{item.sha256}.bin"
        raw = read_bytes(path)
        if digest(raw) != item.sha256:
            raise ValueError("retained recovery evidence hash mismatch")
        evidence[item.name] = raw
    _verify_recovery_artifacts(origin, evidence, checkpoint, verification=verification)
    return evidence


def write_trace_p3(
    path: Path, checkpoint: VerifiedP3Checkpoint, *, final_tick: int
) -> DecisionTraceP3:
    save = checkpoint.save
    if save.world.tick != final_tick or final_tick != _registered_horizon(checkpoint):
        raise ValueError("only a successfully completed horizon can publish a trace")
    trace = DecisionTraceP3(
        trace_schema_version="0.2",
        run_id=save.world.run_id,
        config_hash=save.canonical_config_hash,
        map_hash=save.canonical_map_hash,
        final_tick=final_tick,
        input_manifest_sha256=save.input_manifest_sha256,
        final_checkpoint_sha256=digest(checkpoint.raw),
        log_prefixes=save.log_prefixes,
        final_world_sha256=canonical_sha256(save.world),
        final_runtime_states_sha256=canonical_sha256(
            [state.model_dump(mode="json") for state in save.agent_state.runtime_states]
        ),
        final_budget_sha256=canonical_sha256(save.run_budget),
    )
    _create(path, canonical_bytes(trace))
    return trace


def _registered_horizon(checkpoint: VerifiedP3Checkpoint) -> int:
    registration = decode_model(
        checkpoint.inputs["trial-registration.json"],
        TrialRegistration,
        Path("trial-registration.json"),
    )
    registration_hash = canonical_sha256(registration)
    matching = [
        case
        for case in registration.cases
        if canonical_sha256({"registration_sha256": registration_hash, "case_id": case.case_id})
        == checkpoint.save.run_budget.allocation_key
    ]
    if len(matching) != 1:
        raise ValueError("trace allocation must bind one registered case")
    return matching[0].ticks


def load_trace_p3(
    path: Path,
    *,
    ancestors: tuple[Path, ...] = (),
    source_reader: SourceReader | None = None,
    verification: _VerificationSession | None = None,
) -> tuple[DecisionTraceP3, VerifiedP3Checkpoint]:
    trace = decode_model(read_bytes(path), DecisionTraceP3, path)
    checkpoint = read_checkpoint_p3(
        path.parent / f"checkpoint-{trace.final_tick:010d}.json",
        ancestors=ancestors,
        source_reader=source_reader,
        verification=verification,
    )
    save = checkpoint.save
    if trace.final_tick != _registered_horizon(checkpoint):
        raise ValueError("trace does not complete the registered case horizon")
    if (
        trace.run_id,
        trace.config_hash,
        trace.map_hash,
        trace.input_manifest_sha256,
        trace.final_checkpoint_sha256,
        trace.log_prefixes,
        trace.final_world_sha256,
        trace.final_runtime_states_sha256,
        trace.final_budget_sha256,
    ) != (
        save.world.run_id,
        save.canonical_config_hash,
        save.canonical_map_hash,
        save.input_manifest_sha256,
        digest(checkpoint.raw),
        save.log_prefixes,
        canonical_sha256(save.world),
        canonical_sha256(
            [state.model_dump(mode="json") for state in save.agent_state.runtime_states]
        ),
        canonical_sha256(save.run_budget),
    ):
        raise ValueError("trace differs from its verified final checkpoint")
    return trace, checkpoint
