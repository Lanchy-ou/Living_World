"""Multi-actor boundary scheduling and plan-queue acceptance."""

from test_engine_actions import content_with
from test_sim_policies import PROFILE, policy_config
from test_sim_runtime import WaitPolicy

from living_island.agents.policies._plans import WAIT
from living_island.agents.runtime import Runtime, create_runtime
from living_island.agents.types import ActorScript, IntentTemplate
from living_island.sim.runner import BoundaryLoop
from living_island.world.facts import ActionFailedPayload
from living_island.world.ports import create_engine
from living_island.world.protocol import Coord, EmptyParameters, EntityTarget, TileTarget


def template(action_type, target=None):
    return IntentTemplate(
        action_type=action_type, target=target, parameters=EmptyParameters(), reason=None
    )


def scripted(actor_id, plans):
    return create_runtime(
        actor_id,
        policy_config("scripted-v0", max_plan_actions=5),
        PROFILE,
        ActorScript(actor_id=actor_id, on_exhausted="wait", plans=plans),
        None,
        None,
    )


def test_ai04_multitick_move_is_one_intent_and_queue_continues():
    content = content_with(
        {"ella": (6, 4)},
        map={"walk_cost_budget_per_tick": 2, "step_cost_grass": 2},
        perception={"day_radius_tiles": 10},
    )
    move = template("move_to", TileTarget(kind="tile", position=Coord(x=2, y=4)))
    ella = scripted("ella", [[move, WAIT]])
    loop = BoundaryLoop(create_engine(content, None), [ella])
    commits = [loop.advance() for _ in range(3)]
    first = commits[0][1][0]
    move_id, wait_id = [intent.intent_id for intent in first.plan.intents]
    events = [event for commit, _ in commits for event in commit.events]
    assert [event.intent_id for event in events if event.type == "resident_moved"] == [move_id] * 4
    assert [
        (event.intent_id, event.tick) for event in events if event.type == "action_started"
    ] == [
        (move_id, 1),
        (wait_id, 3),
    ]
    assert [record for _, records in commits for record in records] == [first]
    assert commits[-1][0].snapshot.residents[0].position == Coord(x=2, y=4)


def test_ai05_last_fruit_loser_discards_remainder_and_replans():
    content = content_with({"ella": (3, 3), "ryan": (4, 2)})
    gather = template("gather", EntityTarget(kind="entity", id="fruit_01"))
    ella, ryan = (scripted(actor, [[gather, WAIT]]) for actor in ("ella", "ryan"))
    loop = BoundaryLoop(create_engine(content, None), [ryan, ella])
    _, initial = loop.advance()
    assert [record.actor_id for record in initial] == ["ella", "ryan"]
    settled, decisions = loop.advance()
    assert decisions == []
    [failure] = [event for event in settled.events if event.type == "action_failed"]
    assert isinstance(failure.payload, ActionFailedPayload)
    assert failure.payload.failure_code == "RESOURCE_TAKEN"
    continued, [replacement] = loop.advance()
    assert replacement.actor_id == failure.actor_id
    assert replacement.tick == settled.snapshot.tick
    assert "ACTION_FAILED" in replacement.triggers
    losing = next(record for record in initial if record.actor_id == failure.actor_id)
    assert losing.plan.intents[1].intent_id not in {e.intent_id for e in continued.events}


class PacketTriggers:
    """Inject repeat observations into genuine sleep boundaries."""

    def __init__(self, engine):
        self.engine = engine

    def __getattr__(self, name):
        return getattr(self.engine, name)

    def advance_tick(self):
        commit = self.engine.advance_tick()
        if 1 <= commit.snapshot.tick <= 2:
            [packet] = commit.pending_deliveries
            return commit.model_copy(
                update={
                    "pending_deliveries": [
                        packet.model_copy(
                            update={
                                "decision_triggers": ["NEW_SIGHT", "UTTERANCE_HEARD"],
                            }
                        )
                    ],
                }
            )
        return commit


def test_ai06_deferred_triggers_merge_once_in_canonical_order():
    content = content_with({"ella": (2, 3)}, actions={"sleep_ticks": 3})
    ella = scripted("ella", [[template("sleep"), WAIT]])
    loop = BoundaryLoop(PacketTriggers(create_engine(content, None)), [ella])
    first, [initial] = loop.advance()
    assert first.snapshot.active_actions
    assert loop.advance()[1] == []
    assert loop.advance()[1] == []
    committed, [next_record] = loop.advance()
    assert next_record.triggers == ["NEW_SIGHT", "UTTERANCE_HEARD", "WOKE"]
    assert next_record.decision_ordinal == 1
    assert initial.plan.intents[1].intent_id not in {e.intent_id for e in committed.events}


def test_ai11_sleeper_ingests_each_packet_without_replanning():
    content = content_with({"ella": (2, 3)}, actions={"sleep_ticks": 4})
    ella = scripted("ella", [[template("sleep")]])
    loop = BoundaryLoop(create_engine(content, None), [ella])
    for tick in range(4):
        _, records = loop.advance()
        assert len(records) == (tick == 0)
        assert ella.export_state().latest_perception_tick == tick
    _, [record] = loop.advance()
    assert record.triggers == ["WOKE", "PLAN_FINISHED"]


def test_all_dead_keeps_advancing_without_resident_decisions():
    content = content_with(
        {"ella": (2, 3), "ryan": (4, 4)},
        needs={"initial_health": 1, "initial_hydration": 0},
    )
    runtimes = [scripted(actor, []) for actor in ("ella", "ryan")]
    loop = BoundaryLoop(create_engine(content, None), runtimes)
    dead, decisions = loop.advance()
    assert len(decisions) == 2
    assert not any(resident.alive for resident in dead.snapshot.residents)
    assert dead.pending_deliveries == []
    for tick in range(2, 6):
        commit, decisions = loop.advance()
        assert commit.snapshot.tick == tick
        assert not decisions and not commit.pending_deliveries
    assert [runtime.export_state().latest_perception_tick for runtime in runtimes] == [0, 0]


def test_policy_exception_stops_before_physical_commit():
    content = content_with({"ella": (2, 3)})

    class Unexpected(WaitPolicy):
        def decide(self, request):
            raise RuntimeError("policy bug")

    ella = Runtime("ella", policy_config(), PROFILE, Unexpected())
    loop = BoundaryLoop(create_engine(content, None), [ella])
    import pytest

    with pytest.raises(RuntimeError, match="policy bug"):
        loop.advance()
    assert loop.boundary.snapshot.tick == 0
    with pytest.raises(ValueError, match="stopped"):
        loop.advance()
