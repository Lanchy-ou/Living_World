"""Resident-owned inputs, detached packets and offline model replies."""

import json

import pytest


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
def add_record():
    def add(store, *, kind="belief", content=None, **fields):
        snapshot = store.snapshot
        record = store.registry.parse(
            {
                "id": snapshot.next_id(),
                "owner_id": snapshot.owner_id,
                "kind": kind,
                "created_tick": 0,
                "updated_tick": 0,
                "about_tick": None,
                "sources": [{"kind": "innate"}],
                "confidence": 2,
                "speech_derived": False,
                "last_used_tick": None,
                "use_count": 0,
                "supersedes": None,
                "superseded_by": None,
                "needs_review": False,
                "gist": "I remember " + snapshot.next_id(),
                "text": None,
                "content": content
                if content is not None
                else {
                    "subject": {"kind": "general", "ref": None},
                    "stance": "stable",
                    "topics": ["food"],
                },
                **fields,
            }
        )
        store.apply(snapshot.version, "mechanical", [record])
        return record

    return add


@pytest.fixture
def working_context(audit):
    from living_island.agents.v2.context.day_log import DayLog
    from living_island.agents.v2.context.prefix import FrozenPrefix, render_memory
    from living_island.agents.v2.context.working import WorkingContext

    def build(*, period="p:ella:1", memories=(), verbs=()):
        prefix = FrozenPrefix(period, verbs, (), tuple(render_memory(r) for r in memories), None)
        return WorkingContext(prefix, DayLog(period, audit, phenomena={}))

    return build


@pytest.fixture
def packet():
    from living_island.world.v2.protocol import (
        SCHEMA_VERSION,
        BoundaryDelivery,
        boundary_delivery_id,
    )

    def build(tick=0, reports=(), **perception):
        return BoundaryDelivery.model_validate(
            {
                "delivery_id": boundary_delivery_id("island", tick, "ella"),
                "actor_id": "ella",
                "observed_tick": tick,
                "perception": {
                    "schema_version": SCHEMA_VERSION,
                    "actor_id": "ella",
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
def fake_exchange():
    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls.fake import FakeClock, FakeTransport, ScriptedReply

    def build(outputs):
        clock = FakeClock()
        replies = []
        for value in outputs:
            if isinstance(value, TransportResponse):
                response = value
            else:
                envelope = {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": json.dumps(value)}],
                        }
                    ],
                }
                response = TransportResponse(200, json.dumps(envelope).encode(), True)
            replies.append(ScriptedReply(response))
        return clock, FakeTransport(clock, replies)

    return build
