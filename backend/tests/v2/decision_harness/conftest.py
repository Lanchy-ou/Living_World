from pathlib import Path

import pytest

from v2.working_context.conftest import audit as audit
from v2.working_context.conftest import fake_exchange as fake_exchange
from v2.working_context.conftest import packet as packet

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def island():
    from living_island.sim.v2.compat.config import load_compat_pack
    from living_island.world.content import EffectiveConfig
    from living_island.world.v2.rules import load_vocabulary

    bound = load_compat_pack(
        ROOT / "backend/tests/fixtures/replay/mechanics.toml",
        ROOT / "content/packs/compat-v1",
        load_vocabulary(ROOT / "content/vocabulary/vocab-0.1.toml"),
    )
    return bound, EffectiveConfig.model_validate(bound.config)


@pytest.fixture
def run(island, tmp_path, fake_exchange):
    from living_island.agents.types import OwnProfile
    from living_island.agents.v2.context.prefix import ResidentIdentity
    from living_island.agents.v2.decision.caller import Caller
    from living_island.memory.v2.profiles import SelectedProfile
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import script_policy_config
    from living_island.sim.v2.cli import setup_world
    from living_island.sim.v2.harness.composition import compose
    from v2.consolidation.conftest import journal

    bound, config = island

    def start(outputs, *, memory_on=True, world=None, compat=bound):
        clock, fake = fake_exchange(outputs)
        delays = []

        def delay(seconds):
            delays.append(seconds)
            clock.elapsed_ms += int(seconds * 1000)

        world = world or setup_world(bound, config)
        packets = PacketJournal(tmp_path / str(id(world)), world.run_id)
        files = {}
        kwargs = dict(
            actor="ella",
            identity=ResidentIdentity(
                "Ella", SelectedProfile.load(ROOT / "content/characters/v2/explorer.json")
            ),
            profiles={
                r.id: OwnProfile(profile_id=r.profile_id, initial_goal=r.initial_goal)
                for r in config.residents
            },
            config=script_policy_config(config),
            sleep_ticks=config.actions.sleep_ticks,
            caller=Caller(fake, clock, delay),
            packets=packets,
            journal=journal(files),
            memory_on=memory_on,
            compat=compat,
        )
        return compose(world, **kwargs), fake, delays, kwargs

    return start
