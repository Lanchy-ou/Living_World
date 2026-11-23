"""Reconstruct the committed PR-03 scripts and the registered P2 acceptance starts."""

from dataclasses import dataclass
from functools import partial
from itertools import chain
from pathlib import Path

from pydantic import JsonValue

from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.types import IntentTemplate, PolicyConfig
from living_island.sim.equivalence import v1_extract as archive
from living_island.sim.equivalence.compare import _first
from living_island.sim.equivalence.v1_extract import ScriptCase
from living_island.sim.v2 import cli
from living_island.sim.v2.compat.adapters import project_perception
from living_island.sim.v2.compat.config import BoundCompatPack
from living_island.sim.v2.compat.policy_host import PolicyCheckpoint, PolicyFactory
from living_island.sim.v2.turns import TurnRequest
from living_island.world import protocol as v1
from living_island.world.content import EffectiveConfig, WorldContent
from living_island.world.engine import Engine
from living_island.world.v2 import protocol as v2
from living_island.world.v2.engine import World
from living_island.world.v2.engine.events import EventWriter
from living_island.world.v2.engine.perception import build_deliveries
from living_island.world.v2.engine.state import (
    DialogueSession,
    Entity,
    Held,
    Lineage,
    OnTile,
    Place,
)
from living_island.world.v2.engine.tick import TickContext

from .comparison import Difference, TraceBoundary


@dataclass(frozen=True)
class Prepared:
    world: World
    bound: BoundCompatPack
    config: EffectiveConfig
    policy_config: PolicyConfig
    policy_factory: PolicyFactory
    initial_policies: dict[str, PolicyCheckpoint] | None
    final_scripted_tick: int | None


def _content(bound: BoundCompatPack, config: EffectiveConfig) -> WorldContent:
    return WorldContent(
        config=config,
        map_rows=list(bound.map_rows),
        config_hash=bound.manifest.effective_config_sha256,
        map_hash=bound.manifest.map_sha256,
    )


def _point(value: v1.Coord) -> v2.Coord:
    return v2.Coord(x=value.x, y=value.y)


def _scripted_world(bound: BoundCompatPack, config: EffectiveConfig, script: ScriptCase) -> World:
    # PR-03 owns the starting conditions as well as the intent templates. Apply
    # its setup once to the same pre-observation physical state as ScriptCase.run.
    original = Engine(_content(bound, config), None, ())._state
    if script.setup is not None:
        script.setup(original, config)
    positions = {row.id: [row.position.x, row.position.y] for row in original.residents}
    staged = [
        resident.model_copy(update={"position": positions[resident.id]})
        for resident in config.residents
    ]
    world = cli.setup_world(bound, config.model_copy(update={"residents": staged}))
    state = world.state
    canteen = original.unique_canteen
    for resident in original.residents:
        state.needs[resident.id] = {key: getattr(resident, key) for key in state.needs[resident.id]}
        if resident.id == canteen.holder_id:
            state.entities[canteen.id].place = Held(resident.id)
            state.entities[canteen.id].owner_id = resident.id
    for tree in original.fruit_nodes:
        state.entities[tree.id].components["store"]["count"] = tree.stock

    water = state.entities[f"{canteen.id}_water"]
    if canteen.servings:
        water.quantity = canteen.servings
        water.lineage = (Lineage(water.entity_id, 0, water.quantity, 1),)
    else:
        del state.entities[water.entity_id]
    stacks: list[tuple[Place, str | None, int]] = [
        (Held(row.id), row.id, row.fruit_count) for row in original.residents
    ]
    stacks.extend(
        (OnTile(_point(row.position)), None, row.quantity) for row in original.ground_fruit
    )
    for index, (place, owner, quantity) in enumerate(stacks):
        if quantity:
            key = f"fixture_fruit_{index}"
            state.entities[key] = Entity(
                key,
                "fruit",
                "fruit",
                quantity,
                0,
                owner,
                place,
                {"portable": {"slots_per_unit": 1}},
                {},
                {},
                (),
                True,
                (Lineage(key, 0, quantity, index + 10),),
            )
    for session in original.dialogue_sessions:
        first, second = session.pair_ids
        pair = (first, second)
        state.dialogue_sessions[pair] = DialogueSession(
            pair, session.turn_count, session.last_utterance_tick, session.cooldown_until_tick
        )
    for footprint in original.explored_tiles_by_resident:
        state.explored_tiles_by_resident[footprint.resident_id].update(footprint.tile_indices)
    if script.start:
        _bootstrap_dusk(world, script.start)
    else:
        build_deliveries(TickContext(state, world.pack, EventWriter(state, 0)))
    return world


def _bootstrap_dusk(world: World, start: int) -> None:
    """PR-03's daylight fixture opens after a real wait across the dusk bootstrap."""
    state = world.state
    state.tick = start - 1
    state.clock_minute = state.clock.minute_at(state.tick)
    wait = v2.ModelTurn(
        action=v2.ModelIntentAction(
            kind="intent",
            intent=v2.IntentShape(
                action="wait",
                verb=None,
                target=None,
                instruments=[],
                inputs=[],
                params={},
                reason=None,
            ),
        ),
        utterance=None,
    )
    for actor, packet in state.pending_deliveries.items():
        state.explored_tiles_by_resident[actor].clear()
        state.pending_deliveries[actor] = packet.model_copy(
            update={
                "observed_tick": state.tick,
                "delivery_id": v2.boundary_delivery_id(state.run_id, state.tick, actor),
                "perception": packet.perception.model_copy(update={"tick": state.tick}),
            }
        )
    opening = world.pending_packets()
    world.step(
        [TurnRequest(packet, 0, ("start",)).bind(wait) for packet in opening],
        acknowledged={packet.actor_id: packet.delivery_id for packet in opening},
    )


def _bootstrap_policies(world: World) -> dict[str, PolicyCheckpoint]:
    policies = {}
    for packet in world.pending_packets():
        receipts, _ = PolicyCheckpoint().receipts.ingest(project_perception(packet.perception))
        policies[packet.actor_id] = PolicyCheckpoint(
            cursor=world.tick - 1, receipts=receipts, deferred=("PLAN_FINISHED",)
        )
    return policies


@dataclass(frozen=True)
class CalibrationCase:
    name: str
    config: str
    seed: int
    start: int
    end: int
    fixture_input: Path
    archive: Path | None
    script: ScriptCase | None
    restore_after: int | None = None

    def prepare(self, inputs: Path) -> Prepared:
        bound, config = cli.load_inputs(self.config, self.seed, inputs)
        policy = archive.script_policy_config(config)
        script = self.script
        if script is None:
            world = cli.setup_world(bound, config)
            return Prepared(world, bound, config, policy, RuleBasedPolicy, None, None)
        world = _scripted_world(bound, config, script)
        overrides = {
            (actor, tick + script.start): plan for (actor, tick), plan in script.plans.items()
        }
        factory = partial(archive.FixturePolicy, overrides=overrides, observed=script.observed)
        initial = _bootstrap_policies(world) if script.start else None
        return Prepared(world, bound, config, policy, factory, initial, self.end)


class _Vector(v2.ProtocolModel):
    name: str
    config: str
    seed: int
    actor: str
    ticks: v2.Tick
    plan: tuple[IntentTemplate, ...]


def generic_failure_difference(row: TraceBoundary) -> Difference | None:
    """Check the DL-25 act vector against its expected witness, even if both arms agree."""
    actor = "ella"
    opening = row.actors[actor]
    closing = row.trajectory.final_boundary
    results = [action for action in row.trajectory.actions if action.actor_id == actor]
    physical: list[JsonValue] = [
        [r.outcome, r.failure_code, r.visible_feedback.status, r.visible_feedback.failure_code]
        for r in results
    ]
    submitted: list[JsonValue] = [
        [turn.action.intent.action, turn.action.intent.verb]
        for turn in row.submissions
        if turn.actor_id == actor and turn.action.kind == "intent"
    ]
    ending: dict[str, JsonValue] | None = None
    if closing is not None:
        state = closing.actors[actor]
        decision = state.decision
        ending = {
            "results": [[r.intent_id, r.status, r.failure_code] for r in state.boundary_results],
            "triggers": list(state.boundary_triggers),
            "queue": [i.intent_id for i in state.queue],
            "selected": None
            if decision is None
            else [
                decision.tick,
                decision.decision_ordinal,
                list(decision.triggers),
                [i.action_type for i in decision.plan.intents],
            ],
        }
    witnesses: tuple[tuple[int, int, str, JsonValue, JsonValue], ...] = (
        (0, 0, "submitted", [["act", "eat"]], submitted),
        (0, 0, "queue", ["ella:p000000:i1"], [intent.intent_id for intent in opening.queue]),
        (1, 1, "action_feedback", [["failure", "NO_ITEM", "failed", "NO_ITEM"]], physical),
        (
            1,
            1,
            "next",
            {
                "results": [["ella:p000000:i0", "failure", "NO_ITEM"]],
                "triggers": ["ACTION_FAILED"],
                "queue": [],
                "selected": [1, 1, ["ACTION_FAILED"], ["move_to"]],
            },
            ending,
        ),
    )
    for tick, ordinal, field, expected, actual in witnesses:
        delta = _first(expected, actual, f"dl25.{field}")
        if delta is not None:
            path, wanted, found = delta
            return Difference(
                seed=row.seed,
                tick=tick,
                actor=actor,
                ordinal=ordinal,
                field=path,
                expected=wanted,
                actual=found,
            )
    return None


def calibration_cases(inputs: Path) -> tuple[CalibrationCase, ...]:
    """Enumerate required cases from the registered procedures, independently of available files."""
    bound, config = cli.load_inputs("mechanics", 20261108, inputs)
    scripts = chain(
        archive.urgent_cases(config),
        archive.speech_cases(_content(bound, config)),
        archive.transfer_cases(),
        archive.physical_cases(),
        archive.sleep_and_sight_cases(),
        archive.config_cases(),
    )
    cases = []
    for script in scripts:
        if not script.name.startswith(("wap23-", "wap35-")):
            continue
        path = cli.FIXTURES / "scripted" / f"{script.name}.json.gz"
        restore_after = 2 if script.name == "wap23-reply-first-reply" else script.restore_after
        cases.append(
            CalibrationCase(
                script.name,
                script.config,
                script.seed,
                script.start,
                script.start + script.ticks,
                path,
                path,
                script,
                restore_after,
            )
        )
    vector_file = Path(__file__).with_name("dl25-no-item.json")
    vector = _Vector.model_validate_json(vector_file.read_bytes())
    vector_script = ScriptCase(
        vector.name,
        {(vector.actor, 0): vector.plan},
        ticks=vector.ticks,
        config=vector.config,
        seed=vector.seed,
        observed=vector.actor,
    )
    cases.append(
        CalibrationCase(
            vector.name,
            vector.config,
            vector.seed,
            0,
            vector.ticks,
            vector_file,
            None,
            vector_script,
        )
    )
    for name in cli.matrix_names():
        if name.startswith("acceptance-"):
            seed = int(name.rsplit("-", 1)[1])
            path = cli.FIXTURES / "matrix" / f"{name}.json.gz"
            cases.append(
                CalibrationCase(name, "production", seed, 0, cli.HORIZON, path, path, None)
            )
    return tuple(sorted(cases, key=lambda case: case.name))
