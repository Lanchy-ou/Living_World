"""Record both stand-alone policies through the same world/coordinator boundary."""

from collections.abc import Iterator, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from living_island.agents.types import OwnProfile
from living_island.persistence.v2.journal import PacketJournal, store_once
from living_island.sim.equivalence.projection import Outcome
from living_island.sim.equivalence.v2_extract import snapshot
from living_island.sim.v2.compat.bridge import LegacyBridge
from living_island.sim.v2.compat.policy_host import (
    PolicyCheckpoint,
    PolicyHost,
    PolicySession,
    restore_policies,
)
from living_island.sim.v2.scenarios.receipts import Evidence, State
from living_island.sim.v2.scenarios.runtime import Boundary, Scenario
from living_island.sim.v2.turns import TurnRequest, turn_reasons
from living_island.world import protocol as legacy
from living_island.world.v2.engine import World
from living_island.world.v2.rules.schema import canonical_json_bytes

from .comparison import TraceBoundary
from .fixtures import Prepared

type Mode = Literal["bridge", "visible"]


def _policy_rows(
    hosts: Mapping[str, PolicyHost], states: Mapping[str, PolicyCheckpoint], tick: int
) -> dict[str, JsonValue]:
    rows: dict[str, JsonValue] = {}
    for actor, host in hosts.items():
        # Pending settlements and undeliverable death results exist only in the
        # bridge. The observer records objective terminal actions in the trajectory.
        row = states[actor].model_dump(mode="json", exclude={"pending_bridge", "terminal_results"})
        row["decision"] = (
            host.decision_trace[-1].record.model_dump(mode="json")
            if states[actor].last_decision_tick == tick
            else None
        )
        rows[actor] = row
    return rows


def _bridge_outcomes(
    boundary: Boundary,
    states: Mapping[str, PolicyCheckpoint],
    final_stops: list[legacy.ActionResult],
) -> list[JsonValue]:
    # Actor stops are recorded at the opening. All other private results are
    # captured at the close, including final actions with no surviving recipient.
    # Each resident runs one action in the interval. Keep the engine's settlement
    # order for the byte-level digest of the published PR-07 projection.
    closing = {
        result.actor_id: result
        for state in states.values()
        for result in (*state.pending_bridge.values(), *state.terminal_results)
        if result is not None and result.tick_finished == boundary.tick + 1
    }
    translated = [
        states[action.actor_id].boundary_results[-1]
        if action.stop is not None and action.stop.by == "actor"
        else closing[action.actor_id]
        for action in boundary.result.actions
    ]
    translated.extend(final_stops)
    return [
        Outcome(
            actor_id=result.actor_id,
            intent_id=result.intent_id,
            tick_started=result.tick_started,
            tick_finished=result.tick_finished,
            status=result.status,
            code=result.failure_code or result.interruption_reason,
        ).model_dump(mode="json")
        for result in translated
    ]


def _physical(world: World, canteen_id: str) -> dict[str, JsonValue]:
    # PR-07's extractor leaves these collections empty until appending events.
    # Keep speech, decisions and results in their native, separately keyed fields.
    return snapshot(world, canteen_id).model_dump(
        mode="json", exclude={"decisions", "outcomes", "utterances"}
    )


def _final_proposals(
    world: World, hosts: Mapping[str, PolicyHost]
) -> tuple[dict[str, JsonValue], list[legacy.ActionResult]]:
    """Observe the last scripted frame's decisions on detached policy state.

    PR-03 archives the choices made at its last scripted boundary. Deliver the
    pending packet and apply the stand-alone scheduling/plan rules without
    stepping the world into an extra interval or changing its saved controller.
    """
    submissions: list[JsonValue] = []
    stops = []
    for packet in world.pending_packets():
        host = hosts[packet.actor_id]
        host.ingest(packet)
        reasons = turn_reasons(packet, host.interruption(packet) is not None)
        if reasons:
            ordinal = world.state.turn_ordinals[packet.actor_id]
            proposal = host.propose(TurnRequest(packet, ordinal, reasons), world.run_id)
            submissions.append(proposal.submission.model_dump(mode="json"))
            if proposal.legacy_stop is not None:
                stops.append(proposal.legacy_stop)
            host.commit(proposal)
    states = {actor: host.checkpoint() for actor, host in hosts.items()}
    final: dict[str, JsonValue] = {
        "tick": world.tick,
        "actors": _policy_rows(hosts, states, world.tick),
        "submissions": submissions,
    }
    return final, stops


def scenario(prepared: Prepared, mode: Mode, trace_dir: Path) -> Scenario:
    """Create fresh policy hosts at setup and restore them at a CT-04 checkpoint."""
    config = prepared.config
    canteen_id = config.canteen.unique_item_id
    bridge = LegacyBridge(prepared.bound) if mode == "bridge" else None
    opening_tick = prepared.world.tick
    opening = _physical(prepared.world, canteen_id)
    hosts: dict[str, PolicyHost]
    world: World

    def make_hosts(restored: Mapping[str, PolicyCheckpoint] | None) -> dict[str, PolicyHost]:
        return {
            row.id: PolicyHost(
                prepared.policy_config,
                OwnProfile(profile_id=row.profile_id, initial_goal=row.initial_goal),
                config.actions.sleep_ticks,
                bridge=bridge,
                restored=None if restored is None else restored[row.id],
                policy_factory=prepared.policy_factory,
            )
            for row in config.residents
        }

    def start(current: World, journal: PacketJournal, state: State | None) -> PolicySession:
        nonlocal world, hosts
        world = current
        hosts = make_hosts(prepared.initial_policies if state is None else restore_policies(state))
        return PolicySession(world, hosts, journal)

    def observe(digests: State, boundary: Boundary) -> State:
        states = {actor: host.checkpoint() for actor, host in hosts.items()}
        trajectory: dict[str, JsonValue] = {
            "closing": _physical(world, canteen_id),
            "actions": [action.model_dump(mode="json") for action in boundary.result.actions],
            "utterances": {
                actor: speech.model_dump(mode="json")
                for actor, speech in boundary.result.utterances.items()
            },
            "spoken": [
                event.model_dump(mode="json")
                for event in boundary.result.events
                if event.type == "utterance_spoken"
            ],
        }
        if boundary.tick == opening_tick:
            trajectory["opening"] = opening
        final_stops: list[legacy.ActionResult] = []
        if world.tick == prepared.final_scripted_tick:
            detached = make_hosts(states)
            trajectory["final_boundary"], final_stops = _final_proposals(world, detached)
        row: dict[str, JsonValue] = {
            "seed": config.meta.seed,
            "tick": boundary.tick,
            "actors": _policy_rows(hosts, states, boundary.tick),
            "submissions": [turn.model_dump(mode="json") for turn in boundary.turns.submissions],
            "trajectory": trajectory,
        }
        if mode == "bridge":
            row["projected_outcomes"] = _bridge_outcomes(boundary, states, final_stops)
        data = canonical_json_bytes(row)
        store_once(trace_dir / f"{boundary.tick}.json", data)
        digests[str(boundary.tick)] = sha256(data).hexdigest()
        return digests

    return Scenario(
        prepared.world,
        prepared.bound.manifest.config_blob_sha256,
        prepared.bound.manifest.map_blob_sha256,
        start,
        observe,
    )


def verified_trace(trace_dir: Path, evidence: Evidence) -> Iterator[TraceBoundary]:
    """Verify each observation against its CT-04 evidence before comparison."""
    for tick in range(evidence.opening_tick, evidence.final_tick):
        path = trace_dir / f"{tick}.json"
        data = path.read_bytes()
        if sha256(data).hexdigest() != evidence.observer[str(tick)]:
            raise ValueError(f"{path}: calibration observation digest differs at tick {tick}")
        yield TraceBoundary.model_validate_json(data)
