"""Exact-row memoization must not memoize persistence acceptance or authority."""

from __future__ import annotations

import json
import os
import tarfile
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, PrivateAttr
from test_persistence import initial_checkpoint
from test_recovery import attempt, authority_for
from test_reexecution import LocalProvider, Sentinel, execute

from living_island.agents.p3.types import AllocationHead, ContextRecordP3
from living_island.memory.p3_types import build_decision_id, canonical_bytes
from living_island.persistence import p3 as persistence
from living_island.persistence._codec import PersistenceError
from living_island.persistence.p3 import (
    MODELS,
    _validate_logs,
    _VerificationSession,
    build_recovery_origin,
    checkpoint_verifier,
    decode_records,
    prepare_continuation,
    read_checkpoint_p3,
    verify_recovery_evidence,
)
from living_island.persistence.p3_inspection import GitSourceReader
from living_island.sim import p3 as sim

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "backend/tests/fixtures/p3/evaluation"


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    source = tmp_path_factory.mktemp("cache-source")
    with tarfile.open(FIXTURES / "ui-source.tar.gz", "r:gz") as tar:
        for member in tar.getmembers():
            assert member.isfile() and Path(member.name).name == member.name
            stream = tar.extractfile(member)
            assert stream is not None
            (source / member.name).write_bytes(stream.read())
    reader = GitSourceReader(ROOT)
    checkpoint = source / "checkpoint-0000000004.json"
    return source, checkpoint, reader, read_checkpoint_p3(checkpoint, source_reader=reader)


def _rows(verified):
    for name, model in MODELS.items():
        for row in verified.logs[name].splitlines():
            yield model, row


def _mutate_collections(value):
    """Touch every nested mutable DTO collection, including frozen-model lists."""
    count = 0
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            count += _mutate_collections(getattr(value, name))
    elif isinstance(value, (list, dict)):
        for child in list(value.values()) if isinstance(value, dict) else list(value):
            count += _mutate_collections(child)
        value.clear()
        count += 1
    elif isinstance(value, tuple):
        for child in value:
            count += _mutate_collections(child)
    return count


def test_all_row_models_return_independent_mutable_graphs(archive):
    session = _VerificationSession()
    seen, touched = set(), 0
    for model, raw in _rows(archive[3]):
        if model in seen:
            continue
        seen.add(model)
        first = session.decode(raw, model, Path("first"))
        expected = canonical_bytes(first)
        touched += _mutate_collections(first)
        second = session.decode(raw, model, Path("second"))
        assert canonical_bytes(second) == expected
        touched += _mutate_collections(second)
        assert canonical_bytes(session.decode(raw, model, Path("third"))) == expected
    assert seen == set(MODELS.values()) and touched > 20
    assert session.hits == len(seen) * 2


def test_type_identity_zero_capacity_eviction_and_scan_resistance(archive):
    rows = list(_rows(archive[3]))
    model, raw = rows[0]
    capacity = max(len(row) for _, row in rows)
    tiny, disabled = _VerificationSession(capacity), _VerificationSession(0)
    for owner, row in rows * 2:
        assert tiny.decode(row, owner, Path("a")) == disabled.decode(row, owner, Path("b"))
        assert tiny.raw_bytes <= capacity
    assert tiny.evictions > 0 and disabled.retained_rows == disabled.raw_bytes == disabled.hits == 0
    hot = _VerificationSession(len(raw))
    hot.decode(raw, model, Path("a"))
    hot.decode(raw, model, Path("a"))
    for owner, row in rows:
        hot.decode(row, owner, Path("a"))
    assert hot.retained_rows == 1
    assert hot.decode(raw, model, Path("a")) == disabled.decode(raw, model, Path("a"))
    assert hot.hits >= 3

    class A(BaseModel):
        value: int

    class B(BaseModel):
        value: int

    typed = _VerificationSession()
    assert type(typed.decode(b'{"value":1}', A, Path("a"))) is A
    assert type(typed.decode(b'{"value":1}', B, Path("b"))) is B
    assert typed.retained_rows == typed.misses == 2
    assert _VerificationSession().retained_rows == 0


@pytest.mark.parametrize(
    "mutation", ["version", "duplicate", "noncanonical", "float", "bool", "partial"]
)
def test_invalid_rows_never_cached_and_diagnostics_stay_current(archive, mutation):
    raw = archive[3].logs["contexts-p3.jsonl"].splitlines()[0]
    session = _VerificationSession()
    session.decode(raw, ContextRecordP3, Path("good"))
    value = json.loads(raw)
    if mutation == "version":
        value["context_record_version"] = "9.9"
        bad = canonical_bytes(value)
    elif mutation == "duplicate":
        bad = b'{"run_id":"duplicate",' + raw[1:]
    elif mutation == "noncanonical":
        bad = b" " + raw
    elif mutation in ("float", "bool"):
        value["request"]["tick"] = 0.0 if mutation == "float" else False
        bad = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    else:
        bad = raw[:-1]
    for line in (7, 13):
        with pytest.raises(ValueError) as caught:
            session.decode(bad, ContextRecordP3, Path(f"changed-{line}"), line=line)
        assert f"changed-{line}:{line}" in str(caught.value)
    assert session.retained_rows == 1 and session.misses == 3 and session.hits == 0
    with pytest.raises(ValueError, match="LF"):
        decode_records(raw, ContextRecordP3, Path("no-lf"), verification=session)


def _replace_same_timestamp(path, raw):
    before = path.stat()
    path.write_bytes(raw)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("kind", ["row", "input", "checkpoint", "source"])
def test_current_disk_and_source_bytes_checked_after_warm_cache(archive, tmp_path, kind):
    source, checkpoint, reader, _ = archive
    copy = tmp_path / "copy"
    copy.mkdir()
    for path in source.iterdir():
        (copy / path.name).write_bytes(path.read_bytes())
    target = copy / checkpoint.name
    session = _VerificationSession()
    read_checkpoint_p3(target, source_reader=reader, verification=session)
    if kind == "source":

        def changed(commit, path):
            raw = reader(commit, path)
            return (b"X" if raw[:1] != b"X" else b"Y") + raw[1:]

        with pytest.raises(ValueError):
            read_checkpoint_p3(target, source_reader=changed, verification=session)
        return
    path = (
        copy
        / {"row": "llm-calls.jsonl", "input": "prompt.txt", "checkpoint": checkpoint.name}[kind]
    )
    raw = path.read_bytes()
    if kind == "row":
        assert b'"latency_ms":1' in raw
        changed_raw = raw.replace(b'"latency_ms":1', b'"latency_ms":2', 1)
    elif kind == "checkpoint":
        value = json.loads(raw)
        old = value["canonical_config_hash"]
        value["canonical_config_hash"] = ("0" if old[0] != "0" else "1") + old[1:]
        changed_raw = canonical_bytes(value)
        assert changed_raw != raw
    else:
        changed_raw = b"X" + raw[1:]
    assert len(changed_raw) == len(raw)
    _replace_same_timestamp(path, changed_raw)
    with pytest.raises(ValueError):
        read_checkpoint_p3(target, source_reader=reader, verification=session)


@pytest.mark.parametrize("kind", ["run", "actor", "call", "plan", "recovery", "cursor"])
def test_all_cross_row_joins_repeat_even_when_rows_hit(archive, kind):
    verified = archive[3]
    session = _VerificationSession()
    _validate_logs(verified.save, verified.logs, verified.origins, verification=session)
    save = verified.save.model_copy(deep=True)
    if kind == "run":
        save = save.model_copy(
            update={"world": save.world.model_copy(update={"run_id": "foreign"})}
        )
    elif kind == "actor":
        save.agent_state.runtime_states[0] = save.agent_state.runtime_states[0].model_copy(
            update={"actor_id": "foreign"}
        )
    elif kind == "call":
        save.allocation_entries[0] = save.allocation_entries[0].model_copy(
            update={"terminal_call_sha256": "0" * 64}
        )
    elif kind == "plan":
        state = save.agent_state.runtime_states[0]
        assert state.cognitive_state.experience.intent_refs
        state.cognitive_state.experience.intent_refs.clear()
    elif kind == "recovery":
        save.allocation_entries[0] = save.allocation_entries[0].model_copy(
            update={"state": "recovery"}
        )
    else:
        state = save.agent_state.runtime_states[0]
        save.agent_state.runtime_states[0] = state.model_copy(update={"next_decision_ordinal": 999})
    before = session.hits
    with pytest.raises(ValueError):
        _validate_logs(save, verified.logs, verified.origins, verification=session)
    assert session.hits > before


def test_current_authority_head_never_cached(archive):
    source, path, reader, verified = archive
    session = _VerificationSession()
    verify = checkpoint_verifier(source_reader=reader, horizon=4, verification=session)
    head = AllocationHead(
        checkpoint_sha256=sha256(verified.raw).hexdigest(),
        checkpoint_tick=4,
        input_manifest_sha256=verified.save.input_manifest_sha256,
        run_directory=str(source.resolve()),
        reservation_cursor=len(verified.save.allocation_entries),
    )
    assert verify(head) is not None
    for update in (
        {"checkpoint_sha256": "0" * 64},
        {"reservation_cursor": 0},
        {"input_manifest_sha256": "0" * 64},
    ):
        with pytest.raises(ValueError, match="head differs"):
            verify(head.model_copy(update=update))
    assert session.hits > 0


def test_recovery_artifacts_and_ancestor_are_current_after_cache_hit(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "recovered"
    checkpoint, reader, _ = initial_checkpoint(source)
    _, dispatch, call, entry = attempt(checkpoint)
    evidence = checkpoint.logs.copy()
    evidence["llm-dispatches.jsonl"] += canonical_bytes(dispatch) + b"\n"
    evidence["llm-calls.jsonl"] += canonical_bytes(call) + b"\n"
    authority = authority_for(checkpoint, source, [entry])
    cache = _VerificationSession()
    origin, evidence = build_recovery_origin(checkpoint, authority, evidence, verification=cache)
    prepare_continuation(
        source,
        checkpoint,
        destination,
        offline_origin=origin,
        evidence=evidence,
        verification=cache,
    )
    verify_recovery_evidence(destination, origin, checkpoint, verification=cache)
    call_file = (
        destination / "recovery-evidence" / f"{sha256(evidence['llm-calls.jsonl']).hexdigest()}.bin"
    )
    raw = call_file.read_bytes()
    _replace_same_timestamp(call_file, raw.replace(b'"latency_ms":30000', b'"latency_ms":30001'))
    with pytest.raises(ValueError, match="evidence hash"):
        verify_recovery_evidence(destination, origin, checkpoint, verification=cache)
    bad_authority = authority.model_copy(
        update={"head": authority.head.model_copy(update={"checkpoint_sha256": "0" * 64})}
    )
    with pytest.raises(ValueError, match="exact source checkpoint"):
        build_recovery_origin(checkpoint, bad_authority, evidence, verification=cache)
    assert cache.hits > 0


def test_zero_capacity_and_enabled_execution_and_replay_have_identical_bytes(tmp_path, monkeypatch):
    runs = []
    sessions = []
    for name, capacity in (("off", 0), ("on", 128 * 1024 * 1024), ("evicted", 4096)):

        def factory(capacity=capacity):
            session = _VerificationSession(capacity)
            sessions.append(session)
            return session

        monkeypatch.setattr(sim, "_VerificationSession", factory)
        result, _, reader, provider, _ = execute(
            tmp_path / name, horizon=3, provider=LocalProvider()
        )
        replay = sim.reexecute_p3(
            result.output,
            tmp_path / f"replay-{name}",
            provider=Sentinel(),
            fallback=Sentinel(),
            allocation_store=Sentinel(),
            source_reader=reader,
        )
        assert result.checkpoint == replay.checkpoint and result.trace == replay.trace
        original = {p.name: p.read_bytes() for p in result.output.iterdir() if p.is_file()}
        copied = {p.name: p.read_bytes() for p in replay.output.iterdir() if p.is_file()}
        assert original == copied
        runs.append((original, provider.calls))
    assert runs[0] == runs[1] == runs[2]
    assert sessions[0].retained_rows == sessions[1].retained_rows == 0
    assert sessions[2].hits > 0 and sessions[3].hits > 0
    assert all(s.raw_bytes <= s.max_raw_bytes for s in sessions)


def test_cached_context_replaced_by_valid_foreign_request_still_fails_join(archive):
    verified = archive[3]
    cache = _VerificationSession()
    _validate_logs(verified.save, verified.logs, (), verification=cache)
    rows = verified.logs["contexts-p3.jsonl"].splitlines()
    value = json.loads(rows[0])
    value["run_id"] = "foreign"
    value["decision_id"] = build_decision_id(
        "foreign", value["request"]["actor_id"], value["request"]["decision_ordinal"]
    )
    changed = canonical_bytes(value)
    # This new canonical owner DTO is valid in isolation and enters the cache.
    cache.decode(changed, ContextRecordP3, Path("foreign"))
    logs = {**verified.logs, "contexts-p3.jsonl": b"\n".join([changed, *rows[1:]]) + b"\n"}
    with pytest.raises(ValueError, match="contexts and committed decisions"):
        _validate_logs(verified.save, logs, (), verification=cache)


def test_same_tick_ancestor_current_bytes_checked_after_cache_hit(tmp_path, monkeypatch):
    # Two identical same-tick origins must remain distinct ordered locators.
    shared = _VerificationSession()
    monkeypatch.setattr(sim, "_VerificationSession", lambda: shared)
    original, store, reader, _, fallback = execute(tmp_path / "original", ticks=1, horizon=3)
    first_path = original.output / "checkpoint-0000000001.json"
    one = sim.resume_p3(
        first_path,
        tmp_path / "one",
        allocation_store=store,
        provider=LocalProvider(),
        fallback=fallback,
        source_reader=reader,
        ticks=0,
    )
    second_path = one.output / "checkpoint-0000000001.json"
    two = sim.resume_p3(
        second_path,
        tmp_path / "two",
        ancestors=one.ancestors,
        allocation_store=store,
        provider=LocalProvider(),
        fallback=fallback,
        source_reader=reader,
        ticks=0,
    )
    last_path = two.output / "checkpoint-0000000001.json"
    assert first_path.read_bytes() == second_path.read_bytes() == last_path.read_bytes()
    checked = read_checkpoint_p3(
        last_path, ancestors=two.ancestors, source_reader=reader, verification=shared
    )
    assert len(checked.origins) == 2 and shared.hits > 0
    raw = first_path.read_bytes()
    _replace_same_timestamp(first_path, b" " + raw[1:])
    with pytest.raises(ValueError):
        read_checkpoint_p3(
            last_path, ancestors=two.ancestors, source_reader=reader, verification=shared
        )


class _CustomPickleDTO(BaseModel):
    """Arbitrary valid models must retain the original deep-copy semantics."""

    model_config = ConfigDict(extra="allow")
    values: list[int]
    _state: dict = PrivateAttr(default_factory=lambda: {"nested": [1], "callable": lambda: 1})

    def __reduce_ex__(self, protocol):
        raise AssertionError("custom model pickle hook must not run")


def _model_state(value):
    """Include exact nested types, explicit field sets, private state and extras."""
    kind = type(value)
    if isinstance(value, BaseModel):
        return kind, tuple(
            _model_state(item)
            for item in (
                value.__dict__,
                value.__pydantic_fields_set__,
                value.__pydantic_extra__,
                value.__pydantic_private__,
            )
        )
    if isinstance(value, dict):
        return kind, tuple((_model_state(k), _model_state(v)) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return kind, tuple(_model_state(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return kind, frozenset(_model_state(v) for v in value)
    return kind, value


def _mutable_nodes(value):
    seen, found = set(), []

    def visit(node):
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, BaseModel):
            found.append(node)
            for state in (
                node.__dict__,
                node.__pydantic_fields_set__,
                node.__pydantic_extra__,
                node.__pydantic_private__,
            ):
                visit(state)
        elif isinstance(node, dict):
            found.append(node)
            for k, v in node.items():
                visit(k)
                visit(v)
        elif isinstance(node, (list, set, tuple, frozenset)):
            if isinstance(node, (list, set)):
                found.append(node)
            for v in node:
                visit(v)

    visit(value)
    return found


def _assert_independent_state(session, model, raw):
    original = session.decode(raw, model, Path("first"))
    expected = _model_state(original)
    first = session.decode(raw, model, Path("second"))
    second = session.decode(raw, model, Path("third"))
    assert _model_state(first) == _model_state(second) == expected
    assert canonical_bytes(first) == canonical_bytes(second) == raw
    owner_ids = {id(node) for node in _mutable_nodes(original)}
    nodes = _mutable_nodes(first)
    assert not owner_ids.intersection(id(node) for node in nodes)
    assert not {id(node) for node in nodes}.intersection(
        id(node) for node in _mutable_nodes(second)
    )
    for node in nodes:
        if isinstance(node, (dict, list, set)):
            node.clear()
    assert _model_state(original) == _model_state(second) == expected
    assert _model_state(session.decode(raw, model, Path("fourth"))) == expected


def test_encoded_owner_rows_preserve_complete_state_and_mutable_isolation(archive):
    session = _VerificationSession()
    for model, raw in _rows(archive[3]):
        _assert_independent_state(session, model, raw)
    assert all(isinstance(value, bytes) for value in session._rows.values())


def test_non_owner_and_local_models_keep_private_extra_and_custom_copy_behavior():
    class LocalDTO(_CustomPickleDTO):
        pass

    session = _VerificationSession()
    for model in (_CustomPickleDTO, LocalDTO):
        _assert_independent_state(session, model, b'{"extra":{"nested":[2]},"values":[3]}')
    assert session.retained_rows == session.misses == 2
    assert all(isinstance(value, BaseModel) for value in session._rows.values())


def test_owner_encoding_happens_once_and_loads_only_accept_internal_payload(archive, monkeypatch):
    model, raw = next(_rows(archive[3]))
    session = _VerificationSession()
    encoded, loaded = [], []
    original_dumps, original_loads = persistence.pickle.dumps, persistence.pickle.loads

    def dumps(value, *, protocol):
        assert isinstance(value, model)
        payload = original_dumps(value, protocol=protocol)
        encoded.append(payload)
        return payload

    def loads(payload):
        assert any(payload is internal for internal in encoded)
        loaded.append(payload)
        return original_loads(payload)

    monkeypatch.setattr(persistence.pickle, "dumps", dumps)
    monkeypatch.setattr(persistence.pickle, "loads", loads)
    _assert_independent_state(session, model, raw)
    assert len(encoded) == 1 and len(loaded) == 3
    assert session.hits == 3 and session.misses == 1


@pytest.mark.parametrize("error", [TypeError, RuntimeError])
def test_encode_failure_falls_back_without_changing_admission_or_decodes(
    archive, monkeypatch, error
):
    model, raw = next(_rows(archive[3]))
    calls = []

    def fail(*args, **kwargs):
        calls.append(True)
        raise error("unsupported serialization")

    monkeypatch.setattr(persistence.pickle, "dumps", fail)
    session = _VerificationSession(len(raw))
    _assert_independent_state(session, model, raw)
    assert len(calls) == session.misses == session.retained_rows == 1
    assert session.raw_bytes == session.peak_raw_bytes == len(raw)
    assert not session._cold and session.evictions == 0
    assert isinstance(session._rows[(model, raw)], model)
    with pytest.raises(ValueError, match="bad:17"):
        session.decode(raw + b" ", model, Path("bad"), line=17)
    assert len(calls) == 1 and session.misses == 2


def test_load_failure_falls_back_and_never_masks_decoder_errors(archive, monkeypatch):
    model, raw = next(_rows(archive[3]))
    session, invalidated = _VerificationSession(), _VerificationSession()
    original = session.decode(raw, model, Path("original"))
    invalidated.decode(raw, model, Path("original"))
    calls = []

    def fail(payload):
        calls.append(payload)
        raise RuntimeError("unavailable class state")

    monkeypatch.setattr(persistence.pickle, "loads", fail)
    assert session.decode(raw, model, Path("fallback")) == original
    assert isinstance(session._rows[(model, raw)], model)
    assert session.decode(raw, model, Path("again")) == original
    assert len(calls) == 1 and session.hits == 2 and session.misses == 1

    def rejected(raw, model, path, *, line=None):
        raise PersistenceError(path, "record", "current decoder failure", line=line)

    monkeypatch.setattr(persistence, "decode_model", rejected)
    with pytest.raises(PersistenceError, match="current:19: record: current decoder failure"):
        invalidated.decode(raw, model, Path("current"), line=19)
