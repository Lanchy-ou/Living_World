"""Reproduce the EV-06 waking-prefix failure with the normal resident runner."""

import json

import pytest

from living_island.agents.llm.provider import TransportResponse
from living_island.agents.v2.calls.contracts import json_bytes
from living_island.agents.v2.calls.fake import FakeClock
from living_island.agents.v2.decision.caller import Caller
from v2.decision_harness.resident_vectors import act
from v2.resident_replay.replay_fixture import start


def test_evicted_intention_cannot_reach_decision_or_receive_use_credit(tmp_path):
    recording, _, _ = start(tmp_path)
    resident = recording.session.resident
    retained = "m:ryan:1"
    old_text = "Follow the tracks at dusk."

    class ScriptedResident:
        decisions = 0

        def __init__(self):
            self.sent = []

        def exchange(self, body, timeout_ms):
            wire = json.loads(body)
            kind = wire["text"]["format"]["name"]
            self.sent.append((kind, wire["input"][1]["content"]))
            if kind == "decision":
                self.decisions += 1
                if self.decisions == 1:
                    reply = act(
                        "act",
                        verb="sleep",
                        params={"duration_ticks": 36},
                        intention={"set": old_text},
                    )
                elif self.decisions == 2:
                    reply = '{"step":"recall","query":"What was my intention?"}'
                else:
                    reply = act(intention={"set": f"New intention {self.decisions}."})
            else:
                reply = {
                    "morning": json.dumps({"ids": [evicted, retained]}),
                    "recall": json.dumps({"ids": [evicted]}),
                    "decision_after_recall": act(intention={"set": "Choose another route."}),
                    "consolidation_selection": '{"read":[]}',
                    "consolidation_change_set": '{"ops":[]}',
                }[kind]
            return TransportResponse(
                200,
                json_bytes(
                    {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "status": "completed",
                                "content": [{"type": "output_text", "text": reply}],
                            }
                        ],
                    }
                ),
                True,
            )

    transport = ScriptedResident()
    resident.caller = Caller(transport, FakeClock(), lambda _: None)
    assert recording.advance() is not None
    evicted = resident.period.store.snapshot.current_intention().id
    for _ in range(65):
        assert recording.advance() is not None
        snapshot = resident.period.store.snapshot
        if transport.decisions > 2 and evicted not in {row.id for row in snapshot.records()}:
            break
    else:
        pytest.fail("the script did not fill the intention history")

    context = resident.period.context
    assert context.prefix.morning.selected_ids == (evicted, retained)
    assert any(entry.retrieved and entry.retrieved.id == evicted for entry in context.log.entries)
    assert transport.sent[-1][0] == "decision" and old_text in transport.sent[-1][1]

    # The frozen carriers still name the evicted record. On the old assembler
    # the next exclusive dispatch claim fails in store.credit_dispatch.
    assert recording.advance() is not None
    kind, text = transport.sent[-1]
    assert kind == "decision" and old_text not in text and evicted not in text
    assert retained in text
    assert resident.period.store.snapshot.credited_ids == {retained}
