"""Stage D7's six frozen, successful workload wires on an isolated fake transport."""

from living_island.agents.llm.provider import TransportResponse
from living_island.agents.v2.calls.contracts import digest
from living_island.agents.v2.calls.fake import FakeClock, FakeTransport, ScriptedReply
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.calls.provider import attempt
from living_island.persistence.v2.audit import AuditWriter
from living_island.sim.v2.harness.replay import History


def stage(directory, recording, samples):
    writer = AuditWriter(directory / "provider-check.sqlite")
    journal = Journal(writer.keep, writer.create)
    history = History(recording.audit, recording.audit.cursor())
    verbs = tuple(v.shape for v in recording.session.world.pack.verbs.values())
    staged = {}
    for kind, sample in samples.items():
        key = Journal.cursor(sample["call_id"], "prepared")
        prepared = history.request(key, verbs)
        original = list(history.attempts(prepared))[sample["attempt"]][1]
        raw = history.read(original.raw_output_ref)
        clock = FakeClock()
        transport = FakeTransport(clock, [ScriptedReply(TransportResponse(200, raw, True))])
        for candidate in prepared.record.candidates:
            for entry in candidate.manifest.entries:
                journal.blob(history.read(entry.sha256))
            journal.blob(history.read(candidate.wire_sha256))
        journal.fact(prepared.record.call.call_id, "prepared", prepared.record)
        running = any(
            entry.source.id.endswith("/running")
            and history.read(entry.sha256).startswith(b"Running ")
            for entry in prepared.admitted.candidate.manifest.entries
        )
        result = attempt(
            prepared,
            n=0,
            has_running_action=running,
            journal=journal,
            transport=transport,
            clock=clock,
        )
        (body,) = transport.dispatches
        assert (
            result.terminal.error_class is None
            and result.terminal.parsed_ref == original.parsed_ref
        )
        assert digest(body) == sample["wire_sha256"]
        staged[kind] = dict(
            prepared=key,
            wire_sha256=digest(body),
            sent_bytes=len(body),
            terminal=result.terminal_cursor,
        )
    return staged
