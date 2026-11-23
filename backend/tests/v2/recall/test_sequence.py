"""Exercise both memory arms through the same prepared decision and fake exchange."""

import json

import pytest


@pytest.fixture
def turn(audit, packet, working_context, fake_exchange):
    from living_island.agents.v2.calls.provider import attempt
    from living_island.agents.v2.context.state import render_current_state
    from living_island.agents.v2.recall.attribution import store_credit
    from living_island.agents.v2.recall.recipes import RecipeCues, RecipeRegistry
    from living_island.agents.v2.recall.sequence import run_recall_turn

    def run(turn_id, store, outputs, *, memory_on=True, tick=576, cues=None):
        clock, transport = fake_exchange(outputs)

        def dispatch(prepared, journal):
            return attempt(
                prepared,
                n=1,
                has_running_action=False,
                journal=journal,
                transport=transport,
                clock=clock,
            )

        def read_memory():
            assert memory_on
            snapshot = store.snapshot
            return snapshot.version, snapshot.resident(memory_on=True)

        result = run_recall_turn(
            resident_id="ella",
            turn_id=turn_id,
            context=working_context(period=turn_id),
            cues=RecipeCues(tick, frozenset({"start"})) if cues is None else cues,
            recipes=RecipeRegistry(),
            state=render_current_state(packet(tick), reasons=("start",), time_of_day="noon"),
            memory_on=memory_on,
            read_memory=read_memory,
            journal=audit,
            dispatch=dispatch,
            credit=store_credit(store),
        )
        wires = [json.loads(body) for body in transport.dispatches]
        return result, wires

    return run


def wait_action():
    return {
        "step": "act",
        "action": {
            "kind": "intent",
            "intent": {
                "action": "wait",
                "verb": None,
                "target": None,
                "instruments": [],
                "inputs": [],
                "params": {},
                "reason": None,
            },
        },
        "utterance": None,
        "intention": None,
        "mute": [],
        "cite": [],
    }


def test_dl_10_single_query_then_act_in_both_arms(turn, add_record, tmp_path):
    from living_island.agents.v2.calls.contracts import ActStep
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.recall.recipes import RecipeCues
    from living_island.memory.v2.store import MemoryStore

    query = {"step": "recall", "query": "Where can I find water?"}
    store = MemoryStore("ella")
    # At four days without use, these records score exactly 40.
    eligible = [add_record(store, confidence=2, text="Full memory text.") for _ in range(5)]
    ids = [r.id for r in eligible]
    weak = add_record(store, confidence=1)
    for arm in (True, False):
        turn_id = "turn-on" if arm else "turn-off"
        outputs = [query, {"ids": ids[::-1]}, wait_action()] if arm else [query, wait_action()]
        result, wires = turn(turn_id, store, outputs, memory_on=arm)
        kinds = (
            ["decision", "recall", "decision_after_recall"]
            if arm
            else ["decision", "decision_after_recall"]
        )
        assert [wire["text"]["format"]["name"] for wire in wires] == kinds
        assert [s.prepared.record.call.call_id for s in result.stages] == [
            f"{turn_id}:{kind}" for kind in kinds
        ]
        assert result.ignored_ids == ()
        assert isinstance(result.stages[-1].returned.parsed, ActStep)
        if arm:
            indexed = wires[1]["input"][1]["content"]
            assert query["query"] in indexed and all(r.id in indexed for r in eligible)
            assert weak.id not in indexed and "Full memory text." not in indexed
            assert [entry.retrieved.id for entry in result.entries] == ids[::-1]
            assert all(entry.ref.call_id == f"{turn_id}:recall" for entry in result.entries)
        else:
            (empty,) = result.entries
            assert empty.retrieved is None and empty.ref.mode == "off_empty"
            assert empty.ref.turn_id == turn_id
            assert empty.text == "You cannot remember anything about that."
            receipt = json.loads((tmp_path / Journal.cursor(turn_id, "off_empty")).read_bytes())
            assert receipt["entries"][0]["fragment_sha256"] == empty.fragment_sha256
        act = result.stages[-1].prepared.record
        floor = act.candidates[act.floor_candidate].manifest.entries
        act_text = wires[-1]["input"][1]["content"]
        for entry in result.entries:
            assert act_text.count(entry.part.text) == 1
            assert [item.sha256 for item in floor if item.source.id == entry.id] == [
                entry.fragment_sha256
            ]

    repeat, wires = turn("repeat", store, [query, {"ids": []}, query])
    assert len(wires) == len(repeat.stages) == 3
    assert repeat.stages[-1].returned.parsed is None
    assert repeat.stages[-1].returned.terminal.error_class == "invalid_output"

    # A recipe has a turn-local producer even when the resident goes straight to an act.
    cues = RecipeCues(576, frozenset({"body"}), body_topics=frozenset({"food"}))
    direct, wires = turn("direct", store, [wait_action()], cues=cues)
    assert [w["text"]["format"]["name"] for w in wires] == ["decision"]
    receipt = json.loads((tmp_path / Journal.cursor("direct", "recipe")).read_bytes())
    assert [e["fragment_sha256"] for e in receipt["entries"]] == [
        entry.fragment_sha256 for entry in direct.entries
    ]
    assert direct.entries and all(entry.ref.turn_id == "direct" for entry in direct.entries)


def test_model_selection_is_bound_to_its_reachable_index_and_five_slots(turn, add_record, tmp_path):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    first, second, surplus = [add_record(store) for _ in range(3)]
    weak = add_record(store, confidence=0)
    ids = [first.id, "unknown", weak.id, first.id, second.id, surplus.id]
    turn_id = "selection"
    recall_call = f"{turn_id}:recall"
    result, _ = turn(
        turn_id,
        store,
        [{"step": "recall", "query": "What did I learn?"}, {"ids": ids}, wait_action()],
    )
    assert [e.retrieved.id for e in result.entries] == [first.id, second.id]
    assert result.ignored_ids == ("unknown", weak.id, first.id, surplus.id)
    receipt = json.loads((tmp_path / Journal.cursor(recall_call, "deliberate")).read_bytes())
    assert tuple(receipt["ignored_ids"]) == result.ignored_ids
    for stored, entry in zip(receipt["entries"], result.entries, strict=True):
        assert stored["entry_id"] == entry.id and stored["entry_revision"] == entry.revision
        assert stored["retrieved"] == {
            "id": entry.retrieved.id,
            "content_hash": entry.retrieved.content_hash,
            "store_version": entry.retrieved.store_version,
        }
        assert (tmp_path / stored["fragment_sha256"]).read_bytes() == entry.part.text.encode()
