"""MF-10 and MF-23 against actual framed consolidation candidates and a fake dispatch."""

import json
from dataclasses import replace

from living_island.agents.v2.calls.contracts import Contract
from living_island.agents.v2.calls.guard import Call, Part, Ref, prepare
from living_island.agents.v2.calls.provider import attempt
from living_island.agents.v2.calls.wire import NOTICE, WINDOW, frame
from living_island.agents.v2.context.day_log import DayLog
from living_island.agents.v2.context.delivery import FilteredDelivery
from living_island.agents.v2.context.prefix import FrozenPrefix, render_memory
from living_island.agents.v2.context.working import FrozenPeriod
from living_island.memory.v2.pending import PendingPeriod, PendingPeriods
from living_island.memory.v2.provenance import HeardSpeechEntry, PerceptionEntry
from living_island.sim.v2.harness.consolidation.inputs import FixedInput
from v2.call_wire.test_call_wire import oracle
from v2.memory_changes.test_validation import _store
from v2.working_context.test_day_log import _report


def call(kind, period):
    return Call(
        call_id=f"{period}-{kind}",
        resident_id="ella",
        tick=101,
        period_id=period,
        consolidation_period=period,
    )


def context(period_id, audit, packet, tick):
    prefix = FrozenPrefix(period_id, (), (), (), None)
    log = DayLog(period_id, audit, phenomena={})
    log.deliver(
        FilteredDelivery(
            packet(tick=tick, reports=[_report("need_band_changed", "satiety", band="low")])
        )
    )
    heard = dict(
        speaker_id="mia",
        addressee_id=None,
        text="I will look for fruit.",
        speech_act="statement",
        terms=None,
        in_reply_to=None,
        utterance_id=f"speech-{tick}",
        heard_at_tick=tick + 1,
    )
    log.deliver(
        FilteredDelivery(
            packet(
                tick=tick + 1,
                heard_utterances=[heard],
                reports=[_report("utterance_heard", heard["utterance_id"], addressed=False)],
            )
        )
    )
    state = Part(
        "current_state", Ref(kind="current_state", id=f"{period_id}/map", version="map"), "🌴"
    )
    return FrozenPeriod(prefix, log.entries, (state,))


def fixture_input(audit, packet):
    store, ids = _store()
    base = store.snapshot
    review = base.read(base.ref(ids["belief"][0])).model_copy(update={"needs_review": True})
    store.apply(base.version, "change_set", (review,))
    view = store.snapshot.resident(memory_on=True)
    periods = PendingPeriods("ella")
    for n in (1, 2):
        p = f"p:ella:{n}"
        periods.append(PendingPeriod("ella", p, context(p, audit, packet, 4 * n)))
    current = context("p:ella:3", audit, packet, 100)
    changed = frozenset([*ids["social"], *ids["commitment"]])
    return FixedInput(current, periods.read(), view, store.snapshot.version, changed), ids


def test_mf10_omit_last_selected_then_oldest_pending_then_oldest_current_entry(
    audit, packet, fake_exchange, tmp_path
):
    fixed, ids = fixture_input(audit, packet)
    first, second = ids["episodic"]
    unknown = "not-in-index"
    surplus = [unknown] * 57 + [ids["personality"][0]]
    choice = fixed.select([first, second, first, *surplus])
    assert choice.selected == (first, second)
    assert choice.ignored == (first, *surplus)
    contract = Contract("consolidation_change_set")
    logical = call("change", fixed.period.prefix.period_id)
    assembly = fixed.assembly(choice)
    missing = (second, first, "p:ella:1", "p:ella:2", fixed.period.entries[0].id)
    assert tuple(assembly.parts[i].source.id for i in assembly.omission_order) == (
        *missing,
        fixed.period.entries[1].id,
    )

    # Grow the frozen map to hit the real pinned bound with exactly five omissions.
    visible = [p.text for i, p in enumerate(assembly.parts) if i not in assembly.omission_order[:5]]
    small = frame(
        contract.kind, contract.instructions, contract.schema, "\n".join([NOTICE, *visible])
    )
    (map_part,) = fixed.period.current_state
    large = replace(map_part, text=map_part.text + "x" * (WINDOW - oracle(small.body)))
    fixed = replace(fixed, period=replace(fixed.period, current_state=(large,)))
    prepared = prepare(logical, contract, fixed.assembly(choice), audit)
    clock, transport = fake_exchange(['{"ops":[]}'])
    returned = attempt(
        prepared, n=0, has_running_action=False, journal=audit, transport=transport, clock=clock
    )
    sent = returned.dispatch.sent
    assert tuple(ref.id for ref in sent.omitted) == missing
    assert oracle(transport.dispatches[0]) == sent.manifest.tokens_total == WINDOW
    assert json.loads(transport.dispatches[0])["input"][1]["content"].startswith(NOTICE + "\n")
    full = prepared.record.candidates[0]
    assert not full.omitted and full.manifest.tokens_total > WINDOW
    assert (tmp_path / full.wire_sha256).is_file()
    assert tuple(e.source.id for e in full.manifest.entries if e.source.kind == "day_log") == tuple(
        entry.id for entry in fixed.period.entries
    )
    allowed = fixed.sent(logical, sent.manifest)
    assert fixed.sent_pending(sent.manifest) == ()
    assert {r.id for r in allowed.full} == {ids[k][0] for k in ("social", "commitment", "belief")}
    assert len(allowed.index) == len(fixed.view.records)
    (heard,) = allowed.entries
    assert isinstance(heard, HeardSpeechEntry)
    assert (heard.id, heard.utterance_id, heard.speaker_id) == (
        fixed.period.entries[1].id,
        "speech-100",
        "mia",
    )


def test_mf23_selection_and_change_set_protect_their_distinct_framed_floors(
    audit, packet, tmp_path, fake_exchange
):
    fixed, ids = fixture_input(audit, packet)
    pid = fixed.period.prefix.period_id
    review_id = ids["belief"][0]
    prefix_id = ids["episodic"][0]
    carried = next(r for r in fixed.view.records if r.ref.id == prefix_id)
    prefix = replace(fixed.period.prefix, memories=(render_memory(carried),))
    fixed = replace(fixed, period=replace(fixed.period, prefix=prefix))
    selected = fixed.select([*ids["social"], *ids["commitment"], review_id, prefix_id])
    for kind, choice in (
        ("consolidation_selection", None),
        ("consolidation_change_set", selected),
    ):
        logical = call(kind, pid)
        prepared = prepare(logical, Contract(kind), fixed.assembly(choice), audit)
        floor = prepared.record.candidates[prepared.record.floor_candidate]
        raw = (tmp_path / floor.wire_sha256).read_bytes()
        assert oracle(raw) == floor.manifest.tokens_total
        floor_text = json.loads(raw)["input"][1]["content"]
        assert floor_text.startswith(NOTICE + "\n")
        assert (
            oracle(raw, user=floor_text.removeprefix(NOTICE + "\n")) < floor.manifest.tokens_total
        )
        full_records = [
            e.source
            for e in floor.manifest.entries
            if e.source.kind in ("memory", "mechanical_record")
        ]
        expected = [ids["commitment"][0], review_id, prefix_id]
        if choice is not None:
            expected += ids["social"]
        assert sorted(r.id for r in full_records) == sorted(expected)
        for key in expected:
            projected = next(r for r in fixed.view.records if r.ref.id == key)
            assert render_memory(projected).part.text in floor_text
        assert '"agreement_id"' not in floor_text and '"speech_derived"' not in floor_text
        assert {e.kind for e in floor.omitted} == {"day_log", "pending_period"}
        assert fixed.sent_pending(floor.manifest) == ()
        assert not any(e.source.kind == "day_log" for e in floor.manifest.entries)
        if choice is not None:
            clock, transport = fake_exchange(['{"ops":[]}'])
            returned = attempt(
                prepared,
                n=0,
                has_running_action=False,
                journal=audit,
                transport=transport,
                clock=clock,
            )
            sent = returned.dispatch.sent.manifest
            allowed = fixed.sent(logical, sent)
            assert fixed.sent_pending(sent) == ("p:ella:1", "p:ella:2")
            witnesses = [e for e in allowed.entries if isinstance(e, PerceptionEntry)]
            assert {e.id for e in witnesses} == {
                p.entries[0].id for p in (fixed.period, *(p.context for p in fixed.pending))
            }
            assert all(
                e.about == {"need:satiety"} and e.member_paths == ("reports[0]",) for e in witnesses
            )
