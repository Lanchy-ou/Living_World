"""Recipe selection uses the scheduled cues and the resident's own working period."""


def report(kind, subject, *, addressed=None, band=None):
    return {
        "kind": kind,
        "subject_id": subject,
        "addressed": addressed,
        "band": band,
        "threshold_id": None,
    }


def entity(key, kind="resident", archetype=None, material=None):
    return {
        "entity_id": key,
        "kind": kind,
        "archetype_id": archetype,
        "material_id": material,
        "descriptors": [],
        "position": {"x": 0, "y": 0},
        "quantity": None,
        "observable_signs": [],
    }


def skill(verb, *, expected=(), material=None, status="active"):
    return {
        "hypothesis": {
            "verb": verb,
            "target": None,
            "instruments": [],
            "inputs": [
                {
                    "quantity": 1,
                    "look": {"archetype_id": None, "material_id": material, "descriptors": []},
                }
            ]
            if material
            else [],
            "circumstances": None,
            "expected": list(expected),
        },
        "evidence": {},
        "status": status,
    }


def commitment(counterpart, due):
    return {
        "role": "promisor",
        "counterpart_id": counterpart,
        "terms": {
            "promisor_id": "ella",
            "promisee_id": counterpart,
            "what": {"kind": "return_item", "item_id": "cup"},
            "due_tick": due,
        },
        "due_tick": due,
        "heard_counterpart": True,
        "status": "open",
        "status_note": None,
        "agreement_id": "private:" + counterpart,
    }


def test_dl_09_strength_selection_and_period_deduplication(add_record, working_context, packet):
    from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery
    from living_island.agents.v2.context.entries import DeliberateRecall
    from living_island.agents.v2.recall.recipes import RecipeCues, RecipeRegistry, strength
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    base = add_record(store, confidence=1)
    assert [strength(base, tick) for tick in (0, 143, 144, 575, 576, 720)] == [
        60,
        60,
        50,
        30,
        20,
        20,
    ]
    used = base.model_copy(update={"last_used_tick": 576, "use_count": 5, "confidence": 4})
    assert strength(used, 576) == 160
    assert strength(used, 720) == 150

    strong = add_record(store, confidence=3)
    peer = add_record(store, confidence=3)
    ranked = [add_record(store, confidence=2) for _ in range(3)]
    prefix = add_record(store, confidence=4)
    prior = add_record(store, confidence=4)
    add_record(store, confidence=0)
    add_record(store, confidence=4, superseded_by=strong.id)
    view = store.snapshot.resident(memory_on=True)
    by_id = {r.ref.id: r for r in view.records}
    context = working_context(memories=[by_id[prefix.id]])
    context.log.recall(575, DeliberateRecall(call_id="older-query"), by_id[prior.id])
    registry = RecipeRegistry()
    body = FilteredDelivery(packet(576, [report("need_band_changed", "satiety", band="low")]))
    cues = RecipeCues.from_delivery(body, reasons=frozenset({"body"}))
    entries = registry.append(view, cues, context, "turn-1")
    assert [e.retrieved.id for e in entries] == [strong.id, peer.id, *(r.id for r in ranked)]
    for ordinal, entry in enumerate(entries, 1):
        assert (entry.ref.mode, entry.ref.turn_id, entry.ref.ordinal) == (
            "recipe",
            "turn-1",
            ordinal,
        )
        assert entry.retrieved == by_id[entry.retrieved.id].ref
    # The sixth match, exactly at strength 20, can be recalled at the next turn.
    assert [r.ref.id for r in registry.select(view, cues, context)] == [base.id]
    # Opening a fresh period releases both the prior prefix and recall exclusions.
    assert [r.ref.id for r in registry.select(view, cues, working_context(period="next"))][:2] == [
        prefix.id,
        prior.id,
    ]

    store = MemoryStore("ella")
    verb_match = add_record(store, kind="skill", content=skill("cut"))
    outcome = add_record(store, kind="skill", content=skill("bend", expected=["snaps"]))
    look = add_record(store, kind="skill", content=skill("weave", material="vine"))
    add_record(store, kind="skill", content=skill("cut", status="refuted"))

    def belief(subject, key, *topics):
        return add_record(
            store,
            content={
                "subject": {"kind": subject, "ref": key},
                "stance": "stable",
                "topics": list(topics),
            },
        )

    tree = belief("entity", "tree1")
    archetype = belief("kind_of_thing", "tree")
    water = belief("general", None, "water")
    about_mia = belief("resident", "mia")
    social = add_record(
        store,
        kind="social",
        content={
            "about": "mia",
            "trust": 2,
            "impression": "",
            "facts": {
                "given": [],
                "received": [],
                "agreements": [],
                "last_seen_tick": None,
                "last_heard_tick": None,
            },
        },
    )
    promise = add_record(store, kind="commitment", content=commitment("mia", None))
    view = store.snapshot.resident(memory_on=True)
    context = working_context()

    def selected(delivery, reasons, *, act_ids=()):
        cues = RecipeCues.from_delivery(
            delivery, reasons=frozenset(reasons), act_intent_ids=frozenset(act_ids)
        )
        return {r.ref.id for r in registry.select(view, cues, context)}

    intent = "ella:t000002:a"
    fallback = "ella:t000001:a"
    ended = report("action_ended", intent)
    feedback = {
        "intent_id": intent,
        "status": "done",
        "failure_code": None,
        "stop_reason": None,
        "phenomena": ["snaps"],
        "inspected": None,
        "start_target": None,
        "items_used": [],
    }
    action = FilteredDelivery(
        packet(576, [ended], action_feedback=[feedback]), {intent: FeedbackSource("cut", 0)}
    )
    assert selected(action, ["action_ended"], act_ids=[intent]) == {verb_match.id, outcome.id}
    assert selected(action, ["action_ended"]) == set()  # A kernel action has no act recipe.
    delayed = FilteredDelivery(packet(576, [report("action_ended", fallback)]))
    assert selected(delayed, ["action_ended"], act_ids=[fallback]) == set()
    sight = entity("tree1", "feature", "tree", "vine")
    discovery = FilteredDelivery(
        packet(576, [report("entity_first_seen", "tree1")], visible_entities=[sight])
    )
    assert selected(discovery, ["discovery"]) == {look.id, tree.id, archetype.id}
    hydration = FilteredDelivery(
        packet(576, [report("need_band_changed", "hydration", band="low")])
    )
    assert selected(hydration, ["body"]) == {water.id}
    for addressed, reason in ((True, "direct_speech"), (False, "nearby_speech")):
        speech = {
            "utterance_id": "u1",
            "speaker_id": "mia",
            "heard_at_tick": 576,
            "addressee_id": "ella" if addressed else None,
            "speech_act": "statement",
            "text": "Hello",
            "terms": None,
            "in_reply_to": None,
        }
        heard = FilteredDelivery(
            packet(
                576,
                [report("utterance_heard", "u1", addressed=addressed)],
                heard_utterances=[speech],
            )
        )
        assert selected(heard, [reason]) == {about_mia.id, social.id, promise.id}


def test_dl_22_commitments_precede_stronger_matches_at_both_cue_boundaries(
    add_record, working_context, packet
):
    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.agents.v2.recall.recipes import RecipeCues, RecipeRegistry
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    now = 576
    commitments = [
        add_record(store, kind="commitment", content=commitment(who, due), confidence=0)
        for who, due in (("mia", None), ("sol", now + 24), ("bea", now + 25), ("rui", now - 1))
    ]
    matches = [add_record(store, confidence=4) for _ in range(4)]
    delivery = FilteredDelivery(
        packet(
            now,
            [report("need_band_changed", "satiety", band="low")],
            visible_entities=[entity("mia")],
        )
    )
    cues = RecipeCues.from_delivery(delivery, reasons=frozenset({"body"}))
    result = RecipeRegistry().select(
        store.snapshot.resident(memory_on=True), cues, working_context()
    )
    assert [r.ref.id for r in result] == [
        commitments[0].id,
        commitments[1].id,
        *(r.id for r in matches[:3]),
    ]
