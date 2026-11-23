"""MF-05 and MF-21 at the boundary between the world, worker and durable call journal."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest

from living_island.agents.v2.calls.fake import FakeTransport
from living_island.agents.v2.calls.guard import Part, Ref
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.calls.provider import Dispatch, Terminal
from living_island.agents.v2.calls.wire import WINDOW
from living_island.agents.v2.context.delivery import FilteredDelivery
from living_island.sim.v2.harness.consolidation import PeriodCheckpoint, PeriodCoordinator
from v2.consolidation.conftest import journal, resident, sleeping


class Outstanding(FakeTransport):
    """Keep the fake call in flight until the test supplies the world's next boundary."""

    def __init__(self, clock, replies):
        super().__init__(clock, replies)
        self.started = Event()
        self.release = Event()

    def exchange(self, body, timeout_ms):
        self.started.set()
        assert self.release.wait(10)
        return super().exchange(body, timeout_ms)


def confirmed(packet, files):
    coordinator = resident(journal(files))
    delivery, intents = sleeping(packet)
    coordinator.deliver(delivery, intents=intents)
    return coordinator


def test_mf_05_world_continues_through_outstanding_calls_and_waits_at_k(packet, fake_exchange):
    for interrupted in (False, True):
        files = {}
        coordinator = confirmed(packet, files)
        flow = coordinator.workflow
        clock, fake = fake_exchange(['{"read":[]}', '{"ops":[]}'])
        worker = Outstanding(clock, fake.replies)
        assert flow.state.calls[0].call.tick == 101
        flow.advance(worker, clock)
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(flow.advance, worker, clock)
            try:
                assert worker.started.wait(5)
                result = coordinator.deliver(FilteredDelivery(packet(tick=135, awareness="asleep")))
                assert result.status == "delivered" and coordinator.workflow is flow
                in_flight = flow.state.calls[0].attempts[0]
                assert in_flight.dispatch_cursor in files and in_flight.terminal is None
                if interrupted:
                    # A separately committed death can preempt the worker even at exact K.
                    result = coordinator.death(136)
                    assert result.record.outcome == "abandoned" and result.record.reason == "death"
                    abandoned = flow.checkpoint()
                else:
                    wake = FilteredDelivery(packet(tick=136))
                    result = coordinator.deliver(wake)
                    assert result.status == "waiting" and result.record is None
                    assert coordinator.period_id == "p:ella:1"
            finally:
                worker.release.set()
            future.result(timeout=5)
        if interrupted:
            assert flow.checkpoint() == abandoned
            assert flow.state.calls[0].outcome == "abandoned"
            key = Journal.cursor(in_flight.dispatch.call.call_id, "0.terminal")
            assert Terminal.model_validate_json(files[key]).parsed_ref in files
            flow.advance(worker, clock)
            assert len(worker.dispatches) == 1
        else:
            flow.advance(worker, clock)
            flow.advance(worker, clock)
            result = coordinator.deliver(wake)
            assert result.record.outcome == "committed" and result.record.boundary_tick == 136
            assert len(worker.dispatches) == 2


def test_mf_21_restore_each_interruption_stage_and_seal_at_world_boundary(packet, fake_exchange):
    # Each completed prefix can be interrupted before preparation, after either
    # preparation, or after selection has authorized the change-set call.
    for steps in range(4):
        files = {}
        direct = confirmed(packet, files)
        clock, fake = fake_exchange(['{"read":[]}'])
        for _ in range(steps):
            direct.workflow.advance(fake, clock)
        saved = PeriodCheckpoint.model_validate_json(direct.checkpoint().model_dump_json())
        prefix = files.copy()
        branch = prefix.copy()
        restored = PeriodCoordinator.restore(saved, journal(branch))
        assert restored.workflow.checkpoint() == direct.workflow.checkpoint()
        wake = FilteredDelivery(packet(tick=120))
        left = direct.deliver(wake)
        right = restored.deliver(wake)
        assert right.record == left.record and left.record.reason == "woken"
        assert all(files[key] == data for key, data in prefix.items())
        assert branch == files
        sealed = PeriodCoordinator.restore(restored.checkpoint(), journal(branch))
        dispatches = tuple(fake.dispatches)
        sealed.workflow.advance(fake, clock)
        assert sealed.workflow.state.stage == "cancelled" and tuple(fake.dispatches) == dispatches

    # Take a checkpoint after the dispatch publication but before the terminal publication.
    files = {}
    direct = confirmed(packet, files)
    prior = direct.checkpoint()
    clock, fake = fake_exchange(
        ['{"read":[]}', '{"ops":[{"op":"update","op_id":"r","id":"absent","gist":"New."}]}']
    )
    gated = Outstanding(clock, fake.replies)
    direct.workflow.advance(gated, clock)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(direct.workflow.advance, gated, clock)
        try:
            assert gated.started.wait(5)
            saved = PeriodCheckpoint.model_validate_json(direct.checkpoint().model_dump_json())
            prefix = files.copy()
            slot = saved.attempt.workflow.calls[0].attempts[0]
            assert slot.dispatch_cursor in prefix and slot.terminal_cursor is None
            missing = PeriodCoordinator.restore(saved, journal(prefix.copy())).workflow
            reason = missing.recover(slot.dispatch, None, None)
            assert reason.reason == "INTERRUPTED_CALL_RECOVERY_REQUIRED"
            clock2, empty = fake_exchange([])
            missing.advance(empty, clock2)
            assert not empty.dispatches
        finally:
            gated.release.set()
        future.result(timeout=5)
    terminal = Terminal.model_validate_json(
        files[Journal.cursor(slot.dispatch.call.call_id, "0.terminal")]
    )
    branch = files.copy()
    restored = PeriodCoordinator.restore(saved, journal(branch))
    restored.workflow.recover(slot.dispatch, terminal, files[terminal.parsed_ref])
    assert restored.workflow.state == direct.workflow.state
    assert branch == files and all(branch[key] == data for key, data in prefix.items())

    # Reconcile both committed dispatches when the latest save predates either preparation.
    direct.workflow.advance(gated, clock)
    direct.workflow.advance(gated, clock)
    branch = files.copy()
    older = PeriodCoordinator.restore(prior, journal(branch))
    for call in direct.workflow.state.calls:
        slot = call.attempts[0]
        dispatch = Dispatch.model_validate_json(files[slot.dispatch_cursor])
        terminal = Terminal.model_validate_json(files[slot.terminal_cursor])
        older.workflow.recover(dispatch, terminal, files[terminal.parsed_ref])
    assert older.workflow.state == direct.workflow.state and branch == files
    ready = PeriodCheckpoint.model_validate_json(older.checkpoint().model_dump_json())
    resumed = PeriodCoordinator.restore(ready, journal(branch))
    left = direct.deliver(FilteredDelivery(packet(tick=136)))
    right = resumed.deliver(FilteredDelivery(packet(tick=136)))
    assert right.record == left.record and files == branch
    assert right.record.change_set["ops"] == [
        {"op": "update", "op_id": "r", "id": "absent", "gist": "New."}
    ]

    # An oversized mandatory resident prefix is a real zero-dispatch selection guard case.
    for tick, outcome, status in (
        (120, "abandoned", "delivered"),
        (136, "failed", "stopped_unfit"),
    ):
        coordinator = resident(journal({}))
        context = coordinator.context
        huge = Part("prefix", Ref(kind="template", id="fixed", version="1"), "m" * WINDOW)
        context.prefix = replace(context.prefix, fixed=(huge,))
        delivery, intents = sleeping(packet)
        assert coordinator.deliver(delivery, intents=intents).status == "delivered"
        flow = coordinator.workflow
        flow.advance(empty, clock2)
        assert flow.state.reason == "stopped_unfit"
        assert flow.state.calls[0].attempts == [] and flow.state.calls[0].sent is None
        flow.advance(empty, clock2)
        result = coordinator.deliver(FilteredDelivery(packet(tick=tick)))
        assert result.status == status and result.record.outcome == outcome
        assert result.record.reason == ("woken" if tick < 136 else "stopped_unfit")
        assert flow.state.calls[0].outcome == ("abandoned" if tick < 136 else "stopped_unfit")
        assert not empty.dispatches


def test_recovery_refuses_a_different_parsed_output(packet, fake_exchange):
    files = {}
    coordinator = confirmed(packet, files)
    flow = coordinator.workflow
    clock, fake = fake_exchange(['{"read":[]}'])
    gated = Outstanding(clock, fake.replies)
    flow.advance(gated, clock)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(flow.advance, gated, clock)
        try:
            assert gated.started.wait(5)
            saved = coordinator.checkpoint()
        finally:
            gated.release.set()
        future.result(timeout=5)
    terminal = flow.state.calls[0].attempts[0].terminal
    dispatch = flow.state.calls[0].attempts[0].dispatch
    restored = PeriodCoordinator.restore(saved, journal(files)).workflow
    with pytest.raises(ValueError, match="parsed output differs"):
        restored.recover(dispatch, terminal, b'{"read":["different"]}')
    assert restored.state == saved.attempt.workflow


def test_recovery_rejects_an_unbound_journal_dispatch(packet, fake_exchange):
    files = {}
    coordinator = confirmed(packet, files)
    flow = coordinator.workflow
    clock, fake = fake_exchange(['{"read":[]}'])
    flow.advance(fake, clock)
    saved = coordinator.checkpoint()
    flow.advance(fake, clock)
    slot = flow.state.calls[0].attempts[0]
    restored = PeriodCoordinator.restore(saved, journal(files)).workflow
    for field, value in (
        ("call", slot.dispatch.call.model_copy(update={"call_id": "new-call"})),
        ("n", 1),
        ("prepared_cursor", "other-preparation"),
        ("request_sha256", "other-wire"),
        (
            "sent",
            slot.dispatch.sent.model_copy(
                update={"omitted": (Ref(kind="memory", id="r", version="1"),)}
            ),
        ),
        ("settings", slot.dispatch.settings.model_copy(update={"model": "different"})),
    ):
        with pytest.raises(ValueError, match="differs from the authorized attempt"):
            restored.recover(
                slot.dispatch.model_copy(update={field: value}),
                slot.terminal,
                files[slot.terminal.parsed_ref],
            )
    assert restored.state == saved.attempt.workflow
