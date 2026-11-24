"""A single WAP runner with one resident-local journal per model-controlled actor."""

from dataclasses import asdict
from pathlib import Path

from living_island.agents.types import OwnProfile
from living_island.agents.v2.calls.contracts import digest
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.context.prefix import ResidentIdentity
from living_island.agents.v2.decision.caller import Caller
from living_island.memory.v2.profiles import SelectedProfile
from living_island.persistence.v2.audit import AuditReader, AuditWriter
from living_island.persistence.v2.journal import PacketJournal
from living_island.persistence.v2.manifest import RunManifest, write_manifest
from living_island.sim.equivalence.v1_extract import script_policy_config
from living_island.sim.v2.cli import PACK, VOCABULARY, build_world_setup
from living_island.sim.v2.compat.config import load_compat_pack
from living_island.sim.v2.harness.agreement_facts import project_agreement_facts
from living_island.sim.v2.harness.checkpoint import Boundary, Recording
from living_island.sim.v2.harness.composition import compose
from living_island.sim.v2.runner import Runner
from living_island.world.content import EffectiveConfig
from living_island.world.v2.engine import initialize
from living_island.world.v2.engine.snapshot import encode_snapshot
from living_island.world.v2.engine.validate import ResidentSetup
from living_island.world.v2.protocol import Coord
from living_island.world.v2.rules import load_vocabulary
from v2.fake_workload.script import WorkloadTransport

ROOT = Path(__file__).resolve().parents[4]
SEED = 20261108
TREES = {"ella": 3, "ryan": 2, "mia": 5, "noah": 4, "iris": 0}


class Island:
    def __init__(self, directory, case, ticks):
        self.directory = directory
        self.ticks = ticks
        week = case == "week"
        config_file = (
            ROOT / "backend/tests/fixtures/v1_projection/configs/regrowth-2.toml"
            if week
            else ROOT / "content/worlds/default.toml"
        )
        self.compat = load_compat_pack(
            config_file,
            PACK,
            load_vocabulary(VOCABULARY),
            map_path=ROOT / "content/worlds/default-island.map",
            seed=SEED,
        )
        self.config = config = EffectiveConfig.model_validate(self.compat.config)
        setup = build_world_setup(self.compat, config, pack_ids=self.compat.pack.pack_ids)
        self.profiles = {
            row.id: OwnProfile(profile_id=row.profile_id, initial_goal=row.initial_goal)
            for row in config.residents
        }
        residents = list(setup.residents)
        if week:
            for actor, profile, x in (("noah", "maker", 36), ("iris", "bold", 37)):
                residents.append(ResidentSetup(id=actor, position=Coord(x=x, y=32)))
                self.profiles[actor] = OwnProfile(profile_id=profile, initial_goal="")
        self.setup = setup.model_copy(
            update={"residents": tuple(residents), "run_id": f"ev05-{case}"}
        )
        self.world = initialize(self.compat.pack, self.setup)
        self.manifest = RunManifest.capture(self.world.run_id, self.compat.pack)
        write_manifest(directory / "wap-manifest.json", self.manifest)
        self.packets = PacketJournal(directory / "packets", self.world.run_id)
        self.recordings = {}
        self.fakes = {}
        self.selected = {}
        for actor, profile in self.profiles.items():
            selected = SelectedProfile.load(
                ROOT / f"content/characters/v2/{profile.profile_id}.json"
            )
            self.selected[actor] = selected
            if not week and actor != "ella":
                continue
            home = directory / actor
            writer = AuditWriter(home / "resident.sqlite")
            fake = WorkloadTransport(
                actor,
                self.compat.map_rows,
                config.world.fruit_trees[TREES[actor]],
                config.world.spring,
            )
            self.fakes[actor] = fake
            session = compose(
                self.world,
                actor=actor,
                identity=ResidentIdentity(actor.title(), selected),
                profiles={actor: profile} if week else self.profiles,
                config=script_policy_config(config),
                sleep_ticks=config.actions.sleep_ticks,
                caller=Caller(fake, fake.clock, fake.delay),
                packets=self.packets,
                journal=Journal(writer.keep, writer.create),
                memory_on=True,
                compat=self.compat,
            )
            record = Recording.opening(session, self.packets, AuditReader(writer.path))
            record.save(home / "opening.json")
            self.recordings[actor] = record
        self.runner = Runner(self.world, self.choose, deliver=self.deliver, journal=self.packets)

    def pins(self):
        return {
            "compat": asdict(self.compat.manifest),
            "setup": self.setup.model_dump(mode="json"),
            "wap": self.manifest.model_dump(mode="json"),
            "profiles": {
                actor: {
                    "sha256": selected.sha256,
                    **selected.document.model_dump(),
                    "controller": "fake" if actor in self.fakes else "rule",
                }
                for actor, selected in self.selected.items()
            },
        }

    def deliver(self, packet):
        return self.recordings[packet.actor_id].session._deliver(packet)

    def choose(self, request):
        return self.recordings[request.delivery.actor_id].session._choose(request)

    def advance(self):
        # The fixture's final sleep must leave a delivery at K for any authorized
        # consolidation. A shorter ordinary sleep keeps the last period open.
        for fake in self.fakes.values():
            fake.sleep_duration = max(6, min(36, self.ticks - self.world.tick - 1))
        if len(self.recordings) == 1:
            return self.recordings["ella"].advance()
        # ResidentSession is single-model. Route its normal delivery and choice
        # hooks by actor; settle their proposals together in one authoritative step.
        for record in self.recordings.values():
            record.session.request = None
        result = self.runner.advance()
        if result is None:
            raise RuntimeError(f"Workload stopped at {self.runner.manifest.stop}")
        commit = self.runner.manifest.boundaries[-1]
        world_hash = digest(encode_snapshot(self.world))
        fallbacks = {f.submission.actor_id: f for f in commit.fallback_turns}
        for actor, record in self.recordings.items():
            session = record.session
            host = session.model_host
            request = session.request
            if request:
                proposal = session._staged.pop(actor)
                host.commit(proposal)
            for action in result.actions:
                if action.actor_id == actor:
                    host.capture(
                        action,
                        result.utterances.get(actor),
                        self.world.state.residents[actor].alive,
                    )
            session.agreements = project_agreement_facts(result.events, actor)
            for key in session._finished:
                del session.intents[key]
            session._finished = ()
            session.spoken = None
            decision_key = None
            period = session.resident.period
            journal = period.journal
            if request:
                sub = proposal.submission
                decision = session.resident.publish(
                    request.turn_id, request.reasons, sub, fallbacks.get(actor)
                )
                decision_key = journal.cursor(decision.turn_id, "decision")
                if sub.action.kind == "intent":
                    session.intents[sub.action.intent.intent_id] = sub.action.intent
                session.spoken = sub.utterance
            if not self.world.state.residents[actor].alive:
                period.death(self.world.tick)
                raise RuntimeError(f"{actor} died at {self.world.tick}")
            snap = period.store.snapshot
            event_ref = journal.blob(commit.event_lines)
            journal.fact(
                self.world.run_id,
                f"{commit.tick}.boundary",
                Boundary(
                    tick=commit.tick,
                    through=record.audit.cursor(),
                    committed=True,
                    submissions=commit.submissions,
                    fallbacks=commit.fallback_turns,
                    events=event_ref,
                    world_hash=world_hash,
                    store_version=snap.version,
                    store_hash=snap.store_hash,
                    decision=decision_key,
                    stop=None,
                    incomplete=None,
                ),
            )
        return result
