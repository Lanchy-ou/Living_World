"""A real compatibility runner with a deterministic resident and disconnected replay."""

import json
from pathlib import Path

from v2.decision_harness.resident_vectors import act

ROOT = Path(__file__).resolve().parents[4]


class ResidentTransport:
    def __init__(self):
        self.calls = []
        self.failed_morning = False

    def exchange(self, body, timeout_ms):
        from living_island.agents.llm.provider import TransportResponse

        request = json.loads(body)
        kind = request["text"]["format"]["name"]
        self.calls.append(kind)
        if kind == "morning" and not self.failed_morning:
            self.failed_morning = True
            return TransportResponse(400, b"{}", True)
        outputs = {
            "morning": '{"ids":["m:ryan:1"]}',
            "recall": '{"ids":["m:ryan:1"]}',
            "decision_after_recall": act(
                "act",
                verb="sleep",
                params={"duration_ticks": 36},
                intention={"set": "Remember the beach."},
            ),
            "consolidation_selection": '{"read":[]}',
            "consolidation_change_set": '{"ops":[]}',
            "decision": (
                act("act", verb="sleep", params={"duration_ticks": 36})
                if self.calls.count("decision") == 2
                else '{"step":"recall","query":"What do I remember?"}'
            ),
        }
        if (
            kind == "consolidation_change_set"
            and "| observation] You see ella at" in request["input"][1]["content"]
        ):
            line = next(
                line
                for line in request["input"][1]["content"].splitlines()
                if "| observation] You see ella at" in line
            )
            entry = line[1:].split(" | ", 1)[0]
            tick = int(line.split(" | tick ", 1)[1].split(" | ", 1)[0])
            outputs[kind] = json.dumps(
                {
                    "ops": [
                        {
                            "op": "add",
                            "op_id": "sighting",
                            "ref": "new:1",
                            "record": {
                                "kind": "episodic",
                                "about_tick": {"from": tick, "to": tick},
                                "gist": "I saw Ella nearby.",
                                "confidence": 3,
                                "content": {"participants": ["ella"], "place": None},
                                "sources": [{"kind": "observed", "entry_id": entry}],
                            },
                        }
                    ]
                }
            )
        output = [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": outputs[kind]}],
            }
        ]
        return TransportResponse(
            200, json.dumps({"status": "completed", "output": output}).encode(), True
        )


def start(directory):
    from living_island.agents.types import OwnProfile
    from living_island.agents.v2.calls.fake import FakeClock
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.context.prefix import ResidentIdentity
    from living_island.agents.v2.decision.caller import Caller
    from living_island.memory.v2.profiles import SelectedProfile
    from living_island.persistence.v2.audit import AuditReader, AuditWriter
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import script_policy_config
    from living_island.sim.v2.cli import setup_world
    from living_island.sim.v2.compat.config import load_compat_pack
    from living_island.sim.v2.harness.checkpoint import Recording
    from living_island.sim.v2.harness.composition import compose
    from living_island.world.content import EffectiveConfig
    from living_island.world.v2.engine.perception import build_deliveries
    from living_island.world.v2.engine.tick import EventWriter, TickContext
    from living_island.world.v2.rules import load_vocabulary

    compat = load_compat_pack(
        ROOT / "backend/tests/fixtures/replay/mechanics.toml",
        ROOT / "content/packs/compat-v1",
        load_vocabulary(ROOT / "content/vocabulary/vocab-0.1.toml"),
    )
    config = EffectiveConfig.model_validate(compat.config)
    world = setup_world(compat, config)
    # The mechanics fixture starts at 70 health for an early-death test.
    # Keep Ryan alive for the two K closures in the evidence recording.
    world.state.needs["ryan"]["health"] = 10000
    build_deliveries(TickContext(world.state, world.pack, EventWriter(world.state, 0)))
    fake = ResidentTransport()
    audit = AuditWriter(directory / "resident.sqlite")
    packets = PacketJournal(directory / "packets", world.run_id)
    kwargs = dict(
        actor="ryan",
        identity=ResidentIdentity(
            "Ryan", SelectedProfile.load(ROOT / "content/characters/v2/explorer.json")
        ),
        profiles={
            r.id: OwnProfile(profile_id=r.profile_id, initial_goal=r.initial_goal)
            for r in config.residents
        },
        config=script_policy_config(config),
        sleep_ticks=config.actions.sleep_ticks,
        caller=Caller(fake, FakeClock(), lambda _: None),
        compat=compat,
        memory_on=True,
        packets=packets,
        journal=Journal(audit.keep, audit.create),
    )
    record = Recording.opening(compose(world, **kwargs), packets, AuditReader(audit.path))
    record.save(directory / "opening.json")
    return record, kwargs, fake


def verify(directory, record, kwargs, start_at="opening", *, boundaries):
    from living_island.persistence.v2.manifest import RunManifest
    from living_island.persistence.v2.replay import RuleStore
    from living_island.sim.v2.harness.checkpoint import load
    from living_island.sim.v2.harness.replay import replay_resident

    world, runtime = load(
        directory / f"{start_at}.json", kwargs["compat"].pack, record.packets, record.audit
    )
    manifest = RunManifest.capture(world.run_id, world.pack.source)
    return list(
        replay_resident(
            world,
            runtime,
            manifest,
            record.packets,
            RuleStore(directory),
            record.audit,
            boundaries=boundaries,
        )
    )
