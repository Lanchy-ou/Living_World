import sqlite3
from typing import get_args

import pytest

from v2.resident_replay.replay_fixture import start, verify


def replace_fact(path, key, raw):
    from living_island.agents.v2.calls.contracts import digest

    with sqlite3.connect(path) as db:
        db.execute("UPDATE facts SET hash=?,body=? WHERE name=?", (digest(raw), raw, key))


def test_dl16_saved_submissions_and_resident_continuation(tmp_path):
    from living_island.sim.v2.harness.checkpoint import load
    from living_island.sim.v2.harness.composition import compose
    from living_island.sim.v2.harness.replay import continue_offline

    record, kwargs, fake = start(tmp_path)
    record.advance()
    assert fake.calls == ["decision", "recall", "decision_after_recall"]
    rows = verify(tmp_path, record, kwargs, boundaries=1)
    session = record.session
    assert rows[0].decision == session.records[0]
    world, state = load(
        tmp_path / "opening.json", kwargs["compat"].pack, record.packets, record.audit
    )

    def build(world, state, packets, journal, caller):
        return compose(
            world,
            **{
                **kwargs,
                "restored": state.continuation,
                "packets": packets,
                "journal": journal,
                "caller": caller,
            },
        )

    restored = continue_offline(world, state, record.packets, record.audit, build, boundaries=1)
    assert restored.records == session.records
    assert restored.continuation() == session.continuation()
    assert len(fake.calls) == 3


def test_mm14_every_revision_and_restored_use_keys(tmp_path):
    from living_island.memory.v2.kinds import KindRegistry
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.harness.checkpoint import load
    from living_island.sim.v2.harness.replay import History, replay_revisions

    record, kwargs, _ = start(tmp_path)
    record.advance()
    record.save(tmp_path / "after.json")
    _, state = load(tmp_path / "after.json", kwargs["compat"].pack, record.packets, record.audit)
    live = record.session.resident.period.store.snapshot
    assert state.resident.period.store.restore(KindRegistry()).store_hash == live.store_hash
    assert live.credited_ids == {"m:ryan:1"}
    rows = verify(tmp_path, record, kwargs, boundaries=1)
    assert len(rows[0].revisions) == live.version - 1
    assert rows[0].revisions[-1] == live.store_hash
    from_empty = MemoryStore("ryan")
    every = list(replay_revisions(History(record.audit, record.audit.cursor()), 0, from_empty))
    assert len(every) == live.version and every[1:] == list(rows[0].revisions)
    assert from_empty.snapshot.store_hash == live.store_hash


def test_mf13_committed_change_set_and_mechanical_order(tmp_path):
    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.harness.checkpoint import Revision
    from living_island.sim.v2.harness.replay import History, replay_revisions

    record, _, _ = start(tmp_path)
    store = record.session.resident.period.store
    replay = MemoryStore.from_snapshot(store.snapshot)
    before = record.audit.cursor()
    record.advance()
    record.advance()
    mind = record.session.resident
    flow = mind.period.workflow
    while flow.state.stage != "ready":
        flow.advance(mind.caller.transport, mind.caller.clock)
    packet = mind.delivery.packet
    wake = packet.perception.model_copy(
        update={"awareness": "awake", "tick": 36, "running_action": None}
    )
    sealed = mind.period.deliver(
        FilteredDelivery(
            packet.model_copy(
                update={
                    "observed_tick": 36,
                    "delivery_id": "living-k",
                    "perception": wake,
                    "reports": [],
                }
            )
        )
    )
    assert sealed.record.episodic_created == 1
    history = History(record.audit, record.audit.cursor())
    revisions = [
        Revision.model_validate_json(history.read(key))
        for key in history.audit.keys(before, history.through)
        if key.endswith(".revision.json")
    ]
    assert {r.kind for r in revisions} == {"mechanical", "use", "change_set"}
    assert list(replay_revisions(history, before, replay)) == [r.store_hash for r in revisions]
    assert replay.snapshot.store_hash == store.snapshot.store_hash


def test_dl20_all_floors_and_notice(tmp_path, monkeypatch):
    from living_island.agents.v2.calls.contracts import CallKind, Contract
    from living_island.agents.v2.calls.guard import Assembly, Call, Part, Ref, prepare
    from living_island.agents.v2.calls.wire import NOTICE, WINDOW, frame
    from living_island.sim.v2.harness.replay import History

    record, _, _ = start(tmp_path)
    journal = record.session.resident.period.journal
    protected = Part("index", Ref(kind="index", id="index", version="0"), "é" * (WINDOW // 2 + 1))
    for kind in get_args(CallKind.__value__):
        call = Call(call_id=kind, resident_id="ryan", tick=0, period_id="p1")
        cue = 0 if kind in ("decision", "decision_after_recall", "morning") else None
        prepared = prepare(
            call, Contract(kind), Assembly((protected,), (), frozenset({0}), cue), journal
        )
        history = History(record.audit, record.audit.cursor())
        rebuilt = history.request(prepared.cursor, ())
        assert rebuilt.record == prepared.record and rebuilt.admitted is None
        assert rebuilt.record.candidates[-1].manifest.tokens_total > WINDOW
        assert tuple(history.attempts(rebuilt)) == ()

    contract = Contract("consolidation_selection")
    # A non-ASCII scalar outside the pinned vocabulary counts by UTF-8 byte length.
    overhead = frame(contract.kind, contract.instructions, contract.schema, "é").counted - 2
    floor = "é" * ((WINDOW - overhead) // 2)
    plain = frame(contract.kind, contract.instructions, contract.schema, floor)
    assert plain.counted <= WINDOW and len(plain.body) > 131072
    keep = Part("index", protected.source, floor)
    omit = Part("day_log", Ref(kind="day_log", id="old", version=None), "old entry")
    call = call.model_copy(update={"call_id": "notice"})
    prepared = prepare(call, contract, Assembly((omit, keep), (0,), frozenset({1})), journal)
    assert prepared.admitted is None and prepared.record.candidates[-1].omitted == (omit.source,)
    assert (
        prepared.record.candidates[-1].manifest.tokens_total
        == frame(
            contract.kind, contract.instructions, contract.schema, NOTICE + "\n" + floor
        ).counted
    )
    admitted = prepare(
        call.model_copy(update={"call_id": "large"}),
        contract,
        Assembly((keep,), (), frozenset({0})),
        journal,
    )
    assert admitted.admitted.wire.body == plain.body

    from dataclasses import replace

    from living_island.agents.v2.context import working
    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.sim.v2.harness.consolidation import workflow

    def with_large_floor(target):
        def measure(call, contract, assembly, journal):
            if contract.kind == target:
                assembly = replace(
                    assembly,
                    parts=(*assembly.parts, protected),
                    protected=assembly.protected | {len(assembly.parts)},
                )
            return prepare(call, contract, assembly, journal)

        return measure

    for kind in ("decision", "decision_after_recall"):
        run, _, fake = start(tmp_path / kind)
        with monkeypatch.context() as patch:
            patch.setattr(working, "prepare", with_large_floor(kind))
            assert run.advance() is None
        assert fake.calls == ([] if kind == "decision" else ["decision", "recall"])
        assert run.session.records[-1].submission is None and run.session.world.tick == 0

    for kind in ("consolidation_selection", "consolidation_change_set"):
        for end in ("living_k", "early_wake", "death"):
            run, _, fake = start(tmp_path / kind / end)
            run.advance()
            run.advance()
            period = run.session.resident.period
            flow = period.workflow
            before = period.store.snapshot.store_hash
            with monkeypatch.context() as patch:
                patch.setattr(workflow, "prepare", with_large_floor(kind))
                while flow.state.stage != "ready":
                    flow.advance(fake, run.session.resident.caller.clock)
            assert flow.state.reason == "stopped_unfit" and kind not in fake.calls
            assert period.checkpoint().halt is None
            assert period.store.snapshot.store_hash == before
            if end == "death":
                result = period.death(2)
            else:
                tick = 36 if end == "living_k" else 2
                packet = run.session.resident.delivery.packet
                wake = packet.perception.model_copy(
                    update={"awareness": "awake", "tick": tick, "running_action": None}
                )
                result = period.deliver(
                    FilteredDelivery(
                        packet.model_copy(
                            update={
                                "delivery_id": f"wake-{tick}",
                                "observed_tick": tick,
                                "perception": wake,
                                "reports": [],
                            }
                        )
                    )
                )
            if end == "living_k":
                assert result.status == "stopped_unfit" and result.record.outcome == "failed"
            else:
                assert result.record.outcome == "abandoned"
            assert result.record.write is None
            hashes = [w.write.store_hash for w in result.writes]
            assert period.store.snapshot.store_hash == (hashes[-1] if hashes else before)

    from living_island.agents.v2.context import prefix
    from living_island.sim.v2.manifest import TerminalStop

    run, _, fake = start(tmp_path / "morning")
    run.advance()
    run.advance()
    mind = run.session.resident
    packet = mind.delivery.packet
    wake = packet.perception.model_copy(
        update={"awareness": "awake", "tick": 36, "running_action": None}
    )
    mind.deliver(
        FilteredDelivery(
            packet.model_copy(
                update={
                    "observed_tick": 36,
                    "perception": wake,
                    "delivery_id": "morning",
                    "reports": [],
                }
            )
        ),
        run.session.intents,
        (),
    )
    assert mind.period.context is None
    with monkeypatch.context() as patch:
        patch.setattr(prefix, "prepare", with_large_floor("morning"))
        stopped = mind.decide("wake", ("woke",), "12:00", frozenset())
    assert isinstance(stopped, TerminalStop) and stopped.reason == "stopped_unfit"
    assert "morning" not in fake.calls


def test_dl27_unfit_recall_preserves_pending_batch_and_staged_companion(tmp_path, monkeypatch):
    from living_island.memory.v2.projections import ProjectedRevision
    from living_island.sim.v2.harness.replay import History
    from living_island.sim.v2.manifest import FallbackTurn
    from living_island.world.v2.engine.snapshot import encode_snapshot

    record, kwargs, fake = start(tmp_path)
    session = record.session
    before = encode_snapshot(session.world)
    choose = session.runner._decide
    staged = []

    def choose_with_fallback(request):
        result = choose(request)
        if request.delivery.actor_id == "ella":
            staged.append(result)
            return FallbackTurn(result, "provider_error", "fixture")
        return result

    monkeypatch.setattr(session.runner, "_decide", choose_with_fallback)
    monkeypatch.setattr(ProjectedRevision, "index_line", property(lambda _: "é" * 500000))
    assert record.advance() is None and staged and fake.calls == ["decision"]
    assert encode_snapshot(session.world) == before and record.packets.verify(session.world)
    assert not session.runner.manifest.boundaries
    decision = session.records[-1]
    key = decision.prepared_cursors[-1]
    assert session.runner.manifest.stop.stop.witness == key
    history = History(record.audit, record.audit.cursor())
    prepared = history.request(key, ())
    assert prepared.record.reason == "stopped_unfit" and prepared.admitted is None
    assert decision.submission is None and not decision.fallback.used
    assert tuple(history.attempts(prepared)) == ()
    assert verify(tmp_path, record, kwargs, boundaries=1)[0].decision == decision
    query = next(
        e for e in prepared.record.candidates[0].manifest.entries if e.source.kind == "query"
    )
    assert history.read(query.sha256) == b"What do I remember?"


def test_immutable_and_corrupt_audit_entries(tmp_path):
    from living_island.persistence.v2.audit import AuditReader, AuditWriter

    path = tmp_path / "audit.sqlite"
    writer = AuditWriter(path)
    reader = AuditReader(path)
    writer.keep("test.fact", b"first")
    writer.keep("test.fact", b"first")
    with pytest.raises(FileExistsError):
        writer.create("test.fact", b"first")
    with pytest.raises(ValueError, match="immutable"):
        writer.keep("test.fact", b"second")
    with pytest.raises(KeyError):
        reader.read("test.fact", 0)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE facts SET body=?", (b"changed",))
    with pytest.raises(ValueError, match="audit hash differs for test.fact"):
        reader.read("test.fact")


def test_recover_abandoned_attempt_from_durable_cursor(tmp_path):
    from v2.resident_replay.replay_evidence import interruption_cases

    record, kwargs, _ = start(tmp_path)
    record.advance()
    record.advance()
    record.save(tmp_path / "confirmed.json")
    receipts = interruption_cases(tmp_path, record, kwargs)
    assert all(row["outcome"] == "abandoned" for row in receipts.values())


def test_partial_boundary_requires_restore(tmp_path, monkeypatch):
    from living_island.sim.v2.harness.checkpoint import load
    from living_island.sim.v2.harness.composition import compose
    from living_island.sim.v2.harness.replay import History, InterruptedAttempt, RecordedCaller

    record, kwargs, fake = start(tmp_path)

    def crash(body, timeout_ms):
        raise RuntimeError("interrupted")

    monkeypatch.setattr(fake, "exchange", crash)
    with pytest.raises(RuntimeError, match="interrupted"):
        record.advance()
    with pytest.raises(RuntimeError, match="cannot save"):
        record.save(tmp_path / "partial.json")
    with pytest.raises(RuntimeError, match="restore"):
        record.advance()
    history = History(record.audit, record.audit.cursor())
    world, state = load(
        tmp_path / "opening.json", kwargs["compat"].pack, record.packets, record.audit
    )
    restored = compose(
        world,
        **{
            **kwargs,
            "restored": state.continuation,
            "journal": history.journal(),
            "caller": RecordedCaller.offline(history),
        },
    )
    with pytest.raises(InterruptedAttempt) as error:
        restored.advance()
    assert error.value.disposition.dispatch.n == 0 and world.tick == 0
    assert fake.calls == []


def test_diagnose_request_and_attempt_mismatches(tmp_path):
    from living_island.agents.v2.calls.contracts import json_bytes, read_json
    from living_island.sim.v2.harness.replay import History

    record, _, _ = start(tmp_path)
    record.advance()
    history = History(record.audit, record.audit.cursor())
    key = record.session.records[0].prepared_cursors[1]
    original = history.read(key)

    def replace(key, raw):
        replace_fact(record.audit.path, key, raw)

    for field in ("schema_sha256", "wire_adapter_version", "counter_version"):
        row = read_json(original)
        row["settings"][field] = "incorrect-pin"
        replace(key, json_bytes(row))
        with pytest.raises(ValueError, match=field):
            history.request(key, ())
    row = read_json(original)
    row["call"]["call_id"] = "another-call"
    replace(key, json_bytes(row))
    with pytest.raises(ValueError, match="prepared call ID"):
        history.request(key, ())
    row = read_json(original)
    row["candidates"][0]["manifest"]["tokens_total"] -= 1
    replace(key, json_bytes(row))
    with pytest.raises(ValueError, match="expected .* rebuilt"):
        history.request(key, ())
    replace(key, original)
    prepared = history.request(key, ())
    claim = record.session.resident.period.journal.cursor(
        prepared.record.call.call_id, "0.dispatch"
    )
    raw = read_json(history.read(claim))
    raw["request_sha256"] = "wrong"
    replace(claim, json_bytes(raw))
    with pytest.raises(ValueError, match="sent request differs"):
        list(history.attempts(prepared))
    with sqlite3.connect(record.audit.path) as db:
        db.execute("UPDATE facts SET name=? WHERE name=?", (claim.replace(".0.", ".2."), claim))
    verbs = tuple(s.shape for s in record.session.world.pack.verbs.values())
    with pytest.raises(ValueError, match="unlinked attempt facts"):
        history.verify_calls(0, verbs)


def test_replay_rejects_divergent_boundary_and_intermediate_version(tmp_path):
    from living_island.agents.v2.calls.contracts import json_bytes, read_json
    from living_island.agents.v2.calls.journal import Journal
    from living_island.sim.v2.harness.checkpoint import load
    from living_island.sim.v2.harness.composition import compose
    from living_island.sim.v2.harness.replay import continue_offline

    record, kwargs, _ = start(tmp_path)
    record.advance()
    boundary_key = Journal.cursor(record.session.world.run_id, "0.boundary")
    original = record.audit.read(boundary_key)

    def build(world, state, packets, journal, caller):
        return compose(
            world,
            **{
                **kwargs,
                "restored": state.continuation,
                "packets": packets,
                "journal": journal,
                "caller": caller,
            },
        )

    for field, value, agent_error, world_error in (
        ("world_hash", "wrong", "restored continuation", "boundary world or memory"),
        ("submissions", [], "replayed settlement", "decision submission"),
        ("committed", False, "terminal disposition", None),
    ):
        row = read_json(original)
        row[field] = value
        replace_fact(record.audit.path, boundary_key, json_bytes(row))
        world, state = load(
            tmp_path / "opening.json", kwargs["compat"].pack, record.packets, record.audit
        )
        with pytest.raises(ValueError, match=agent_error):
            continue_offline(world, state, record.packets, record.audit, build, boundaries=1)
        if world_error:
            with pytest.raises(ValueError, match=world_error):
                verify(tmp_path, record, kwargs, boundaries=1)
    replace_fact(record.audit.path, boundary_key, original)
    key = Journal.cursor("ryan", "v2.revision")
    row = read_json(record.audit.read(key))
    row["store_hash"] = "wrong"
    replace_fact(record.audit.path, key, json_bytes(row))
    with pytest.raises(ValueError, match="store hash differs at version 2"):
        verify(tmp_path, record, kwargs, boundaries=1)
