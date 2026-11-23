"""Lifecycle, immutable revision receipts and subjective beliefs."""

import json
from unittest.mock import Mock


def _seen(entry_id):
    return {"kind": "observed", "entry_id": entry_id}


def _belief(gist, sources):
    return {
        "kind": "belief",
        "gist": gist,
        "content": {"subject": {"kind": "place", "ref": "3,8"}, "stance": "stable", "topics": []},
        "sources": sources,
        "confidence": 2,
    }


def _add(number, gist, sources):
    return {"op": "add", "ref": f"new:{number}", "record": _belief(gist, sources)}


def _commit(store, ops, *, full=(), seen=(), speech=()):
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.provenance import HeardSpeechEntry, PerceptionEntry, SentInput
    from living_island.memory.v2.validation import decode_change_set

    base = store.snapshot
    sightings = tuple(
        PerceptionEntry(
            "ella", key, f"packet-{key}", ("tiles[0]",), "observation", frozenset({"place:3,8"})
        )
        for key in seen
    )
    utterances = tuple(
        HeardSpeechEntry(
            "ella", f"entry-{key}", f"packet-{key}", ("heard_utterances[0]",), key, "mia"
        )
        for key in speech
    )
    sent = SentInput(
        "ella",
        f"call-{base.version}",
        tuple(base.ref(key) for key in full),
        entries=(*sightings, *utterances),
    )
    change_set = decode_change_set(
        json.dumps({"ops": [{"op_id": str(n), **op} for n, op in enumerate(ops)]}), base.version
    )
    staged = stage_change_set(store, change_set, sent, tick=base.version + 1)
    assert [v.reason for v in staged.verdicts] == [None] * len(ops)
    assert [v.op_id for v in staged.verdicts] == [str(n) for n in range(len(ops))]
    assert store.snapshot is base
    return staged, staged.commit(store).write


def test_mm08_supersession_preserves_history_and_marks_the_inference():
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    original, dependent, independent, successor = (f"m:ella:{n}" for n in range(1, 5))
    inferred = {"kind": "inferred", "call_id": "call-0", "memory_ids": ["new:1"]}
    staged, creation = _commit(
        store,
        [
            _add(1, "The spring seems dry", [_seen("morning")]),
            _add(2, "I should carry water", [inferred]),
            _add(3, "There is moss on the bank", [_seen("morning")]),
            _add(4, "Water flows from the bank", [_seen("afternoon")]),
        ],
        seen=("morning", "afternoon"),
    )
    prior = store.snapshot
    (citation,) = staged.effects[1].bindings[0].revisions
    assert citation == prior.ref(original)
    assert creation.blobs[citation.content_hash].gist == "The spring seems dry"

    _, write = _commit(
        store, [{"op": "supersede", "id": original, "by": successor}], full=(original, successor)
    )
    assert (write.before_version, write.after_version) == (prior.version, prior.version + 1)
    assert {c.id for c in write.changes} == {original, dependent, successor}
    view = store.snapshot.resident(memory_on=True)
    (history,) = view.history()
    assert history.ref.id == original and history.record.superseded_by == successor
    assert (
        history.record.gist == "The spring seems dry" and " | superseded | " in history.index_line
    )
    assert history.ref.content_hash != citation.content_hash
    live = {entry.ref.id: entry.record for entry in view.live()}
    assert live[successor].supersedes == original
    assert live[dependent].needs_review and not live[independent].needs_review
    assert live[dependent].sources[0].memory_ids == [original]


def test_mm09_merge_unions_sources_and_forget_removes_resident_access():
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    first, second, independent, merged = (f"m:ella:{n}" for n in range(1, 5))
    told = {"kind": "told", "speaker_id": "mia", "utterance_id": "u1"}
    _commit(
        store,
        [
            _add(1, "We found a spring", [_seen("morning"), told]),
            _add(2, "It was still flowing", [_seen("morning"), _seen("afternoon")]),
            _add(3, "The approach is steep", [_seen("morning")]),
        ],
        seen=("morning", "afternoon"),
        speech=("u1",),
    )
    member_refs = tuple(store.snapshot.ref(key) for key in (first, second))
    staged, merge_write = _commit(
        store,
        [
            {
                "op": "merge",
                "ids": [first, second],
                "ref": "new:1",
                "record": _belief("The spring flows throughout the day", [_seen("evening")]),
            }
        ],
        full=(first, second),
        seen=("evening",),
    )
    assert staged.effects[0].carried_from == member_refs
    (added,) = staged.effects[0].bindings
    assert (added.entry_id, added.delivery_id, added.member_paths) == (
        "evening",
        "packet-evening",
        ("tiles[0]",),
    )
    prior = store.snapshot
    record = prior.read(prior.ref(merged))
    assert [source.model_dump() for source in record.sources] == [
        _seen("afternoon"),
        _seen("evening"),
        _seen("morning"),
        told,
    ]
    assert record.speech_derived
    assert {r.ref.id for r in prior.resident(memory_on=True).history()} == {first, second}
    for key in (first, second):
        assert prior.read(prior.ref(key)).superseded_by == merged

    forgotten = (merged, first, second)
    _, forget_write = _commit(
        store, [{"op": "forget", "id": key} for key in forgotten], full=forgotten
    )
    assert tuple(change.id for change in forget_write.changes) == forgotten
    for change in forget_write.changes:
        assert change.after is None
        assert change.before.content_hash == prior.ref(change.id).content_hash
        assert merge_write.blobs[change.before.content_hash] == prior.read(prior.ref(change.id))
    view = store.snapshot.resident(memory_on=True)
    assert [item.ref.id for item in view.records] == [independent]
    assert view.live() == view.records and view.history() == () and view.current_intention is None
    assert view.index() == (view.records[0].index_line,)
    assert all(key not in view.index()[0] for key in forgotten)


def test_mf09_well_sourced_false_belief_survives_with_world_reader_disabled():
    from living_island.memory.v2.store import MemoryStore

    # A delivered sighting witnesses the place. The fixture's simulator knows the water is clean.
    world = {"3,8": {"poisoned": False}}
    world_reader = Mock(side_effect=AssertionError("consolidation consulted objective state"))
    store = MemoryStore("ella")
    store.read_world_state = world_reader
    false_claim = "The spring is poisoned"
    staged, write = _commit(store, [_add(1, false_claim, [_seen("spring")])], seen=("spring",))
    world_reader.assert_not_called()
    (entry,) = store.snapshot.resident(memory_on=True).live()
    assert not world[entry.record.content.subject.ref]["poisoned"]
    assert entry.record.gist == false_claim and entry.record.confidence == 2
    assert write.blobs[entry.ref.content_hash].gist == false_claim
    (witness,) = staged.effects[0].bindings
    assert (witness.entry_id, witness.delivery_id, witness.member_paths) == (
        "spring",
        "packet-spring",
        ("tiles[0]",),
    )
