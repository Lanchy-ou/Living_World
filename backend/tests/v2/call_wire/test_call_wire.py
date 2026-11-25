"""DL-08, DL-11 and the call port's reachable input and journal boundaries."""

import json
from dataclasses import replace
from typing import get_args

import pytest


@pytest.fixture
def audit(tmp_path):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.persistence._files import atomic_create
    from living_island.persistence.v2.journal import store_once

    return Journal(
        lambda key, data: store_once(tmp_path / key, data),
        lambda key, data: atomic_create(tmp_path / key, data),
    )


def part(kind, key, text):
    from living_island.agents.v2.calls.guard import Part, Ref

    return Part(kind, Ref(kind=kind, id=key, version="revision-2", member_path=key), text)


def call(key="call"):
    from living_island.agents.v2.calls.guard import Call

    return Call(call_id=key, resident_id="ella", period_id="p1", turn_id="turn-1", tick=9)


def oracle(body, *, user=None):
    # Independent rendering from the actual wire using the P3 certified plain-span counter.
    from living_island.agents.llm.provider import _plain_token_bound

    wire = json.loads(body)
    shape = json.dumps(wire["text"]["format"]["schema"], ensure_ascii=False)
    prefix = (
        "\n\n## Response Format:\n\nYou MUST strictly adhere to the following schema to reply:\n"
    )
    system, message = wire["input"]
    return (
        5
        + _plain_token_bound(system["content"] + prefix + shape)
        + _plain_token_bound(message["content"] if user is None else user)
    )


def resolved(candidate, path):
    return tuple((path / entry.sha256).read_bytes() for entry in candidate.manifest.entries)


def reply(text, *, status=200, usage=None, reasoning=False, delay=0):
    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls.fake import ScriptedReply

    output = [
        {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text}],
        }
    ]
    if reasoning:
        output.insert(0, {"type": "reasoning", "content": [{"text": "detached audit evidence"}]})
    body = json.dumps(
        {"status": "completed", "model": "deepseek-flash", "output": output, "usage": usage}
    ).encode()
    return ScriptedReply(TransportResponse(status, body, True), delay)


def test_dl_08_pressure_on_exact_framed_integer_boundaries(tmp_path, audit):
    from hashlib import sha256
    from pathlib import Path

    from living_island.agents.llm import provider
    from living_island.agents.llm.provider import InputCounterUnavailable
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.guard import Assembly, prepare, rebuild
    from living_island.agents.v2.calls.wire import WINDOW, frame

    contract = Contract("morning")
    bare = frame(contract.kind, contract.instructions, contract.schema, "🌴")
    words = ["clear", "busy", "crowded", "heavy and crowded", "overloaded"]
    for i, percent in enumerate((5, 15, 30, 50)):
        for delta in (-1, 0, 1):
            target = percent * WINDOW // 100 + delta
            user = "🌴" + "x" * (target - oracle(bare.body))
            assembly = Assembly((part("current_state", "body", user),), (), frozenset({0}), 1)
            prepared = prepare(call(str(target)), contract, assembly, audit)
            (full,) = prepared.record.candidates
            (cue,) = full.manifest.derived
            assert cue.counted == target
            assert cue.text == f"Your thoughts feel {words[i + (delta >= 0)]}."
            wire = (tmp_path / full.wire_sha256).read_bytes()
            assert oracle(wire, user=user) == target
            assert oracle(wire) == full.manifest.tokens_total > target
            assert json.loads(wire)["input"][1]["content"] == user + "\n" + cue.text
            assert rebuild(full, prepared.record.settings, resolved(full, tmp_path)).body == wire
    changed = prepared.record.settings.model_copy(update={"counter_version": "different"})
    assert (
        sha256(Path(provider.__file__).read_bytes()).hexdigest()
        == prepared.record.settings.counter_source_sha256
    )
    with pytest.raises(InputCounterUnavailable):
        rebuild(full, changed, resolved(full, tmp_path))


def test_dl_11_omission_notice_changes_fit_and_protects_floor(tmp_path, audit):
    from living_island.agents.llm.provider import MAX_REQUEST_BYTES
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.fake import FakeClock, FakeTransport
    from living_island.agents.v2.calls.guard import Assembly, prepare, rebuild
    from living_island.agents.v2.calls.provider import attempt
    from living_island.agents.v2.calls.wire import NOTICE, WINDOW, frame

    contract = Contract("decision")
    prefix = (part("memory", "first", "a" * 80), part("memory", "last", "b" * 80))
    log = tuple(part("day_log", f"d:{i}", f"day entry {i}") for i in range(22))
    base = "🌴"
    cue = "Your thoughts feel overloaded."
    at_boundary = "\n".join(p.text for p in (*prefix, *log[2:])) + f"\n{base}\n{cue}"
    small = frame(contract.kind, contract.instructions, contract.schema, at_boundary)
    current = base + "x" * (WINDOW - oracle(small.body))
    parts = (*prefix, *log, part("current_state", "state", current))
    order = (2, 3, 1, 0)
    assembly = Assembly.decision(
        parts, prefix_memories=(0, 1), day_log=tuple(range(2, 24)), pressure_at=len(parts)
    )
    assert assembly.omission_order == order
    assert Assembly.decision(
        parts,
        prefix_memories=(0, 1),
        day_log=tuple(range(2, 24)),
        pressure_at=len(parts),
        recall_entries=frozenset({2}),
    ).omission_order == (3, 1, 0)
    prepared = prepare(call(), contract, assembly, audit)
    record = prepared.record
    assert record.settings.model_window == 1_000_000 and record.settings.max_output_tokens == 8_000
    assert record.admitted_candidate == 3 and record.floor_candidate == 4
    assert prepared.admitted.candidate.omitted == tuple(parts[i].source for i in (2, 3, 1))
    assert [p.source.id for p in log] == [f"d:{i}" for i in range(22)]
    for i, candidate in enumerate(record.candidates):
        assert candidate.omitted == tuple(parts[j].source for j in order[:i])
        wire = rebuild(candidate, record.settings, resolved(candidate, tmp_path))
        assert oracle(wire.body) == candidate.manifest.tokens_total
        text = json.loads(wire.body)["input"][1]["content"]
        assert (NOTICE in text) == bool(i)
        assert candidate.manifest.derived == record.candidates[0].manifest.derived
        if i == 2:
            assert oracle(wire.body, user=text.removeprefix(NOTICE + "\n")) == WINDOW < wire.counted
    assert len(prepared.admitted.wire.body) > MAX_REQUEST_BYTES
    assert len(list(tmp_path.glob("*.dispatch.json"))) == 0
    clock = FakeClock()
    transport = FakeTransport(clock, [reply('{"step":"recall","query":"where?"}')])
    returned = attempt(
        prepared, n=0, journal=audit, transport=transport, clock=clock, has_running_action=False
    )
    assert returned.dispatch.sent == record.candidates[3]
    assert transport.dispatches == [prepared.admitted.wire.body]
    oversized = replace(assembly, parts=(*parts[:-1], replace(parts[-1], text=current + "x" * 500)))
    stopped = prepare(call("oversized"), contract, oversized, audit)
    assert stopped.record.reason == "stopped_unfit"
    assert stopped.record.candidates[-1].manifest.tokens_total > WINDOW
    assert (
        attempt(
            stopped, n=0, journal=audit, transport=transport, clock=clock, has_running_action=False
        )
        is None
    )
    assert len(transport.dispatches) == len(list(tmp_path.glob("*.dispatch.json"))) == 1

    # Replacing one short entry with the notice makes the floor larger than the full request.
    short_log = log[:21]
    full_user = "\n".join([p.text for p in short_log] + [base, cue])
    exact_state = base + "x" * (WINDOW - oracle(small.body, user=full_user))
    exact_parts = (*short_log, part("current_state", "state", exact_state))
    exact = prepare(
        call("full-at-window"),
        contract,
        Assembly.decision(
            exact_parts, prefix_memories=(), day_log=tuple(range(21)), pressure_at=len(exact_parts)
        ),
        audit,
    )
    full, floor = exact.record.candidates
    assert exact.record.admitted_candidate == 0 and exact.admitted.candidate == full
    assert full.omitted == () and exact.record.reason is None
    assert oracle(exact.admitted.wire.body) == full.manifest.tokens_total == WINDOW
    assert exact.record.floor_candidate == 1 and floor.omitted == (short_log[0].source,)
    floor_wire = (tmp_path / floor.wire_sha256).read_bytes()
    assert oracle(floor_wire) == floor.manifest.tokens_total > WINDOW
    assert json.loads(floor_wire)["input"][1]["content"].startswith(NOTICE + "\n")


def test_assembler_partition_pressure_and_index_floor(audit):
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.guard import Assembly, prepare

    parts = (part("index", "one", "one"),)
    for order, floor in [((), ()), ((0, 0), ()), ((1,), ()), ((0,), (0,))]:
        with pytest.raises(ValueError, match="partition"):
            Assembly(parts, order, frozenset(floor))
    for slot in (-1, 2):
        with pytest.raises(ValueError, match="outside"):
            Assembly(parts, (), frozenset({0}), slot)
    for kind, slot in [("recall", 0), ("morning", None)]:
        with pytest.raises(ValueError, match="pressure slot"):
            prepare(call(), Contract(kind), Assembly(parts, (), frozenset({0}), slot), audit)
    for kind, slot in [("morning", 1), ("recall", None)]:
        with pytest.raises(ValueError, match="protected"):
            prepare(call(), Contract(kind), Assembly(parts, (0,), frozenset(), slot), audit)
    for kind, order in [
        ("consolidation_selection", (1, 0)),
        ("consolidation_change_set", (2, 1, 0)),
    ]:
        parts = (
            part("day_log", "old", "entry"),
            part("pending_period", "older", "period"),
            part("memory", "last-picked", "memory"),
            part("index", "index", "index"),
        )
        kept = frozenset(range(len(parts))) - frozenset(order)
        result = prepare(call(kind), Contract(kind), Assembly(parts, order, kept), audit)
        assert result.record.candidates[-1].omitted == tuple(parts[i].source for i in order)
        assert result.record.candidates[-1].manifest.derived == ()


def test_schema_preflight_preserves_world_choices_and_rejects_m9_regex():
    from living_island.agents.v2.calls.contracts import CallKind, Contract, check_schema
    from living_island.world.v2.protocol import EnabledVerb, model_turn_schema

    verbs = (EnabledVerb(id="test", params=(), target_kinds=()),)
    for kind in get_args(CallKind.__value__):
        shape = json.loads(Contract(kind, verbs).schema)
        if kind.startswith("decision"):
            variants = shape["$defs"]["IntentShape"]["oneOf"]
            expected = model_turn_schema(verbs)["$defs"]["IntentShape"]["oneOf"]
            assert [v["properties"]["verb"] for v in variants] == [
                v["properties"]["verb"] for v in expected
            ]
            assert shape["$defs"]["Terms"] == model_turn_schema(verbs)["$defs"]["Terms"]
    with pytest.raises(ValueError, match="surrogate"):
        check_schema({"properties": {"text": {"pattern": r"^[^\uD800-\uDFFF]*$"}}})


def test_model_output_is_typed_at_each_kind_boundary():
    from living_island.agents.v2.calls.changes import ChangeSetOutput, Forget, InvalidOperation
    from living_island.agents.v2.calls.contracts import (
        ActStep,
        Contract,
        MemoryIDs,
        RecallStep,
        Selection,
    )

    act = dict(
        step="act", action={"kind": "continue"}, utterance=None, intention=None, mute=[], cite=[]
    )
    for kind, version, raw, model in [
        ("decision", "0.4", dict(step="recall", query="?"), RecallStep),
        ("decision_after_recall", "0.4", {**act, "actor_id": "unbound"}, ActStep),
        ("morning", "0.3", {"ids": ["m:one"]}, MemoryIDs),
        ("recall", "0.2", {"ids": []}, MemoryIDs),
        ("consolidation_selection", "0.4", {"read": []}, Selection),
        (
            "consolidation_change_set",
            "0.4",
            {"ops": [{"op": "forget", "op_id": "f", "id": "m:x"}]},
            ChangeSetOutput,
        ),
    ]:
        contract = Contract(kind)
        assert contract.prompt_version == f"{kind}/{version}"
        assert contract.instructions.endswith(
            " Reply with only the JSON object that matches the response schema, "
            "with no other text before or after it."
        )
        text = json.dumps(raw)
        assert isinstance(contract.parse(text, has_running_action=True), model)
        for invalid in (f"Here is my response.\n\n{text}", f"{text}\n\nDone."):
            with pytest.raises(ValueError):
                contract.parse(invalid, has_running_action=True)
    batch = Contract("consolidation_change_set").parse(
        '{"ops":[{"op":"unknown"},{"op":"forget","op_id":"f","id":"m:1"}]}',
        has_running_action=False,
    )
    assert isinstance(batch.ops[0], InvalidOperation) and isinstance(batch.ops[1], Forget)
    assert (
        Contract("decision")
        .parse(json.dumps(act | {"intention": {"clear": True}}), has_running_action=True)
        .intention.clear
    )
    intent = {
        "action": "wait",
        "verb": None,
        "target": None,
        "instruments": [],
        "inputs": [],
        "params": {},
        "reason": "x" * 301,
    }
    speech = {
        "speech_act": "statement",
        "addressee_id": None,
        "terms": None,
        "in_reply_to": None,
        "text": "x" * 501,
    }
    for kind, value, running in [
        ("decision_after_recall", {"step": "recall", "query": "again"}, True),
        ("decision", {"step": "recall", "query": "x" * 201}, True),
        ("decision", {**act, "intention": {"set": "x" * 501}}, True),
        ("decision", {**act, "intention": {"clear": 1}}, True),
        ("decision", {**act, "cite": ["x"] * 11}, True),
        ("decision", act, False),
        ("decision", {**act, "mute": ["body"]}, True),
        ("decision", {**act, "utterance": speech}, True),
        ("decision", {**act, "action": {"kind": "intent", "intent": intent}}, True),
        ("recall", {"ids": [7]}, False),
        ("morning", {"ids": ["m:1"] * 21}, False),
        ("consolidation_selection", {"ids": []}, False),
        ("consolidation_change_set", {"ops": 42}, False),
    ]:
        with pytest.raises(ValueError):
            Contract(kind).parse(json.dumps(value), has_running_action=running)
    for text in ['{"ids":[],"ids":[]}', '{"ids":[NaN]}', r'{"ids":["\ud800"]}', "not json"]:
        with pytest.raises(ValueError):
            Contract("morning").parse(text, has_running_action=False)


def test_dispatch_claim_and_terminal_are_durable_at_io_and_restore(tmp_path, audit):
    from living_island.agents.v2.calls.contracts import Contract, MemoryIDs
    from living_island.agents.v2.calls.fake import FakeClock, FakeTransport
    from living_island.agents.v2.calls.guard import Assembly, PreparedRecord, prepare
    from living_island.agents.v2.calls.provider import (
        Dispatch,
        Interrupted,
        Terminal,
        attempt,
        restore,
    )
    from living_island.persistence._codec import PersistenceError

    prepared = prepare(
        call(),
        Contract("recall"),
        Assembly((part("query", "q", "?"),), (), frozenset({0})),
        audit,
    )
    assert (
        PreparedRecord.model_validate_json((tmp_path / prepared.cursor).read_bytes())
        == prepared.record
    )
    clock = FakeClock()
    replies = [
        reply(
            '{"ids":["m:1"]}',
            usage={
                "input_tokens": 12,
                "output_tokens": 3,
                "input_tokens_details": {"cached_tokens": 5},
            },
            reasoning=True,
            delay=17,
        ),
        reply("{", delay=10),
        reply("{}", status=429),
    ]

    class Observe(FakeTransport):
        def exchange(self, body, timeout_ms):
            n = len(self.dispatches)
            row = Dispatch.model_validate_json(
                (tmp_path / audit.cursor("call", f"{n}.dispatch")).read_bytes()
            )
            assert (tmp_path / row.request_sha256).read_bytes() == body
            assert isinstance(restore(row, None), Interrupted)
            assert not (tmp_path / audit.cursor("call", f"{n}.terminal")).exists()
            return super().exchange(body, timeout_ms)

    transport = Observe(clock, replies)
    results = []
    for n, timeout in enumerate((100, 10, 100)):
        returned = attempt(
            prepared,
            n=n,
            journal=audit,
            transport=transport,
            clock=clock,
            has_running_action=False,
            timeout_ms=timeout,
        )
        terminal = Terminal.model_validate_json((tmp_path / returned.terminal_cursor).read_bytes())
        assert restore(returned.dispatch, terminal) == terminal
        assert (tmp_path / terminal.raw_output_ref).read_bytes() == replies[n].response.body
        results.append(returned)
    ok, late, limited = results
    assert isinstance(ok.parsed, MemoryIDs) and ok.parsed.ids == ["m:1"]
    assert json.loads((tmp_path / ok.terminal.parsed_ref).read_bytes()) == {"ids": ["m:1"]}
    assert b"detached audit evidence" in (tmp_path / ok.terminal.reasoning_ref).read_bytes()
    assert ok.terminal.tokens.model_dump() == {
        "input": 12,
        "output": 3,
        "cache_hit": 5,
        "cache_miss": 7,
    }
    assert ok.terminal.missing_usage_reason is None and ok.terminal.latency_ms == 17
    assert late.terminal.error_class == "timeout" and late.parsed is None
    assert limited.terminal.error_class == "rate_limit" and limited.terminal.missing_usage_reason
    assert transport.dispatches == [prepared.admitted.wire.body] * 3
    wire = json.loads(transport.dispatches[0])
    assert wire["text"]["format"]["schema"] == json.loads(prepared.contract.schema)
    assert "detached audit evidence" not in str(wire) and '"properties"' not in str(wire["input"])
    with pytest.raises(PersistenceError):
        attempt(
            prepared, n=0, journal=audit, transport=transport, clock=clock, has_running_action=False
        )
    with pytest.raises(ValueError, match="different dispatch"):
        restore(ok.dispatch, late.terminal)
    assert len(transport.dispatches) == 3


def test_provider_faults_never_adopt_partial_or_malformed_output(tmp_path, audit):
    from living_island.agents.llm.provider import MAX_RESPONSE_BYTES, TransportResponse
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.fake import FakeClock, FakeTransport, ScriptedReply
    from living_island.agents.v2.calls.guard import Assembly, prepare
    from living_island.agents.v2.calls.provider import attempt

    clock = FakeClock()
    prepared = prepare(call(), Contract("morning"), Assembly((), (), frozenset(), 0), audit)
    ok = reply('{"ids":[]}').response
    envelope = json.loads(ok.body)
    missing_status = envelope.copy()
    del missing_status["status"]
    timeout_ms = 10
    cases = [
        (ScriptedReply(TransportResponse(None, None, False, "timeout")), "timeout"),
        (ScriptedReply(ok, delay_ms=timeout_ms + 1), "timeout"),
        (ScriptedReply(TransportResponse(None, None, False, "transport_error")), "server_error"),
        (ScriptedReply(replace(ok, status=503)), "server_error"),
        (ScriptedReply(replace(ok, status=429)), "rate_limit"),
        (ScriptedReply(replace(ok, status=400)), "provider_error"),
        (ScriptedReply(replace(ok, complete=False)), "invalid_output"),
        (ScriptedReply(replace(ok, body=b"")), "invalid_output"),
        (ScriptedReply(replace(ok, body=b"\xff")), "invalid_output"),
        (ScriptedReply(replace(ok, body=b"z" * (MAX_RESPONSE_BYTES + 1))), "invalid_output"),
        (ScriptedReply(replace(ok, body=json.dumps(missing_status).encode())), "invalid_output"),
        (reply("{broken"), "invalid_output"),
        (reply('{"ids":"wrong"}'), "invalid_output"),
    ]
    for change, expected in [
        ({"status": "incomplete"}, "invalid_output"),
        ({"status": "failed"}, "provider_error"),
        ({"error": {"code": "x"}}, "provider_error"),
        ({"model": "different"}, "provider_error"),
        ({"usage": {"output_tokens": 8001}}, "invalid_output"),
        ({"output": []}, "invalid_output"),
    ]:
        cases.append(
            (ScriptedReply(replace(ok, body=json.dumps(envelope | change).encode())), expected)
        )
    transport = FakeTransport(clock, (script for script, _ in cases))
    for n, (script, expected) in enumerate(cases):
        returned = attempt(
            prepared,
            n=n,
            journal=audit,
            transport=transport,
            clock=clock,
            has_running_action=False,
            timeout_ms=timeout_ms,
        )
        assert returned.terminal.error_class == expected
        assert returned.terminal.latency_ms == script.delay_ms
        assert returned.parsed is None and returned.terminal.parsed_ref is None
        raw = script.response
        if raw.body is None:
            assert returned.terminal.raw_output_ref is None
        else:
            assert (tmp_path / returned.terminal.raw_output_ref).read_bytes() == raw.body[
                :MAX_RESPONSE_BYTES
            ]
    with pytest.raises(ValueError, match="timeout"):
        attempt(
            prepared,
            n=len(cases),
            journal=audit,
            transport=transport,
            clock=clock,
            has_running_action=False,
            timeout_ms=0,
        )
    assert len(transport.dispatches) == len(cases)


def test_replay_refuses_changed_settings_parts_pressure_or_wire(tmp_path, audit):
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.guard import Assembly, prepare, rebuild

    prepared = prepare(call(), Contract("morning"), Assembly((), (), frozenset(), 0), audit)
    candidate = prepared.admitted.candidate
    settings = prepared.record.settings
    data = resolved(candidate, tmp_path)
    bad_derived = candidate.manifest.model_copy(update={"derived": ()})
    for changed, pins, parts, message in [
        (candidate, settings.model_copy(update={"model": "other"}), data, "settings"),
        (candidate, settings, (b"x", *data[1:]), "part differs"),
        (candidate.model_copy(update={"manifest": bad_derived}), settings, data, "pressure"),
        (candidate.model_copy(update={"wire_sha256": "bad"}), settings, data, "rebuilt"),
    ]:
        with pytest.raises(ValueError, match=message):
            rebuild(changed, pins, parts)
