from living_island.agents.v2.calls.guard import Entry, Section
from living_island.agents.v2.context.entries import DayEntry
from living_island.agents.v2.context.prefix import memory_ref
from living_island.agents.v2.recall.attribution import ActCitations, Citation, SentFragment
from living_island.analysis.v2.continuity import History
from living_island.analysis.v2.export import export
from living_island.analysis.v2.learning import Learning, attempts, predicts
from living_island.analysis.v2.shards import InspectionArchive
from living_island.contract import inspection_v2 as ia


def choice(template, actor, tick, origin="model"):
    turn = f"{actor}:t{tick:06}"
    action = template.submission.action
    intent = action.intent.model_copy(
        update=dict(actor_id=actor, turn_id=turn, intent_id=turn + ":a", verb="combine")
    )
    submission = template.submission.model_copy(
        update=dict(
            actor_id=actor,
            observed_tick=tick,
            turn_id=turn,
            action=action.model_copy(update={"intent": intent}),
        )
    )
    return template.model_copy(
        update=dict(
            resident_id=actor,
            turn_id=turn,
            tick=tick,
            submission=submission,
            origin=origin,
            period_id=f"p:{actor}:2",
            call_ids=[turn + "-act"],
        )
    )


def event(turn, name, payload, tick=None):
    return ia.WorldEvent(
        schema_version="wap/0.1",
        run_id="island",
        event_id=turn.turn_id + "/" + name,
        tick=turn.tick if tick is None else tick,
        seq_in_tick=0,
        type=name,
        actor_id=turn.resident_id,
        intent_id=turn.submission.action.intent.intent_id,
        target_id=None,
        llm_call_id=None,
        caused_by_event_ids=[],
        payload=payload,
    )


def events(turn, rule, kind, archetype):
    return [
        event(turn, "act_items", {"slots": [{"parts": [{"archetype_id": archetype}]}]}),
        event(turn, "act_settled", dict(rule_id=rule, kind=kind, verb="combine")),
    ]


def test_ev04_adopted_choice_learning_paths(short, packet):
    seed = short.read(short.index.decisions[0].shard)
    base = seed.calls[-1]
    older = choice(seed.record, "ella", 2)
    watcher = choice(seed.record, "mia", 3)
    final = choice(seed.record, "ella", 20)
    first, second = "p:ella:1", "p:ella:2"

    def delivered(tick, name, kind, ref):
        p = packet(tick=tick)
        entry = DayEntry(
            id=name, type=kind, tick=tick, text=name, delivery_id=p.delivery_id, ref=ref
        )
        return ia.JoinedEntry(
            entry=entry, event_ids=[name + "-event"], members=[], missing_reason=None
        )

    fail = delivered(
        4,
        "fail",
        "action_result",
        dict(kind="feedback", intent_id=older.submission.action.intent.intent_id),
    )
    fail = fail.model_copy(update={"event_ids": [older.turn_id + "/act_settled"]})
    start, settle = [
        delivered(
            t,
            "watch-" + phase,
            "observation",
            dict(
                kind="observed_action",
                intent_id=watcher.submission.action.intent.intent_id,
                phase=phase,
            ),
        )
        for t, phase in [(5, "start"), (6, "settle")]
    ]
    heard = delivered(
        7, "lesson", "heard_speech", dict(kind="utterance", utterance_id="u1", speaker_id="mia")
    )
    record = ia.Record(
        id="m:ella:1",
        owner_id="ella",
        kind="belief",
        created_tick=8,
        updated_tick=8,
        sources=[{"kind": "observed", "entry_id": "fail"}],
        gist="That binding failed",
        content={"subject": {"kind": "general", "ref": None}, "stance": "stable", "topics": []},
        about_tick=None,
        confidence=2,
        last_used_tick=None,
        use_count=0,
        supersedes=None,
        superseded_by=None,
        needs_review=False,
        text=None,
        speech_derived=False,
    )
    ref = ia.RevisionRef(record.id, 3, record.content_hash())
    revisions = ia.Revisions(
        resident_id="ella", store_version=3, records=[ia.Revision(ref=ref, record=record)]
    )

    def score(
        sent=(), *, watched=True, own=None, cited=False, checked=None, memory=False, earlier=True
    ):
        deliveries = [
            ia.Delivery(packet=packet(tick=e.entry.tick), period_id=first, entries=[e])
            for e in [fail, start, *([settle] if watched else []), heard]
        ]
        deliveries.append(
            ia.Delivery(packet=packet(tick=8), period_id=first if earlier else second, entries=[])
        )
        history = History(deliveries, [revisions], [], {}, 10)
        parts = [
            Entry(source=e.entry.part.source, sha256=e.entry.fragment_sha256, tokens=1)
            for e in sent
        ]
        if memory:
            parts.append(Entry(source=memory_ref(ref), sha256="a" * 64, tokens=1))
        manifest = base.sent_manifest.model_copy(
            update={"sections": (Section(section="day_log", entries=tuple(parts)),)}
        )
        citations = []
        if cited:
            citations = [
                ActCitations(
                    turn_id=final.turn_id,
                    call_id=final.call_ids[-1],
                    attempt=0,
                    request_sha256=base.attempts[0].dispatch.request_sha256,
                    valid=(
                        Citation(
                            id=heard.entry.id,
                            fragments=(
                                SentFragment(
                                    source=heard.entry.part.source,
                                    sha256=heard.entry.fragment_sha256,
                                    memory_revision=None,
                                ),
                            ),
                        ),
                    ),
                    invalid=(),
                )
            ]
        call = base.model_copy(
            update={
                "call": base.call.model_copy(update={"call_id": final.call_ids[-1]}),
                "sent_manifest": manifest,
                "adopted_citations": citations,
            }
        )
        saved = (
            []
            if checked is None
            else [
                ia.SpeechCheck(
                    instance_id="check",
                    ids=["u1", "axe"],
                    check="told_event",
                    checker="owner",
                    date="2026-11-24",
                    note="Checked the axe lesson",
                    verdict=checked,
                )
            ]
        )
        past = events(older, *own) if own else []
        log = [
            *past,
            *events(watcher, "axe", "applied", "cord"),
            *events(final, "axe", "applied", "cord"),
        ]
        learning = Learning(
            history, log, [older, final], saved, {e.entry.revision: e.entry for e in sent}
        )
        return learning.paths({final.call_ids[-1]: call})[0]

    assert score().flags == ["prior_knowledge"]
    failed = ("other", "unmet", "cord")
    assert score([fail], own=failed).flags == ["own_failures"]
    assert score([fail], own=("pot", "unmet", "clay")).flags == ["prior_knowledge"]
    assert score([start], watched=False).flags == ["prior_knowledge"]
    assert score([start, settle]).flags == ["watched"]
    assert score([heard], cited=True).unchecked_utterances == ["u1"]
    assert "told" not in score([heard], checked="carries").flags
    assert "told" not in score([heard], checked="different", cited=True).flags
    assert score([heard], checked="carries", cited=True).flags == ["told"]
    assert score(memory=True, own=failed).flags == ["earlier_period"]
    assert not score(memory=True, own=failed, earlier=False).flags
    mixed = score(
        [fail, start, settle, heard], memory=True, own=failed, cited=True, checked="carries"
    )
    assert mixed.flags == ["earlier_period", "own_failures", "told", "watched"]
    assert {
        ref.content_hash,
        older.turn_id + "/act_items",
        final.turn_id + "/act_settled",
        "check",
    } <= set(mixed.trace)
    assert mixed == score(
        [fail, start, settle, heard], memory=True, own=failed, cited=True, checked="carries"
    )


def test_ev05_mechanical_evidence_for_snapped_vine_and_origin(
    packet, fake_exchange, short, tmp_path
):
    from v2.inspection_export.formation_capture import capture_formation

    def deceptive_packet(**fields):
        for feedback in fields.get("action_feedback", []):
            for item in feedback["items_used"]:
                item["descriptors"] = [{"property_id": "strength", "value": "sturdy"}]
        return packet(**fields)

    paths, closed, _, _ = capture_formation(tmp_path, deceptive_packet, fake_exchange)
    dest = tmp_path / "analysis"
    index = export(*paths, dest)
    archive = InspectionArchive.open(dest)
    deliveries = [archive.read(ref) for ref in index.deliveries]
    revisions = [archive.read(ref) for ref in index.revisions]
    writes = {ref.id: archive.read(ref) for ref in index.evidence_writes}
    objective = archive.read(index.attempts).events
    model = choice(short.read(short.index.decisions[0].shard).record, "ella", 0)
    record = archive.read(index.consolidations[0].shard).record

    def score(decisions, evidence, created=False, snapshots=None):
        first = next(r for r in revisions[0].records if r.record.kind == "skill")
        creator = record.model_copy(
            update={
                "result_version": first.ref.store_version,
                "effects": [
                    ia.Effect(
                        op_id="new",
                        edits=[first.record],
                        produced_id=first.ref.id,
                        evictions=[],
                        carried_from=[],
                        bindings=[],
                    )
                ],
            }
        )
        history = History(
            deliveries, snapshots or revisions, [creator] if created else [record], evidence, 10
        )
        return Learning(history, objective, decisions, [], {}).scores()[0]

    unknown = score([], writes)
    assert unknown.attempts is None and unknown.reason == "missing originating decision"
    assert unknown.origin == "supplied"
    measured = score([model], writes, True)
    settlement = attempts(objective, [model])[model.submission.action.intent.intent_id]
    feedback = next(d for d in deliveries if d.packet.perception.action_feedback)
    skill = next(r.record.content for r in revisions[0].records if r.record.kind == "skill")
    assert predicts(skill, settlement, feedback, model.submission)
    wrong_binding = skill.hypothesis.inputs[0].model_copy(
        update={"look": skill.hypothesis.inputs[0].look.model_copy(update={"material_id": "grass"})}
    )
    guess = skill.model_copy(
        update={"hypothesis": skill.hypothesis.model_copy(update={"inputs": [wrong_binding]})}
    )
    assert not predicts(guess, settlement, feedback, model.submission)
    assert measured.origin == "self_found" and measured.creator_call == closed.change_set_call_id
    assert measured.attempts == measured.matched_expected == 1 and measured.accuracy == "1"
    assert '"vine"' in measured.prediction and '"snaps"' in measured.prediction
    assert any(source.family == "evidence_writes" for source in measured.links)
    # The settlement arrived after the fallback turn. Later model control cannot own it.
    fallback = score(
        [model.model_copy(update={"origin": "fallback"}), choice(model, "ella", 8)], writes, True
    )
    assert fallback.fallback_attempts == 1 and fallback.attempts == 0 and fallback.accuracy is None
    assert "incomplete evidence writes" in score([], {}, True).reason
    empty = score([], {}, True, revisions[:1])
    assert empty.attempts == 0 and empty.reason == "no qualifying observations"
    supplied = score([], {}, snapshots=revisions[-1:])
    assert supplied.supplied_attempts == 1 and supplied.attempts == 0
    assert archive.read(index.metrics).resident_analysis.skills[0] == unknown
