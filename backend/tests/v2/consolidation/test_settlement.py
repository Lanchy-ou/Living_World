"""Surviving-boundary commits, failed-period retention and the change-set wire cutoff."""

import json

import pytest

from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery
from living_island.agents.v2.context.prefix import FrozenPrefix


def _begin(coordinator, packet, start):
    from v2.consolidation.conftest import sleeping

    sleep, intents = sleeping(packet, tick=start + 1, start=start)
    coordinator.deliver(sleep, intents=intents)
    return coordinator.workflow


def _open_next(coordinator):
    coordinator.open(FrozenPrefix(coordinator.period_id, (), (), (), None))


def _seen(packet, tick, actor):
    entity = dict(
        kind="resident",
        entity_id=actor,
        archetype_id=None,
        material_id=None,
        descriptors=[],
        position={"x": 1, "y": 0},
        observable_signs=[],
        quantity=None,
    )
    return FilteredDelivery(packet(tick=tick, visible_entities=[entity]))


def _complete(workflow, transport, clock):
    # Bound the fake scheduler by the maximum of two preparations plus eight attempts.
    for _ in range(10):
        if workflow.state.stage == "ready":
            break
        delay = workflow.advance(transport, clock)
        clock.elapsed_ms += round(delay * 1000)
    assert workflow.state.stage == "ready"


def _fruit_given(packet):
    from living_island.world.v2.protocol import Intent

    identity = "ella:t000099:a"
    intent = Intent.model_validate(
        dict(
            actor_id="ella",
            turn_id="ella:t000099",
            intent_id=identity,
            action="give",
            verb=None,
            target={"kind": "resident", "id": "mia"},
            reason=None,
            instruments=[],
            inputs=[],
            params={"item": {"kind": "held", "archetype_id": "fruit"}, "quantity": 2},
        )
    )
    feedback = dict(
        intent_id=identity,
        status="done",
        failure_code=None,
        stop_reason=None,
        phenomena=[],
        inspected=None,
        start_target=None,
        items_used=[
            dict(
                entity_id="fruit",
                role="item",
                quantity=2,
                archetype_id="fruit",
                material_id=None,
                descriptors=[],
            )
        ],
    )
    return (
        FilteredDelivery(
            packet(
                tick=102,
                awareness="asleep",
                action_feedback=[feedback],
                reports=[
                    dict(
                        kind="action_ended",
                        subject_id=identity,
                        band=None,
                        threshold_id=None,
                        addressed=None,
                    )
                ],
            ),
            {identity: FeedbackSource("give", 0)},
        ),
        {identity: intent},
    )


def test_mf08_rebase_preserves_facts_and_allocation_across_restore(packet, fake_exchange):
    from living_island.memory.v2.mechanical import AgreementFact
    from living_island.memory.v2.records import Social
    from living_island.sim.v2.harness.consolidation import PeriodCoordinator
    from living_island.world.v2.protocol import Terms
    from v2.consolidation.conftest import journal, resident
    from v2.mechanical_memory.test_agreements import TERMS

    facts = {}
    original = resident(journal(facts))
    delivery = original.deliver(_seen(packet, 99, "mia"))
    observed = delivery.entries[0]
    workflow = _begin(original, packet, 100)
    clock, transport = fake_exchange(['{"read":["m:ella:1"]}'])
    workflow.advance(transport, clock)
    workflow.advance(transport, clock)
    saved = original.checkpoint()
    restored_facts = facts.copy()
    restored = PeriodCoordinator.restore(
        type(saved).model_validate_json(saved.model_dump_json()), journal(restored_facts)
    )
    assert restored.workflow.state == workflow.state

    def add(op_id, sources):
        return dict(
            op="add",
            op_id=op_id,
            ref=f"new:{op_id}",
            record=dict(
                kind="belief",
                gist="Mia is nearby",
                confidence=2,
                sources=sources,
                content=dict(
                    subject={"kind": "resident", "ref": "mia"}, stance="stable", topics=[]
                ),
            ),
        )

    update = dict(
        op="update",
        op_id="social",
        id="m:ella:1",
        gist="Generous",
        content={"impression": "Generous"},
    )
    change = workflow.state.calls[-1].call.call_id
    ops = [
        update,
        add("1", [{"kind": "observed", "entry_id": observed.id}]),
        add("2", [{"kind": "inferred", "call_id": change, "memory_ids": ["new:1"]}]),
        {"op_id": "bad", "op": "forget", "id": "m:ella:1"},
    ]
    after = []
    agreement = AgreementFact(
        agreement_id="island:0000000102:000002",
        role="promisee",
        counterpart_id="mia",
        terms=Terms.model_validate(TERMS),
        due_tick=300,
        accepted_tick=102,
        proposal_id="island:0000000099:000000",
        acceptance_id="island:0000000102:000001",
    )
    for coordinator in (original, restored):
        clock, transport = fake_exchange([json.dumps({"ops": ops})])
        _complete(coordinator.workflow, transport, clock)
        assert b"m:ella:2" not in transport.dispatches[0]
        given, intents = _fruit_given(packet)
        coordinator.deliver(given, intents=intents, agreements=[agreement])
        cutoff = coordinator.store.snapshot
        assert cutoff.read(cutoff.ref("m:ella:2")).kind == "commitment"
        boundary = coordinator.deliver(_seen(packet, 136, "zed"))
        record = boundary.record
        assert (record.outcome, record.result_version) == ("committed", cutoff.version + 1)
        assert [v.reason for v in record.verdicts] == [None, None, None, "authority"]
        assert boundary.writes[0].write.before_version == record.result_version
        latest = coordinator.store.snapshot
        social = latest.read(latest.ref("m:ella:1"))
        assert isinstance(social.content, Social)
        assert social.updated_tick == 136
        assert (social.gist, social.content.impression) == ("Generous", "Generous")
        assert social.content.facts.given[0].quantity == 2
        assert social.content.facts.agreements == [agreement.agreement_id]
        assert latest.read(latest.ref("m:ella:4")).sources[0].memory_ids == ["m:ella:3"]
        (binding,) = record.effects[2].bindings
        assert binding.revisions[0].id == record.effects[1].produced_id == "m:ella:3"
        assert binding.revisions[0].store_version == record.result_version
        assert record.write.blobs[binding.revisions[0].content_hash].id == "m:ella:3"
        assert all(coordinator.period_id in entry.id for entry in boundary.entries)
        after.append((latest.version, latest.store_hash, record))

        _open_next(coordinator)
        following = _begin(coordinator, packet, 200)
        clock, transport = fake_exchange(['{"read":[]}'])
        following.advance(transport, clock)
        following.advance(transport, clock)
        assert b"m:ella:2" in transport.dispatches[0]
        assert agreement.agreement_id.encode() not in transport.dispatches[0]
    assert after[0] == after[1]
    assert facts == restored_facts


def test_mf11_three_exhausted_provider_calls_keep_memory_and_archive_oldest(
    packet, audit, tmp_path
):
    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls.fake import FakeClock, FakeTransport, ScriptedReply
    from v2.consolidation.conftest import resident

    coordinator = resident(audit)
    coordinator.deliver(_seen(packet, 99, "mia"))
    initial = coordinator.store.snapshot
    for number in range(1, 4):
        start = 100 * number
        coordinator.log.response(start, f"turn-{number}", f"My day {number}")
        workflow = _begin(coordinator, packet, start)
        clock = FakeClock()
        provider_error = ScriptedReply(TransportResponse(503, b"{}", True))
        transport = FakeTransport(clock, [provider_error] * 4)
        _complete(workflow, transport, clock)
        assert transport.dispatches == [transport.dispatches[0]] * 4
        assert clock.elapsed_ms == 14_000
        result = coordinator.deliver(FilteredDelivery(packet(tick=start + 36)))
        assert (result.record.outcome, result.record.reason) == ("failed", "provider")
        assert result.record.pending_after == tuple(
            f"p:ella:{n}" for n in range(max(1, number - 1), number + 1)
        )
        assert coordinator.period_id == f"p:ella:{number + 1}"
        assert coordinator.store.snapshot.store_hash == initial.store_hash
        assert f"My day {number}" in [
            entry.text for entry in coordinator.checkpoint().pending[-1].context.entries
        ]
        _open_next(coordinator)
    assert [p.state for p in result.record.pending] == ["evicted", "retained", "retained"]
    assert initial.records()[0].content.about == "mia"
    evicted = json.loads((tmp_path / audit.cursor("p:ella:1", "evicted")).read_bytes())
    assert "My day 1" in [entry["text"] for entry in evicted["period"]["entries"]]


def test_mf16_only_full_periods_on_committed_change_wire_leave_pending(
    packet, audit, fake_exchange, monkeypatch
):
    from living_island.agents.v2.calls import guard
    from living_island.agents.v2.calls.contracts import Contract
    from living_island.agents.v2.calls.wire import NOTICE, frame
    from v2.consolidation.conftest import resident

    coordinator = resident(audit)
    for number in (1, 2):
        start = 100 * number
        coordinator.log.response(start, f"turn-{number}", "I remember fruit. " * 20)
        current = _begin(coordinator, packet, start)
        clock, transport = fake_exchange(["{}", "{}"])
        _complete(current, transport, clock)
        assert len(transport.dispatches) == 2
        result = coordinator.deliver(FilteredDelivery(packet(tick=start + 36)))
        assert result.record.reason == "parse"
        _open_next(coordinator)

    workflow = _begin(coordinator, packet, 300)
    clock, transport = fake_exchange(['{"read":[]}', '{"ops":[]}'])
    workflow.advance(transport, clock)
    workflow.advance(transport, clock)
    selection, change = workflow.state.calls
    assert workflow.fixed.sent_pending(selection.sent.manifest) == ("p:ella:1", "p:ella:2")
    shape = Contract("consolidation_change_set")
    lines = [p.text for p in change.authorized.assembly.parts if p.source.id != "p:ella:1"]
    counted = frame(
        shape.kind, shape.instructions, shape.schema, "\n".join([NOTICE, *lines])
    ).counted
    monkeypatch.setattr(guard, "WINDOW", counted)
    _complete(workflow, transport, clock)
    assert workflow.sent_pending_ids == ("p:ella:2",)
    result = coordinator.deliver(FilteredDelivery(packet(tick=336)))
    assert result.record.outcome == "committed"
    assert [(p.period_id, p.state) for p in result.record.pending] == [
        ("p:ella:1", "omitted"),
        ("p:ella:2", "included"),
    ]
    assert result.record.pending_after == ("p:ella:1",)


@pytest.mark.parametrize("intervening", ["edit", "remove", "create"])
def test_reject_model_owned_change_between_snapshots_before_publishing(packet, audit, intervening):
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.provenance import SentInput
    from living_island.memory.v2.validation import decode_change_set
    from living_island.sim.v2.harness.consolidation.settlement import (
        VersionConflict,
        commit_rebased,
    )
    from v2.consolidation.conftest import resident

    coordinator = resident(audit)
    coordinator.deliver(_seen(packet, 99, "mia"))
    store = coordinator.store
    frozen = store.snapshot
    staged = stage_change_set(
        store, decode_change_set('{"ops":[]}', frozen.version), SentInput("ella", "c"), 136
    )
    original = frozen.records()[0]
    if intervening == "edit":
        store.apply(frozen.version, "change_set", [original.model_copy(update={"text": "changed"})])
    elif intervening == "remove":
        store.apply(frozen.version, "change_set", [original.id])
    else:
        store.set_intention(
            tick=105, turn_id="turn", text="I will find fruit.", source=original.sources[0]
        )
    changed = store.snapshot
    with pytest.raises(VersionConflict):
        commit_rebased(store, staged)
    assert store.snapshot is changed
