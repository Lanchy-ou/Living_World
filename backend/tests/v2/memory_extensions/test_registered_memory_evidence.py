import json
from dataclasses import asdict

import pytest


@pytest.fixture(scope="module")
def shore(tmp_path_factory):
    from v2.memory_extensions.extension_fixture import shore_recording

    directory = tmp_path_factory.mktemp("shore")
    return (directory, *shore_recording(directory))


def fact(record, producer, slot):
    from living_island.agents.v2.calls.journal import Journal

    return json.loads(record.audit.read(Journal.cursor(producer, slot)))


def snapshot_at(record, version):
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.harness.replay import History, replay_revisions

    history = History(record.audit, record.audit.cursor())
    live = record.session.resident.period.store
    store = MemoryStore(live.snapshot.owner_id, live.registry)
    for _ in replay_revisions(history, 0, store):
        if store.snapshot.version == version:
            return store.snapshot
    pytest.fail(f"missing recorded store version {version}")


def test_mm15_off_arm_persists_mechanical_writes_behind_empty_reads(tmp_path):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.persistence.v2.audit import AuditReader, AuditWriter
    from living_island.sim.v2.harness.checkpoint import Recording
    from living_island.sim.v2.harness.composition import compose
    from v2.resident_replay.replay_fixture import start

    setup, kwargs, fake = start(tmp_path / "setup")
    audit = AuditWriter(tmp_path / "off.sqlite")
    session = compose(
        setup.session.world,
        **{**kwargs, "memory_on": False, "journal": Journal(audit.keep, audit.create)},
    )
    record = Recording.opening(session, kwargs["packets"], AuditReader(audit.path))
    mind = session.resident
    base_traits = next(p.text for p in mind.period.context.prefix.fixed if p.source.id == "traits")
    record.advance()
    current = mind.memory()[1]
    assert current.current_intention.record.text == "Remember the beach."
    assert current.index() == () and current.live() == ()
    for _ in range(37):
        if mind.period.number == 2 and mind.period.context is not None:
            break
        assert record.advance() is not None
    assert mind.period.number == 2
    prefix = mind.period.context.prefix
    assert prefix.memories == () and prefix.morning is None
    assert next(p.text for p in prefix.fixed if p.source.id == "traits") == base_traits
    snapshot = snapshot_at(record, mind.period.store.snapshot.version)
    records = snapshot.records()
    assert any(r.kind == "social" and r.content.about == "ella" for r in records)
    assert any(r.kind == "intention" and r.content.state == "reset" for r in records)
    personality = next(r.content for r in records if r.kind == "personality")
    assert personality == kwargs["identity"].profile.document.traits.personality()
    assert mind.memory()[1].index() == () and mind.memory()[1].current_intention is None
    assert set(fake.calls) == {"decision", "decision_after_recall"}
    assert all(not d.used_memories for d in session.records)
    empty = fact(record, session.records[0].turn_id, "off_empty")
    assert [e["retrieved"] for e in empty["entries"]] == [None]


def test_mm16_registered_kind_reaches_sent_prefix_and_replays(shore):
    from v2.resident_replay.replay_fixture import verify

    directory, record, kwargs, fake, seal = shore
    prefix = record.session.resident.period.context.prefix
    (memory,) = prefix.memories
    added = next(e for e in seal["effects"] if e["op_id"] == "beach")
    assert prefix.morning.selected_ids == (added["produced_id"],)
    snapshot = snapshot_at(record, memory.revision.store_version)
    stored = snapshot.read(memory.revision)
    assert stored.kind == "shore_note" and stored.content.landmark == "beach"
    (visible,) = [r for r in snapshot.resident(memory_on=True).live() if r.ref == memory.revision]
    assert visible.flags == ("coastal", "needs_review")
    assert " | coastal,needs_review | " in visible.index_line
    wake = record.session.records[-1]
    sent = fact(record, wake.call_ids[0], "0.dispatch")["sent"]["manifest"]
    prefix_section = next(s for s in sent["sections"] if s["section"] == "prefix")
    (part,) = [p for p in prefix_section["entries"] if p["source"]["kind"] == "memory"]
    assert part["source"] == memory.part.source.model_dump()
    assert part["sha256"] == memory.sha256
    assert json.loads(record.audit.read(part["sha256"])) == visible.record.model_dump(mode="json")

    calls = tuple(fake.calls)
    # Both checkpoints precede tick zero. Only the second contains the extension seed.
    count = record.session.world.tick
    opening = verify(directory, record, kwargs, boundaries=count)
    seeded = verify(directory, record, kwargs, start_at="seeded", boundaries=count)
    assert opening[0].revisions[-len(seeded[0].revisions) :] == seeded[0].revisions
    assert len(opening[0].revisions) == len(seeded[0].revisions) + 2
    assert opening[1:] == seeded[1:]
    assert seeded[-1].decision == wake
    assert (
        seeded[-1].boundary.store_hash == record.session.resident.period.store.snapshot.store_hash
    )
    assert tuple(fake.calls) == calls


def test_mf14_registered_kind_uses_normal_change_set(shore):
    _, record, _, _, seal = shore
    assert seal["outcome"] == "committed"
    by_op = {v["op_id"]: v["result"] for v in seal["verdicts"]}
    assert [by_op[k] for k in ("beach", "cove", "pier", "revise", "supersede")] == ["committed"] * 5
    write = seal["write"]
    assert write["kind"] == "change_set"
    assert seal["result_version"] == write["before_version"] + 1 == write["after_version"]
    committed = snapshot_at(record, seal["result_version"])
    assert committed.store_hash == seal["store_hash"]
    for effect in seal["effects"][:3]:
        key = effect["produced_id"]
        note = committed.read(committed.ref(key))
        assert note.content.landmark == effect["op_id"]
        assert note.sources[0].call_id == seal["change_set_call_id"]


def test_dl19_registered_recipe_follows_wake_reason_and_repeats_exactly(shore):
    from living_island.agents.v2.context.working import WorkingContext
    from living_island.agents.v2.recall.recipes import RecipeCues
    from living_island.sim.v2.harness.consolidation.checkpoint import PeriodLog
    from living_island.sim.v2.harness.replay import History
    from v2.memory_extensions.extension_fixture import ANCESTOR

    _, record, _, _, seal = shore
    start, wake = record.session.records
    assert start.reasons == ("start",) and "woke" in wake.reasons
    initial = fact(record, start.turn_id, "recipe")
    assert ANCESTOR not in [e["retrieved"]["id"] for e in initial["entries"]]
    parts = fact(record, wake.turn_id, "recipe")["entries"]
    expected_ids = [e["produced_id"] for e in seal["effects"] if e["op_id"] in ("cove", "pier")]
    assert [p["retrieved"]["id"] for p in parts] == expected_ids
    sent = fact(record, wake.call_ids[0], "0.dispatch")["sent"]["manifest"]
    sent_parts = {e["source"]["id"]: e for s in sent["sections"] for e in s["entries"]}
    for p in parts:
        assert sent_parts[p["entry_id"]]["sha256"] == p["fragment_sha256"]
        assert sent_parts[p["entry_id"]]["source"]["version"] == p["entry_revision"]
        assert p["retrieved"]["id"] in record.audit.read(p["fragment_sha256"]).decode()

    mind = record.session.resident
    before = snapshot_at(record, parts[0]["retrieved"]["store_version"])
    state = mind.period.log.checkpoint()
    pos = next(i for i, e in enumerate(state.entries) if e.id == parts[0]["entry_id"])
    before_recipe = state.model_copy(update={"entries": state.entries[:pos]})
    history = History(record.audit, record.audit.cursor())
    log = PeriodLog.restore(before_recipe, history.journal(), {})
    context = WorkingContext(mind.period.context.prefix, log)
    view = before.resident(memory_on=True)
    assert not mind.recipes.append(
        view, RecipeCues(wake.tick, frozenset({"start"})), context, wake.turn_id
    )
    cues = RecipeCues.from_delivery(
        mind.delivery, reasons=frozenset((*wake.reasons, *mind.classes))
    )
    rebuilt = mind.recipes.append(view, cues, context, wake.turn_id)
    assert [(e.id, asdict(e.retrieved), e.revision, e.fragment_sha256) for e in rebuilt] == [
        (p["entry_id"], p["retrieved"], p["entry_revision"], p["fragment_sha256"]) for p in parts
    ]


def test_mm19_kept_commitment_stays_in_inspection_and_leaves_resident_reads(shore):
    from v2.memory_extensions.extension_fixture import PROMISE

    _, record, _, _, seal = shore
    initial, wake = record.session.records
    assert PROMISE in initial.used_memories
    snapshot = snapshot_at(record, seal["result_version"])
    kept = snapshot.read(snapshot.ref(PROMISE))
    assert kept.content.status == "kept" and kept.content.status_note == "I went."
    assert all(r.ref.id != PROMISE for r in snapshot.resident(memory_on=True).records)
    morning = record.session.resident.period.context.prefix.morning
    assert PROMISE in morning.ignored_ids and PROMISE not in morning.selected_ids
    assert PROMISE in fact(record, wake.call_ids[1], "deliberate")["ignored_ids"]
    assert PROMISE not in wake.used_memories


def test_mm23_evicted_source_resolves_and_repeating_hearsay_only_witnesses_speech(shore):
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.projections import RevisionRef
    from living_island.memory.v2.provenance import SentInput
    from living_island.memory.v2.store import MemoryStore
    from living_island.memory.v2.validation import decode_change_set
    from v2.memory_extensions.extension_fixture import ANCESTOR

    _, record, _, _, seal = shore
    live = record.session.resident.period.store
    store = MemoryStore.from_snapshot(live.snapshot, live.registry)
    effects = {e["op_id"]: e for e in seal["effects"]}
    ref = RevisionRef(**effects["beach"]["bindings"][0]["revisions"][0])
    revised = store.snapshot.read(store.snapshot.ref(ANCESTOR))
    assert revised.content.landmark == "upper inlet" and revised.content_hash() != ref.content_hash

    # One history slot. Superseding another live note evicts the older ancestor.
    old, new = (effects[k]["produced_id"] for k in ("cove", "pier"))
    base = store.snapshot
    sent = SentInput(base.owner_id, "next-call", full=(base.ref(old), base.ref(new)))
    op = {"op_id": "replace", "op": "supersede", "id": old, "by": new}
    staged = stage_change_set(
        store, decode_change_set(json.dumps({"ops": [op]}), base.version), sent, 37
    )
    assert staged.evictions == (ANCESTOR,)
    staged.commit(store)
    view = store.snapshot.resident(memory_on=True)
    assert ANCESTOR not in {r.ref.id for r in view.records}
    descendant = next(r.record for r in view.live() if r.ref.id == effects["beach"]["produced_id"])
    assert descendant.sources[0].memory_ids == [ref.id] == [ANCESTOR]
    original = snapshot_at(record, ref.store_version).read(ref)
    assert original.content.landmark == "inlet" and original.sources[0].kind == "told"
    assert original.sources[0].speaker_id == "ella"
    proposal = next(op for op in seal["change_set"]["ops"] if op["op_id"] == "claim_observed")
    key = proposal["record"]["sources"][0]["entry_id"]
    archive = json.loads(record.audit.read(seal["closed_context"]))
    spoken = next(e for e in archive["log"]["entries"] if e["id"] == key)
    assert spoken["type"] == "utterance_result" and original.gist in spoken["text"]
    assert spoken["about"] == ["spoke:" + spoken["ref"]["utterance_id"]]
    verdict = next(v for v in seal["verdicts"] if v["op_id"] == "claim_observed")
    assert (verdict["result"], verdict["reason"]) == ("dropped", "source_kind")
