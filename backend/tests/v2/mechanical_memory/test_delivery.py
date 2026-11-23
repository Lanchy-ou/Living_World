"""Mechanical writes at the real gift, consumption and fallback packet boundaries."""

from functools import partial

from v2.engine.conftest import pack as pack
from v2.engine.conftest import setup as setup
from v2.engine.perception.conftest import make_world as make_world
from v2.mechanical_memory.mechanical_delivery_support import (
    BODY,
    GIFT_STACKS,
    SLEEP_RULE,
    A,
    B,
    C,
    entity,
    pending,
    step,
    turn,
)
from v2.mechanical_memory.mechanical_skill_support import add_skill


class Mind:
    def __init__(self, owner, audit):
        from living_island.agents.v2.context.day_log import DayLog
        from living_island.memory.v2.mechanical import MechanicalWriter
        from living_island.memory.v2.store import MemoryStore

        self.log = DayLog(
            f"p:{owner}:1",
            audit,
            phenomena={"snaps": "It snaps.", "finds_nothing": "There is nothing to take."},
        )
        self.store = MemoryStore(owner)
        self.writer = MechanicalWriter(self.store)

    def deliver(self, packet, intents, *, report_positions=None, feedback_positions=None):
        from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery
        from living_island.sim.v2.harness.agreement_facts import mechanical_delivery

        sources = {}
        for idx, feedback in enumerate(packet.perception.action_feedback):
            intent = intents[feedback.intent_id]
            slot = idx if feedback_positions is None else feedback_positions[feedback.intent_id]
            sources[intent.intent_id] = FeedbackSource(intent.verb or intent.action, slot)
        delivery = FilteredDelivery(packet, sources, report_positions=report_positions)
        evidence = mechanical_delivery(delivery, self.log.deliver(delivery), intents)
        return self.writer.deliver(evidence)

    def seed_skill(self, verb, target, inputs=()):
        hypothesis = dict(
            verb=verb,
            target=target,
            inputs=list(inputs),
            instruments=[],
            circumstances=None,
            expected=["snaps"],
        )
        return add_skill(self.store, "active", hypothesis)

    def quantities(self, direction):
        return {
            (rec.content.about, transfer.archetype_id): transfer.quantity
            for rec in self.store.snapshot.records()
            if rec.kind == "social"
            for transfer in getattr(rec.content.facts, direction)
        }


def _intent_map(*turns):
    return {turn.action.intent.intent_id: turn.action.intent for turn in turns}


def _gift(make_world, control):
    """Publish the M12 three-tick transfer, with an actual held-stack merge."""
    sleeping = control in ("waking", "asleep")
    world = make_world(
        [(A, 2, 1), (B, 3, 1), (C, 3, 2)],
        settings=BODY,
        rules=SLEEP_RULE,
        instances=GIFT_STACKS,
        night=0 if control == "dark" else 4,
        start=1170 if control == "dark" else 360,
    )
    submissions = []
    if sleeping:
        rest = turn(
            world,
            B,
            "act",
            verb="sleep",
            params={"duration_ticks": 6 if control == "waking" else 7},
        )
        submissions.append(rest)
        step(world, rest)
        step(world)
        step(world)
    before = pending(world, B).perception.inventory[0]
    give = turn(
        world,
        A,
        "give",
        target=entity(B, "resident"),
        params={"item": {"kind": "held", "archetype_id": "arch_a"}, "quantity": 1},
    )
    submissions.append(give)
    step(world, give)
    step(world)
    if sleeping:
        assert pending(world, B).perception.awareness == "asleep"
    if control == "failed":
        move = turn(world, B, "move_to", target={"kind": "tile", "position": {"x": 4, "y": 1}})
        submissions.append(move)
        step(world, move)
    else:
        step(world)
    after = pending(world, B).perception.inventory[0]
    assert before.entity_id == after.entity_id == "gift_survivor"
    return world, _intent_map(*submissions), after.quantity - before.quantity


def test_mm24_equal_inventory_changes_distinguish_witnessed_merged_portions(make_world, audit):
    for control, expected in [("waking", {(A, "arch_a"): 1}), ("dark", {})]:
        world, intents, increase = _gift(make_world, control)
        assert increase == 1
        recipient = Mind(B, audit)
        delivery = pending(world, B)
        assert delivery.perception.awareness == "awake"
        if control == "waking":
            assert any(report.kind == "woke" for report in delivery.reports)
            (phase,) = delivery.perception.observed_actions
            (portion,) = phase.received_items
            assert (phase.phase, portion.entity_id) == ("settle", "gift_source")
        else:
            assert delivery.perception.observed_actions == []
        recipient.deliver(delivery, intents)
        assert recipient.quantities("received") == expected


def test_mf18_transfer_controls_and_one_tick_consumed_start_look(make_world, audit):
    for control in ("waking", "asleep", "dark", "failed"):
        world, intents, increase = _gift(make_world, control)
        giver, target, observer = (Mind(owner, audit) for owner in (A, B, C))
        for owner, mind in zip((A, B, C), (giver, target, observer), strict=True):
            mind.deliver(pending(world, owner), intents)
        assert increase == (control != "failed")
        assert giver.quantities("given") == ({} if control == "failed" else {(B, "arch_a"): 1})
        assert target.quantities("received") == ({(A, "arch_a"): 1} if control == "waking" else {})
        assert observer.quantities("received") == {}

    rule = """
[[rule]]
id = "consume_cord"
trigger = "verb:strike"
work_ticks = 1
target = { where = { archetype = "arch_c" } }
inputs = [{ slot = "cord", where = { archetype = "arch_a" }, qty = 1 }]
outputs = [{ archetype = "arch_a", quantity = 1, at = "actor" }]
phenomena = { success = ["snaps"] }
"""
    held = """
[[instance]]
id = "cord"
archetype = "arch_a"
at = { holder = "res_a" }
properties = { strength = 2 }
apparent = { hardness = 1 }
tell = ["strength"]
"""
    target_look = dict(archetype_id="arch_c", material_id=None, descriptors=[])
    input_look = dict(
        archetype_id="arch_a",
        material_id="mat_a",
        descriptors=[dict(property_id="hardness", word="soft")],
    )
    for receipt_only in (False, True):
        world = make_world([(A, 2, 1), (B, 3, 1)], rules=rule, instances=held)
        assert "inst_c" in world.state.exposure_receipts_by_resident[A].entities
        if receipt_only:
            world.state.visible_entities_by_resident[A].remove("inst_c")
        strike = turn(
            world,
            A,
            "act",
            verb="strike",
            target=entity("inst_c"),
            inputs=[{"item": {"kind": "item", "id": "cord"}, "quantity": 1}],
        )
        step(world, strike)
        result = pending(world, A)
        (feedback,) = result.perception.action_feedback
        assert (feedback.start_target is None) == receipt_only
        assert "cord" not in [item.entity_id for item in result.perception.inventory]
        actor = Mind(A, audit)
        key = actor.seed_skill("strike", target_look, [dict(look=input_look, quantity=1)])
        actor.deliver(result, _intent_map(strike))
        revision = actor.store.snapshot
        evidence = revision.read(revision.ref(key)).content.evidence
        assert evidence.attempts == evidence.matched_expected == int(not receipt_only)


def test_mf15_filtered_fallback_after_restore_keeps_senses_and_watcher(make_world, audit, tmp_path):
    from rule_policy_builders import config

    from living_island.agents.types import OwnProfile
    from living_island.agents.v2.context.state import render_current_state
    from living_island.memory.v2.mechanical import MechanicalWriter
    from living_island.memory.v2.store import MemoryStore
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import FixturePolicy, action
    from living_island.sim.v2.compat.policy_host import (
        PolicyHost,
        PolicySession,
        UseFallback,
        restore_policies,
    )
    from living_island.world.v2 import protocol as wap

    rule = """
[[rule]]
id = "delayed_gather"
trigger = "verb:gather"
target = { where = { archetype = "basket" } }
work_ticks = 3
success_per_mille = 0
phenomena = { chance_failed = ["snaps", "finds_nothing"] }
"""
    basket = """
[[archetype]]
id = "basket"
kind = "item"
stackable = false
matter = { mineral = 1 }
components = { store = { archetype = "arch_a", count = 1, capacity = 2 } }
"""
    placed = """
[[instance]]
id = "basket_1"
archetype = "basket"
at = { tile = [1, 1] }
"""
    world = make_world(
        [(A, 2, 1), (B, 3, 1)],
        settings=BODY.replace("invalid_attempt_ticks = 1", "invalid_attempt_ticks = 3"),
        rules=SLEEP_RULE + rule,
        archetypes=basket,
        instances=GIFT_STACKS + placed,
    )
    journal = PacketJournal(tmp_path / "packets", world.run_id)
    minds = {who: Mind(who, audit) for who in (A, B)}
    target = dict(archetype_id="basket", material_id=None, descriptors=[])
    skills = {who: mind.seed_skill("gather", target) for who, mind in minds.items()}
    plans = {
        (A, 1): (action("gather", entity("basket_1")),),
        (A, 5): (action("gather", entity("inst_c")),),
    }

    def hosts(restored=None):
        return {
            who: PolicyHost(
                config(width=9, height=6),
                OwnProfile(profile_id=who, initial_goal="Explore"),
                6,
                restored=restored[who] if restored is not None else None,
                policy_factory=partial(FixturePolicy, overrides=plans, observed=A),
            )
            for who in minds
        }

    received = {}
    physical_packets = {}
    intents = {}
    model_ticks = []

    def deliver(public):
        received[public.actor_id, public.observed_tick] = public
        raw = pending(session.world, public.actor_id)
        reports = [report for report in public.reports if isinstance(report, wap.WorldReport)]
        physical = wap.BoundaryDelivery(
            delivery_id=public.delivery_id,
            actor_id=public.actor_id,
            observed_tick=public.observed_tick,
            perception=public.perception,
            reports=reports,
        )
        physical_packets[public.actor_id, public.observed_tick] = physical
        minds[public.actor_id].deliver(
            physical,
            intents,
            report_positions=tuple(raw.reports.index(report) for report in reports),
            feedback_positions={
                result.intent_id: i for i, result in enumerate(raw.perception.action_feedback)
            },
        )
        return public.actor_id == A and public.observed_tick in (2, 6)

    def choose(public):
        who, tick = public.actor_id, public.observed_tick
        if who == A and tick in (1, 5):
            return UseFallback("offline model failure")
        if who == A:
            model_ticks.append(tick)
        if public.perception.running_action is not None:
            return wap.ModelTurn(action=wap.ContinueAction(kind="continue"), utterance=None)
        if who == B and tick == 1:
            command = "give"
            towards = entity(A, "resident")
            params = {"item": {"kind": "held", "archetype_id": "arch_a"}, "quantity": 1}
        else:
            command, towards, params = "wait", None, {}
        return wap.ModelTurn(
            action=wap.ModelIntentAction(
                kind="intent",
                intent=wap.IntentShape(
                    action=command,
                    verb=None,
                    target=towards,
                    instruments=[],
                    inputs=[],
                    params=params,
                    reason=None,
                ),
            ),
            utterance=None,
        )

    def advance(session):
        result = session.advance()
        boundary = session.runner.manifest.boundaries[-1]
        for submission in boundary.submissions:
            if submission.action.kind == "intent":
                intent = submission.action.intent
                intents[intent.intent_id] = intent
        return result

    session = PolicySession(world, hosts(), journal, model=choose, model_delivery=deliver)
    advance(session)
    advance(session)
    (fallback,) = session.runner.manifest.boundaries[-1].fallback_turns
    assert fallback.submission.utterance is None
    own_log = minds[A].log
    assert own_log.response(1, fallback.submission.turn_id, None) is None
    intent_id = fallback.submission.action.intent.intent_id

    def restore(session):
        path = tmp_path / f"before-delivery-{session.world.tick}.json"
        save_checkpoint(path, session.world, journal, session.checkpoint())
        restored = load_checkpoint(path, session.world.pack.source, journal)
        assert session.world.pending_packets() == restored.world.pending_packets()
        for mind in minds.values():
            checkpoint = mind.writer.checkpoint()
            mind.store = MemoryStore.from_snapshot(mind.store.snapshot)
            mind.writer = MechanicalWriter(mind.store, restored=checkpoint)
        return PolicySession(
            restored.world,
            hosts(restore_policies(restored.sim_checkpoint)),
            journal,
            model=choose,
            model_delivery=deliver,
        )

    session = restore(session)
    advance(session)
    settled = advance(session)
    own = next(act for act in settled.actions if act.intent_id == intent_id)
    assert own.settlement.kind == "chance_failed" and own.visible_feedback.items_used
    assert own.visible_feedback.phenomena == ["finds_nothing", "snaps"]
    advance(session)
    assert model_ticks == [0, 2, 4]
    assert received[A, 2].perception.running_action.intent_id == intent_id
    assert not received[A, 4].perception.action_feedback
    assert any(r.kind == "action_ended" and r.subject_id is None for r in received[A, 4].reports)
    state = render_current_state(
        physical_packets[A, 4], reasons=("action_ended",), time_of_day="day"
    )
    assert any("gift_source" in p.text and "quantity 3" in p.text for p in state.parts)
    assert any("satiety" in p.text for p in state.parts)
    assert any(e.type == "body_change" for e in own_log.entries)
    assert minds[A].quantities("received") == {(B, "arch_a"): 1}

    # This second gather has a generic, delayed world failure. The handback
    # takes place while it is still running; restore its pending end packet too.
    advance(session)
    (second,) = session.runner.manifest.boundaries[-1].fallback_turns
    failed_id = second.submission.action.intent.intent_id
    assert second.submission.utterance is None
    assert own_log.response(5, second.submission.turn_id, None) is None
    advance(session)
    ended = advance(session)
    failure = next(act for act in ended.actions if act.intent_id == failed_id)
    assert (failure.tick_finished, failure.visible_feedback.status) == (8, "failed")
    assert failure.visible_feedback.failure_code == "INVALID_TARGET"
    session = restore(session)
    advance(session)
    assert model_ticks == [0, 2, 4, 6, 8]
    assert received[A, 6].perception.running_action.intent_id == failed_id
    assert not received[A, 8].perception.action_feedback
    assert failed_id not in received[A, 8].model_dump_json()
    assert all(e.type != "own_response" for e in own_log.entries)
    assert not any(
        e.ref.kind == "feedback" and e.ref.intent_id in {intent_id, failed_id}
        for e in own_log.entries
    )
    assert all(
        "offline model failure" not in e.text and "snaps" not in e.text for e in own_log.entries
    )
    for who, expected in [(A, 0), (B, 1)]:
        snapshot = minds[who].store.snapshot
        facts = snapshot.read(snapshot.ref(skills[who])).content.evidence
        assert facts.attempts == 0
        assert facts.watched == facts.watched_matched == expected
    phases = [
        e.ref.phase for e in minds[B].log.entries if getattr(e.ref, "intent_id", None) == intent_id
    ]
    assert phases == ["start", "settle"]
