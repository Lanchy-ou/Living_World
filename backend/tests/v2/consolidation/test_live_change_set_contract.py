"""The tick-442 omissions and a valid sleep-to-morning change set."""

import json
from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from living_island.agents.v2.calls.contracts import Contract, digest, json_bytes
from living_island.agents.v2.calls.guard import Call
from living_island.agents.v2.context.delivery import FilteredDelivery
from living_island.agents.v2.context.prefix import ResidentIdentity, open_prefix
from living_island.agents.v2.context.state import render_current_state
from living_island.agents.v2.decision.caller import Caller
from living_island.memory.v2.changes import stage_change_set
from living_island.memory.v2.kinds import KindRegistry
from living_island.memory.v2.profiles import SelectedProfile
from living_island.memory.v2.provenance import SentInput
from living_island.memory.v2.store import MemoryStore
from living_island.memory.v2.validation import decode_change_set
from living_island.sim.v2.harness.consolidation.checkpoint import StoreImage
from v2.consolidation.conftest import journal, resident
from v2.consolidation.test_consolidation_settlement import _begin, _complete, _seen


def test_tick442_proposals_keep_their_individual_validator_verdicts():
    capture = json.loads(Path(__file__).with_name("tick442-change-sets.json").read_bytes())
    contract = Contract("consolidation_change_set")
    expected = [
        [("op1", "format"), ("op2", "format"), ("op3", "authority"), ("op4", "depends_on")],
        [
            ("o1", "format"),
            ("o2", "format"),
            ("o3", "format"),
            ("o4", "authority"),
            ("o5", "format"),
            ("o6", "depends_on"),
            ("o7", "depends_on"),
        ],
    ]
    for case, reasons in zip(capture["cases"], expected, strict=True):
        assert digest(json_bytes(case["response"])) == case["parsed_sha256"]
        snapshot = StoreImage.model_validate(case["store"]).restore(KindRegistry())
        store = MemoryStore.from_snapshot(snapshot)
        sent = TypeAdapter(SentInput).validate_json(json_bytes(case["sent"]))
        parsed = contract.parse(json.dumps(case["response"]), has_running_action=False)
        change = decode_change_set(
            parsed.model_dump_json(by_alias=True, exclude_unset=True), snapshot.version
        )
        staged = stage_change_set(store, change, sent, case["tick"])
        assert [(v.op_id, v.reason) for v in staged.verdicts] == reasons
        assert json.loads(json_bytes([asdict(v) for v in staged.verdicts])) == case["verdicts"]
        assert not staged.effects and store.snapshot is snapshot


def test_change_set_contract_and_full_personality_reach_commit_and_morning(packet, fake_exchange):
    profile = SelectedProfile.load(
        Path(__file__).parents[1] / "memory_store" / "fixtures" / "synthetic_min.json"
    )
    store = MemoryStore("ella")
    profile.initialize(store)
    facts = {}
    log = journal(facts)
    coordinator = resident(log, store=store)
    (observation,) = coordinator.deliver(_seen(packet, 99, "mia")).entries
    workflow = _begin(coordinator, packet, 100)
    call_id = "p:ella:1:101:change_set"
    inferred = {"kind": "inferred", "memory_ids": ["new:1"], "call_id": call_id}
    ops = [
        {
            "op": "add",
            "op_id": "episode",
            "ref": "new:1",
            "record": {
                "kind": "episodic",
                "gist": "I saw Mia nearby.",
                "about_tick": {"from": 99, "to": 99},
                "content": {"participants": ["mia"], "place": None},
                "sources": [{"kind": "observed", "entry_id": observation.id}],
                "confidence": 2,
            },
        },
        {
            "op": "add",
            "op_id": "belief",
            "ref": "new:2",
            "record": {
                "kind": "belief",
                "gist": "Mia has been nearby.",
                "content": {
                    "subject": {"kind": "resident", "ref": "mia"},
                    "stance": "stable",
                    "topics": ["people"],
                },
                "sources": [inferred],
                "confidence": 2,
            },
        },
        {"op": "trait", "op_id": "trait", "trait_id": "caution", "delta": 1, "sources": [inferred]},
    ]
    clock, transport = fake_exchange(['{"read":[]}', json.dumps({"ops": ops})])
    _complete(workflow, transport, clock)
    change_wire = json.loads(transport.dispatches[1])
    defs = change_wire["text"]["format"]["schema"]["$defs"]
    new_record = defs["NewRecord"]["properties"]
    assert "160" in new_record["gist"]["description"]
    assert len(new_record["content"]["examples"]) == 3
    assert defs["Add"]["properties"]["ref"]["examples"] == ["new:1"]
    assert "Change-set call ID" in defs["Inferred"]["properties"]["call_id"]["description"]
    assert "Intentions are read-only" in change_wire["input"][0]["content"]
    user = change_wire["input"][1]["content"]
    assert f"Change-set call ID for inferred sources: {call_id}" in user
    assert '"traits":' in user and '"kind":"personality"' in user

    waking = packet(tick=136)
    result = coordinator.deliver(FilteredDelivery(waking)).record
    assert result.outcome == "committed" and result.episodic_created == 1
    assert [v.result for v in result.verdicts] == ["committed"] * 3
    episode, belief, trait = result.effects
    assert episode.produced_id and belief.produced_id and trait.edits
    view = store.snapshot.resident(memory_on=True)
    memory = next(r for r in view.records if r.ref.id == belief.produced_id)
    assert memory.record.sources[0].memory_ids == [episode.produced_id]
    assert memory.record.sources[0].call_id == call_id

    clock, transport = fake_exchange([json.dumps({"ids": [episode.produced_id]})])
    caller = Caller(transport, clock, lambda _: None)
    morning = open_prefix(
        call=Call(call_id="p:ella:2:morning", resident_id="ella", period_id="p:ella:2", tick=136),
        identity=ResidentIdentity("Ella", profile),
        verbs=(),
        traits=profile.document.traits,
        view=view,
        store_version=store.snapshot.version,
        memory_on=True,
        waking=render_current_state(waking, reasons=("woke",), time_of_day="morning"),
        journal=log,
        select=lambda prep: caller.dispatch(prep, log, running=False).parsed,
    )
    assert [r.revision.id for r in morning.memories] == [episode.produced_id]
    assert "I saw Mia nearby." in morning.memories[0].part.text
