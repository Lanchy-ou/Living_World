"""Memory model §11 vectors and the public input boundaries of MM-01."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError


def envelope(number=1, *, owner="ella", kind="belief", content=None, **fields):
    if content is None:
        content = {
            "subject": {"kind": "general", "ref": None},
            "stance": "stable",
            "topics": [],
        }
    return {
        "id": f"m:{owner}:{number}",
        "owner_id": owner,
        "kind": kind,
        "content": content,
        "created_tick": 0,
        "updated_tick": 0,
        "about_tick": None,
        "sources": [{"kind": "observed", "entry_id": "e1"}],
        "confidence": 3,
        "speech_derived": False,
        "last_used_tick": None,
        "use_count": 0,
        "supersedes": None,
        "superseded_by": None,
        "needs_review": False,
        "gist": "Fruit grows here",
        "text": None,
        **fields,
    }


def commitment(number, *, status="open"):
    return envelope(
        number,
        kind="commitment",
        sources=[],
        gist="private-agreement",
        content={
            "agreement_id": "private-agreement",
            "role": "promisee",
            "counterpart_id": "mia",
            "terms": {
                "promisor_id": "mia",
                "promisee_id": "ella",
                "what": {"kind": "give_item", "item": {"quantity": 2, "archetype_id": "fruit"}},
                "due_tick": 300,
            },
            "due_tick": 300,
            "heard_counterpart": False,
            "status": status,
            "status_note": None,
        },
    )


def skill(number, look, **fields):
    return envelope(
        number,
        kind="skill",
        content={
            "hypothesis": {
                "verb": "cut",
                "target": look,
                "instruments": [look],
                "inputs": [{"look": look, "quantity": 1}],
                "circumstances": None,
                "expected": ["split"],
            },
            "evidence": {},
            "status": "refuted",
        },
        **fields,
    )


def test_mm01_envelope():
    from living_island.memory.v2.kinds import KindRegistry

    parse = KindRegistry().parse
    record = parse(
        envelope(
            sources=[
                {"kind": "innate"},
                {"kind": "inferred", "call_id": "c", "memory_ids": ["m:ella:2"]},
                {"kind": "told", "utterance_id": "s", "speaker_id": "mia"},
                {"kind": "observed", "entry_id": "z"},
                {"kind": "observed", "entry_id": "a"},
            ],
            gist="果" * 160,
        )
    )
    wire = json.loads(record.model_dump_json())
    assert [s["kind"] for s in wire["sources"]] == [
        "observed",
        "observed",
        "told",
        "inferred",
        "innate",
    ]
    assert wire["sources"][0]["entry_id"] == "a"
    assert wire["needs_review"] is False and wire["speech_derived"] is False
    assert wire["last_used_tick"] is None and wire["about_tick"] is None
    assert parse(wire) == record
    assert parse(commitment(1)).sources == []

    for key in wire:
        with pytest.raises((KeyError, ValidationError)):
            parse({name: value for name, value in wire.items() if name != key})
    for change in (
        {"sources": []},
        {"sources": [{"kind": "foreign"}]},
        {"sources": [{"kind": "inferred", "call_id": "c", "memory_ids": []}]},
        {"confidence": -1},
        {"confidence": 5},
        {"confidence": True},
        {"needs_review": 0},
        {"last_used_tick": False},
        {"use_count": -1},
        {"created_tick": 1},
        {"updated_tick": 1.0},
        {"gist": "x" * 161},
        {"gist": "first\nsecond"},
        {"gist": "line\r"},
        {"gist": "first\u2028second"},
        {"text": "x" * 2001},
        {"extra": 3},
        {"owner_id": "mia"},
        {"id": "m:ella:01"},
        {"about_tick": {"from": 5, "to": 4}},
        {"about_tick": {"from": 1, "to": 4}},
        {"content": {**wire["content"], "stance": "dated"}},
        {"kind": "episodic", "content": {"participants": [], "place": None}},
    ):
        with pytest.raises(ValidationError):
            parse({**wire, **change})
    episode = parse(
        envelope(
            kind="episodic",
            about_tick={"from": 0, "to": 1},
            content={"participants": ["ella"], "place": {"x": 0, "y": 1}},
        )
    )
    assert episode.model_dump()["about_tick"] == {"from": 0, "to": 1}


def test_mm02_resident_ids_survive_merge_and_forget():
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    other = MemoryStore("mia")
    parse = store.registry.parse
    first, second = (parse(envelope(n)) for n in (1, 2))
    store.apply(0, "change_set", [first, second])
    merged = parse(envelope(3))
    store.apply(
        1,
        "change_set",
        [
            first.model_copy(update={"superseded_by": merged.id}),
            second.model_copy(update={"superseded_by": merged.id}),
            merged,
        ],
    )
    store.apply(2, "change_set", [first.id, second.id, merged.id])
    assert not store.snapshot.records()
    assert store.snapshot.next_id() == "m:ella:4"
    for invalid in (first, parse(envelope(5)), parse(envelope(1, owner="mia"))):
        with pytest.raises(ValueError, match="next resident-local ID"):
            store.apply(3, "change_set", [invalid])
    store.apply(3, "change_set", [parse(envelope(4))])
    assert other.snapshot.next_id() == "m:mia:1"
    other.apply(0, "mechanical", [parse(envelope(1, owner="mia"))])


def test_mm03_versions_use_and_pinned_revisions():
    from living_island.memory.v2.store import DecisionDispatch, MemoryStore

    def run():
        store = MemoryStore("ella")
        first, second = [store.registry.parse(envelope(n)) for n in (1, 2)]
        mechanical = store.apply(0, "mechanical", [first])
        committed = store.apply(1, "change_set", [second, first.model_copy(update={"gist": "南"})])
        frozen = store.snapshot
        ref = frozen.ref(first.id)
        data = frozen.read(ref).model_dump(mode="json", exclude={"last_used_tick", "use_count"})
        expected = json.dumps(
            data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
        assert ref.content_hash == hashlib.sha256(expected).hexdigest()
        assert (
            ref.content_hash in committed.blobs
            and mechanical.changes[0].after.content_hash != ref.content_hash
        )
        dispatch = DecisionDispatch("decision", "t1", "call1", 7, (ref, ref))
        assert store.credit_dispatch(replace(dispatch, revisions=())) is None
        use = store.credit_dispatch(dispatch)
        assert use.credited == (ref,) and use.dispatch == dispatch and not use.blobs
        assert store.credit_dispatch(replace(dispatch, call_id="retry")) is None
        assert store.snapshot.ref(first.id).content_hash == ref.content_hash
        after = store.credit_dispatch(
            DecisionDispatch(
                "decision_after_recall", "t1", "call2", 7, (ref, frozen.ref(second.id))
            )
        )
        assert [r.id for r in after.credited] == [second.id]
        assert [r.use_count for r in store.snapshot.records()] == [1, 1]
        assert [r.last_used_tick for r in store.snapshot.records()] == [7, 7]
        assert store.credit_dispatch(replace(dispatch, turn_id="t2", tick=8)).after_version == 5
        assert frozen.read(ref).use_count == 0
        with pytest.raises(ValueError, match="revision"):
            store.snapshot.read(ref)
        with pytest.raises(ValueError, match="revision"):
            frozen.read(replace(ref, content_hash="0" * 64))
        assert [
            (w.before_version, w.after_version) for w in (mechanical, committed, use, after)
        ] == [
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 4),
        ]
        assert len({w.store_hash for w in (mechanical, committed, use, after)}) == 4
        return mechanical, committed, use, after, store.snapshot.store_hash

    assert run() == run()


def test_mm04_sorted_safe_index_flags_and_archive():
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    parse = store.registry.parse
    link = commitment(3)
    private_id = link["content"]["agreement_id"]
    social = envelope(
        4,
        kind="social",
        gist=private_id,
        content={
            "about": "mia",
            "trust": 2,
            "impression": "",
            "facts": {
                "given": [],
                "received": [],
                "agreements": [private_id, "unwritten-link"],
                "last_seen_tick": None,
                "last_heard_tick": None,
            },
        },
    )
    store.apply(
        0,
        "mechanical",
        [
            parse(envelope(1, needs_review=True, superseded_by="m:ella:2")),
            parse(envelope(2)),
            parse(link),
            parse(social),
            parse(
                skill(
                    5,
                    {"archetype_id": None, "material_id": None, "descriptors": []},
                    superseded_by="m:ella:6",
                )
            ),
            *[parse(envelope(n)) for n in range(6, 11)],
        ],
    )
    visible = store.snapshot.resident(memory_on=True)
    ids = [entry.record.id for entry in visible.records]
    assert ids == sorted(ids) and ids[1] == "m:ella:10"
    assert (
        visible.index()[0] == "m:ella:1 | belief | c3 | needs_review,superseded | Fruit grows here"
    )
    assert visible.index()[1] == "m:ella:10 | belief | c3 | - | Fruit grows here"
    assert visible.index()[3] == (
        "m:ella:3 | commitment | c3 | open | mia agreed to give 2 fruit by tick 300 "
        "(I did not hear their answer)"
    )
    assert visible.records[5].flags == ("refuted", "superseded")
    social_fields = visible.records[4].record.model_dump()
    assert social_fields["content"]["facts"]["agreements"] == ["m:ella:3"]
    for entry in visible.records:
        rendered = entry.record.model_dump_json()
        assert private_id not in rendered and "unwritten-link" not in rendered
        assert "agreement_id" not in rendered and "speech_derived" not in rendered
    assert [entry.record.id for entry in visible.history()] == ["m:ella:1", "m:ella:5"]
    assert len(visible.live()) == 8
    # An independent heard utterance legitimately carries the same bytes as a private join.
    heard = {"kind": "told", "utterance_id": private_id, "speaker_id": "mia"}
    store.apply(
        1,
        "change_set",
        [
            parse(envelope(2, sources=[heard], speech_derived=True)),
            parse(commitment(3, status="kept")),
            parse({**social, "gist": "We know each other from the spring"}),
        ],
    )
    updated = store.snapshot.resident(memory_on=True)
    assert all(entry.record.id != "m:ella:3" for entry in updated.records)
    assert updated.records[2].record.model_dump()["sources"] == [heard]
    assert updated.records[3].record.gist == "We know each other from the spring"
    assert store.snapshot.read(store.snapshot.ref("m:ella:3")).archived
    assert store.snapshot.resident(memory_on=False).index() == ()


def test_mm05_hypothesis_uses_perceived_descriptor_words():
    from living_island.memory.v2.kinds import KindRegistry
    from living_island.memory.v2.records import Look
    from living_island.world.v2.protocol import InspectView

    perceived = InspectView.model_validate(
        {
            "entity_id": "e-9",
            "archetype_id": "flake",
            "material_id": "flint",
            "descriptors": [
                {"property_id": "weight", "value": "light"},
                {"property_id": "edge", "value": "sharp"},
            ],
        }
    )
    look = Look.perceived(perceived).model_dump()
    assert look == {
        "archetype_id": "flake",
        "material_id": "flint",
        "descriptors": [
            {"property_id": "edge", "word": "sharp"},
            {"property_id": "weight", "word": "light"},
        ],
    }
    parse = KindRegistry().parse
    assert parse(skill(1, look)).model_dump()["content"]["hypothesis"]["target"] == look
    for descriptor in ({"property_id": "edge", "word": 3}, {"property_id": "edge", "value": 3}):
        with pytest.raises(ValidationError):
            parse(skill(1, {**look, "descriptors": [descriptor]}))


def test_mm18_replace_clear_and_off_arm_reset():
    from living_island.memory.v2.records import Observed
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")

    def set_at(tick, text="Carry water"):
        return store.set_intention(
            turn_id=f"turn{tick}", tick=tick, text=text, source=Observed(entry_id=f"entry{tick}")
        )

    set_at(1, "my own\nwords")
    original = store.snapshot.current_intention()
    assert original.text == "my own\nwords" and original.gist == "my own words"
    set_at(2)
    old, current = store.snapshot.records()
    assert (old.content.state, old.content.ended_turn, old.superseded_by) == (
        "replaced",
        "turn2",
        current.id,
    )
    assert store.snapshot.resident(memory_on=False).current_intention.record.supersedes == old.id
    store.end_intention(tick=3, turn_id="turn3")
    cleared = store.snapshot.read(store.snapshot.ref(current.id))
    assert (cleared.content.state, cleared.content.ended_turn, cleared.superseded_by) == (
        "cleared",
        "turn3",
        None,
    )
    assert store.snapshot.current_intention() is None
    set_at(4)
    store.end_intention(tick=5, turn_id=None)
    visible = store.snapshot.resident(memory_on=True)
    reset = visible.history()[-1].record
    assert (reset.content.state, reset.content.ended_turn, reset.superseded_by) == (
        "reset",
        None,
        None,
    )
    assert visible.current_intention is None and visible.records == visible.history()
    assert store.snapshot.resident(memory_on=False).records == ()
    assert store.end_intention(tick=6, turn_id=None) is None
    with pytest.raises(ValueError, match="historical intention"):
        store.apply(store.snapshot.version, "mechanical", [original])
    for tick in range(6, 29):
        set_at(tick)
    assert len(store.snapshot.resident(memory_on=True).history()) == 20
    assert old.id not in {record.id for record in store.snapshot.records()}


def test_atomic_write_input_rejects_stale_or_invalid_batch():
    from living_island.memory.v2.store import DecisionDispatch, MemoryStore

    store = MemoryStore("ella")
    record = store.registry.parse(envelope())
    receipt = store.apply(0, "mechanical", [record])
    base = store.snapshot
    with pytest.raises(ValueError, match="stale"):
        store.apply(0, "change_set", [])
    with pytest.raises(KeyError):
        store.apply(1, "change_set", [record.id, "m:ella:99"])
    with pytest.raises(ValueError, match="change a record's kind"):
        store.apply(1, "mechanical", [store.registry.parse(commitment(1))])
    ref = base.ref(record.id)
    with pytest.raises(KeyError):
        store.credit_dispatch(
            DecisionDispatch("decision", "t1", "c1", 2, (ref, replace(ref, id="m:mia:1")))
        )
    assert store.snapshot is base and base.read(ref).use_count == 0
    record.sources.clear()
    receipt.blobs[ref.content_hash].sources.clear()
    base.read(ref).sources.clear()
    base.resident(memory_on=True).records[0].record.sources.clear()
    assert len(base.read(ref).sources) == 1
    retry = store.credit_dispatch(DecisionDispatch("decision", "t1", "c2", 2, (ref,)))
    assert retry.credited == (ref,)


def test_use_credit_requires_a_decision_dispatch():
    from living_island.memory.v2.store import DecisionDispatch

    for stage, tick in (("consolidation_selection", 7), ("morning_selection", 7), ("decision", -1)):
        with pytest.raises(ValidationError):
            DecisionDispatch(stage, "t1", "c1", tick, ())


def test_registry_boundary_uses_declared_schema_flags_operations_and_recipes():
    from living_island.memory.v2.kinds import Kind, KindRegistry
    from living_island.memory.v2.records import Content, MemoryRecord
    from living_island.memory.v2.store import MemoryStore

    class Synthetic(Content):
        kind = "synthetic"
        label: str

        def flags(self):
            return ("test_flag",)

    definition = Kind(Synthetic, 4, 2, frozenset({"add"}), ("test_reason",))
    registry = KindRegistry()
    fields = envelope(kind="synthetic", content={"label": "test"})
    with pytest.raises(KeyError):
        registry.parse(fields)
    registry.register(definition)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)
    with pytest.raises(ValidationError):
        registry.parse({**fields, "content": {"label": 4}})
    typed = registry.parse(fields)
    assert registry["synthetic"] == definition
    store = MemoryStore("ella", registry)
    store.apply(0, "change_set", [typed])
    view = store.snapshot.resident(memory_on=True).records[0]
    assert view.flags == ("test_flag",) and view.record.model_dump()["content"] == {"label": "test"}
    with pytest.raises(ValidationError, match="does not match"):
        MemoryRecord.model_validate({**fields, "kind": "belief", "content": typed.content})

    class OtherSchema(Synthetic):
        pass

    wrong_schema = MemoryRecord.model_validate({**fields, "content": OtherSchema(label="test")})
    with pytest.raises(ValueError, match="registered schema"):
        store.apply(1, "change_set", [wrong_schema])


def test_current_intention_uniqueness_at_batch_boundary():
    from living_island.memory.v2.records import Observed
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    store.set_intention(
        tick=1, turn_id="t1", text="Inspect the tree", source=Observed(entry_id="a")
    )
    first = store.snapshot.current_intention()
    with pytest.raises(ValueError, match="already has a current intention"):
        store.apply(1, "mechanical", [first.model_copy(update={"id": store.snapshot.next_id()})])
    assert store.snapshot.current_intention() == first


def test_selected_profile_file_boundary(tmp_path):
    from living_island.memory.v2.profiles import SelectedProfile
    from living_island.memory.v2.store import MemoryStore

    base = Path(__file__).resolve().parents[4] / "content" / "characters"
    for profile, vector in [
        ("explorer", [4, 1, 2, 2, 2]),
        ("cautious", [1, 4, 1, 1, 3]),
        ("cooperative", [2, 2, 4, 3, 2]),
        ("synthetic_min", [0] * 5),
        ("synthetic_max", [4] * 5),
    ]:
        if profile.startswith("synthetic"):
            path = Path(__file__).parent / "fixtures" / f"{profile}.json"
        else:
            path = base / "v2" / f"{profile}.json"
            legacy = json.loads((base / f"{profile}.json").read_bytes())
            assert legacy["profile_schema_version"] == "0.1"
            assert legacy["values"] == json.loads(path.read_bytes())["values"]
        fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
        selected = SelectedProfile.load(path, expected_sha256=fingerprint)
        assert selected.sha256 == fingerprint and selected.document.profile_id == profile
        store = MemoryStore("ella")
        selected.initialize(store)
        (personality,) = store.snapshot.records()
        assert personality.confidence == 4 and [s.kind for s in personality.sources] == ["innate"]
        assert [(t.value, t.base, t.min, t.max, t.changes) for t in personality.content.traits] == [
            (v, v, max(0, v - 1), min(4, v + 1), []) for v in vector
        ]
        assert [t.trait_id for t in personality.content.traits] == [
            "curiosity",
            "caution",
            "sociability",
            "trustfulness",
            "diligence",
        ]
        with pytest.raises(ValueError, match="stale"):
            selected.initialize(store)

    with pytest.raises(ValueError, match="SHA-256"):
        SelectedProfile.load(path, expected_sha256="0" * 64)
    with pytest.raises(ValidationError):
        SelectedProfile.load(base / "explorer.json")
    malformed = tmp_path / "malformed-profile.json"
    fields = selected.document.model_dump()
    for changes in (
        {"traits": {"curiosity": 3}},
        {"traits": {**fields["traits"], "caution": 5}},
        {"values": ["duplicate", "duplicate"]},
    ):
        malformed.write_text(json.dumps({**fields, **changes}), encoding="utf-8")
        with pytest.raises(ValidationError):
            SelectedProfile.load(malformed)
    bad_personality = personality.content.model_dump()
    bad_personality["traits"].pop()
    with pytest.raises(ValidationError, match="one of each"):
        store.registry.parse({**personality.model_dump(), "content": bad_personality})


def test_pending_append_and_consume_boundary():
    from living_island.memory.v2.pending import PendingPeriod, PendingPeriods

    pending = PendingPeriods("ella")
    other = PendingPeriods("mia")
    periods = [PendingPeriod("ella", str(n), [n]) for n in range(4)]
    with pytest.raises(ValueError, match="another resident"):
        other.append(periods[0])
    assert pending.append(periods[0]) is None
    assert pending.append(periods[1]) is None
    with pytest.raises(ValueError, match="already pending"):
        pending.append(periods[0])
    periods[0].context.append(42)
    pending.read()[0].context.clear()
    assert pending.append(periods[2]) == PendingPeriod("ella", "0", [0])
    assert pending.consume([]) == ()
    assert pending.consume(["2"]) == (periods[2],)
    assert pending.read() == (periods[1],)
    assert other.read() == ()
