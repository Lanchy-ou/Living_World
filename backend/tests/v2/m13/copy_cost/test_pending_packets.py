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
