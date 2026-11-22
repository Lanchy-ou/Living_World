"""Gate 1 vectors for restoring and recording completed v2 boundaries."""

import json
from dataclasses import replace
from hashlib import sha256

import pytest
from persistence_support import make_world as make_world
from persistence_support import pack as pack
from persistence_support import setup as setup
from persistence_support import vectors

A, B = vectors.A, vectors.B


def restore(world, snapshot=None, pack=None):
    from living_island.world.v2.engine.snapshot import encode_snapshot, restore_snapshot

    return restore_snapshot(
        encode_snapshot(world) if snapshot is None else snapshot,
        world.pack.source if pack is None else pack,
        pack_ids=world.state.library.pack_ids,
    )


def typed_turn(world, actor, action, **fields):
    from living_island.world.v2.protocol import TurnSubmission

    return TurnSubmission.model_validate(vectors.turn(world, actor, action, **fields))


def proposed(key, trigger, **fields):
    return {
        "id": key,
        "trigger": trigger,
        "provenance": {
            "kind": "proposed",
            "llm_call_id": "fixture_call",
            "approved_by": "fixture_owner",
            "approved_at_tick": 0,
        },
        **fields,
    }


def store_for(world, directory):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.persistence.v2.replay import RuleStore

    return PacketJournal(directory / "packets", world.run_id), RuleStore(directory)


@pytest.mark.parametrize(
    ("scenario", "args"),
    [
        pytest.param(vectors.test_wap05_replacement_feedback_is_delivered_once, (), id="replace"),
        pytest.param(vectors.test_wap19_exact_mixed_report_order_and_no_repeat, (), id="awake"),
        # CR-P3.5-EN-05 is pending. The exact wake vector has progress and no hearing.
        pytest.param(
            vectors.test_en25_final_sleep_tick_never_hears_even_when_sleep_settles_first,
            (1, True),
            id="wake",
        ),
        pytest.param(vectors.test_round3_consumption_sight_and_actor_death, (), id="watch"),
    ],
)
def test_en05_packet_vectors_restore_before_every_ack(
    scenario, args, make_world, monkeypatch, tmp_path
):
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import TurnSubmission, canonical_bytes

    original_step = vectors.step

    def restore_and_step(world, *submissions):
        journal, store = store_for(world, tmp_path / world.pack.source.pack_id)
        snapshot = encode_snapshot(world)
        restored = restore(world, snapshot)
        assert restored.state == world.state
        assert encode_snapshot(restored) == snapshot
        packets = tuple(map(canonical_bytes, world.pending_packets()))
        assert tuple(map(canonical_bytes, restored.pending_packets())) == packets

        # Re-ingest after a crash between journaling the delivery and acknowledging it.
        tick = world.tick
        assert journal.ingest(world) == journal.ingest(restored)
        assert tuple(map(canonical_bytes, journal.read(tick))) == packets

        actual = record_boundary(
            restored, journal, store, tuple(map(TurnSubmission.model_validate, submissions))
        )
        expected = original_step(world, *submissions)
        assert actual == expected
        assert encode_snapshot(restored) == encode_snapshot(world)
        return expected

    monkeypatch.setattr(vectors, "step", restore_and_step)
    scenario(make_world, *args)


def test_en20_en21_wap16_replay_rule_additions_and_store_refill(pack, setup, tmp_path):
    from living_island.persistence.v2.manifest import RunManifest, read_manifest, write_manifest
    from living_island.persistence.v2.replay import RecordedBoundary, record_boundary, replay
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import action_schema_sha256, encode_event_line
    from living_island.world.v2.rules import load_pack
    from living_island.world.v2.rules.schema import canonical_json_bytes

    base = load_pack(tmp_path / "engine-test", pack.vocabulary)
    packs = (base, pack)
    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path / "run")
    manifest = RunManifest.capture(world.run_id, packs)
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)
    assert read_manifest(manifest_path) == manifest
    assert tuple(pin.pack_hash for pin in manifest.packs) == tuple(p.pack_hash for p in packs)
    assert manifest.rule_library_hash == pack.rule_library_hash
    assert pack.rules["rule_b"].data["provenance"] == {"kind": "authored", "pack_id": "engine-test"}

    beginning = encode_snapshot(world)
    assert world.initial_events[0].payload["initial_snapshot_hash"] == sha256(beginning).hexdigest()
    verb_shapes = tuple(verb.shape for verb in world.pack.verbs.values())
    schema_hash = action_schema_sha256(verb_shapes)
    # Preserve the authored rule's conditions and target so ID is the tie-breaker.
    raw = {key: value for key, value in pack.rules["rule_b"].data.items() if key != "provenance"}
    slow = {**raw, **proposed("a_long_gather", "verb:gather", work_ticks=4)}
    fast = {**raw, **proposed("a_fast_gather", "verb:gather", work_ticks=1)}
    periodic = proposed("a_periodic", "every:100", subject={"archetype": "arch_b"})
    records = []
    expected = []

    def advance(submissions=(), additions=()):
        result = record_boundary(world, journal, store, submissions, rule_additions=additions)
        event_lines = b"".join(map(encode_event_line, result.events))
        records.append(RecordedBoundary(submissions, event_lines))
        expected.append((encode_snapshot(world), event_lines))
        return result

    first = advance(
        (typed_turn(world, B, "act", verb="gather", target=vectors.entity("inst_b")),), (slow,)
    )
    added = first.events[0]
    assert added.type == "rule_added"
    pin = added.payload["content_hash"]
    saved_rule = store.run_directory / "rules" / f"{pin}.json"
    assert saved_rule.read_bytes() == canonical_json_bytes(
        world.pack.source.rules["a_long_gather"].data
    )
    assert added.payload["provenance"] == slow["provenance"]
    assert any(event.type == "store_count_changed" for event in first.events)
    assert world.state.active_actions[B].rule_id == "a_long_gather"
    assert world.state.library.rule_library_hash != manifest.rule_library_hash
    assert manifest.rule_library_hash == pack.rule_library_hash

    # Walking A next to the store keeps the first gather running across another addition.
    advance((typed_turn(world, A, "move_to", target=vectors.tile(2, 2)),))
    both = advance(
        (typed_turn(world, A, "act", verb="gather", target=vectors.entity("inst_b")),),
        (fast, periodic),
    )
    assert [event.payload["rule_id"] for event in both.events[:2]] == [
        "a_fast_gather",
        "a_periodic",
    ]
    assert all(event.type == "rule_added" for event in both.events[:2])
    assert both.actions[0].settlement.rule_id == "a_fast_gather"
    assert world.state.active_actions[B].rule_id == "a_long_gather"
    assert action_schema_sha256(verb.shape for verb in world.pack.verbs.values()) == schema_hash
    assert action_schema_sha256(verb_shapes[:-1]) != schema_hash
    final = advance()
    assert final.actions[0].settlement.rule_id == "a_long_gather"

    for start, segment, checkpoints in (
        (beginning, records, expected),
        (expected[0][0], records[1:], expected[1:]),
    ):
        for _ in range(2):
            replayed = replay(start, manifest, packs, journal, store, segment)
            assert [(frame.snapshot, frame.event_lines) for frame in replayed] == checkpoints
    assert encode_snapshot(restore(world, pack=pack)) == expected[-1][0]

    world_rule = store.run_directory / "rules" / f"{both.events[1].payload['content_hash']}.json"
    periodic_bytes = world_rule.read_bytes()
    malformed = json.loads(periodic_bytes)
    del malformed["instruments"]
    world_rule.write_bytes(canonical_json_bytes(malformed))
    with pytest.raises(ValueError, match="canonical world rule must have empty instruments"):
        list(replay(beginning, manifest, packs, journal, store, records))
    world_rule.write_bytes(periodic_bytes)

    rule_bytes = saved_rule.read_bytes()
    saved_rule.write_bytes(rule_bytes + b"\n")
    with pytest.raises(ValueError, match="canonical rule bytes"):
        list(replay(beginning, manifest, packs, journal, store, records))
    altered = json.loads(rule_bytes)
    altered["provenance"]["approved_by"] = "different_approver"
    saved_rule.write_bytes(canonical_json_bytes(altered))
    with pytest.raises(ValueError, match="event log differs"):
        list(replay(beginning, manifest, packs, journal, store, records))
    altered["work_ticks"] += 1
    saved_rule.write_bytes(canonical_json_bytes(altered))
    with pytest.raises(ValueError, match="rule content does not match"):
        list(replay(beginning, manifest, packs, journal, store, records))
    saved_rule.unlink()
    with pytest.raises(FileNotFoundError, match=str(pin)):
        list(replay(beginning, manifest, packs, journal, store, records))


def test_rule_write_failure_keeps_boundary_pending(pack, setup, tmp_path, monkeypatch):
    from living_island.persistence.v2.replay import RuleStore, record_boundary
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.events import EventWriter
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.rules import validate_proposal
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    journal, failing_store = store_for(world, tmp_path / "unwritable")
    raw = proposed("a_new_rule", "every:100", subject={"archetype": "arch_b"})
    content = validate_proposal(pack, raw)
    path = failing_store.run_directory / "rules" / f"{content.content_hash}.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"wrong bytes")
    before = encode_snapshot(world)
    emit = EventWriter.emit
    store = RuleStore(tmp_path / "retry")

    def check_write(writer, event_type, payload, **fields):
        if event_type == "rule_added":
            file = store.run_directory / "rules" / f"{payload['content_hash']}.json"
            assert file.read_bytes() == canonical_json_bytes(content.data)
        return emit(writer, event_type, payload, **fields)

    monkeypatch.setattr(EventWriter, "emit", check_write)
    with pytest.raises(ValueError, match="re-ingestion differs"):
        record_boundary(world, journal, failing_store, rule_additions=(raw,))
    assert encode_snapshot(world) == before
    assert journal.read(0) == world.pending_packets()
    retried = record_boundary(world, journal, store, rule_additions=(raw,))
    assert retried.events[0].type == "rule_added"


@pytest.mark.parametrize("answer", ["accept", "refuse"])
def test_en21_first_and_second_proposal_replies_after_checkpoint(pack, setup, tmp_path, answer):
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path)
    cursor = {packet.actor_id: packet.delivery_id for packet in world.pending_packets()}
    proposal = {
        **vectors.statement(B),
        "speech_act": "propose",
        "terms": {
            "promisor_id": A,
            "promisee_id": B,
            "what": {"kind": "be_at", "position": {"x": 1, "y": 1}},
            "due_tick": 8,
        },
    }
    offered = record_boundary(
        world, journal, store, (typed_turn(world, A, "wait", speech=proposal),)
    )
    proposal_id = offered.utterances[A].utterance_id
    checkpoint = tmp_path / "before_reply.json"
    sim_state = {"delivery_cursors": cursor}
    journal.ingest(world)
    save_checkpoint(checkpoint, world, journal, sim_state)
    restored = load_checkpoint(checkpoint, pack, journal, pack_ids=setup.pack_ids)
    assert restored.sim_checkpoint == sim_state
    assert restored.first_journal_tick == 0
    assert encode_snapshot(restored.world) == encode_snapshot(world)
    accepted = record_boundary(
        restored.world,
        journal,
        store,
        (
            typed_turn(
                world,
                B,
                "wait",
                speech={
                    **vectors.statement(A),
                    "speech_act": answer,
                    "in_reply_to": proposal_id,
                },
            ),
        ),
    )
    assert accepted.utterances[B].failure_code is None
    world = restore(restored.world)
    assert world.state.proposals[proposal_id].answer == answer
    assert len(world.state.agreements) == (answer == "accept")
    second = record_boundary(
        world,
        journal,
        store,
        (
            typed_turn(
                world,
                B,
                "wait",
                speech={
                    **vectors.statement(A),
                    "speech_act": "accept",
                    "in_reply_to": proposal_id,
                },
            ),
        ),
    )
    assert second.utterances[B].failure_code == "INVALID_REPLY"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("vocabulary_hash", "0" * 64, "vocabulary hash"),
        ("rule_library_hash", "0" * 64, "rule library"),
        ("pack_hash", "0" * 64, "pack identity"),
    ],
)
def test_wap11_refuses_changed_snapshot_pins(pack, setup, field, value, error):
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    raw = json.loads(encode_snapshot(world))
    raw["library"][field] = value
    with pytest.raises(ValueError, match=error):
        restore(world, canonical_json_bytes(raw))


def test_snapshot_refuses_noncanonical_bytes_and_fractional_component_values(pack, setup):
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    snapshot = encode_snapshot(world)
    with pytest.raises(ValueError, match="canonical snapshot bytes"):
        restore(world, snapshot + b"\n")
    raw = json.loads(snapshot)
    raw["entities"]["inst_c"]["components"]["container"]["accepts"]["hardness_min"] = 1.5
    with pytest.raises(ValueError, match="fractional"):
        restore(world, canonical_json_bytes(raw))


def test_manifest_rejects_wrong_protocol_and_loaded_content(pack, tmp_path):
    from living_island.persistence.v2.manifest import RunManifest, read_manifest, write_manifest
    from living_island.world.v2.rules import load_pack
    from living_island.world.v2.rules.schema import canonical_json_bytes

    base = load_pack(tmp_path / "engine-test", pack.vocabulary)
    manifest = RunManifest.capture("test", (base, pack))
    with pytest.raises(ValueError, match="loaded content differs"):
        manifest.check_content((replace(base, pack_hash="0" * 64), pack))
    with pytest.raises(ValueError, match="base-first"):
        RunManifest.capture("test", (pack,))
    with pytest.raises(ValueError, match="at least one"):
        RunManifest.capture("test", ())
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="canonical manifest"):
        read_manifest(path)
    path.write_bytes(canonical_json_bytes({**json.loads(original), "schema_version": "wap/99"}))
    with pytest.raises(ValueError, match="wap/0.1"):
        read_manifest(path)


def test_en29_acknowledged_start_look_survives_tool_wear_and_disappearance(make_world, tmp_path):
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine.snapshot import encode_snapshot

    world = make_world(
        [(A, 3, 1), (B, 2, 1)],
        instances="""
[[instance]]
id = "saved_tool"
archetype = "arch_d"
at = { holder = "res_a" }
state = { durability = { wear = 2 } }
properties = { strength = 2 }
apparent = { hardness = 1 }
tell = ["strength"]
""",
        rules="""
[[rule]]
id = "a_slow_strike"
trigger = "verb:strike"
work_ticks = 3
target = { where = { archetype = "arch_b" } }
instruments = [{ slot = "tool", where = { archetype = "arch_d" }, qty = 1 }]

[[rule]]
id = "a_wear"
trigger = "every:1"
subject = { archetype = "arch_d" }
conditions = [
  { id = "left", kind = "state", of = "subject", field = "durability.left", op = ">", value = 0 }
]
effects = [{ op = "set_state", of = "subject", field = "durability.wear", add = 1 }]
""",
    )
    journal, store = store_for(world, tmp_path)
    start = typed_turn(
        world,
        A,
        "act",
        verb="strike",
        target=vectors.entity("inst_b"),
        instruments=[{"kind": "item", "id": "saved_tool"}],
    )
    record_boundary(world, journal, store, (start,))
    start_packet = vectors.packet(world, B)
    (start_watch,) = start_packet.perception.observed_actions
    (old_tool,) = [item for item in start_watch.visible_items if item.role == "instrument"]
    assert old_tool.entity_id == "saved_tool"
    assert vectors.looks(old_tool)["hardness"] == "soft"
    assert world.state.entities["saved_tool"].components["durability"]["wear"] == 3
    wear = record_boundary(world, journal, store)
    assert any(
        row.type == "entity_consumed" and row.payload["entity_id"] == "saved_tool"
        for row in wear.events
    )
    assert world.state.active_actions[A].rule_id == "a_slow_strike"
    assert "saved_tool" not in world.state.entities
    assert journal.read(1)[1] == start_packet
    assert start_packet.delivery_id != vectors.packet(world, B).delivery_id
    restored = restore(world)
    result = record_boundary(restored, journal, store)
    assert result == vectors.step(world)
    assert encode_snapshot(restored) == encode_snapshot(world)
    (finished,) = result.actions
    assert finished.settlement.kind == "unmet"
    assert finished.settlement.failed_check == "tool"
    assert old_tool in finished.visible_feedback.items_used
    (settle_watch,) = vectors.packet(restored, B).perception.observed_actions
    assert settle_watch.phase == "settle"
    assert all(item.entity_id != "saved_tool" for item in settle_watch.visible_items)
    assert journal.read(1)[1].perception.observed_actions[0] == start_watch


def test_en29_restored_counter_skips_consumed_id_and_exhaustion_is_atomic(
    pack,
    setup,
    tmp_path,
    monkeypatch,
):
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine import ids, initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path)

    def gather(world):
        return typed_turn(world, B, "act", verb="gather", target=vectors.entity("inst_b"))

    created = record_boundary(world, journal, store, (gather(world),))
    (new_entity,) = [e.payload["entity_id"] for e in created.events if e.type == "matter_moved"]
    assert new_entity in world.state.entities
    consume = proposed(
        "consume_portable",
        "every:2",
        subject={"archetype": "arch_a"},
        effects=[{"op": "consume", "of": "subject"}],
    )
    record_boundary(world, journal, store, rule_additions=(consume,))
    assert new_entity not in world.state.entities
    before = encode_snapshot(world)
    restored = restore(world, before, pack)
    counter = restored.state.entity_counter
    assert new_entity in counter.issued
    candidate = ids.entity_candidate

    def force_collision(seed, n, k):
        return new_entity if (n, k) == (counter.n, 0) else candidate(seed, n, k)

    monkeypatch.setattr(ids, "entity_candidate", force_collision)
    replayed = record_boundary(restored, journal, store, (gather(restored),))
    allocated = candidate(world.state.seed, counter.n, 1)
    assert [row.payload["entity_id"] for row in replayed.events if row.type == "matter_moved"] == [
        allocated
    ]
    assert restored.state.entity_counter.n == counter.n + 1

    exhausted = json.loads(before)
    exhausted["entity_counter"]["n"] = ids.MAX_EXACT - 1
    exhausted_bytes = canonical_json_bytes(exhausted)
    restored = restore(world, exhausted_bytes, pack)
    with pytest.raises(OverflowError, match="creation counter exhausted"):
        record_boundary(restored, journal, store, (gather(restored),))
    assert encode_snapshot(restored) == exhausted_bytes


def test_journal_rejects_wrong_run_and_changed_deliveries(pack, setup, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    journal, _ = store_for(world, tmp_path)
    wrong_journal = PacketJournal(journal.directory, "another_run")
    with pytest.raises(ValueError, match="different run"):
        wrong_journal.ingest(world)
    journal.ingest(world)
    with pytest.raises(ValueError, match="batch identity"):
        wrong_journal.read(0)

    file = journal.directory / "0.json"
    payload = json.loads(file.read_bytes())
    file.write_bytes(canonical_json_bytes({**payload, "packets": payload["packets"] * 2}))
    with pytest.raises(ValueError, match="one packet per resident"):
        journal.read(0)
    with pytest.raises(ValueError, match="re-ingestion differs"):
        journal.ingest(world)
    with pytest.raises(ValueError, match="journal differs at boundary 0"):
        journal.verify(world)

    file.write_bytes(canonical_json_bytes(payload) + b"\n")
    with pytest.raises(ValueError, match="canonical packet journal"):
        journal.read(0)


def test_checkpoint_refuses_inconsistent_prefix(pack, setup, tmp_path):
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine import initialize

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path)
    other_directory = PacketJournal(tmp_path / "other", world.run_id)
    wrong_run = PacketJournal(journal.directory, "another_run")
    record_boundary(world, journal, store)
    path = tmp_path / "checkpoint.json"
    with pytest.raises(ValueError, match="must belong to the same run"):
        save_checkpoint(path, world, wrong_run, {})
    with pytest.raises(ValueError, match="must end before the pending boundary"):
        save_checkpoint(path, world, journal, {}, first_journal_tick=2)
    with pytest.raises(ValueError, match="missing packet journal boundary 0"):
        save_checkpoint(path, world, other_directory, {})
    assert not path.exists()
    save_checkpoint(path, world, journal, {})
    with pytest.raises(ValueError, match="missing packet journal boundary 0"):
        load_checkpoint(path, pack, other_directory, pack_ids=setup.pack_ids)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="canonical checkpoint"):
        load_checkpoint(path, pack, journal, pack_ids=setup.pack_ids)
