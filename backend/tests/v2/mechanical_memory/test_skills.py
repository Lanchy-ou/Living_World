"""MF-03 and MF-22 exercise the writer through delivered packet and day-log members."""

from v2.mechanical_memory.mechanical_skill_support import add_skill


def _look(archetype=None, material=None, **words):
    return {
        "archetype_id": archetype,
        "material_id": material,
        "descriptors": [{"property_id": key, "word": word} for key, word in words.items()],
    }


def _use(identity, role, quantity, archetype, material=None, **words):
    return {
        "entity_id": identity,
        "role": role,
        "quantity": quantity,
        "archetype_id": archetype,
        "material_id": material,
        "descriptors": [{"property_id": key, "value": word} for key, word in words.items()],
    }


def _skill_store(actor, *recipes):
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore(actor)
    for status, recipe in recipes:
        add_skill(store, status, recipe)
    return store


def _report(kind, subject):
    return dict(kind=kind, subject_id=subject, addressed=None, band=None, threshold_id=None)


def _feedback(identity, *, items=(), target=None, phenomena=(), **fields):
    return {
        "intent_id": identity,
        "status": "done",
        "stop_reason": None,
        "failure_code": None,
        "inspected": None,
        "items_used": list(items),
        "start_target": target,
        "phenomena": list(phenomena),
        **fields,
    }


def _observation(identity, tick, phase, *, target, look, verb, items=(), phenomena=()):
    return {
        "actor_id": identity.split(":")[0],
        "intent_id": identity,
        "action": "act",
        "verb": verb,
        "tick": tick,
        "phase": phase,
        "target": target,
        "start_target": look,
        "visible_items": list(items),
        "received_items": [],
        "phenomena": list(phenomena),
    }


def test_mf_03_skill_counts_only_fitting_own_and_paired_watched_attempts(packet, audit):
    from living_island.agents.v2.context.day_log import DayLog
    from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery
    from living_island.memory.v2.mechanical import MechanicalWriter
    from living_island.sim.v2.harness.agreement_facts import mechanical_delivery
    from living_island.world.v2.protocol import Intent

    vine = _look("fibre", "vine", texture="sturdy")
    recipe = {
        "verb": "bind",
        "target": {"terrain": "rock"},
        "instruments": [_look("pick"), _look("pick", "flint")],
        "inputs": [{"quantity": 3, "look": vine}],
        "expected": ["bound", "firm"],
        "circumstances": None,
    }
    store = _skill_store("ella", ("active", recipe), ("refuted", recipe))
    writer = MechanicalWriter(store)
    words = {"bound": "It holds.", "firm": "It is firm.", "snaps": "The fibres snap."}
    log = DayLog("p:ella:1", audit, phenomena=words)
    target = {"kind": "tile", "position": {"x": 1, "y": 0}}
    look = dict(target, terrain="rock")
    # Two held stacks appear equally sturdy. One snaps on the second attempt.
    # The broad instrument slot must leave the flint pick for the narrower slot.
    picks = [
        _use("pick-a", "instrument", 1, "pick", "flint"),
        _use("pick-b", "instrument", 1, "pick", "stone"),
    ]
    fibres = [
        _use("stack-a", "input", 2, "fibre", "vine", texture="sturdy"),
        _use("stack-b", "input", 1, "fibre", "vine", texture="sturdy"),
    ]
    complete = picks + fibres

    def own(tick, uses, expected, **fields):
        identity = f"ella:t{tick:06}:a"
        intent = Intent.model_validate(
            dict(
                intent_id=identity,
                turn_id=identity[:-2],
                actor_id="ella",
                action="act",
                verb="bind",
                target=target,
                instruments=[{"kind": "item", "id": p["entity_id"]} for p in picks],
                inputs=[{"item": {"kind": "held", "archetype_id": "fibre"}, "quantity": 3}],
                params={},
                reason=None,
            )
        )
        result = _feedback(identity, items=uses, target=look, phenomena=expected, **fields)
        delivery = FilteredDelivery(
            packet(
                tick=tick, action_feedback=[result], reports=[_report("action_ended", identity)]
            ),
            {identity: FeedbackSource("bind", 0)},
        )
        return writer.deliver(
            mechanical_delivery(delivery, log.deliver(delivery), {identity: intent})
        )

    own(1, complete, ["bound", "firm"])
    own(2, complete, ["bound", "snaps"])
    assert not own(3, picks + [fibres[0], dict(fibres[1], material_id="grass")], ["bound", "firm"])
    assert not own(4, complete, [], status="failed", failure_code="OUT_OF_REACH")
    assert not own(5, complete, [], status="stopped", stop_reason="own_choice")

    def watch(tick, phases):
        observations = [
            _observation(
                f"{resident}:t000001:a",
                tick,
                phase,
                verb="bind",
                target=target,
                look=look,
                items=complete if phase == "start" else (),
                phenomena=["bound", "firm"] if phase == "settle" else (),
            )
            for resident, phase in phases
        ]
        delivery = FilteredDelivery(
            packet(
                tick=tick,
                observed_actions=observations,
                reports=[
                    _report("action_observed", i)
                    for i in sorted({view["intent_id"] for view in observations})
                ],
            )
        )
        writes = writer.deliver(mechanical_delivery(delivery, log.deliver(delivery)))
        return [write for write in writes if write.skill is not None]

    assert not watch(6, [("mia", "start"), ("ryan", "start"), ("sam", "start")])
    receipts = watch(7, [("mia", "settle"), ("zoe", "settle"), ("sam", "stop")])
    assert len(receipts) == 1 and receipts[0].skill.intent_id == "mia:t000001:a"
    live, refuted = (record for record in store.snapshot.records() if record.kind == "skill")
    assert live.content.evidence.model_dump() == {
        "attempts": 2,
        "matched_expected": 1,
        "other_outcomes": 1,
        "last_attempt_tick": 2,
        "watched": 1,
        "watched_matched": 1,
    }
    assert refuted.content.evidence.model_dump(exclude_defaults=True) == {}


def test_mf_22_fallback_handback_keeps_progress_and_joins_watcher_evidence(packet, audit):
    from living_island.agents.types import OwnProfile, PolicyConfig
    from living_island.agents.v2.context.day_log import DayLog
    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.agents.v2.context.state import render_current_state
    from living_island.memory.v2.mechanical import MechanicalWriter
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.compat.policy_host import PolicyCheckpoint, PolicyHost
    from living_island.sim.v2.harness.agreement_facts import (
        actor_feedback_members,
        mechanical_delivery,
    )
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world import protocol as v1
    from living_island.world.v2 import protocol as wap

    target = {"kind": "entity", "id": "tree-1"}
    look = dict(target, archetype_id="fruit_tree", material_id=None, descriptors=[])
    private = "private planner rationale"
    legacy = v1.ActionIntent.model_validate(
        dict(
            intent_id="legacy",
            plan_id="plan",
            actor_id="ella",
            action_type="gather",
            target=target,
            parameters={},
            reason=private,
        )
    )
    config = PolicyConfig(
        policy_id="random-v0",
        seed=1,
        max_plan_actions=1,
        map_width=3,
        map_height=3,
        script_sha256=None,
        source_trace_sha256=None,
    )
    profile = OwnProfile(profile_id="ella", initial_goal="Find fruit.")
    host = PolicyHost(config, profile, 36, restored=PolicyCheckpoint(queue=(legacy,)))
    needs = [
        dict(need_id=name, band="good") for name in ("satiety", "hydration", "stamina", "health")
    ]
    fallback = host.propose(
        TurnRequest(packet(tick=1, needs=needs), 1, ()), "island", fallback=True
    )
    host.commit(fallback)
    identity = fallback.submission.action.intent.intent_id
    assert fallback.submission.utterance is None
    # A real checkpoint round-trip occurs before delivery acknowledgement.
    host = PolicyHost(
        config,
        profile,
        36,
        restored=PolicyCheckpoint.model_validate_json(host.checkpoint().model_dump_json()),
    )
    recipe = {
        "verb": "gather",
        "target": _look("fruit_tree"),
        "inputs": [],
        "instruments": [],
        "circumstances": None,
        "expected": ["picks_fruit"],
    }
    actor = MechanicalWriter(_skill_store("ella", ("active", recipe)))
    actor_log = DayLog("p:ella:1", audit, phenomena={})
    observed = _skill_store("mia", ("active", recipe))
    witness = MechanicalWriter(observed)
    witness_log = DayLog("p:mia:1", audit, phenomena={"picks_fruit": "Fruit falls."})

    def watched(tick, phase):
        view = _observation(
            identity,
            tick,
            phase,
            target=target,
            look=look,
            verb="gather",
            phenomena=["picks_fruit"] if phase == "settle" else (),
        )
        delivery = FilteredDelivery(
            packet(
                actor="mia",
                tick=tick,
                observed_actions=[view],
                reports=[_report("action_observed", identity)],
            )
        )
        entries = witness_log.deliver(delivery)
        return mechanical_delivery(delivery, entries), entries[0]

    start, start_entry = watched(2, "start")
    assert all(write.skill is None for write in witness.deliver(start))
    running = dict(
        intent_id=identity,
        action="act",
        verb="gather",
        tick_started=1,
        progress="halfway",
        start_target=look,
        items=[],
    )
    middle = packet(tick=2, needs=needs, running_action=running)
    host.ingest(middle)
    handback = host.resume_model(
        TurnRequest(middle, 2, ()),
        "island",
        wap.ModelTurn(action=wap.ContinueAction(kind="continue"), utterance=None),
    )
    host.commit(handback)
    result = _feedback(identity, target=look, phenomena=["picks_fruit"])
    ended = packet(
        tick=3, needs=needs, action_feedback=[result], reports=[_report("action_ended", identity)]
    )
    for raw in (middle, ended):
        host.ingest(raw)
        public = host.model_packet(raw)
        assert not public.perception.action_feedback
        if raw is middle:
            current = public.perception.running_action
            assert current.progress == "halfway" and current.start_target is None
        else:
            assert public.perception.running_action is None
            assert [(r.kind, r.subject_id) for r in public.reports] == [("action_ended", None)]
        # A neutral action end schedules the model; it has no memory result member.
        delivery = FilteredDelivery(
            raw.model_copy(update={"perception": public.perception, "reports": []})
        )
        parts = render_current_state(delivery.packet, reasons=(), time_of_day="morning").parts
        words = " ".join(part.text for part in parts)
        assert private not in words and "picks_fruit" not in words
        if raw is middle:
            assert "Running gather, halfway" in words
        entries = actor_log.deliver(delivery)
        assert not entries and not actor.deliver(mechanical_delivery(delivery, entries))

    settle, settle_entry = watched(3, "settle")
    resumed = MechanicalWriter(observed, restored=witness.checkpoint())
    before = observed.snapshot
    original = before.ref("m:mia:1")
    receipts = resumed.deliver(settle)
    (receipt,) = (write for write in receipts if write.skill is not None)
    assert receipt.skill.hypothesis == original
    assert (receipt.skill.actor_id, receipt.skill.intent_id) == ("ella", identity)
    assert receipt.skill.delta == {"watched": 1, "watched_matched": 1}
    for member, entry in zip(receipt.members, (start_entry, settle_entry), strict=True):
        assert member.delivery_id == entry.delivery_id and member.entry_id == entry.id
        assert (
            member.entry_revision == entry.revision
            and member.path == "perception.observed_actions[0]"
        )
    actor_member = actor_feedback_members((ended,))[identity]
    assert actor_member.delivery_id == ended.delivery_id
    assert actor_member.path == "perception.action_feedback[0]" and actor_member.entry_id is None
    assert observed.snapshot.read(observed.snapshot.ref(original.id)).content.evidence.watched == 1
    # Replay from before acknowledgement reproduces both revisions and the exact joins.
    replay = MechanicalWriter(MemoryStore.from_snapshot(before), restored=witness.checkpoint())
    assert replay.deliver(settle) == receipts
    assert not resumed.deliver(settle)
