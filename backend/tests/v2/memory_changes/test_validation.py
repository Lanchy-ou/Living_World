"""MF §3.3 authority and the model response boundary, exercised on an isolated store."""

import json

import pytest

TOLD = {"kind": "told", "speaker_id": "mia", "utterance_id": "s1"}
CONTENTS = {
    "episodic": {"participants": ["mia"], "place": None},
    "belief": {"subject": {"kind": "resident", "ref": "mia"}, "stance": "stable", "topics": []},
    "skill": {
        "hypothesis": {
            "verb": "weave",
            "target": None,
            "instruments": [],
            "inputs": [],
            "circumstances": None,
            "expected": ["twists"],
        },
        "status": "active",
    },
    "social": {
        "about": "mia",
        "facts": {
            "given": [],
            "received": [],
            "agreements": [],
            "last_seen_tick": 1,
            "last_heard_tick": 1,
        },
        "trust": 2,
        "impression": "",
    },
    "commitment": {
        "agreement_id": "agreement",
        "role": "promisee",
        "counterpart_id": "mia",
        "terms": {
            "promisor_id": "mia",
            "promisee_id": "ella",
            "what": {"kind": "give_item", "item": {"quantity": 1, "archetype_id": "fruit"}},
            "due_tick": 300,
        },
        "due_tick": 300,
        "heard_counterpart": False,
        "status": "open",
        "status_note": None,
    },
    "intention": {"set_turn": "t1", "state": "current", "ended_turn": None},
}


def _new(kind, **edits):
    return {
        "kind": kind,
        "gist": "Remember this",
        "confidence": 1,
        "sources": [TOLD],
        "content": CONTENTS.get(kind, {}),
        **({"about_tick": {"from": 1, "to": 1}} if kind == "episodic" else {}),
        **edits,
    }


def _store():
    from living_island.memory.v2.profiles import TraitValues
    from living_island.memory.v2.store import MemoryStore

    traits = TraitValues(curiosity=4, caution=1, sociability=2, trustfulness=2, diligence=2)
    store = MemoryStore("ella")
    ids = {}
    bodies = []
    for kind in (*CONTENTS, "personality"):
        ids[kind] = []
        for _ in range(2 if kind in ("belief", "episodic", "skill") else 1):
            rid = store.snapshot.next_id(len(bodies))
            proposed = _new(kind)
            if kind == "skill":
                proposed["content"] = {**CONTENTS[kind], "evidence": {"attempts": 7}}
            if kind == "personality":
                proposed["content"] = traits.personality()
                proposed.update(sources=[{"kind": "innate"}], confidence=4)
            bodies.append(
                store.registry.parse(
                    {
                        "about_tick": None,
                        **proposed,
                        "id": rid,
                        "owner_id": "ella",
                        "created_tick": 1,
                        "updated_tick": 1,
                        "last_used_tick": None,
                        "use_count": 0,
                        "speech_derived": kind != "personality",
                        "needs_review": False,
                        "supersedes": None,
                        "superseded_by": None,
                        "text": None,
                    }
                )
            )
            ids[kind].append(rid)
    store.apply(0, "mechanical", bodies)
    return store, ids


def _run(store, *ops, commit=False, index_only=()):
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.provenance import HeardSpeechEntry, SentInput
    from living_island.memory.v2.validation import decode_change_set

    base = store.snapshot
    change = decode_change_set(
        json.dumps({"ops": [{"op_id": str(i), **op} for i, op in enumerate(ops)]}), base.version
    )
    sent = SentInput(
        "ella",
        "call",
        full=tuple(base.ref(r.id) for r in base.records() if r.id not in index_only),
        index=tuple(base.ref(rid) for rid in index_only),
        entries=(HeardSpeechEntry("ella", "e1", "delivery", ("heard[0]",), "s1", "mia"),),
    )
    staged = stage_change_set(store, change, sent, 8)
    if commit:
        staged.commit(store)
    return [v.reason for v in staged.verdicts]


def _op(operation, kind, ids):
    rid, *others = ids[kind]
    by = others[0] if others else rid
    variants = {
        "add": {"ref": "new:1", "record": _new(kind)},
        "merge": {"ref": "new:1", "ids": [rid, by], "record": _new(kind, sources=[])},
        "update": {"id": rid, "gist": "Revised"},
        "supersede": {"id": rid, "by": by},
        "confidence": {"id": rid, "to": 2},
        "review_done": {"id": rid},
        "forget": {"id": rid},
        "commitment_status": {"id": rid, "status": "kept", "note": "Mia brought it"},
        "trait": {"trait_id": "caution", "delta": 1, "sources": [TOLD]},
    }
    return {"op": operation, **variants[operation]}


def _read(store, rid):
    return store.snapshot.read(store.snapshot.ref(rid))


def test_mf06_each_op_and_kind_uses_the_authority_table():
    from living_island.memory.v2.validation import allowed_kind

    store, ids = _store()
    revisable = {"add", "merge", "update", "confidence", "supersede", "forget", "review_done"}
    permissions = {
        "episodic": revisable,
        "belief": revisable,
        "social": {"update", "confidence", "review_done"},
        "skill": revisable - {"merge"},
        "commitment": {"commitment_status", "review_done"},
        "intention": set(),
        "personality": {"trait"},
    }
    for kind, permits in permissions.items():
        for op in sorted(revisable | {"trait", "commitment_status"}):
            assert allowed_kind(store.registry, op, kind) == (op in permits)
            # The trait wire has no target ID. Its only target is the local personality.
            if op == "trait" and kind != "personality":
                continue
            expected = None if op in permits else "authority"
            assert _run(store, _op(op, kind, ids)) == [expected], (kind, op)

    social = ids["social"][0]
    edit = {"op": "update", "id": social, "gist": "Much closer"}
    for fields in (
        {"content": {"trust": 4}},
        {"content": {"about": "ada"}},
        {"about_tick": {"from": 3, "to": 4}},
        {"add_sources": [TOLD]},
    ):
        assert _run(store, {**edit, **fields}) == ["authority"]
    assert _run(store, {**edit, "content": {"facts": {}, "trust": 5}}) == ["format"]
    for field in (
        "owner_id",
        "kind",
        "created_tick",
        "updated_tick",
        "last_used_tick",
        "use_count",
        "supersedes",
        "superseded_by",
        "needs_review",
    ):
        assert _run(store, {**edit, field: None}) == ["authority"]
    assert _run(store, {"op": "add", "ref": "new:1", "record": _new("belief", id="fake")}) == [
        "authority"
    ]
    trait = _op("trait", "personality", ids)
    for field in ("base", "min", "max", "changes"):
        assert _run(store, {**trait, field: None}) == ["authority"]
    assert _run(store, trait, {**trait, "delta": -1}) == [None, "authority"]
    assert _run(
        store,
        {**edit, "content": {"trust": 3, "impression": "Generous"}},
        {**edit, "content": {"trust": 2}},
        commit=True,
    ) == [None, "authority"]
    assert _read(store, social).content.impression == "Generous"
    assert _read(store, social).content.trust == 3
    rid = store.snapshot.next_id()
    assert _run(
        store,
        _op("add", "belief", ids),
        {"op": "update", "id": "new:1", "gist": "Read my new note", "text": "Details"},
        {"op": "supersede", "id": ids["belief"][0], "by": "new:1"},
        commit=True,
    ) == [None, None, None]
    assert (_read(store, rid).text, _read(store, rid).supersedes) == ("Details", ids["belief"][0])


def test_mm10_mechanical_fields_and_archived_commitment():
    store, ids = _store()
    for kind, field, attempted in (
        ("commitment", "terms", {}),
        ("social", "facts", {}),
        ("skill", "evidence", {"attempts": 10}),
    ):
        rid = ids[kind][0]
        original = _read(store, rid)
        assert _run(
            store,
            {"op": "update", "id": rid, "gist": "Edited", "content": {field: attempted}},
            commit=True,
        ) == ["authority"]
        assert _read(store, rid) == original
    rid = ids["commitment"][0]
    assert _run(store, {"op": "forget", "id": rid}) == ["authority"]
    assert _run(store, _op("commitment_status", "commitment", ids), commit=True) == [None]
    assert _read(store, rid).content.status_note == "Mia brought it"
    assert _read(store, rid).archived
    assert all(r.ref.id != rid for r in store.snapshot.resident(memory_on=True).records)


def test_mm11_only_sourced_single_step_trait_drift_within_profile_bounds():
    store, ids = _store()
    rid = ids["personality"][0]
    base = {t.trait_id: t.base for t in _read(store, rid).content.traits}
    assert base == {
        "curiosity": 4,
        "caution": 1,
        "sociability": 2,
        "trustfulness": 2,
        "diligence": 2,
    }
    trait = _op("trait", "personality", ids)
    for invalid in ({"delta": 2}, {"trait_id": "curiosity"}, {"sources": []}, {"delta": True}):
        assert _run(store, {**trait, **invalid}) == ["format"]
    assert _run(store, trait, index_only=[rid]) == ["provenance"]
    assert _run(store, trait, commit=True) == [None]
    caution = next(t for t in _read(store, rid).content.traits if t.trait_id == "caution")
    assert caution.base == 1 and caution.value == 2
    assert [c.model_dump() for c in caution.changes] == [
        {"tick": 8, "from": 1, "to": 2, "sources": [TOLD]}
    ]
    assert _run(store, trait) == ["format"]


def test_mm20_hypothesis_revision_preserves_old_and_starts_new_evidence():
    store, ids = _store()
    old, other = ids["skill"]
    new_id = store.snapshot.next_id()
    revised = {**CONTENTS["skill"]["hypothesis"], "expected": ["snaps"]}
    assert _run(
        store, {"op": "update", "id": old, "gist": "Revise", "content": {"hypothesis": revised}}
    ) == ["authority"]
    assert _run(
        store, {"op": "merge", "ids": [old, other], "ref": "new:1", "record": _new("belief")}
    ) == ["authority"]
    add = {
        "op": "add",
        "ref": "new:1",
        "record": _new("skill", content={"hypothesis": revised, "status": "active"}),
    }
    for extra in (
        {"content": {**add["record"]["content"], "evidence": {}}},
        {"about_tick": {"from": 1, "to": 2}},
    ):
        assert _run(store, {**add, "record": {**add["record"], **extra}}) == ["authority"]
    assert _run(store, add, {"op": "supersede", "id": old, "by": "new:1"}, commit=True) == [
        None,
        None,
    ]
    assert _read(store, old).history
    assert _read(store, old).content.evidence.attempts == 7
    head = _read(store, new_id)
    assert head.content.hypothesis.expected == ["snaps"]
    assert head.content.evidence.model_dump() == {
        "attempts": 0,
        "matched_expected": 0,
        "other_outcomes": 0,
        "watched": 0,
        "watched_matched": 0,
        "last_attempt_tick": None,
    }


def test_change_set_response_boundary_and_per_operation_parse_failures():
    from living_island.memory.v2.validation import ResponseFormatError, decode_change_set

    for raw in ("{", "[]", "{}", '{"ops":{}}', '{"ops":[],"base_version":0}'):
        with pytest.raises(ResponseFormatError):
            decode_change_set(raw, 8)
    raw = json.dumps(
        {
            "ops": [
                False,
                {"op": "unknown", "op_id": "a"},
                {"op": "confidence", "op_id": "b", "id": "some-id", "to": True},
                {
                    "op": "merge",
                    "op_id": "c",
                    "ids": ["m:ella:1", 7],
                    "ref": "new:1",
                    "record": {
                        "kind": "belief",
                        "sources": [{"kind": "inferred", "memory_ids": ["new:2"]}],
                    },
                },
                {"op": "update", "op_id": "d", "id": "some-id", "gist": "ok", "text": None},
                {"op": "review_done", "op_id": "e", "id": "some-id", "new_field": True},
                {"op": "review_done", "op_id": "f", "id": "some-id"},
            ]
        }
    )
    decoded = decode_change_set(raw, 8)
    assert decoded.base_version == 8
    assert [op.problem for op in decoded.ops] == ["format"] * 6 + [None]
    merge = decoded.ops[3]
    assert merge.unresolved_operands
    assert not decoded.ops[2].unresolved_operands
    for bad in (
        {"op": "supersede", "id": "m:ella:1"},
        {
            "op": "add",
            "ref": "new:1",
            "record": _new("belief", sources=[{"kind": "inferred", "call_id": "call"}]),
        },
        {
            "op": "update",
            "id": "m:ella:1",
            "gist": "x",
            "add_sources": [
                {"kind": "inferred", "call_id": "call", "memory_ids": ["m:ella:1", False]}
            ],
        },
    ):
        (proposal,) = decode_change_set(json.dumps({"ops": [{"op_id": "bad", **bad}]}), 8).ops
        assert proposal.problem == "format" and proposal.unresolved_operands
    assert (merge.op_id, merge.ref, merge.operands, merge.inferred_ids, merge.new_kind) == (
        "c",
        "new:1",
        ("m:ella:1",),
        ("new:2",),
        "belief",
    )
