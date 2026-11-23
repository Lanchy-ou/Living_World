"""World confirmation, period membership and the surviving K barrier."""

import json

import pytest

from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.context.delivery import FilteredDelivery
from living_island.agents.v2.context.prefix import FrozenPrefix
from living_island.sim.v2.harness.consolidation import PeriodCheckpoint, PeriodCoordinator
from v2.consolidation.conftest import journal as memory_journal
from v2.consolidation.conftest import resident, sleeping
from v2.engine.conftest import pack as pack
from v2.engine.conftest import setup as setup
from v2.engine.perception.conftest import make_world as make_world
from v2.working_context.test_day_log import _report


def _ready(flow, fake_exchange):
    clock, fake = fake_exchange(['{"read":[]}', '{"ops":[]}'])
    for _ in range(4):
        flow.advance(fake, clock)
    assert flow.state.stage == "ready"
    return fake


def test_mf04_sleep_and_faint_count_from_the_committed_start(packet, fake_exchange):
    for cause, end in (("sleep", 136), ("faint", 137)):
        mind = resident(memory_journal({}))
        mind.deliver(FilteredDelivery(packet(tick=100)))
        assert mind.workflow is None
        if cause == "sleep":
            first, intents = sleeping(packet)
        else:
            first, intents = FilteredDelivery(packet(tick=101, awareness="unconscious")), {}
        mind.deliver(first, intents=intents)
        _ready(mind.workflow, fake_exchange)
        for tick in range(102, end):
            result = mind.deliver(
                FilteredDelivery(
                    packet(
                        tick=tick,
                        awareness=first.packet.perception.awareness,
                    )
                )
            )
            assert result.record is None
            assert mind.period_id == "p:ella:1"
        wake = FilteredDelivery(packet(tick=end, reports=[_report("woke")]))
        result = mind.deliver(wake)
        assert (result.record.s_tick, result.record.started_tick) == (end - 36, 101)
        assert result.record.boundary_tick == end and result.record.outcome == "committed"
        assert result.record.confirming_delivery == first.packet.delivery_id
        assert mind.period_id == "p:ella:2"
        version = mind.store.snapshot.version
        assert mind.deliver(wake).record is None and mind.store.snapshot.version == version

    for duration, wake_at in ((35, 135), (6, 106), (54, 120)):
        mind = resident(memory_journal({}))
        context = mind.context
        first, intents = sleeping(packet, duration=duration)
        mind.deliver(first, intents=intents)
        assert (mind.workflow is None) == (duration < 36)
        result = mind.deliver(FilteredDelivery(packet(tick=wake_at, reports=[_report("woke")])))
        if duration >= 36:
            assert result.record.reason == "woken"
        assert [e.type for e in mind.log.entries] == ["sleep", "sleep"]
        assert mind.context is context and mind.store.snapshot.version == 0

    mind = resident(memory_journal({}))
    _, intents = sleeping(packet)
    mind.deliver(FilteredDelivery(packet(tick=101)), intents=intents)
    assert mind.workflow is None
    first, intents = sleeping(packet, tick=111, start=110)
    mind.deliver(first, intents=intents)
    result = mind.death(128)
    assert result.record.reason == "death" and result.record.result_version is None
    assert mind.period_id == "p:ella:1" and mind.context is None


def test_mf12_off_arm_closes_resets_and_keeps_writing_before_first_wake(packet):
    from living_island.memory.v2.records import Observed

    files = {}
    journal = memory_journal(files)
    mind = resident(journal, memory_on=False)
    mind.store.set_intention(
        turn_id="ella:t000001", tick=1, text="Find fresh water", source=Observed(entry_id="e1")
    )
    first, intents = sleeping(packet, duration=54)
    mind.deliver(first, intents=intents)
    assert mind.workflow is None and mind.store.snapshot.current_intention() is not None
    result = mind.deliver(
        FilteredDelivery(
            packet(
                tick=136,
                awareness="asleep",
                reports=[_report("need_band_changed", "satiety", band="low")],
            )
        )
    )
    assert result.record.outcome == "off_arm"
    assert result.record.selection_call_id is result.record.change_set_call_id is None
    closed = json.loads(files[result.record.closed_context])
    assert [e["type"] for e in closed["log"]["entries"]] == ["sleep"]
    assert mind.context is None and mind.store.snapshot.current_intention() is None
    assert mind.store.snapshot.records()[0].content.state == "reset"
    assert [e.id for e in result.entries] == ["d:p:ella:2:1"]
    mind.deliver(FilteredDelivery(packet(tick=140, awareness="asleep")))
    result = mind.deliver(
        FilteredDelivery(
            packet(
                tick=154,
                reports=[_report("woke")],
                visible_entities=[_visible("mia"), _visible("zed")],
            )
        )
    )
    assert [w.write.after_version for w in result.writes] == [3, 4]
    current = mind.open(FrozenPrefix(mind.period_id, (), (), (), None))
    assert [e.type for e in current.log.entries] == [
        "body_change",
        "observation",
        "observation",
        "sleep",
    ]
    assert not current.prefix.memories and not mind.store.snapshot.resident(memory_on=False).records
    assert all(".dispatch." not in key and ".authorized." not in key for key in files)


def _visible(key):
    return dict(
        kind="resident",
        entity_id=key,
        archetype_id=None,
        material_id=None,
        position={"x": 0, "y": 1},
        quantity=None,
        descriptors=[],
        observable_signs=[],
    )


def test_mf17_oversized_change_floor_records_stop_only_at_surviving_k(packet, fake_exchange):
    from living_island.agents.v2.calls.guard import Part, Ref
    from living_island.agents.v2.calls.wire import WINDOW
    from living_island.memory.v2.store import MemoryStore

    # The selection schema fits, but the larger mandatory change-set schema does not.
    part = Part(
        "prefix", Ref(kind="template", id="identity", version="test"), "x" * (WINDOW - 3000)
    )
    prefix = FrozenPrefix("p:ella:1", (), (part,), (), None)
    files = {}
    journal = memory_journal(files)
    mind = PeriodCoordinator(MemoryStore("ella"), journal, prefix)
    first, intents = sleeping(packet)
    mind.deliver(first, intents=intents)
    flow = mind.workflow
    clock, fake = fake_exchange(['{"read":[]}'])
    for _ in range(4):
        flow.advance(fake, clock)
    selection, change = flow.state.calls
    assert len(fake.dispatches) == 1 and selection.sent is not None
    floor = change.prepared.candidates[change.prepared.floor_candidate]
    assert change.prepared.reason == "stopped_unfit" and floor.manifest.tokens_total > WINDOW
    assert change.attempts == [] and change.sent is None
    assert (
        mind.deliver(FilteredDelivery(packet(tick=135, awareness="asleep"))).status == "delivered"
    )
    result = mind.deliver(FilteredDelivery(packet(tick=136)))
    assert (result.status, result.record.outcome, result.record.reason) == (
        "stopped_unfit",
        "failed",
        "stopped_unfit",
    )
    assert result.record.pending_after == ("p:ella:1",)
    assert not mind.store.snapshot.version
    assert (
        json.loads(files[journal.cursor(change.call.call_id, "outcome")])["outcome"]
        == "stopped_unfit"
    )
    assert mind.deliver(FilteredDelivery(packet(tick=136))).status == "stopped_unfit"


def test_mf20_sleeping_deliveries_survive_restore_but_never_enter_fixed_calls(
    make_world, packet, fake_exchange
):
    from living_island.memory.v2.store import MemoryStore
    from living_island.world.v2.protocol import Intent
    from v2.engine.perception.test_packets import BODY, SLEEP_RULE, A, B, C, sleep, step
    from v2.engine.perception.test_packets import packet as world_packet

    # The compat sight comes from the engine's sleeping-sight switch and corpse creation.
    world = make_world(
        [(A, 2, 1), (B, 3, 1), (C, 2, 2)],
        settings="sight_while_asleep = true\n" + BODY,
        rules=SLEEP_RULE,
        start=340,
        night=1,
        radius=4,
    )
    journal = memory_journal({})
    mind = PeriodCoordinator(MemoryStore(A), journal, FrozenPrefix(f"p:{A}:1", (), (), (), None))
    bound = sleep(world, A, 36)
    intent = Intent.model_validate(bound["action"]["intent"])
    step(world, bound)
    mind.deliver(FilteredDelivery(world_packet(world)), intents={intent.intent_id: intent})
    clock, fake = fake_exchange(['{"read":[]}', '{"ops":[]}'])
    mind.workflow.advance(fake, clock)
    mind.workflow.advance(fake, clock)
    mind.workflow.advance(fake, clock)
    before = [call.admitted_wire for call in mind.workflow.state.calls]
    world.state.needs[B].update(health=1, satiety=1)
    step(world)
    later = mind.deliver(FilteredDelivery(world_packet(world)))
    corpse = next(
        e
        for e in later.entries
        if e.type == "observation" and any("corpse" in key for key in e.about)
    )
    assert all(corpse.id not in wire for wire in before)
    saved = PeriodCheckpoint.model_validate_json(mind.checkpoint().model_dump_json())
    mind = PeriodCoordinator.restore(saved, journal)
    assert corpse in mind.log.entries and mind.workflow.state.calls[-1].admitted_wire == before[-1]
    mind.workflow.advance(fake, clock)
    assert fake.dispatches == [wire.encode() for wire in before]
    wake = mind.deliver(FilteredDelivery(packet(actor=A, tick=20, reports=[_report("woke")])))
    assert wake.record.reason == "woken" and corpse in mind.context.log.entries

    # Starter has no sleeping sight. A delivered need-band report still reaches the live log.
    files = {}
    journal = memory_journal(files)
    mind = resident(journal)
    initial = mind.deliver(
        FilteredDelivery(
            packet(
                tick=99,
                visible_entities=[_visible("mia"), _visible("zed")],
            )
        )
    )
    assert [w.write.changes[0].id for w in initial.writes] == ["m:ella:1", "m:ella:2"]
    assert [w.write.after_version for w in initial.writes] == [1, 2]
    first, intents = sleeping(packet)
    mind.deliver(first, intents=intents)
    fake = _ready(mind.workflow, fake_exchange)
    result = mind.deliver(
        FilteredDelivery(
            packet(
                tick=115,
                awareness="asleep",
                reports=[_report("need_band_changed", "hydration", band="low")],
            )
        )
    )
    (body,) = result.entries
    assert body.type == "body_change" and all(
        body.id.encode() not in wire for wire in fake.dispatches
    )
    saved = PeriodCheckpoint.model_validate_json(mind.checkpoint().model_dump_json())
    restored = PeriodCoordinator.restore(saved, journal)
    terminal = restored.death(136)
    assert terminal.record.outcome == "abandoned" and terminal.record.reason == "death"
    assert terminal.record.result_version is None and restored.store.snapshot.version == 2
    closed = json.loads(files[terminal.record.closed_context])
    assert closed["log"]["entries"][-1]["id"] == body.id
    assert restored.period_id == "p:ella:1" and restored.context is None
    assert restored.workflow.state.stage == "cancelled" and restored.death(136).record is None


def test_partial_publication_resumes_from_the_last_acknowledged_boundary(packet, fake_exchange):
    files = {}
    durable = memory_journal(files)
    failed = False

    def keep(key, data):
        nonlocal failed
        if key.endswith(".consolidation.json") and not failed:
            failed = True
            raise OSError("interrupted before publishing the K record")
        durable.keep(key, data)

    mind = resident(Journal(keep, durable.create))
    first, intents = sleeping(packet)
    mind.deliver(first, intents=intents)
    _ready(mind.workflow, fake_exchange)
    saved = mind.checkpoint()
    uninterrupted_files = files.copy()
    uninterrupted = PeriodCoordinator.restore(saved, memory_journal(uninterrupted_files))
    wake = FilteredDelivery(packet(tick=136, reports=[_report("woke")]))
    with pytest.raises(OSError):
        mind.deliver(wake)
    with pytest.raises(RuntimeError, match="incomplete period boundary"):
        mind.checkpoint()
    with pytest.raises(RuntimeError, match="incomplete period boundary"):
        mind.deliver(wake)
    recovered = PeriodCoordinator.restore(saved, durable)
    assert recovered.deliver(wake) == uninterrupted.deliver(wake)
    assert recovered.checkpoint() == uninterrupted.checkpoint()
    assert files == uninterrupted_files
