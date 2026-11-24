from living_island.agents.v2.calls.guard import Ref
from living_island.analysis.v2.continuity import History, continuity
from living_island.contract import inspection_v2 as ia


def test_ev23_guard_dispositions_exact_supplier_and_first_dispatch(short, packet):
    decision = short.read(short.index.decisions[0].shard)
    before = decision.record.period_id
    actor = decision.record.resident_id
    after = "short-wake"
    failed_period = "after-failure"
    guard = Ref(kind="pending_period", id="unread period", version="1")
    recall = decision.calls[1]

    def stage(identity, kind, outcome, period, omitted=False):
        attempt = recall.attempts[0]
        sent = attempt.dispatch.sent.model_copy(update={"omitted": (guard,) if omitted else ()})
        dispatch = attempt.dispatch.model_copy(update={"sent": sent})
        return recall.model_copy(
            update={
                "call_kind": kind,
                "outcome": outcome,
                "call": recall.call.model_copy(update={"call_id": identity, "period_id": period}),
                "attempts": [attempt.model_copy(update={"dispatch": dispatch})],
            }
        )

    stages = [
        stage("abandoned selection", "consolidation_selection", "abandoned", before, True),
        stage("selected", "consolidation_selection", "adopted", before),
        stage("committed", "consolidation_change_set", "adopted", before, True),
        stage("selected again", "consolidation_selection", "adopted", after),
        stage("bad change set", "consolidation_change_set", "failed", after, True),
        stage("guarded morning", "morning", "adopted", before, True),
    ]

    def close(period, tick, outcome, select, change):
        return ia.ConsolidationRecord(
            record_schema="mf/0.1",
            resident_id=actor,
            period_id=period,
            arm="on",
            s_tick=tick - 1,
            started_tick=tick - 1,
            confirming_delivery="confirmation",
            boundary_tick=tick,
            outcome=outcome,
            reason=None,
            base_version=1,
            result_version=None,
            store_hash="a" * 64,
            selection_call_id=select,
            change_set_call_id=change,
            selection=None,
            change_set=None,
            verdicts=[],
            relabel_flags=[],
            pending=[],
            pending_after=[],
            closed_context=None,
            effects=[],
            episodic_created=0,
            write=None,
        )

    rows = [
        close(before, 10, "abandoned", "abandoned selection", None),
        close(before, 20, "committed", "selected", "committed"),
        close(after, 30, "failed", "selected again", "bad change set"),
    ]
    deliveries = [
        ia.Delivery(packet=packet(tick=t, actor=actor), period_id=p, entries=[])
        for t, p in [(0, before), (10, before), (20, after), (30, failed_period)]
    ]
    revisions = [short.read(r) for r in short.index.revisions]
    history = History(deliveries, revisions, rows, {}, 10)
    later = decision.record.model_copy(update={"period_id": after, "tick": 21})
    calls = {c.call.call_id: c for c in [*decision.calls, *stages]}
    activity = continuity(history, [later], calls, {})
    assert [c.supplies_period for c in activity.consolidations] == [None, after, None]
    assert [c.outcome for c in activity.consolidations] == ["abandoned", "committed", "failed"]
    assert activity.consolidations[0].calls[0].omitted == [guard]
    assert activity.consolidations[2].calls[-1].outcome == "failed"
    periods = {p.period_id: p for p in activity.periods}
    assert periods[before].exposed and periods[after].inherited_from == [
        activity.consolidations[1].attempt_id
    ]
    assert periods[after].exposed_turns == [later.turn_id] and not periods[failed_period].exposed
    assert len(activity.uses) == len(decision.record.use_updates) > 0
    for row, receipt in zip(activity.uses, decision.record.use_updates, strict=True):
        assert (row.call_id, row.before_version, row.after_version) == (
            receipt.call_id,
            receipt.before_version,
            receipt.after_version,
        )
        assert row.created_period == before and row.created_day == row.day == 1
    omitted = continuity(history, [later.model_copy(update={"use_updates": []})], calls, {})
    next_day = continuity(history, [later.model_copy(update={"tick": 150})], calls, {})
    assert all(u.created_day == 1 and u.day == 2 for u in next_day.uses)
    assert not omitted.uses and any(c.retrieved for p in omitted.periods for c in p.calls)
