"""DL-06 and DL-23, using direct packet deliveries and the journal's exact bytes."""

from hashlib import sha256


def _report(kind, subject=None, **data):
    return dict(kind=kind, subject_id=subject, band=None, threshold_id=None, addressed=None) | data


def _item(identity, word="long"):
    return dict(
        entity_id=identity,
        archetype_id="cord",
        material_id="vine",
        descriptors=[{"property_id": "length", "value": word}],
    )


def _entity(identity, word="long"):
    return dict(
        _item(identity, word),
        kind="item",
        quantity=1,
        position={"x": 1, "y": 2},
        observable_signs=[],
    )


def _running(action, verb, intent, progress=None):
    return dict(
        action=action,
        verb=verb,
        intent_id=intent,
        tick_started=0,
        progress=progress,
        start_target=None,
        items=[],
    )


def _feedback(intent, **fields):
    return (
        dict(
            intent_id=intent,
            status="done",
            failure_code=None,
            stop_reason=None,
            inspected=None,
            start_target=None,
            items_used=[],
            phenomena=[],
        )
        | fields
    )


def test_dl_06_append_only_day_log(packet, audit, tmp_path):
    from living_island.agents.v2.context.day_log import DayLog
    from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery, OwnSpeech
    from living_island.agents.v2.context.entries import DeliberateRecall, LocalRecall
    from living_island.memory.v2.projections import ProjectedRevision, ResidentRecord, RevisionRef
    from living_island.memory.v2.records import Innate, Intention
    from living_island.world.v2.protocol import Utterance

    period = "p:ella:1"
    log = DayLog(period, audit, phenomena={"snap": "The fibres part."})
    first = "ella:t000001:a"
    second = "ella:t000002:a"
    cue = dict(
        cue_id="tracks",
        position={"x": 2, "y": 4},
        detail_level="near",
        physical_description="shallow prints",
        direction="north",
    )
    # This delivery follows an original fallback feedback slot. The independent
    # sight, body, and own adopted action survive sim's provenance projection.
    physical = packet(
        tick=1,
        action_feedback=[
            _feedback(
                first,
                inspected=_item("rope", "dry fibres"),
                items_used=[dict(_item("rope"), role="instrument", quantity=1)],
                phenomena=["snap"],
            )
        ],
        running_action=_running("act", "weave", second, "halfway"),
        visible_entities=[_entity("rope")],
        environmental_cues=[cue],
        last_utterance_feedback={"utterance_id": "spoken-1", "failure_code": None},
        heard_utterances=[
            dict(
                speaker_id="ryan",
                addressee_id=None,
                text="Hello.",
                speech_act="statement",
                utterance_id="heard-1",
                terms=None,
                in_reply_to=None,
                heard_at_tick=1,
            )
        ],
        reports=[
            _report("action_ended", first),
            _report("need_band_changed", "satiety", band="low"),
            _report("need_threshold_crossed", "hydration", threshold_id="urgent"),
            _report("utterance_heard", "heard-1", addressed=False),
            _report("entity_first_seen", "rope"),
            _report("entity_first_seen", "tracks"),
            _report("progress_step", second),
            _report("progress_step", first),
        ],
    )
    own_words = Utterance(
        addressee_id="ryan", speech_act="statement", text="I see it.", terms=None, in_reply_to=None
    )
    projection = FilteredDelivery(
        physical,
        {first: FeedbackSource("weave", 1)},
        OwnSpeech(physical.perception.last_utterance_feedback, own_words),
        tuple(range(1, 1 + len(physical.reports))),
    )
    initial = log.deliver(projection)
    assert {entry.type for entry in initial} == {
        "action_result",
        "inspection",
        "utterance_result",
        "heard_speech",
        "observation",
        "body_change",
        "progress",
    }
    (result,) = [e for e in initial if e.type == "action_result"]
    assert result.text.startswith("Your weave ended: done") and "The fibres part." in result.text
    assert {
        "verb:weave",
        "entity:rope",
        "archetype:cord",
        "material:vine",
        "phenomenon:snap",
    } == set(result.about)
    assert result.member_paths == ("perception.action_feedback[1]", "reports[1]")
    (said,) = [e for e in initial if e.type == "utterance_result"]
    assert said.about == ("spoke:spoken-1",)
    assert any(e.text.startswith("You said to ryan:") for e in initial)
    assert any(e.text.startswith("ryan said to everyone:") for e in initial)
    assert any("You notice shallow prints" in e.text for e in initial)
    assert any(e.about == ("need:hydration",) and "urgent" in e.text for e in initial)
    assert any(e.text == "Your weave is halfway." for e in initial)
    assert any(e.text == "Your weave progressed." and e.about == ("verb:weave",) for e in initial)

    # Muting gives no turn and never reaches the perception logger.
    unchanged = packet(tick=2, visible_entities=[_entity("rope")], environmental_cues=[cue])
    assert log.deliver(FilteredDelivery(unchanged)) == ()
    different = packet(tick=3, visible_entities=[_entity("rope", "frayed")])
    (changed,) = log.deliver(FilteredDelivery(different))
    assert "frayed" in changed.text and "place:1,2" in changed.about
    raw = '{  "step": "act", "action": { "kind": "continue" }}'
    own = log.response(3, "ella:t000003", raw)
    assert own.text == raw and own.delivery_id is None and own.ref.turn_id == "ella:t000003"
    before = log.entries
    # The retry/fallback pass the empty adopted output from the host.
    assert log.response(3, "ella:t000004", None) is None and log.entries == before
    view = ResidentRecord(
        id="m:ella:1",
        owner_id="ella",
        kind="intention",
        created_tick=0,
        updated_tick=0,
        about_tick=None,
        sources=[Innate()],
        confidence=3,
        last_used_tick=None,
        use_count=0,
        supersedes=None,
        superseded_by=None,
        needs_review=False,
        gist="Bring food.",
        text="For the walk.",
        content=Intention(set_turn="ella:t000001", state="current", ended_turn=None),
    )
    revision = ProjectedRevision(RevisionRef(view.id, 2, "as-written"), view, ())
    recalled = log.recall(3, DeliberateRecall(call_id="recall-1"), revision)
    assert recalled.retrieved == revision.ref and "For the walk." in recalled.text
    assert view.id in recalled.text and recalled.delivery_id is None
    recipe = log.recall(3, LocalRecall(mode="recipe", turn_id="ella:t000003", ordinal=1), revision)
    assert recipe.ref.mode == "recipe"
    assert log.empty_recall(3, "ella:t000003", 2).text == "You cannot remember anything about that."

    sleeper = _running("act", "sleep", second)
    confirmation = packet(tick=4, awareness="asleep", running_action=sleeper)
    (asleep,) = log.deliver(FilteredDelivery(confirmation))
    assert asleep.text == "You fall asleep." and asleep.ref.turn_id == second.removesuffix(":a")
    frozen = log.entries
    during_sleep = packet(
        tick=5,
        awareness="asleep",
        running_action=sleeper,
        reports=[_report("need_band_changed", "health", band="good")],
    )
    (body,) = log.deliver(FilteredDelivery(during_sleep))
    assert body.type == "body_change" and body not in frozen
    next_period = DayLog("p:ella:2", audit, phenomena={}, prior_awareness="asleep")
    assert [e.type for e in next_period.deliver(FilteredDelivery(during_sleep))] == ["body_change"]
    (wake,) = log.deliver(FilteredDelivery(packet(tick=6, reports=[_report("woke")])))
    assert wake.text == "You wake." and wake.ref.report_kind == "woke"
    assert log.entries[: len(frozen)] == frozen

    failure = packet(
        tick=7, last_utterance_feedback={"utterance_id": None, "failure_code": "OUT_OF_HEARING"}
    )
    (failed,) = log.deliver(
        FilteredDelivery(
            failure, own_speech=OwnSpeech(failure.perception.last_utterance_feedback, own_words)
        )
    )
    assert failed.about == () and failed.ref.utterance_id is None
    assert failed.text == "Your words to ryan were not said: out of hearing"
    assert failed.member_paths == ("perception.last_utterance_feedback",)
    assert [e.id for e in log.entries] == [
        f"d:{period}:{n}" for n in range(1, len(log.entries) + 1)
    ]
    for entry in log.entries:
        assert (tmp_path / entry.revision).read_bytes() == entry.canonical
        fragment = (tmp_path / entry.fragment_sha256).read_bytes()
        assert fragment == entry.part.text.encode()
        assert sha256(fragment).hexdigest() == entry.fragment_sha256


def test_dl_23_inspected_watched_and_verbatim_members(packet, audit):
    from living_island.agents.v2.context.day_log import DayLog
    from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery

    log = DayLog("p:ella:1", audit, phenomena={"slides": "It slips."})
    mine, theirs = "ella:t000001:a", "ryan:t000001:a"
    look = _item("fibre", "dry")
    material = dict(look, role="item", quantity=2)
    base = dict(
        intent_id=theirs,
        actor_id="ryan",
        action="give",
        verb=None,
        target={"kind": "resident", "id": "ella"},
        start_target=None,
        received_items=[],
        visible_items=[],
        phenomena=[],
    )
    identifier = "resident-" + "x" * 500
    heard = dict(
        utterance_id="heard-proposal",
        speaker_id=identifier,
        addressee_id="ella",
        speech_act="propose",
        text="Q" * 499 + "?",
        in_reply_to=None,
        terms=dict(
            promisor_id=identifier,
            promisee_id="ella",
            due_tick=43,
            what=dict(kind="be_at", position={"x": 0, "y": 1}),
        ),
        heard_at_tick=9,
    )
    description = "rough grain " * 130
    p = packet(
        tick=9,
        action_feedback=[_feedback(mine, inspected=_item("fibre", description))],
        heard_utterances=[heard],
        observed_actions=[
            base
            | dict(
                tick=8,
                phase="start",
                visible_items=[material],
                start_target={
                    "kind": "resident",
                    "id": "ella",
                    "archetype_id": None,
                    "material_id": None,
                    "descriptors": [{"property_id": "sign", "value": "tired"}],
                },
            ),
            base | dict(tick=9, phase="settle", received_items=[material], phenomena=["slides"]),
        ],
        reports=[
            _report("action_ended", mine),
            _report("action_observed", theirs),
            _report("utterance_heard", "heard-proposal", addressed=True),
        ],
    )
    entries = log.deliver(FilteredDelivery(p, {mine: FeedbackSource("inspect", 0)}))
    assert all(e.delivery_id == p.delivery_id for e in entries)
    spoken, start, settle, feedback, inspection = entries
    assert spoken.verbatim == p.perception.heard_utterances[0]
    assert len(spoken.text) > 1000 and heard["text"] in spoken.text and identifier in spoken.text
    assert spoken.ref.utterance_id == heard["utterance_id"]
    assert set(spoken.about) == {"resident:ella", f"resident:{identifier}", "place:0,1"}
    assert spoken.member_paths == ("perception.heard_utterances[0]", "reports[1]")
    assert [entry.ref.phase for entry in (start, settle)] == ["start", "settle"]
    assert (start.tick, settle.tick) == (8, 9)
    assert (start.ref.intent_id, settle.ref.intent_id) == (theirs, theirs)
    assert "tired" in start.text and "2 × fibre" in start.text and "dry" in start.text
    assert "You received 2 × fibre" in settle.text and "It slips." in settle.text
    assert {
        "resident:ella",
        "resident:ryan",
        "verb:give",
        "entity:fibre",
        "material:vine",
        "archetype:cord",
        "phenomenon:slides",
    } == set(settle.about)
    assert start.member_paths == ("perception.observed_actions[0]", "reports[2]")
    assert settle.member_paths == ("perception.observed_actions[1]", "reports[2]")
    assert feedback.member_paths == ("perception.action_feedback[0]", "reports[0]")
    assert feedback.ref.intent_id == inspection.ref.intent_id == mine
    assert inspection.member_paths == ("perception.action_feedback[0].inspected",)
    assert inspection.type == "inspection"
    assert (
        inspection.text.startswith("Looking closely at fibre") and "rough grain" in inspection.text
    )
    assert len(inspection.text) <= 1000 and inspection.text.endswith(("rough…", "grain…"))
