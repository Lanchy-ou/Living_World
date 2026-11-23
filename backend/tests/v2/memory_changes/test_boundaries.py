"""The harness pins a resident snapshot before submitting model bytes."""

import pytest


def test_staging_requires_the_sent_resident_and_base_version():
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.provenance import SentInput
    from living_island.memory.v2.store import MemoryStore
    from living_island.memory.v2.validation import decode_change_set

    store = MemoryStore("ella")
    for resident, version in (("mia", 0), ("ella", 1)):
        change = decode_change_set('{"ops":[]}', version)
        with pytest.raises(ValueError, match="resident's frozen base"):
            stage_change_set(store, change, SentInput(resident, "call"), 1)
    assert store.snapshot.version == 0


def test_staged_batch_cannot_overwrite_a_different_snapshot():
    from living_island.memory.v2.changes import stage_change_set
    from living_island.memory.v2.provenance import SentInput
    from living_island.memory.v2.records import Observed
    from living_island.memory.v2.store import MemoryStore
    from living_island.memory.v2.validation import decode_change_set

    store = MemoryStore("ella")
    other = MemoryStore.from_snapshot(store.snapshot)
    for target, text in ((store, "Fetch water"), (other, "Gather fruit")):
        target.set_intention(turn_id="turn", tick=1, text=text, source=Observed(entry_id="own"))
    empty = decode_change_set('{"ops":[]}', store.snapshot.version)
    staged = stage_change_set(store, empty, SentInput("ella", "call"), 2)
    for _ in range(2):
        before = other.snapshot
        with pytest.raises(ValueError, match="requires its original base"):
            staged.commit(other)
        assert other.snapshot is before
        other.apply(before.version, "mechanical", [])
