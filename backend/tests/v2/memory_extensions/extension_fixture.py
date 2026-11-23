"""One registered kind, a wake recipe and a deterministic compatibility-world recording."""

import json
import re
from dataclasses import replace

from living_island.agents.llm.provider import TransportResponse
from living_island.memory.v2.kinds import Kind
from living_island.memory.v2.records import Commitment, Content, MemoryRecord, Told
from v2.decision_harness.resident_vectors import act
from v2.resident_replay.replay_fixture import start


class ShoreNote(Content):
    kind = "shore_note"
    landmark: str

    def flags(self):
        return ("coastal",)


SHORE = Kind(ShoreNote, 8, 1, frozenset({"add", "update", "supersede"}), ("woke",))
ANCESTOR = "m:ryan:2"
PROMISE = "m:ryan:3"


def seed(store):
    told = Told(utterance_id="earlier-message", speaker_id="ella")
    promise = Commitment.model_validate(
        dict(
            role="promisor",
            counterpart_id="ella",
            terms=dict(
                promisor_id="ryan",
                promisee_id="ella",
                what={"kind": "be_at", "position": {"x": 1, "y": 1}},
                due_tick=24,
            ),
            due_tick=24,
            heard_counterpart=True,
            status="open",
            status_note=None,
            agreement_id="earlier-agreement",
        )
    )
    for content, gist, sources in (
        (ShoreNote(landmark="inlet"), "Ella says the inlet floods.", [told]),
        (promise, promise.summary(), []),
    ):
        snapshot = store.snapshot
        record = MemoryRecord(
            id=snapshot.next_id(),
            owner_id=snapshot.owner_id,
            kind=content.kind,
            created_tick=0,
            updated_tick=0,
            about_tick=None,
            sources=sources,
            confidence=2,
            last_used_tick=None,
            use_count=0,
            supersedes=None,
            superseded_by=None,
            needs_review=False,
            gist=gist,
            text=None,
            speech_derived=bool(sources),
            content=content,
        )
        store.apply(
            snapshot.version, "mechanical" if content is promise else "change_set", [record]
        )


def shore_ops(call_id, spoken_entry):
    ops = [
        dict(
            op="add",
            op_id=name,
            ref=f"new:{n}",
            record=dict(
                kind=SHORE.schema.kind,
                gist=f"Remember the {name}.",
                content={"landmark": name},
                confidence=2,
                sources=[dict(kind="inferred", memory_ids=[ANCESTOR], call_id=call_id)],
            ),
        )
        for n, name in enumerate(("beach", "cove", "pier"), start=1)
    ]
    return ops + [
        dict(
            op="add",
            op_id="claim_observed",
            ref="new:4",
            record=dict(
                kind="shore_note",
                gist="The inlet floods.",
                confidence=3,
                content={"landmark": "inlet"},
                sources=[{"kind": "observed", "entry_id": spoken_entry}],
            ),
        ),
        dict(
            op="update",
            op_id="revise",
            id=ANCESTOR,
            gist="The report is uncertain.",
            content={"landmark": "upper inlet"},
        ),
        dict(op="supersede", op_id="supersede", id=ANCESTOR, by="new:1"),
        dict(op="commitment_status", op_id="keep", id=PROMISE, status="kept", note="I went."),
    ]


class ShoreTransport:
    def __init__(self):
        self.calls = []
        self.change_call = None

    def exchange(self, body, timeout_ms):
        request = json.loads(body)
        kind = request["text"]["format"]["name"]
        self.calls.append(kind)
        prompt = request["input"][1]["content"]
        if kind == "consolidation_selection":
            answer = {"read": [ANCESTOR]}
        elif kind == "consolidation_change_set":
            spoken = re.search(r"\[([^ ]+) \| tick \d+ \| utterance_result\] You said", prompt)
            assert spoken, prompt
            answer = {"ops": shore_ops(self.change_call, spoken[1])}
        elif kind == "morning":
            beach = re.search(r"(m:ryan:\d+) \| shore_note .*Remember the beach\.", prompt)
            assert beach, prompt
            answer = {"ids": [beach[1], PROMISE]}
        elif kind == "recall":
            answer = {"ids": [PROMISE, ANCESTOR]}
        elif kind == "decision":
            answer = {"step": "recall", "query": "What do I remember?"}
        elif self.calls.count("decision_after_recall") == 1:
            answer = json.loads(
                act(
                    "act",
                    verb="sleep",
                    params={"duration_ticks": 36},
                    intention={"set": "Check the beach."},
                )
            )
            answer["utterance"] = dict(
                addressee_id=None,
                speech_act="statement",
                text="Ella says the inlet floods.",
                terms=None,
                in_reply_to=None,
            )
        else:
            answer = json.loads(act())
        message = {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(answer)}],
        }
        return TransportResponse(
            200, json.dumps({"status": "completed", "output": [message]}).encode(), True
        )


def shore_recording(directory):
    record, kwargs, _ = start(directory)
    mind = record.session.resident
    store = mind.period.store
    store.registry.register(SHORE)
    mind.recipes.register(
        SHORE.recipes[0], lambda cues, revision: "coastal" in revision.flags, kind=ShoreNote.kind
    )
    seed(store)
    fake = ShoreTransport()
    mind.caller = replace(mind.caller, transport=fake)
    record.save(directory / "seeded.json")
    for _ in range(38):
        assert record.advance() is not None
        if flow := mind.period.workflow:
            call = flow.state.calls[0].call
            fake.change_call = f"{call.period_id}:{call.tick}:change_set"
        if mind.period.number == 2 and mind.period.context is not None:
            break
    assert mind.period.number == 2 and mind.period.context is not None
    keys = record.audit.keys(0, record.audit.cursor())
    (seal,) = [
        json.loads(record.audit.read(key)) for key in keys if key.endswith(".consolidation.json")
    ]
    return record, kwargs, fake, seal
