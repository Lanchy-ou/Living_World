"""Detached resident packets and the write-only call journal for the context tests."""

import json

import pytest


@pytest.fixture
def packet():
    from living_island.world.v2.protocol import (
        SCHEMA_VERSION,
        BoundaryDelivery,
        boundary_delivery_id,
    )

    def build(*, tick=0, actor="ella", reports=(), **perception):
        return BoundaryDelivery.model_validate(
            {
                "delivery_id": boundary_delivery_id("island", tick, actor),
                "actor_id": actor,
                "observed_tick": tick,
                "perception": {
                    "schema_version": SCHEMA_VERSION,
                    "actor_id": actor,
                    "tick": tick,
                    "awareness": "awake",
                    "needs": [],
                    "own_position": {"x": 0, "y": 0},
                    "inventory": [],
                    "running_action": None,
                    "visible_tiles": [],
                    "explored_static_tiles": [],
                    "visible_entities": [],
                    "transient_sightings": [],
                    "environmental_cues": [],
                    "heard_utterances": [],
                    "observed_actions": [],
                    "action_feedback": [],
                    "last_utterance_feedback": None,
                    **perception,
                },
                "reports": list(reports),
            }
        )

    return build


@pytest.fixture
def audit(tmp_path):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.persistence._files import atomic_create
    from living_island.persistence.v2.journal import store_once

    return Journal(
        lambda key, data: store_once(tmp_path / key, data),
        lambda key, data: atomic_create(tmp_path / key, data),
    )


@pytest.fixture
def fake_exchange():
    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls.fake import FakeClock, FakeTransport, ScriptedReply

    def build(outputs):
        clock = FakeClock()
        replies = []
        for text in outputs:
            envelope = {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": text}],
                    }
                ],
            }
            replies.append(
                ScriptedReply(TransportResponse(200, json.dumps(envelope).encode(), True))
            )
        return clock, FakeTransport(clock, replies)

    return build
