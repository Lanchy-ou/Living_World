"""DL-05 and the membership boundary of the morning selection."""

import json
from dataclasses import replace
from pathlib import Path

import pytest


@pytest.fixture
def waking(packet, audit):
    from living_island.agents.v2.calls.guard import Call
    from living_island.agents.v2.context.prefix import ResidentIdentity, VerbDescription
    from living_island.agents.v2.context.state import render_current_state
    from living_island.memory.v2.profiles import SelectedProfile
    from living_island.memory.v2.store import MemoryStore
    from living_island.world.v2.protocol import EnabledVerb

    profile = SelectedProfile.load(
        Path(__file__).parents[1] / "memory_store" / "fixtures" / "synthetic_min.json"
    )
    store = MemoryStore("ella")
    profile.initialize(store)
    fields = dict(
        owner_id="ella",
        created_tick=1,
        updated_tick=1,
        about_tick=None,
        sources=[{"kind": "observed", "entry_id": "d:p1:1"}],
        confidence=3,
        speech_derived=False,
        last_used_tick=None,
        use_count=0,
        supersedes=None,
        superseded_by=None,
        needs_review=False,
    )
    records = [
        store.registry.parse(
            dict(
                fields,
                id=store.snapshot.next_id(i),
                kind="belief",
                gist=f"Appearance {i}",
                text=f"Details {i}",
                content={
                    "subject": {"kind": "general", "ref": None},
                    "stance": "stable",
                    "topics": [],
                },
            )
        )
        for i in range(20)
    ]
    records.append(
        store.registry.parse(
            dict(
                fields,
                id=store.snapshot.next_id(20),
                kind="commitment",
                gist="",
                text=None,
                content={
                    "agreement_id": "private-acceptance",
                    "role": "promisee",
                    "counterpart_id": "mia",
                    "terms": {
                        "promisor_id": "mia",
                        "promisee_id": "ella",
                        "what": {"kind": "be_at", "position": {"x": 1, "y": 1}},
                        "due_tick": 150,
                    },
                    "due_tick": 150,
                    "heard_counterpart": True,
                    "status": "open",
                    "status_note": None,
                },
            )
        )
    )
    store.apply(store.snapshot.version, "change_set", records)
    return dict(
        call=Call(call_id="morning-2", resident_id="ella", tick=100, period_id="p2"),
        identity=ResidentIdentity("Ella", profile),
        verbs=(VerbDescription(EnabledVerb(id="rest", target_kinds=(), params=()), "Rest."),),
        traits=profile.document.traits.model_copy(update={"curiosity": 1}),
        view=store.snapshot.resident(memory_on=True),
        store_version=store.snapshot.version,
        memory_on=True,
        waking=render_current_state(packet(tick=100), reasons=(), time_of_day="morning"),
        journal=audit,
    )


def scripted_selector(fake_exchange, journal, *outputs):
    from living_island.agents.v2.calls.contracts import MorningIDs
    from living_island.agents.v2.calls.provider import attempt

    clock, transport = fake_exchange(json.dumps({"ids": ids}) for ids in outputs)

    def select(prepared):
        for n in range(1, len(outputs) + 1):
            result = attempt(
                prepared,
                n=n,
                has_running_action=False,
                journal=journal,
                transport=transport,
                clock=clock,
            )
            assert result is not None
            if result.parsed is not None:
                assert isinstance(result.parsed, MorningIDs)
                return result.parsed
            assert result.terminal.error_class == "invalid_output"
        return None

    return select, transport


def test_dl_05_one_frozen_prefix_per_period(waking, fake_exchange, tmp_path):
    from living_island.agents.v2.calls.guard import PreparedRecord
    from living_island.agents.v2.calls.wire import WINDOW
    from living_island.agents.v2.context.prefix import MorningStop, open_prefix

    call = waking["call"]
    ids = [f"m:ella:{i}" for i in range(21, 1, -1)]
    select, transport = scripted_selector(fake_exchange, waking["journal"], ids + ["surplus"], ids)
    args = dict(waking, select=select)
    for tick, on in ((0, True), (100, False)):
        key = call.model_copy(update={"tick": tick})
        skipped = open_prefix(**dict(args, call=key, memory_on=on))
        assert skipped.morning is None and not skipped.memories and not transport.dispatches
        assert ("slightly curious" if on else "hardly curious") in skipped.fixed[2].text

    result = open_prefix(**args)
    assert result.morning.outcome == "adopted"
    assert result.morning.selected_ids == tuple(ids)
    assert [part.source.id for part in result.fixed] == ["verbs", "identity", "traits"]
    assert result.parts[0].text == "rest: Rest."
    assert [result.parts[i].source.id for i in result.memory_positions] == ids
    assert "Details 19" in result.memories[0].part.text
    expected = next(record for record in waking["view"].records if record.ref.id == ids[0])
    assert result.memories[0].revision == expected.ref
    assert len(transport.dispatches) == 2 and transport.dispatches[0] == transport.dispatches[1]
    wire = json.loads(transport.dispatches[0])
    system, user = [message["content"] for message in wire["input"]]
    assert "twenty memory IDs" in system
    assert "Ella" in user and "Your thoughts feel" in user and "morning" in user
    assert " | commitment | c3 | open | " in user
    assert "private-acceptance" not in user and "Details 19" not in user
    assert "Rest." not in user and "curious" not in user
    prepared = PreparedRecord.model_validate_json(
        (tmp_path / result.morning.prepared_cursor).read_bytes()
    )
    index = [e.source for e in prepared.candidates[0].manifest.entries if e.source.kind == "index"]
    assert all(source.version == str(waking["store_version"]) for source in index)
    assert [source.id for source in index[1:]] == [r.ref.id for r in waking["view"].records]
    short_wake = call.model_copy(update={"tick": 105})
    assert open_prefix(**dict(args, call=short_wake), previous=result) is result
    assert len(transport.dispatches) == 2

    failed_selector, failures = scripted_selector(
        fake_exchange, waking["journal"], ids + ["extra"], ids + ["extra"]
    )
    next_call = call.model_copy(update={"call_id": "morning-3", "period_id": "p3"})
    failed = open_prefix(**dict(args, call=next_call, select=failed_selector), previous=result)
    assert failed.morning.outcome == "failed" and failed.memories == ()
    assert len(failures.dispatches) == 2

    # An identity longer than the usable window is still mandatory.
    too_long = replace(waking["identity"], name="🌴" + "x" * WINDOW)
    unfit_call = next_call.model_copy(update={"call_id": "morning-4", "period_id": "p4"})
    stop = open_prefix(**dict(args, identity=too_long, call=unfit_call), previous=failed)
    assert isinstance(stop, MorningStop) and stop.morning.outcome == "stopped_unfit"
    record = stop.prepared.record
    assert record.candidates[record.floor_candidate].manifest.tokens_total > WINDOW
    assert record.admitted_candidate is None and len(transport.dispatches) == 2


def test_morning_selection_membership(waking, fake_exchange):
    from living_island.agents.v2.context.prefix import open_prefix

    select, _ = scripted_selector(
        fake_exchange, waking["journal"], ["not-in-this-index", "m:ella:2", "m:ella:2", "m:ella:3"]
    )
    result = open_prefix(**waking, select=select)
    assert result.morning.selected_ids == ("m:ella:2", "m:ella:3")
    assert result.morning.ignored_ids == ("not-in-this-index", "m:ella:2")
