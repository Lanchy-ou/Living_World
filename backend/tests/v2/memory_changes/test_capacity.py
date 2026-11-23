"""Memory-model §11 capacity and skill lifecycle vectors."""

import json


def _id(number):
    return f"m:ella:{number}"


def _record(kind):
    content = {
        "belief": {"subject": {"kind": "resident", "ref": "mia"}, "stance": "stable", "topics": []},
        "episodic": {"participants": ["mia"], "place": None},
        "skill": {
            "hypothesis": {
                "verb": "cut",
                "target": None,
                "instruments": [],
                "inputs": [],
                "circumstances": None,
                "expected": ["split"],
            },
            "status": "active",
        },
    }
    return {
        "kind": kind,
        "gist": f"Remembered {kind}",
        "content": content[kind],
        "about_tick": {"from": 0, "to": 0} if kind == "episodic" else None,
        "sources": [{"kind": "observed", "entry_id": "initial-observation"}],
        "confidence": 3,
        "text": None,
    }


def _seed(kind, count, overrides=None):
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    edits = []
    for number in range(1, count + 1):
        fields = _record(kind)
        if kind == "skill":
            fields["content"]["evidence"] = {}
        edit = {
            **fields,
            "id": _id(number),
            "owner_id": "ella",
            "created_tick": 0,
            "updated_tick": 0,
            "speech_derived": False,
            "last_used_tick": None,
            "use_count": 0,
            "supersedes": None,
            "superseded_by": None,
            "needs_review": False,
            **(overrides or {}).get(number, {}),
        }
        edits.append(store.registry.parse(edit))
    store.apply(0, "change_set", edits)
    return store


def _add(kind, number):
    record = _record(kind)
    record["sources"] = [{"kind": "inferred", "call_id": "changes", "memory_ids": [_id(1)]}]
    return {"op_id": f"add-{number}", "op": "add", "ref": f"new:{number}", "record": record}


def _stage(store, ops, *, full=()):
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.provenance import SentInput
    from living_island.memory.v2.validation import decode_change_set

    snapshot = store.snapshot
    sent = SentInput(
        "ella",
        "changes",
        full=tuple(snapshot.ref(_id(n)) for n in full),
        index=(snapshot.ref(_id(1)),),
    )
    return stage_change_set(
        store, decode_change_set(json.dumps({"ops": ops}), snapshot.version), sent, tick=10
    )


def test_mm12_capacity_order_history_and_mechanical_writes():
    episodes = _seed("episodic", 300)
    stage = _stage(episodes, [_add("episodic", 1)])
    assert stage.verdicts[0].reason == "capacity"
    assert stage.evictions == ()
    stage.commit(episodes)
    assert len(episodes.snapshot.records()) == 300

    # A mechanical commitment still arrives when the episodic partition is full.
    commitment = episodes.registry.parse(
        {
            **episodes.snapshot.records()[0].model_dump(),
            "id": _id(301),
            "kind": "commitment",
            "about_tick": None,
            "sources": [],
            "content": {
                "agreement_id": "a1",
                "role": "promisee",
                "counterpart_id": "mia",
                "terms": {
                    "promisor_id": "mia",
                    "promisee_id": "ella",
                    "what": {"kind": "be_at", "position": {"x": 1, "y": 0}},
                    "due_tick": 10,
                },
                "due_tick": 10,
                "heard_counterpart": False,
                "status": "open",
                "status_note": None,
            },
        }
    )
    episodes.apply(episodes.snapshot.version, "mechanical", [commitment])
    assert len(episodes.snapshot.resident(memory_on=True).index()) == 301
    archived = _stage(
        episodes,
        [
            {
                "op": "commitment_status",
                "op_id": "kept",
                "id": _id(301),
                "status": "kept",
                "note": "Mia came.",
            }
        ],
        full=(301,),
    )
    assert archived.verdicts[0].result == "committed"
    archived.commit(episodes)
    assert episodes.snapshot.read(episodes.snapshot.ref(_id(301))).archived
    assert len(episodes.snapshot.resident(memory_on=True).index()) == 300

    beliefs = _seed(
        "belief",
        200,
        {
            2: {"confidence": 1, "last_used_tick": 0, "use_count": 1},
            3: {"confidence": 1, "last_used_tick": 4, "use_count": 1},
            9: {"confidence": 1},
            10: {"confidence": 1},
        },
    )
    stage = _stage(beliefs, [_add("belief", n) for n in range(1, 5)])
    assert [v.result for v in stage.verdicts] == ["committed"] * 4
    assert stage.evictions == tuple(_id(n) for n in (10, 9, 2, 3))
    receipt = stage.commit(beliefs).write
    assert tuple(c.id for c in receipt.changes if c.after is None) == stage.evictions
    assert len(beliefs.snapshot.records()) == 200

    refuted = {**_record("skill")["content"], "status": "refuted", "evidence": {}}
    skills = _seed(
        "skill",
        80,
        {
            9: {"content": refuted},
            10: {"content": refuted},
            11: {"content": refuted, "created_tick": 1, "updated_tick": 1},
        },
    )
    stage = _stage(skills, [_add("skill", n) for n in range(1, 5)])
    assert [v.reason for v in stage.verdicts] == [None, None, None, "capacity"]
    assert stage.evictions == (_id(10), _id(9), _id(11))
    stage.commit(skills)
    assert len(skills.snapshot.records()) == 80

    # IDs 2 through 10 are the oldest. Among those, ...:10 sorts before ...:2.
    chain = {
        n: {
            "superseded_by": _id(n + 1),
            "supersedes": _id(n - 1) if n > 2 else None,
            "created_tick": int(n > 10),
            "updated_tick": 1,
        }
        for n in range(2, 202)
    }
    chain[202] = {"supersedes": _id(201), "created_tick": 1, "updated_tick": 1}
    history = _seed("belief", 203, chain)
    stage = _stage(
        history,
        [
            {"op": "supersede", "op_id": "first", "id": _id(202), "by": _id(1)},
            {"op": "supersede", "op_id": "second", "id": _id(1), "by": _id(203)},
        ],
        full=(1, 202, 203),
    )
    assert [v.result for v in stage.verdicts] == ["committed", "committed"]
    assert stage.evictions == (_id(10), _id(2))
    stage.commit(history)
    view = history.snapshot.resident(memory_on=True)
    assert len(view.history()) == 200 and len(view.live()) == 1
    assert {_id(10), _id(2)}.isdisjoint(r.ref.id for r in view.history())


def test_mm22_refuted_skill_evidence_eligibility_and_eviction():
    from living_island.memory.v2.capacity import eligible_skills
    from living_island.memory.v2.store import MemoryStore

    content = {**_record("skill")["content"], "evidence": {"attempts": 3, "other_outcomes": 3}}
    skills = _seed("skill", 80, {2: {"content": content}})
    refute = _stage(
        skills,
        [
            {
                "op_id": "refute",
                "op": "update",
                "id": _id(2),
                "gist": "Cutting failed three times",
                "content": {"status": "refuted"},
            }
        ],
        full=(2,),
    )
    assert refute.verdicts[0].result == "committed"
    refutation_receipt = refute.commit(skills).write
    at_cap = skills.snapshot
    view = at_cap.resident(memory_on=True)
    assert len(view.live()) == 80
    refuted = next(entry for entry in view.live() if entry.ref.id == _id(2))
    assert " | refuted | " in refuted.index_line
    assert {entry.ref.id for entry in eligible_skills(view)} == {_id(n) for n in range(1, 81)} - {
        _id(2)
    }

    add = _stage(skills, [_add("skill", 1)])
    assert add.verdicts[0].result == "committed" and add.evictions == (_id(2),)
    receipt = add.commit(skills).write
    removed = next(change for change in receipt.changes if change.after is None)
    assert removed.id == refuted.ref.id and removed.before.content_hash == refuted.ref.content_hash
    audit_body = refutation_receipt.blobs[removed.before.content_hash]
    assert audit_body.content.evidence.attempts == audit_body.content.evidence.other_outcomes == 3
    assert all(entry.ref.id != _id(2) for entry in skills.snapshot.resident(memory_on=True).records)

    alternate = MemoryStore.from_snapshot(at_cap)
    replace = _stage(
        alternate,
        [{"op": "supersede", "op_id": "replace", "id": _id(2), "by": _id(1)}],
        full=(1, 2),
    )
    assert replace.verdicts[0].result == "committed"
    replace.commit(alternate)
    add = _stage(alternate, [_add("skill", 1)])
    assert add.verdicts[0].result == "committed" and add.evictions == ()
    add.commit(alternate)
    view = alternate.snapshot.resident(memory_on=True)
    assert len(view.live()) == len(eligible_skills(view)) == 80
    assert [(entry.ref.id, entry.flags) for entry in view.history()] == [
        (_id(2), ("refuted", "superseded"))
    ]
