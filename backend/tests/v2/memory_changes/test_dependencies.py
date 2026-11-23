"""Ordered failure diagnostics, revision bindings and transactional rollback."""

import json
from dataclasses import replace


def rid(number):
    return f"m:b:{number}"


def infer(*ids, call_id="call"):
    return {"kind": "inferred", "memory_ids": list(ids), "call_id": call_id}


TOLD = {"kind": "told", "utterance_id": "u1", "speaker_id": "a"}
SEEN = {"kind": "observed", "entry_id": "spring"}


def add(n, *sources, confidence=3):
    return {
        "op": "add",
        "ref": f"new:{n}",
        "record": {
            "kind": "belief",
            "content": {
                "subject": {"kind": "place", "ref": "38,30"},
                "topics": [],
                "stance": "stable",
            },
            "gist": "Water at the spring",
            "sources": list(sources),
            "confidence": confidence,
        },
    }


def stage(store, ops, reasons, *, full=(), index=()):
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.provenance import HeardSpeechEntry, PerceptionEntry, SentInput
    from living_island.memory.v2.validation import decode_change_set

    base = store.snapshot
    sent = SentInput(
        "b",
        "call",
        tuple(base.ref(rid(n)) for n in full),
        tuple(base.ref(rid(n)) for n in index),
        (
            HeardSpeechEntry("b", "heard", "p", ("heard_utterances[0]",), "u1", "a"),
            PerceptionEntry(
                "b", "spring", "p", ("tiles[0]",), "observation", frozenset({"place:38,30"})
            ),
            PerceptionEntry(
                "b",
                "own",
                "p",
                ("last_utterance_feedback",),
                "utterance_result",
                frozenset({"spoke:u2"}),
            ),
        ),
    )
    change = decode_change_set(
        json.dumps({"ops": [{"op_id": str(i), **op} for i, op in enumerate(ops)]}), base.version
    )
    staged = stage_change_set(store, change, sent, tick=10)
    assert [(v.result, v.reason) for v in staged.verdicts] == [
        ("committed" if reason is None else "dropped", reason) for reason in reasons
    ]
    assert store.snapshot is base
    return staged


def seeded(*, live=200):
    from living_island.memory.v2.kinds import KindRegistry
    from living_island.memory.v2.store import MemoryStore

    class FixtureRegistry(KindRegistry):
        def __getitem__(self, kind):
            policy = super().__getitem__(kind)
            return replace(policy, live_capacity=live) if kind == "belief" else policy

    store = MemoryStore("b", FixtureRegistry())
    ops = [add(1, TOLD, confidence=0), add(2, SEEN, confidence=1), add(3, infer("new:1"))]
    stage(store, ops, [None, None, None]).commit(store)
    return store


def test_mf07_first_failures_and_independent_commits():
    store = seeded(live=3)
    before = {r.id: r for r in store.snapshot.records()}
    bad_speaker = {**TOLD, "speaker_id": "b"}
    forbidden = add(1, TOLD, confidence=4)
    forbidden["record"]["kind"] = "commitment"
    guess = add(1, SEEN)
    guess["record"]["content"]["stance"] = "guess"
    for invalid, reason in (
        ({"op": "invent"}, "format"),
        (forbidden, "format"),  # The speech cap precedes kind authority.
        (guess, "format"),
        (
            {"op": "update", "id": rid(1), "gist": "A guess", "content": {"stance": "guess"}},
            "format",
        ),
        ({"op": "update", "id": rid(99), "gist": 2, "owner_id": "b"}, "format"),
        ({"op": "update", "id": rid(99), "gist": "Edit", "owner_id": "b"}, "authority"),
        ({"op": "forget", "id": rid(99)}, "reference"),
        ({"op": "update", "id": rid(2), "gist": "Index is read only"}, "provenance"),
        ({"op": "forget", "id": rid(3)}, "provenance"),  # Guard omitted the actual record.
        (add(1, infer(rid(3))), "provenance"),
        (add(1, bad_speaker), "provenance"),
        (add(1, infer(rid(2), call_id="another-call")), "provenance"),
        (add(1, {"kind": "innate"}), "provenance"),
        ({"op": "update", "id": rid(1), "gist": "Replaced", "sources": [SEEN]}, "source_kind"),
    ):
        rejected = stage(store, [invalid], [reason], full=(1,), index=(2,))
        assert rejected.effects == ()

    # Every candidate is explicitly mutated later, so a fourth belief cannot make room.
    touches = [{"op": "confidence", "id": rid(n), "to": 1} for n in (1, 2, 3)]
    full = (1, 2, 3)
    stage(store, [add(1, TOLD), *touches], ["capacity", None, None, None], full=full)

    # The rejected producer's prospective victim is 1. A read of 1, use of its ref,
    # and the malformed write to 2 all retain their dependency diagnostics.
    ops = [
        add(1, bad_speaker),
        {"op": "update", "id": rid(2), "gist": "Depends", "add_sources": [infer("new:1")]},
        {"op": "confidence", "id": rid(2), "to": 9},
        {"op": "confidence", "id": rid(3), "to": 2},
        add(2, infer(rid(1))),
    ]
    result = stage(
        store,
        ops,
        ["provenance", "depends_on", "depends_on", None, "depends_on"],
        full=(2, 3),
        index=(1,),
    )
    assert [v.depends_on for v in result.verdicts] == [(), ("0",), ("0", "1"), (), ("0",)]
    assert result.evictions == ()
    assert [e.op_id for e in result.effects] == ["3"]
    receipt = result.commit(store)
    assert [change.id for change in receipt.write.changes] == [rid(3)]
    assert not receipt.relabel_flags
    after = {r.id: r for r in store.snapshot.records()}
    assert after.keys() == before.keys()
    assert after[rid(1)] == before[rid(1)] and after[rid(2)] == before[rid(2)]
    assert after[rid(3)].confidence == 2


def test_mf19_refs_dependency_precedence_and_implicit_writes():
    store = seeded()
    base = store.snapshot
    full = (1, 2, 3)

    def check(ops, reasons):
        return stage(store, ops, reasons, full=full)

    rejected = stage(
        store,
        [
            {"op": "supersede", "id": rid(1), "by": rid(2)},
            {"op": "review_done", "id": rid(3)},
        ],
        ["provenance", "depends_on"],
        full=(1, 3),
        index=(2,),
    )
    assert rejected.verdicts[1].depends_on == ("0",)
    assert rejected.effects == ()  # Includes both backlinks and the inferred record's review flag.
    store_after = rejected.commit(store)
    assert not store_after.write.changes and store.snapshot.records() == base.records()
    for op in (
        {"op": "supersede", "id": rid(1), "by": rid(1)},
        {**add(1, TOLD), "op": "merge", "ids": [rid(1), rid(1)]},
        {"op": "update", "id": rid(1), "gist": "Self-inference", "add_sources": [infer(rid(3))]},
        add(1, infer("new:20")),
        add(1, infer(rid(99))),
    ):
        check([op], ["reference"])
    check(
        [
            {"op": "supersede", "id": rid(1), "by": rid(2)},
            {"op": "supersede", "id": rid(2), "by": rid(1)},
        ],
        [None, "reference"],
    )
    check(
        [
            add(1, infer(rid(1))),
            {"op": "update", "id": rid(1), "gist": "Circular", "add_sources": [infer("new:1")]},
        ],
        [None, "reference"],
    )
    check(
        [
            add(1, infer("new:2")),
            add(2, SEEN),
            {"op": "commitment_status", "id": "new:2", "status": "kept", "note": "Guess"},
        ],
        ["reference", None, "authority"],
    )
    check(
        [add(1, SEEN), add(2, infer("new:1", rid(4)))],
        [None, "provenance"],  # An authorized alias cannot authorize a guessed physical ID.
    )
    check(
        [{"op": "forget", "id": rid(1)}, {"op": "confidence", "id": rid(1), "to": 3}],
        [None, "reference"],
    )
    check(
        [{"op": "confidence", "op_id": "dup", "id": rid(n), "to": 1} for n in (1, 2)],
        ["format", "format"],
    )
    duplicates = check(
        [
            add(1, SEEN),
            {**add(1, SEEN), "op": "merge", "ids": [rid(1), rid(2)]},
            {"op": "supersede", "id": "new:1", "by": "undefined"},
        ],
        ["format", "format", "depends_on"],
    )
    assert duplicates.verdicts[-1].depends_on == ("0", "1")
    check(
        [
            {
                "op": "update",
                "id": rid(1),
                "gist": "I said so",
                "add_sources": [{"kind": "observed", "entry_id": "own"}],
            }
        ],
        ["source_kind"],
    )

    # A pre-existing ID cites its sent revision; a producer ref cites the staged revision.
    pinned = stage(
        store,
        [
            {"op": "update", "id": rid(1), "gist": "Updated after dispatch"},
            add(1, infer(rid(1), rid(2))),
            {"op": "update", "id": "new:1", "gist": "Updated producer"},
            add(2, infer("new:1")),
        ],
        [None] * 4,
        full=(1,),
        index=(2,),
    )
    assert pinned.effects[1].bindings[0].revisions == (
        store.snapshot.ref(rid(1)),
        store.snapshot.ref(rid(2)),
    )
    (staged_ref,) = pinned.effects[3].bindings[0].revisions
    assert staged_ref.id == rid(4) and staged_ref.store_version == store.snapshot.version + 1
    assert staged_ref.content_hash == pinned.effects[2].edits[0].content_hash()
    assert staged_ref.content_hash != pinned.effects[1].edits[0].content_hash()

    capped = seeded(live=3)
    bypass = stage(
        capped,
        [add(1, SEEN), {"op": "confidence", "id": rid(1), "to": 8}],
        [None, "format"],
        full=(1,),
    )
    assert bypass.evictions == (rid(2),)
    bypass.commit(capped)
    assert {r.id for r in capped.snapshot.records()} == {rid(1), rid(3), rid(4)}

    # An unresolved operand cannot select a speculative victim or poison a later inference.
    capped = seeded(live=3)
    unresolved = stage(
        capped,
        [add(1, SEEN, infer("new:99")), add(2, infer(rid(1)))],
        ["reference", None],
        index=(1,),
    )
    assert unresolved.evictions == (rid(1),)
