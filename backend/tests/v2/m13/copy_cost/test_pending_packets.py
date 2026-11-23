"""Check mutable descendants of packets returned to independent readers."""

from pathlib import Path
from runpy import run_path

_fixtures = run_path(str(Path(__file__).resolve().parents[2] / "engine/conftest.py"))
pack = _fixtures["pack"]
setup = _fixtures["setup"]


def test_pending_readers_own_exploration_and_nested_entity_lists(pack, setup, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.protocol import canonical_bytes

    world = initialize(pack, setup)
    original = world.pending_packets()
    expected = tuple(map(canonical_bytes, original))
    edited = world.pending_packets()[0].perception

    assert edited.explored_static_tiles
    edited.explored_static_tiles.clear()
    edited.visible_entities[0].observable_signs.append("weak")

    assert tuple(map(canonical_bytes, original)) == expected
    assert tuple(map(canonical_bytes, world.pending_packets())) == expected
    journal = PacketJournal(tmp_path, world.run_id)
    journal.ingest(world)
    assert tuple(map(canonical_bytes, journal.read(0))) == expected


def test_runner_callbacks_own_their_tile_lists(pack, setup, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.manifest import TerminalStop
    from living_island.sim.v2.runner import Runner
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.protocol import canonical_bytes

    world = initialize(pack, setup)
    expected = {packet.actor_id: canonical_bytes(packet) for packet in world.pending_packets()}
    journal = PacketJournal(tmp_path, world.run_id)

    def edit(packet):
        assert canonical_bytes(packet) == expected[packet.actor_id]
        view = packet.perception
        assert view.visible_tiles and view.explored_static_tiles
        view.visible_tiles.clear()
        view.explored_static_tiles.clear()
        view.visible_entities[0].observable_signs.append("weak")

    def deliver(packet):
        edit(packet)
        return False

    def decide(request):
        edit(request.delivery)
        return TerminalStop("test stop", None)

    runner = Runner(world, decide, deliver=deliver, journal=journal)
    assert runner.advance() is None
    assert runner.manifest.stop is not None
    assert {
        packet.actor_id: canonical_bytes(packet) for packet in world.pending_packets()
    } == expected
    assert {packet.actor_id: canonical_bytes(packet) for packet in journal.read(0)} == expected


def test_model_packet_owns_lists_after_filtering(pack, setup):
    from living_island.agents.types import OwnProfile, PolicyConfig, RuleParams
    from living_island.sim.v2.compat.policy_host import NeutralActionEnd, PolicyHost
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.protocol import canonical_bytes

    host = PolicyHost(
        PolicyConfig(
            policy_id="rule-based-v0",
            seed=setup.seed,
            max_plan_actions=1,
            map_width=len(setup.terrain.rows[0]),
            map_height=len(setup.terrain.rows),
            script_sha256=None,
            source_trace_sha256=None,
            rule_params=RuleParams(
                rule_params_version="0.1",
                canteen_use="enabled",
                cue_use="enabled",
                fruit_carry_target=2,
                failed_target_retry_ticks=36,
            ),
        ),
        OwnProfile(profile_id="test", initial_goal="Explore"),
        sleep_ticks=1,
    )
    packet = initialize(pack, setup).pending_packets()[0]
    first, second = host.model_packet(packet), host.model_packet(packet)
    original_packet, original_view = canonical_bytes(packet), canonical_bytes(second)

    first.perception.explored_static_tiles.clear()
    first.perception.visible_entities[0].observable_signs.append("weak")
    first.reports.append(NeutralActionEnd())

    assert canonical_bytes(second) == original_view
    assert canonical_bytes(packet) == original_packet
