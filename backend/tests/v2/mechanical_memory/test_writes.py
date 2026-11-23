"""Mechanical write receipts and joins at the resident and coordinator boundaries."""

import pytest


def _given(packet, audit):
    from living_island.agents.v2.context.day_log import DayLog
    from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery
    from living_island.world.v2.protocol import Intent

    mine = "ella:t000002:a"
    theirs = "zed:t000001:a"
    intent = Intent.model_validate(
        dict(
            actor_id="ella",
            turn_id="ella:t000002",
            intent_id=mine,
            action="give",
            verb=None,
            target={"kind": "resident", "id": "mia"},
            reason=None,
            instruments=[],
            inputs=[],
            params={"item": {"kind": "held", "archetype_id": "fruit"}, "quantity": 2},
        )
    )
    portion = dict(
        entity_id="fruit-1",
        role="item",
        quantity=2,
        archetype_id="fruit",
        material_id=None,
        descriptors=[],
    )
    feedback = dict(
        intent_id=mine,
        status="done",
        failure_code=None,
        stop_reason=None,
        phenomena=[],
        inspected=None,
        start_target=None,
        items_used=[portion],
    )
    watched = dict(
        actor_id="zed",
        intent_id=theirs,
        tick=2,
        phase="settle",
        action="give",
        verb=None,
        target={"kind": "resident", "id": "ella"},
        start_target=None,
        received_items=[dict(portion, entity_id="fruit-2")],
        visible_items=[],
        phenomena=[],
    )
    reports = [
        dict(kind=kind, subject_id=identity, band=None, threshold_id=None, addressed=None)
        for kind, identity in (("action_ended", mine), ("action_observed", theirs))
    ]
    # An earlier private result was removed, leaving the own result in original slot one.
    given = FilteredDelivery(
        packet(tick=2, action_feedback=[feedback], observed_actions=[watched], reports=reports),
        {mine: FeedbackSource("give", 1)},
    )
    entries = DayLog("p:ella:1", audit, phenomena={}).deliver(given)
    return given, entries, {mine: intent}


def test_mf_01_mechanical_log_versions_and_allocation(packet, audit):
    from test_agreements import AGREEMENT, _event, _exchange

    from living_island.memory.v2.mechanical import MechanicalWriter
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.harness.agreement_facts import (
        mechanical_delivery,
        project_agreement_facts,
    )

    # Both parties get one record, including the proposer asleep through acceptance.
    for owner in ("ella", "mia"):
        snapshot, _ = _exchange(owner, packet, audit)
        assert len([r for r in snapshot.records() if r.kind == "commitment"]) == 1
    given, entries, intents = _given(packet, audit)
    fact = project_agreement_facts([_event()], "ella")
    delivery = mechanical_delivery(given, entries, intents)
    store = MemoryStore("ella")
    writer = MechanicalWriter(store)
    log = writer.deliver(delivery, agreements=fact)
    assert [entry.write.before_version for entry in log] == [0, 1, 2, 3]
    assert [entry.write.after_version for entry in log] == [1, 2, 3, 4]
    changes = [entry.write.changes[0] for entry in log]
    assert [change.id for change in changes] == ["m:ella:1", "m:ella:2", "m:ella:2", "m:ella:3"]
    assert changes[2].before == changes[1].after
    assert all(
        entry.write.blobs[change.after.content_hash].id == change.id
        for entry, change in zip(log, changes, strict=True)
    )
    for receipt, entry in zip(log[:2], entries, strict=True):
        (key,) = receipt.members
        assert (key.delivery_id, key.entry_id, key.entry_revision) == (
            given.packet.delivery_id,
            entry.id,
            entry.revision,
        )
    assert [receipt.members[0].path for receipt in log[:2]] == [
        "perception.observed_actions[0]",
        "perception.action_feedback[1]",
    ]
    received, given = [
        store.snapshot.read(store.snapshot.ref(key)).content.facts
        for key in ("m:ella:1", "m:ella:2")
    ]
    assert received.received[0].quantity == given.given[0].quantity == 2
    assert log[2].agreement == log[3].agreement == fact[0]
    assert log[3].agreement.agreement_id == AGREEMENT
    assert store.snapshot.read(store.snapshot.ref("m:ella:3")).sources == []
    assert writer.deliver(delivery, agreements=fact) == ()
    assert store.snapshot.store_hash == log[-1].write.store_hash
    assert MechanicalWriter(MemoryStore("ella")).deliver(delivery, agreements=fact) == log


def test_reject_entry_from_another_delivery(packet, audit):
    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.sim.v2.harness.agreement_facts import mechanical_delivery

    _, entries, _ = _given(packet, audit)
    with pytest.raises(ValueError, match="day entry"):
        mechanical_delivery(FilteredDelivery(packet(actor="mia")), entries)


def test_reject_unrelated_submission_in_feedback_join(packet, audit):
    from living_island.sim.v2.harness.agreement_facts import mechanical_delivery

    given, entries, intents = _given(packet, audit)
    (identity,) = intents
    intents[identity] = intents[identity].model_copy(update={"intent_id": "ella:t000003:a"})
    with pytest.raises(ValueError, match="submitted intent"):
        mechanical_delivery(given, entries, intents)


def test_reject_delivery_to_another_store(packet):
    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.memory.v2.mechanical import MechanicalWriter
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.harness.agreement_facts import mechanical_delivery

    writer = MechanicalWriter(MemoryStore("ella"))
    with pytest.raises(ValueError, match="another resident"):
        writer.deliver(mechanical_delivery(FilteredDelivery(packet(actor="mia")), ()))


def test_reject_another_residents_writer_checkpoint():
    from living_island.memory.v2.mechanical import MechanicalWriter
    from living_island.memory.v2.store import MemoryStore

    checkpoint = MechanicalWriter(MemoryStore("mia")).checkpoint()
    with pytest.raises(ValueError, match="writer checkpoint"):
        MechanicalWriter(MemoryStore("ella"), restored=checkpoint)


def test_reject_misrouted_party_fact_before_writes(packet, audit):
    from test_agreements import _event

    from living_island.memory.v2.mechanical import MechanicalWriter
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.harness.agreement_facts import (
        mechanical_delivery,
        project_agreement_facts,
    )

    given, entries, intents = _given(packet, audit)
    writer = MechanicalWriter(MemoryStore("ella"))
    with pytest.raises(ValueError, match="wrong party"):
        writer.deliver(
            mechanical_delivery(given, entries, intents),
            agreements=project_agreement_facts([_event()], "mia"),
        )
    assert writer.store.snapshot.version == 0
