"""Retain small, digest-bound observations alongside the ordinary CT-04 journal."""

from pathlib import Path
from typing import Literal

from living_island.agents.types import DecisionRecord, OwnProfile
from living_island.analysis.data import RunLimits
from living_island.persistence.v2.journal import PacketJournal, store_once
from living_island.sim.equivalence.projection import Frame
from living_island.sim.equivalence.v1_extract import script_policy_config
from living_island.sim.equivalence.v2_extract import snapshot
from living_island.sim.v2 import cli
from living_island.sim.v2.compat.policy_host import (
    PolicyHost,
    PolicySession,
    _Proposal,
    restore_policies,
)
from living_island.world import protocol as legacy
from living_island.world.v2 import protocol as v2
from living_island.world.v2.engine import World, initialize
from living_island.world.v2.engine.items import tile_of
from living_island.world.v2.rules import load_vocabulary
from living_island.world.v2.rules.schema import canonical_json_bytes, content_hash

from ..receipts import State
from ..runtime import Boundary, Scenario
from ..starter import load_starter_pack

type Arm = Literal["compat-v1", "starter-v1"]


class Start(v2.ProtocolModel):
    intent: legacy.ActionIntent
    verb: str
    position: v2.Coord
    target: v2.Coord | None
    item: str | None
    utterance: bool
    intent_id: str


class Opening(v2.ProtocolModel):
    frame: Frame
    events: tuple[v2.WorldEvent, ...]
    map_rows: tuple[str, ...]
    tree_positions: dict[str, v2.Coord]
    limits: RunLimits
    canteen: str


class Interval(v2.ProtocolModel):
    frame: Frame
    events: tuple[v2.WorldEvent, ...]
    starts: dict[str, Start]
    decisions: list[DecisionRecord]
    outcomes: tuple[v2.ActionResult, ...]
    speech: dict[str, v2.UtteranceFeedback]
    awareness: dict[str, str]


class RecordingHost(PolicyHost):
    """Expose committed proposals to the observer, including on the death boundary."""

    committed: _Proposal | None = None

    def commit(self, proposal: _Proposal) -> None:
        super().commit(proposal)
        self.committed = proposal


def scenario(directory: Path, seed: int, arm: Arm) -> Scenario:
    config_dir = directory / "config"
    bound, cfg = cli.load_inputs("production", seed, config_dir)
    if arm == "starter-v1":
        starter = load_starter_pack(
            config_dir / "production.toml",
            cli.PACK.parent / arm,
            load_vocabulary(cli.VOCABULARY),
            map_path=config_dir / f"{bound.manifest.map_blob_sha256}.map",
            seed=seed,
        )
        initial = initialize(starter.pack, starter.setup)
    else:
        initial = cli.setup_world(bound, cfg)
    canteen = cfg.canteen.unique_item_id
    tree_positions = {
        key: tile_of(initial.state, e.place)
        for key, e in initial.state.entities.items()
        if e.archetype_id == "fruit_tree"
    }
    opening = Opening(
        frame=snapshot(initial, canteen),
        events=initial.initial_events,
        map_rows=bound.map_rows,
        tree_positions=tree_positions,
        canteen=canteen,
        limits=RunLimits(
            cfg.needs.min_value,
            cfg.needs.hydration_gain_per_serving,
            cfg.canteen.capacity_servings,
            cfg.fruit.max_stock_per_tree,
            cfg.inventory.slot_capacity,
            cfg.time.tick_minutes,
        ),
    )
    observations = directory / "observations"
    data = opening.model_dump(mode="json")
    store_once(observations / "opening.json", canonical_json_bytes(data))
    opening_hash = content_hash(data)
    world: World
    hosts: dict[str, RecordingHost]
    positions: dict[str, v2.Coord]
    awareness: dict[str, str]

    def remember() -> None:
        nonlocal positions, awareness
        positions = {k: r.position for k, r in world.state.residents.items() if r.alive}
        awareness = {k: world.state.awareness[k].kind for k in positions}

    def start(current: World, journal: PacketJournal, saved: State | None) -> PolicySession:
        nonlocal world, hosts
        world = current
        remember()
        states = restore_policies(saved) if saved is not None else None
        policy = script_policy_config(cfg)
        hosts = {
            r.id: RecordingHost(
                policy,
                OwnProfile(profile_id=r.profile_id, initial_goal=r.initial_goal),
                cfg.actions.sleep_ticks,
                restored=states[r.id] if states else None,
            )
            for r in cfg.residents
        }
        return PolicySession(world, hosts, journal)

    def observe(pins: State, boundary: Boundary) -> State:
        starts = {}
        records = []
        for actor, host in hosts.items():
            proposal = host.committed
            host.committed = None
            if proposal is None:
                continue
            if proposal.decision is not None:
                records.append(proposal.decision.trace.record)
            choice = proposal.submission.action
            if proposal.intent is None or not isinstance(choice, v2.IntentAction):
                continue
            intent = choice.intent
            target = intent.target
            pos = positions[actor]
            item = None
            location = None
            if isinstance(target, v2.TileTarget):
                location = target.position
            elif isinstance(target, v2.EntityTarget):
                location = tree_positions.get(target.id)
                if location is not None:
                    item = "fruit_tree"
                elif target.id == canteen:
                    location, item = pos, "canteen"
            if isinstance(proposal.intent.parameters, legacy.ItemTransferParameters):
                item = proposal.intent.parameters.item_type
            starts[actor] = Start(
                intent=proposal.intent,
                verb=intent.verb or intent.action,
                position=pos,
                target=location,
                item=item,
                utterance=proposal.submission.utterance is not None,
                intent_id=intent.intent_id,
            )
        for event in boundary.result.events:
            if event.type == "resident_fell_asleep" and event.actor_id is not None:
                awareness[event.actor_id] = "asleep"
        row = Interval(
            frame=snapshot(world, canteen),
            events=boundary.result.events,
            starts=starts,
            decisions=records,
            outcomes=boundary.result.actions,
            speech=boundary.result.utterances,
            awareness=awareness,
        )
        data = row.model_dump(mode="json")
        store_once(observations / f"{boundary.tick}.json", canonical_json_bytes(data))
        pins["opening"] = opening_hash
        pins[str(boundary.tick)] = content_hash(data)
        remember()
        return pins

    return Scenario(
        initial, bound.manifest.config_blob_sha256, bound.manifest.map_blob_sha256, start, observe
    )
