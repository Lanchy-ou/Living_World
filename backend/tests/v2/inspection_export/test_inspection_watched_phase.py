"""EV-17 follows an observed action from the delivered packet to its objective event."""

from v2.decision_harness.resident_vectors import act
from v2.inspection_export.short_capture import seal_capture
from v2.resident_replay.replay_fixture import start


def test_ev17_export_joins_watched_phase(tmp_path, fake_exchange):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.decision.caller import Caller
    from living_island.analysis.v2.export import export
    from living_island.analysis.v2.joins import Events
    from living_island.analysis.v2.shards import InspectionArchive
    from living_island.persistence.v2.audit import AuditReader, AuditWriter
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.harness.checkpoint import Recording
    from living_island.sim.v2.harness.composition import compose

    seed, kwargs, _ = start(tmp_path / "seed")
    world = seed.session.world
    source = tmp_path / "ella"
    writer = AuditWriter(source / "resident.sqlite")
    packets = PacketJournal(source / "packets", world.run_id)
    clock, transport = fake_exchange([act()] * 4)
    kwargs.update(
        actor="ella",
        caller=Caller(transport, clock, lambda _: None),
        packets=packets,
        journal=Journal(writer.keep, writer.create),
    )
    recording = Recording.opening(compose(world, **kwargs), packets, AuditReader(writer.path))
    for _ in range(3):
        assert recording.advance() is not None
    dest = tmp_path / "inspection"
    paths = seal_capture(tmp_path, source, recording, kwargs, "on")
    index = export(*paths, dest)
    archive = InspectionArchive.open(dest)
    view = next(
        archive.read(ref) for ref in index.deliveries if ref.id.endswith(":0000000002:ella")
    )
    events = archive.read(index.attempts).events
    observed = [entry for entry in view.entries if entry.entry.ref.kind == "observed_action"]
    assert {
        entry.entry.ref.phase for entry in observed if entry.members[0]["actor_id"] == "ryan"
    } == {"start", "settle"}
    for entry in observed:
        watched = entry.members[0]
        expected = {
            "observer_id": "ella",
            "actor_id": watched["actor_id"],
            "observed_intent_id": watched["intent_id"],
            "phase": watched["phase"],
        }
        (event,) = [e for e in events if e.type == "action_observed" and e.payload == expected]
        assert entry.event_ids == [event.event_id] and entry.missing_reason is None
        # An older or incomplete capture may retain the other observer or the
        # other phase while missing this exact observation.
        incomplete = Events()
        for other in events:
            if other.event_id != event.event_id:
                incomplete.add(other)
        missing = incomplete.join(view.packet, entry.entry, view.packet.model_dump(mode="json"))
        assert missing.event_ids == []
        assert (
            missing.missing_reason == "missing action_observed event for observer, intent and phase"
        )
