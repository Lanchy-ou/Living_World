"""Source, witness and persistent speech-ancestry examples from MM §11 and MF §9."""

import json

import pytest

SPRING = {"kind": "place", "ref": "38,30"}
CORD = {"kind": "entity", "ref": "cord"}
HEARD = {"kind": "told", "utterance_id": "u1", "speaker_id": "a"}
SEEN = {"kind": "observed", "entry_id": "spring"}
SNAPS = {"kind": "observed", "entry_id": "snap"}


def deliveries():
    from living_island.memory.v2.provenance import HeardSpeechEntry, PerceptionEntry

    def perception(name, kind, path, *keys, owner="b"):
        return PerceptionEntry(owner, name, "packet", (path,), kind, frozenset(keys))

    return (
        HeardSpeechEntry("b", "heard", "packet", ("heard_utterances[0]",), "u1", "a"),
        perception("spring", "observation", "tiles[0]", "place:38,30"),
        perception(
            "snap", "action_result", "action_feedback[0]", "entity:cord", "phenomenon:snaps"
        ),
        perception("hunger", "body_change", "body_reports[0]", "need:satiety"),
        perception("repeated", "utterance_result", "last_utterance_feedback", "spoke:u2"),
        perception("other-spring", "observation", "tiles[0]", "place:38,30", owner="a"),
    )


def add(n, sources, confidence, subject=SPRING, gist="The spring is poisoned", **fields):
    return {
        "op": "add",
        "ref": f"new:{n}",
        "record": {
            "kind": "belief",
            "gist": gist,
            "content": {"subject": subject, "topics": [], "stance": "stable"},
            "sources": sources,
            "confidence": confidence,
            **fields,
        },
    }


def inference(*ids):
    return {"kind": "inferred", "call_id": "call", "memory_ids": list(ids)}


def run(store, ops, reasons, *, use_index=(), entries=None):
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.provenance import SentInput
    from living_island.memory.v2.validation import decode_change_set

    base = store.snapshot
    refs = tuple(item.ref for item in base.resident(memory_on=True).records)
    sent = SentInput(
        base.owner_id,
        "call",
        tuple(ref for ref in refs if ref.id not in use_index),
        tuple(ref for ref in refs if ref.id in use_index),
        deliveries() if entries is None else entries,
    )
    wire = {"ops": [{"op_id": str(i), **op} for i, op in enumerate(ops)]}
    staged = stage_change_set(store, decode_change_set(json.dumps(wire), base.version), sent, 10)
    assert [v.reason for v in staged.verdicts] == reasons
    return staged, staged.commit(store)


def read(store, key):
    return store.snapshot.read(store.snapshot.ref(key))


def test_sent_perception_type_excludes_speech_and_model_outputs():
    from pydantic import ValidationError

    from living_island.memory.v2.provenance import PerceptionEntry

    for kind in ("heard_speech", "own_response", "recall"):
        with pytest.raises(ValidationError, match="literal_error"):
            PerceptionEntry("b", "e", "p", ("member",), kind, frozenset({"place:38,30"}))


def test_delivered_source_requires_a_member_path():
    from pydantic import ValidationError

    from living_island.memory.v2.provenance import HeardSpeechEntry

    with pytest.raises(ValidationError, match="too_short"):
        HeardSpeechEntry("b", "e", "packet", (), "u1", "a")


def test_mm06_confidence_defaults_caps_and_relabel_inspection():
    from living_island.memory.v2.provenance import BoundRevision, SentInput, bind_sources
    from living_island.memory.v2.records import Inferred, Innate, Observed, Told
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("b")
    _, committed = run(
        store,
        [
            add(1, [HEARD], 2),
            add(2, [SEEN], 4),
            add(3, [SNAPS], 4, CORD, "The cord snapped"),
            add(4, [HEARD, SEEN], 4),
            add(5, [SEEN], 3, speech_derived=False),
            add(6, [HEARD], 1),
        ],
        [None, None, None, "format", "format", None],
    )
    told, observed, cord, other_told = store.snapshot.records()
    assert not observed.speech_derived and not cord.speech_derived
    assert told.speech_derived and other_told.speech_derived
    (flag,) = committed.relabel_flags
    assert flag.flagged == store.snapshot.ref(observed.id)
    assert flag.overlaps == tuple(store.snapshot.ref(key) for key in (told.id, other_told.id))
    assert flag.shared_keys == ("place:38,30",)
    assert (flag.store_version, flag.change_set_call_id) == (store.snapshot.version, "call")
    for projected in store.snapshot.resident(memory_on=True).records:
        assert "speech_derived" not in projected.record.model_dump()
        assert "possible_relabel" not in projected.index_line
        assert "relabel" not in projected.record.model_dump_json()

    sent = SentInput("b", "call", entries=deliveries())
    bound = {r.id: BoundRevision(store.snapshot.ref(r.id), r) for r in (told, observed)}
    seen = Observed(entry_id="spring")
    heard = Told(utterance_id="u1", speaker_id="a")
    conclusion = Inferred(memory_ids=[observed.id, told.id], call_id="call")
    for trust, expected in enumerate((0, 1, 1, 2, 3)):
        evidence = bind_sources([heard], told.content, sent, bound, {"a": trust})
        assert evidence.default_confidence == expected
        assert not evidence.provenance_error
        assert evidence.bindings[0].member_paths == ("heard_utterances[0]",)
    for sources, expected in (([seen], 3), ([conclusion], 2), ([seen, heard], 3), ([Innate()], 4)):
        assert bind_sources(sources, told.content, sent, bound, {}).default_confidence == expected

    run(
        store,
        [
            {"op": "confidence", "id": told.id, "to": 4},
            {"op": "update", "id": cord.id, "gist": cord.gist, "add_sources": [HEARD]},
        ],
        ["format", "format"],
    )
    assert read(store, cord.id) == cord
    run(
        store,
        [
            {"op": "confidence", "id": cord.id, "to": 3},
            {"op": "update", "id": cord.id, "gist": cord.gist, "add_sources": [HEARD]},
        ],
        [None, None],
    )
    assert read(store, cord.id).speech_derived


def test_mm07_told_source_cannot_be_relabelled():
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("b")
    run(store, [add(1, [HEARD], 2)], [None])
    (original,) = store.snapshot.records()
    for fields, reason in (
        ({"sources": [SEEN]}, "source_kind"),
        ({"add_sources": [{"kind": "observed", "entry_id": "heard"}]}, "provenance"),
    ):
        run(store, [{"op": "update", "id": original.id, "gist": "New gist", **fields}], [reason])
        assert read(store, original.id) == original


def test_mf24_observation_witnesses_the_residents_subject():
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("b")
    unrelated = {"kind": "observed", "entry_id": "hunger"}
    foreign = {"kind": "observed", "entry_id": "other-spring"}
    own_words = {"kind": "observed", "entry_id": "repeated"}
    _, committed = run(
        store,
        [
            add(1, [HEARD, unrelated], 3),
            add(2, [HEARD], 3),
            add(3, [HEARD, SEEN], 3),
            add(4, [HEARD, SEEN], 4),
            add(5, [HEARD, foreign], 3),
            add(6, [HEARD, own_words], 3),
            add(7, [SEEN], 3, {"kind": "general", "ref": None}),
            add(8, [SNAPS], 4, CORD, "The cord snapped"),
        ],
        ["provenance", None, None, "format", "provenance", "source_kind", "provenance", None],
    )
    assert not committed.relabel_flags
    told, seen_and_told, snapped = store.snapshot.records()
    assert told.speech_derived and seen_and_told.speech_derived
    assert not snapped.speech_derived
    assert [s.kind for s in seen_and_told.sources] == ["observed", "told"]


def test_mm25_inferred_and_merged_ancestry_survives_eviction_and_restore():
    from living_island.memory.v2.store import MemoryStore

    for root_source, speech_derived in ((HEARD, True), (SEEN, False)):
        store = MemoryStore("b")
        run(store, [add(1, [root_source], 3), add(2, [SEEN], 3)], [None, None])
        root, witness = store.snapshot.records()
        run(store, [add(1, [inference(root.id)], 3)], [None], use_index=(root.id,))
        inferred = read(store, "m:b:3")
        merge = {**add(1, [], 3), "op": "merge", "ids": [root.id, witness.id]}
        run(store, [merge], [None])
        merged = read(store, "m:b:4")
        assert inferred.speech_derived == merged.speech_derived == speech_derived
        # Fill the remaining history slots with records from an earlier fixture merge.
        # Superseding its survivor then evicts the oldest unprotected revision.
        base = store.snapshot
        room = store.registry["belief"].history_capacity - 2
        survivor, successor = base.next_id(room), base.next_id(room + 1)
        history = [
            witness.model_copy(update={"id": base.next_id(n), "superseded_by": survivor})
            for n in range(room)
        ]
        store.apply(
            base.version,
            "change_set",
            [
                *history,
                witness.model_copy(update={"id": survivor}),
                witness.model_copy(update={"id": successor}),
            ],
        )
        staged, _ = run(store, [{"op": "supersede", "id": survivor, "by": successor}], [None])
        assert staged.evictions == (root.id,)
        run(
            store,
            [
                add(1, [SEEN, inference(inferred.id)], 4),
                add(2, [SEEN, inference(merged.id)], 4),
            ],
            ["format" if speech_derived else None] * 2,
        )
        saved = store.snapshot
        # The retained snapshot contains no root. The restored writer has no audit input.
        assert root.id not in {r.id for r in saved.records()}
        store = MemoryStore.from_snapshot(saved)
        for ancestor in (inferred, merged):
            refs = [SEEN, inference(ancestor.id)]
            run(
                store,
                [add(1, refs, 4), add(2, refs, 3)],
                ["format" if speech_derived else None, None],
            )
        run(
            store,
            [{"op": "update", "id": inferred.id, "gist": "Also seen", "add_sources": [SEEN]}],
            [None],
        )
        assert read(store, inferred.id).speech_derived == speech_derived
        run(
            store,
            [add(1, [SEEN, inference(inferred.id)], 4)],
            ["format" if speech_derived else None],
        )
