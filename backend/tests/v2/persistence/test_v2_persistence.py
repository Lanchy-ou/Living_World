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
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path / "run")
    manifest = RunManifest.capture(world.run_id, pack)
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)
    assert read_manifest(manifest_path) == manifest
    assert manifest.pack_ids == setup.pack_ids
    assert manifest.packs[-1].pack_hash == pack.pack_hash
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
            replayed = replay(start, manifest, pack, journal, store, segment)
            assert [(frame.snapshot, frame.event_lines) for frame in replayed] == checkpoints
    assert encode_snapshot(restore(world, pack=pack)) == expected[-1][0]

    world_rule = store.run_directory / "rules" / f"{both.events[1].payload['content_hash']}.json"
    periodic_bytes = world_rule.read_bytes()
    malformed = json.loads(periodic_bytes)
    del malformed["instruments"]
    world_rule.write_bytes(canonical_json_bytes(malformed))
    with pytest.raises(ValueError, match="canonical world rule must have empty instruments"):
        list(replay(beginning, manifest, pack, journal, store, records))
    world_rule.write_bytes(periodic_bytes)

    rule_bytes = saved_rule.read_bytes()
    saved_rule.write_bytes(rule_bytes + b"\n")
    with pytest.raises(ValueError, match="canonical rule bytes"):
        list(replay(beginning, manifest, pack, journal, store, records))
    altered = json.loads(rule_bytes)
    altered["provenance"]["approved_by"] = "different_approver"
    saved_rule.write_bytes(canonical_json_bytes(altered))
    with pytest.raises(ValueError, match="event log differs"):
        list(replay(beginning, manifest, pack, journal, store, records))
    altered["work_ticks"] += 1
    saved_rule.write_bytes(canonical_json_bytes(altered))
    with pytest.raises(ValueError, match="rule content does not match"):
        list(replay(beginning, manifest, pack, journal, store, records))
    saved_rule.unlink()
    with pytest.raises(FileNotFoundError, match=str(pin)):
        list(replay(beginning, manifest, pack, journal, store, records))


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
    restored = load_checkpoint(checkpoint, pack, journal)
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
    from living_island.world.v2.rules.schema import canonical_json_bytes

    manifest = RunManifest.capture("test", pack)
    with pytest.raises(ValueError, match="loaded content differs"):
        manifest.check_content(replace(pack, pack_hash="0" * 64))
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
    from living_island.world.v2.rules.schema import canonical_json_bytes

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
        load_checkpoint(path, pack, other_directory)
    valid = path.read_bytes()
    payload = json.loads(valid)
    path.write_bytes(canonical_json_bytes({**payload, "next_journal_tick": 0}))
    with pytest.raises(ValueError, match="must end before the pending boundary"):
        load_checkpoint(path, pack, journal)
    path.write_bytes(canonical_json_bytes({**payload, "run_id": "foreign_run"}))
    with pytest.raises(ValueError, match="checkpoint and world"):
        load_checkpoint(path, pack, journal)
    path.write_bytes(valid + b"\n")
    with pytest.raises(ValueError, match="canonical checkpoint"):
        load_checkpoint(path, pack, journal)


@pytest.mark.parametrize("entry", ["save", "load"])
@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("foreign", "batch identity"),
        ("malformed", "Invalid JSON"),
        ("noncanonical", "canonical packet journal"),
        ("row_tick", "packet identity"),
        ("batch_tick", "batch identity"),
        ("foreign_delivery", "packet identity"),
        ("perception_tick", "packet identity"),
        ("perception_actor", "packet identity"),
    ],
)
def test_checkpoint_validates_every_referenced_batch(
    pack, setup, tmp_path, entry, corruption, message
):
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import boundary_delivery_id
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path / "genuine")
    record_boundary(world, journal, store)
    record_boundary(world, journal, store)
    path = tmp_path / "checkpoint.json"
    # The coordinator owns this payload and can use its own cursor representation.
    cursor = {"coordinator": {"opaque_cursor": ["checkpoint", 2]}}
    save_checkpoint(path, world, journal, cursor)
    valid = load_checkpoint(path, pack, journal)
    assert valid.sim_checkpoint == cursor
    assert encode_snapshot(valid.world) == encode_snapshot(world)

    batch = journal.directory / "1.json"
    data = batch.read_bytes()
    payload = json.loads(data)
    match corruption:
        case "foreign":
            other = initialize(pack, setup.model_copy(update={"run_id": "foreign_run"}))
            foreign, other_store = store_for(other, tmp_path / "foreign")
            record_boundary(other, foreign, other_store)
            foreign.ingest(other)
            data = (foreign.directory / "1.json").read_bytes()
        case "malformed":
            data = b"{"
        case "noncanonical":
            data += b"\n"
        case "row_tick":
            payload["packets"][0]["observed_tick"] = 2
            data = canonical_json_bytes(payload)
        case "batch_tick":
            payload["observed_tick"] = 2
            for packet in payload["packets"]:
                packet["observed_tick"] = 2
                packet["perception"]["tick"] = 2
                packet["delivery_id"] = boundary_delivery_id(world.run_id, 2, packet["actor_id"])
            data = canonical_json_bytes(payload)
        case "foreign_delivery":
            packet = payload["packets"][0]
            packet["delivery_id"] = boundary_delivery_id("foreign_run", 1, packet["actor_id"])
            data = canonical_json_bytes(payload)
        case "perception_tick":
            payload["packets"][0]["perception"]["tick"] = 2
            data = canonical_json_bytes(payload)
        case "perception_actor":
            payload["packets"][0]["perception"]["actor_id"] = B
            data = canonical_json_bytes(payload)
    batch.write_bytes(data)
    if entry == "save":
        target = tmp_path / "invalid_save.json"
        with pytest.raises(ValueError, match=message):
            save_checkpoint(target, world, journal, cursor)
        assert not target.exists()
    else:
        with pytest.raises(ValueError, match=message):
            load_checkpoint(path, pack, journal)


@pytest.mark.parametrize("opening_tick", [0, 1])
def test_future_approval_cannot_commit_rule_at_opening_boundary(
    pack, setup, tmp_path, opening_tick
):
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path)
    for _ in range(opening_tick):
        record_boundary(world, journal, store)
    before = encode_snapshot(world)
    pending = world.pending_packets()
    library = world.state.library
    current = proposed("current_rule", "every:100", subject={"archetype": "arch_b"})
    future = proposed("future_rule", "every:100", subject={"archetype": "arch_b"})
    current["provenance"]["approved_at_tick"] = opening_tick
    future["provenance"]["approved_at_tick"] = opening_tick + 1
    with pytest.raises(ValueError, match="approved after the opening boundary"):
        record_boundary(world, journal, store, rule_additions=(current, future))
    assert encode_snapshot(world) == before
    assert world.pending_packets() == pending
    assert world.state.library == library
    assert not (store.run_directory / "rules").exists()

    result = record_boundary(world, journal, store, rule_additions=(current,))
    added = result.events[0]
    assert added.type == "rule_added"
    assert added.tick == opening_tick + 1
    assert added.payload["provenance"]["approved_at_tick"] == opening_tick


def test_replay_refuses_a_recorded_rule_approved_after_the_opening_tick(pack, setup, tmp_path):
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RecordedBoundary, record_boundary, replay
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import encode_event_line
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path)
    record_boundary(world, journal, store)
    before = encode_snapshot(world)
    rule = proposed("current_rule", "every:100", subject={"archetype": "arch_b"})
    rule["provenance"]["approved_at_tick"] = world.tick
    result = record_boundary(world, journal, store, rule_additions=(rule,))
    added = result.events[0]
    manifest = RunManifest.capture(world.run_id, pack)
    original = RecordedBoundary((), b"".join(map(encode_event_line, result.events)))
    (frame,) = replay(before, manifest, pack, journal, store, (original,))
    assert frame.snapshot == encode_snapshot(world)

    rule_file = store.run_directory / "rules" / f"{added.payload['content_hash']}.json"
    changed = json.loads(rule_file.read_bytes())
    changed["provenance"]["approved_at_tick"] = added.tick
    rule_file.write_bytes(canonical_json_bytes(changed))
    new_event = added.model_copy(
        update={"payload": {**added.payload, "provenance": changed["provenance"]}},
    )
    recorded = RecordedBoundary(
        (),
        b"".join(map(encode_event_line, (new_event, *result.events[1:]))),
    )
    with pytest.raises(ValueError, match="approved after the opening boundary"):
        list(replay(before, manifest, pack, journal, store, (recorded,)))


def test_manifest_capture_uses_the_actual_loaded_ancestry(pack, setup, tmp_path):
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot, restore_snapshot
    from living_island.world.v2.rules import ContentError, load_pack

    world = initialize(pack, setup)
    wrong_setup = setup.model_copy(update={"pack_ids": ("wrong_parent", pack.pack_id)})
    with pytest.raises(ValueError, match="active composition"):
        initialize(pack, wrong_setup)
    original = RunManifest.capture(world.run_id, pack)
    original.check_content(pack)
    parent = tmp_path / "engine-test" / "pack.toml"
    leaf = tmp_path / "engine_core" / "pack.toml"
    text = parent.read_text(encoding="utf-8")
    assert "inventory_slots = 6" in text
    parent.write_text(text.replace("inventory_slots = 6", "inventory_slots = 7"), encoding="utf-8")
    reloaded = load_pack(leaf.parent, pack.vocabulary)
    assert reloaded.data["inventory_slots"] == 7
    assert reloaded.pack_hash != pack.pack_hash
    assert RunManifest.capture(world.run_id, reloaded).packs[0] != original.packs[0]
    assert RunManifest.capture(world.run_id, pack) == original
    with pytest.raises(ValueError, match="loaded content differs"):
        original.check_content(reloaded)

    # An ancestor can fail standalone validation and still participate in an
    # admissible composition. The authorized overlay restores the original leaf.
    assert "max_gain_per_tick = 4" in text
    parent.write_text(
        text.replace("max_gain_per_tick = 4", "max_gain_per_tick = 0"), encoding="utf-8"
    )
    leaf.write_text(
        leaf.read_text(encoding="utf-8")
        + """
[needs.stamina]
replace = true
min = 0
max = 10000
initial = 6000
band_cutoffs = [2000, 4000, 6000, 8000]
max_gain_per_tick = 4
max_loss_per_tick = 4
""",
        encoding="utf-8",
    )
    with pytest.raises(ContentError, match="NEED_RATE"):
        load_pack(parent.parent, pack.vocabulary)
    repaired = load_pack(leaf.parent, pack.vocabulary)
    assert repaired.pack_hash == pack.pack_hash
    repaired_manifest = RunManifest.capture(world.run_id, repaired)
    repaired_manifest.check_content(repaired)
    assert repaired_manifest.pack_ids == original.pack_ids
    assert repaired_manifest.packs[0] != original.packs[0]
    assert repaired_manifest.packs[-1] == original.packs[-1]
    with pytest.raises(ValueError, match="loaded content differs"):
        original.check_content(repaired)
    with pytest.raises(ValueError, match="pack identity"):
        restore_snapshot(encode_snapshot(world), repaired)


def test_pending_packet_accessor_cannot_mutate_world(pack, setup, tmp_path):
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import canonical_bytes

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path)
    original = tuple(map(canonical_bytes, world.pending_packets()))
    pending_ids = {packet.actor_id: packet.delivery_id for packet in world.pending_packets()}
    before = encode_snapshot(world)
    packet = world.pending_packets()[0]
    assert packet.perception.visible_tiles
    packet.perception.visible_tiles.clear()
    assert encode_snapshot(world) == before
    assert journal.ingest(world) == pending_ids
    assert tuple(map(canonical_bytes, journal.read(0))) == original
    record_boundary(world, journal, store)
    assert world.tick == 1
    assert all(packet.delivery_id not in pending_ids.values() for packet in world.pending_packets())


def test_initial_event_is_complete_when_appended(pack, setup, monkeypatch):
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.events import EventWriter
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import encode_event_line

    emit = EventWriter.emit
    initialized = []

    def capture(writer, kind, payload, **fields):
        event = emit(writer, kind, payload, **fields)
        if kind == "world_initialized":
            initialized.append(encode_event_line(writer.events[-1]))
        return event

    monkeypatch.setattr(EventWriter, "emit", capture)
    world = initialize(pack, setup)
    event = world.initial_events[0]
    assert initialized == [encode_event_line(event)]
    assert event.seq_in_tick == 0
    assert event.payload["initial_snapshot_hash"] == sha256(encode_snapshot(world)).hexdigest()
    sequences = range(len(world.initial_events))
    assert [e.seq_in_tick for e in world.initial_events] == list(sequences)
    assert [e.event_id for e in world.initial_events] == [
        f"{world.run_id}:0000000000:{seq:06d}" for seq in sequences
    ]
    assert world.state.next_event_seq_in_tick == world.state.event_log_cursor == len(sequences)


def test_replay_refuses_changed_journal_at_input_boundary(pack, setup, tmp_path):
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RecordedBoundary, record_boundary, replay
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import encode_event_line
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    initial = encode_snapshot(world)
    initial_rng = world.state.resolution_rng_state_uint32
    journal, store = store_for(world, tmp_path)
    manifest = RunManifest.capture(world.run_id, pack)
    turns = tuple(typed_turn(world, actor, "wait") for actor in (A, B))
    result = record_boundary(world, journal, store, turns)
    assert len(result.actions) == 2
    assert world.state.resolution_rng_state_uint32 != initial_rng
    rows = (RecordedBoundary(turns, b"".join(map(encode_event_line, result.events))),)
    (frame,) = replay(initial, manifest, pack, journal, store, rows)
    assert frame.snapshot == encode_snapshot(world)
    assert frame.event_lines == rows[0].event_lines

    with pytest.raises(ValueError, match="snapshot belongs to a different run"):
        list(replay(initial, RunManifest.capture("wrong_run", pack), pack, journal, store, rows))

    path = journal.directory / "0.json"
    payload = json.loads(path.read_bytes())
    assert payload["packets"][0]["perception"]["visible_tiles"]
    payload["packets"][0]["perception"]["visible_tiles"].clear()
    path.write_bytes(canonical_json_bytes(payload))
    assert journal.read(0)[0].perception.visible_tiles == []
    with pytest.raises(ValueError, match="packet journal differs at boundary 0"):
        list(replay(initial, manifest, pack, journal, store, rows))


def test_dependent_additions_keep_admission_order_in_restore_and_replay(make_world, pack, tmp_path):
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RecordedBoundary, record_boundary, replay
    from living_island.world.v2.engine.snapshot import encode_snapshot, restore_snapshot
    from living_island.world.v2.protocol import encode_event_line

    world = make_world([(A, 3, 1), (B, 2, 1)], settings='disable = ["rule_e", "rule_g"]')
    leaf = world.pack.source
    initial = encode_snapshot(world)
    manifest = RunManifest.capture(world.run_id, leaf)
    journal, store = store_for(world, tmp_path / "run")
    process = proposed(
        "z_process",
        "when:check_a",
        **{
            k: v
            for k, v in pack.rules["rule_g"].data.items()
            if k not in {"id", "trigger", "provenance", "instruments"}
        },
    )
    builder = proposed(
        "a_builder",
        "verb:build",
        **{
            k: v
            for k, v in pack.rules["rule_e"].data.items()
            if k not in {"id", "trigger", "provenance"}
        },
    )
    with pytest.raises(ValueError, match="no process rule"):
        record_boundary(world, journal, store, rule_additions=(builder, process))
    assert encode_snapshot(world) == initial
    assert not (store.run_directory / "rules").exists()
    result = record_boundary(world, journal, store, rule_additions=(process, builder))
    added = tuple(event for event in result.events if event.type == "rule_added")
    assert [event.payload["rule_id"] for event in added] == ["z_process", "a_builder"]
    saved = encode_snapshot(world)
    restored = restore_snapshot(saved, leaf)
    assert restored.state == world.state
    assert encode_snapshot(restored) == saved
    rows = (RecordedBoundary((), b"".join(map(encode_event_line, result.events))),)
    (frame,) = replay(initial, manifest, leaf, journal, store, rows)
    assert frame.snapshot == saved
    assert frame.event_lines == rows[0].event_lines
    reversed_rows = (RecordedBoundary((), b"".join(map(encode_event_line, reversed(added)))),)
    with pytest.raises(ValueError, match="no process rule"):
        list(replay(initial, manifest, leaf, journal, store, reversed_rows))


@pytest.mark.parametrize("published", [False, True])
def test_store_once_propagates_failure_without_a_winning_file(tmp_path, monkeypatch, published):
    from living_island.persistence.v2 import journal

    path = tmp_path / "packet.json"
    data = b"{}"
    problem = journal.PersistenceError(path, "file", "publisher failed")

    def competing_write(path, data):
        if published:
            path.write_bytes(data)
        raise problem

    monkeypatch.setattr(journal, "atomic_create", competing_write)
    if published:
        journal.store_once(path, data)
        assert path.read_bytes() == data
    else:
        with pytest.raises(journal.PersistenceError) as raised:
            journal.store_once(path, data)
        assert raised.value is problem
        assert not path.exists()


@pytest.fixture(params=["snapshot", "checkpoint"])
def restore_through(request, tmp_path):
    """Read altered world bytes directly or inside a genuine checkpoint."""
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.world.v2.engine.snapshot import restore_snapshot
    from living_island.world.v2.rules.schema import canonical_json_bytes

    def reader_for(world, pack, journal):
        if request.param == "snapshot":
            return lambda data: restore_snapshot(data, pack)

        path = tmp_path / "restore_check.json"
        coordinator = {"cursor": {"last_delivered": [world.tick - 1]}}
        save_checkpoint(path, world, journal, coordinator)
        checkpoint = json.loads(path.read_bytes())

        def read_checkpoint(data):
            checkpoint["world_snapshot"] = data.decode("utf-8")
            path.write_bytes(canonical_json_bytes(checkpoint))
            restored = load_checkpoint(path, pack, journal)
            assert restored.sim_checkpoint == coordinator
            return restored.world

        return read_checkpoint

    return reader_for


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("delivery_id", "packet identity"),
        ("perception_actor", "packet identity"),
        ("perception_tick", "packet identity"),
        ("envelope_tick", "packet identity"),
        ("map_key", "one pending packet per living resident"),
        ("missing", "one pending packet per living resident"),
        ("key_actor", "packet actor differs from its map key"),
        ("dead_recipient", "one pending packet per living resident"),
    ],
)
def test_restore_refuses_inconsistent_pending_packet(
    pack, setup, tmp_path, restore_through, corruption, message
):
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import boundary_delivery_id, canonical_bytes
    from living_island.world.v2.rules.schema import canonical_json_bytes

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path)
    record_boundary(world, journal, store)
    original = encode_snapshot(world)
    read = restore_through(world, pack, journal)
    control = read(original)
    assert encode_snapshot(control) == original
    assert tuple(map(canonical_bytes, control.pending_packets())) == tuple(
        map(canonical_bytes, world.pending_packets())
    )

    state = json.loads(original)
    pending = state["pending_deliveries"]
    packet = pending[A]
    match corruption:
        case "delivery_id":
            packet["delivery_id"] = boundary_delivery_id("foreign_run", world.tick, A)
        case "perception_actor":
            packet["perception"]["actor_id"] = B
        case "perception_tick":
            packet["perception"]["tick"] += 1
        case "envelope_tick":
            packet["observed_tick"] += 1
        case "map_key":
            pending["wrong_recipient"] = pending.pop(A)
        case "missing":
            del pending[A]
        case "key_actor":
            pending[A] = pending[B]
        case "dead_recipient":
            state["residents"][A]["alive"] = False
    with pytest.raises(ValueError, match=message):
        read(canonical_json_bytes(state))


@pytest.mark.parametrize("approval", [1, 8])
def test_restore_refuses_impossible_active_approval(
    pack, setup, tmp_path, restore_through, approval
):
    from living_island.persistence.v2.replay import record_boundary
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.rules.loader import library_hash
    from living_island.world.v2.rules.schema import canonical_json_bytes, content_hash

    world = initialize(pack, setup)
    journal, store = store_for(world, tmp_path)
    rule = proposed("candidate", "every:100", subject={"archetype": "arch_b"})
    record_boundary(world, journal, store, rule_additions=(rule,))
    assert world.tick == 1
    original = encode_snapshot(world)
    read = restore_through(world, pack, journal)
    assert encode_snapshot(read(original)) == original

    state = json.loads(original)
    library = state["library"]
    [[rule_id, added]] = library["added_rules"]
    rules = {**{name: item.data for name, item in pack.rules.items()}, rule_id: added["data"]}
    assert library_hash(rules) == library["rule_library_hash"]
    added["data"]["provenance"]["approved_at_tick"] = approval
    assert (
        content_hash({key: value for key, value in added["data"].items() if key != "provenance"})
        == added["content_hash"]
    )
    library["rule_library_hash"] = library_hash(rules)
    with pytest.raises(ValueError, match="approved after the opening boundary"):
        read(canonical_json_bytes(state))
