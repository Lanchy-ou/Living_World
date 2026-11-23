from v2.mechanical_memory.mechanical_agreement_support import (
    ACCEPTANCE,
    PROPOSAL,
    agreement_exchange,
)


def test_mf25_formation_and_projection_isolation(formation, packet, audit):
    _, closed, snapshot, _ = formation
    assert closed.outcome == "committed"
    verdicts = {v.op_id: v.reason for v in closed.verdicts}
    assert verdicts == {
        "1": None,
        "2": "format",
        "3": None,
        "4": None,
        "5": None,
        "6": None,
        "at-four": "format",
        "lower": None,
        "at-three": None,
    }
    effects = {e.op_id: e for e in closed.effects}
    mixed, cord = (effects[k].edits[0] for k in ("1", "3"))
    assert mixed.speech_derived and mixed.confidence == 3
    assert not cord.speech_derived and cord.confidence == 4
    current = snapshot.read(snapshot.ref(cord.id))
    assert current.confidence == 3 and current.speech_derived
    flag = next(f for f in closed.relabel_flags if f.shared_keys == ("place:2,1",))
    assert flag.flagged == snapshot.ref(effects["4"].produced_id)
    assert flag.overlaps == (snapshot.ref(mixed.id),)
    for row in snapshot.records():
        assert "relabel" not in row.model_dump_json()
    for row in snapshot.resident(memory_on=True).records:
        assert "relabel" not in row.record.model_dump_json()
        assert "relabel" not in row.index_line
    party, log = agreement_exchange("ella", packet, audit)
    record = next(r for r in party.records() if r.kind == "commitment")
    spoke = next(e for e in log.entries if e.type == "utterance_result")
    assert spoke.about == ("spoke:" + PROPOSAL,)
    assert [s.model_dump() for s in record.sources] == [{"kind": "observed", "entry_id": spoke.id}]
    assert ACCEPTANCE not in str(record.sources)


def test_ev25_export_links_both_immutable_revisions(formation, tmp_path):
    from living_island.analysis.v2.export import export
    from living_island.analysis.v2.shards import InspectionArchive

    paths, closed, snapshot, _ = formation
    dest = tmp_path / "inspection"
    index = export(*paths, dest)
    archive = InspectionArchive.open(dest)
    store = archive.read(index.stores[-1].shard)
    assert store.index_lines == list(snapshot.resident(memory_on=True).index())
    flag = next(f for f in store.relabel_flags if f.shared_keys == ("place:2,1",))
    assert flag in closed.relabel_flags
    assert archive.revision("ella", flag.flagged).speech_derived is False
    assert archive.revision("ella", flag.overlaps[0]).speech_derived is True
    for r in store.records:
        assert "relabel" not in r.model_dump_json()
    for ref in index.calls:
        for wire in archive.read(ref.shard).requests:
            assert "relabel" not in wire.text and flag.flagged.content_hash not in wire.text


def test_ev18_packet_ancestor_hypothesis_and_saved_check(formation, tmp_path):
    from living_island.analysis.v2.export import export
    from living_island.analysis.v2.shards import InspectionArchive

    paths, _, _, skill = formation
    dest = tmp_path / "for-analysis"
    index = export(*paths, dest)
    view = InspectionArchive.open(dest)
    packet = next(view.read(r) for r in index.deliveries if ":0000000001:" in r.id)
    assert all(d.tick != 1 for d in index.decisions)
    own = next(e for e in packet.entries if e.entry.type == "action_result")
    assert own.members[0]["items_used"][0]["material_id"] == "vine"
    assert own.event_ids == ["island:0000000001:000000"]
    write = next(w for w in map(view.read, index.evidence_writes) if w.skill)
    assert write.skill.hypothesis.id == skill and write.skill.delta["matched_expected"] == 1
    assert view.revision("ella", write.skill.hypothesis).content.hypothesis.expected == ["snaps"]
    assert any(
        e.intent_id == write.skill.intent_id and e.payload["rule_id"] == "bind_snaps"
        for e in view.read(index.attempts).events
    )
    closed = view.read(index.consolidations[0].shard).record
    inferred = next(e for e in closed.effects if e.op_id == "5")
    ancestor = inferred.bindings[0].revisions[0]
    assert view.revision("ella", ancestor).gist == "The cord snapped"
    latest = view.read(index.stores[-1].shard)
    assert next(r for r in latest.records if r.id == ancestor.id).gist == "Mia also warned me"
    (check,) = view.read(index.metrics).content_checks
    heard = next(
        e for e in view.read(index.deliveries[0]).entries if e.entry.type == "heard_speech"
    )
    assert check.verdict == "carries" and check.ids == [
        heard.entry.ref.utterance_id,
        *heard.event_ids,
    ]
