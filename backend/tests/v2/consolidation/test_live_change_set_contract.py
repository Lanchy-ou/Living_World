"""Captured consolidation verdicts and a valid sleep-to-morning change set."""

import json
from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from living_island.agents.v2.calls.contracts import (
    EPISODIC_ADD_EXAMPLE,
    Contract,
    digest,
    json_bytes,
)
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


def _replay_proposals(filename):
    capture = json.loads(Path(__file__).with_name(filename).read_bytes())
    contract = Contract("consolidation_change_set")
    for case in capture["cases"]:
        assert digest(json_bytes(case["response"])) == case["parsed_sha256"]
        snapshot = StoreImage.model_validate(case["store"]).restore(KindRegistry())
        store = MemoryStore.from_snapshot(snapshot)
        sent = TypeAdapter(SentInput).validate_json(json_bytes(case["sent"]))
        parsed = contract.parse(json.dumps(case["response"]), has_running_action=False)
        assert parsed.model_dump(mode="json", by_alias=True, exclude_unset=True) == case["response"]
        change = decode_change_set(
            parsed.model_dump_json(by_alias=True, exclude_unset=True), snapshot.version
        )
        staged = stage_change_set(store, change, sent, case["tick"])
        assert json.loads(json_bytes([asdict(v) for v in staged.verdicts])) == case["verdicts"]
        assert store.snapshot is snapshot
        writes = staged.commit(store).write.changes
        assert json.loads(json_bytes([asdict(w) for w in writes])) == case.get("writes", [])
        yield [(v.op_id, v.reason, v.depends_on) for v in staged.verdicts]


def test_tick442_proposals_keep_their_individual_validator_verdicts():
    first, second = _replay_proposals("tick442-change-sets.json")
    assert [reason for _, reason, _ in first] == ["format", "format", "authority", "depends_on"]
    assert [reason for _, reason, _ in second] == [
        "format",
        "format",
        "format",
        "authority",
        "format",
        "depends_on",
        "depends_on",
    ]


def test_probe1_proposals_keep_all_sixteen_verdicts_and_the_skill_write():
    first, second = _replay_proposals("probe1-change-sets.json")
    assert first == [
        ("op1", "format", ()),
        ("op2", "format", ()),
        ("op3", "depends_on", ("op1", "op2")),
        ("op4", "format", ()),
        ("op5", None, ()),
        ("op6", "format", ()),
    ]
    assert second == [
        ("add_1", "format", ()),
        ("add_2", "format", ()),
        ("add_3", "format", ()),
        ("add_4", "format", ()),
        ("add_5", "provenance", ()),
        ("add_6", "provenance", ()),
        ("add_7", "depends_on", ("add_3",)),
        ("add_8", "provenance", ()),
        ("update_1", "authority", ()),
        ("update_2", "authority", ()),
    ]


def _assert_sent_creation_schema(schema):
    defs = schema["$defs"]

    def resolve(ref):
        return defs[ref.rsplit("/", 1)[1]]

    operations = resolve(schema["properties"]["ops"]["items"]["$ref"])["discriminator"]["mapping"]
    add = resolve(operations["add"])["properties"]
    record = resolve(add["record"]["$ref"])
    assert record["discriminator"]["propertyName"] == "kind"
    types = {key: resolve(ref) for key, ref in record["discriminator"]["mapping"].items()}
    assert types.keys() == {"episodic", "belief", "skill"}
    merge = resolve(resolve(operations["merge"])["properties"]["record"]["$ref"])
    assert merge["discriminator"]["mapping"].keys() == {"episodic", "belief"}
    assert "about_tick" in types["episodic"]["required"]
    assert "about_tick" not in types["skill"]["properties"]
    assert not types["skill"]["additionalProperties"]
    assert "160" in types["episodic"]["properties"]["gist"]["description"]
    for kind, fields in (
        ("episodic", {"participants", "place"}),
        ("belief", {"subject", "stance", "topics"}),
        ("skill", {"hypothesis", "status"}),
    ):
        assert resolve(types[kind]["properties"]["content"]["$ref"])["properties"].keys() == fields
    stances = {
        rule["properties"]["content"]["properties"]["stance"]["const"]: rule
        for rule in types["belief"]["oneOf"]
    }
    assert stances["dated"]["required"] == ["about_tick"]
    assert stances["dated"]["properties"]["about_tick"] == {"type": "object"}
    assert stances["stable"]["properties"]["about_tick"] == {"type": "null"}
    assert "about_tick" not in stances["guess"]["properties"]
    assert add["ref"]["examples"] == ["new:1"]
    assert "Change-set call ID" in defs["Inferred"]["properties"]["call_id"]["description"]
    assert "omit" in defs["Update"]["properties"]["add_sources"]["description"].lower()


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
    episode_example = json.loads(EPISODIC_ADD_EXAMPLE)
    episode_example["record"]["about_tick"] = {"from": 99, "to": 99}
    episode_example["record"]["sources"][0]["entry_id"] = observation.id
    ops = [
        episode_example,
        {
            "op": "add",
            "op_id": "belief",
            "ref": "new:2",
            "record": {
                "kind": "belief",
                "gist": "Mia has been nearby.",
                "about_tick": {"from": 99, "to": 99},
                "content": {
                    "subject": {"kind": "resident", "ref": "mia"},
                    "stance": "dated",
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
    _assert_sent_creation_schema(change_wire["text"]["format"]["schema"])
    instructions = change_wire["input"][0]["content"]
    assert "Intentions are read-only" in instructions
    assert EPISODIC_ADD_EXAMPLE in instructions
    user = change_wire["input"][1]["content"]
    assert f"Change-set call ID for inferred sources: {call_id}" in user
    assert "resident:mia" in observation.about
    keys = "; ".join(observation.about)
    assert f"{observation.part.text}\nObserved witness keys: {keys}" in user
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
