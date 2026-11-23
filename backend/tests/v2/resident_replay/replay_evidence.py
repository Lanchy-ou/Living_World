"""Card-end evidence. Invoke with python -m v2.resident_replay.replay_evidence from tests."""

import json
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

from v2.resident_replay.replay_fixture import start, verify


def branch(directory, source, kwargs, bookmark):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.persistence.v2.audit import AuditReader, AuditWriter
    from living_island.sim.v2.harness.checkpoint import Recording, load
    from living_island.sim.v2.harness.composition import compose

    world, runtime = load(bookmark, kwargs["compat"].pack, source.packets, source.audit)
    writer = AuditWriter(directory / "resident.sqlite")
    # Copy exactly the pinned journal prefix to an independent evidence branch.
    for key in source.audit.keys(0, runtime.cursor):
        writer.keep(key, source.audit.read(key))
    journal = Journal(writer.keep, writer.create)
    session = compose(world, **{**kwargs, "journal": journal, "restored": runtime.continuation})
    recording = Recording(session, source.packets, AuditReader(writer.path))
    recording.save(directory / "opening.json")
    return recording


def deliver_late_reply(directory, fork, kwargs, call):
    from living_island.sim.v2.harness.replay import History, InterruptedAttempt

    period = fork.session.resident.period
    caller = fork.session.resident.caller

    class LateReply:
        def exchange(self, body, timeout_ms):
            # Bookmark and inspect the durable claim while exchange is outstanding.
            fork.save(directory / "inflight.json")
            prefix = History(fork.audit, fork.audit.cursor())
            recovered = branch(directory / "recovery", fork, kwargs, directory / "inflight.json")
            try:
                prefix.recover_flow(recovered.session.resident.period.workflow)
            except InterruptedAttempt as exc:
                assert exc.disposition.dispatch.call == call
            else:
                raise AssertionError("unresolved dispatch must carry interrupted disposition")
            period.death(fork.session.world.tick)
            return caller.transport.exchange(body, timeout_ms)

    period.workflow.advance(LateReply(), caller.clock)


def interruption_cases(directory, record, kwargs):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.calls.provider import Interrupted, Terminal
    from living_island.sim.v2.harness.consolidation.workflow import CallDisposition
    from living_island.sim.v2.harness.replay import History

    results = {}
    for stage in ("authorized", "prepared", "dispatched"):
        fork = branch(directory / stage, record, kwargs, directory / "confirmed.json")
        period = fork.session.resident.period
        flow = period.workflow
        call = flow.state.calls[0].call
        caller = fork.session.resident.caller
        if stage != "authorized":
            flow.advance(caller.transport, caller.clock)
        if stage == "dispatched":
            deliver_late_reply(directory, fork, kwargs, call)
        else:
            period.death(fork.session.world.tick)
        history = History(fork.audit, fork.audit.cursor())
        receipt = CallDisposition.model_validate_json(
            history.read(Journal.cursor(call.call_id, "outcome"))
        )
        assert receipt.outcome == "abandoned"
        assert (receipt.prepared_cursor is None) == (stage == "authorized")
        assert len(receipt.attempts) == int(stage == "dispatched")
        if receipt.prepared_cursor:
            prepared = history.request(receipt.prepared_cursor, ())
            attempts = list(history.attempts(prepared))
            if stage == "dispatched":
                cursor, terminal = receipt.attempts[0]
                assert terminal is None
                assert isinstance(attempts[0][1], Terminal)
                at_dispatch = next(
                    i
                    for i in range(1, history.through + 1)
                    if fork.audit.keys(i - 1, i) == (cursor,)
                )
                (attempt,) = History(fork.audit, at_dispatch).attempts(prepared)
                assert isinstance(attempt[1], Interrupted)
            else:
                assert not attempts
        results[stage] = receipt.model_dump(mode="json")
    return results


def capture(directory):
    from living_island.agents.v2.calls.guard import PreparedRecord
    from living_island.agents.v2.context.prefix import MorningReceipt
    from living_island.memory.v2.projections import ProjectedRevision
    from living_island.sim.v2.harness.checkpoint import load
    from living_island.sim.v2.harness.composition import compose
    from living_island.sim.v2.harness.replay import continue_offline

    record, kwargs, fake = start(directory)
    session = record.session
    record.advance()
    record.advance()
    record.save(directory / "confirmed.json")
    assert session.resident.period.workflow is not None
    while session.resident.period.number < 3 or session.resident.period.context is None:
        assert session.world.tick <= 74
        assert record.advance() is not None
    count = session.world.tick
    captured_calls = tuple(fake.calls)
    records = verify(directory, record, kwargs, boundaries=count)
    world, state = load(
        directory / "confirmed.json", kwargs["compat"].pack, record.packets, record.audit
    )

    def build(world, state, packets, journal, caller):
        return compose(
            world,
            **{
                **kwargs,
                "restored": state.continuation,
                "packets": packets,
                "journal": journal,
                "caller": caller,
            },
        )

    replayed = continue_offline(
        world, state, record.packets, record.audit, build, boundaries=count - world.tick
    )
    assert replayed.continuation() == session.continuation()
    assert replayed.records == [r for r in session.records if r.tick >= 2]
    assert tuple(fake.calls) == captured_calls
    keys = record.audit.keys(0, record.audit.cursor())
    prepared = [
        PreparedRecord.model_validate_json(record.audit.read(key))
        for key in keys
        if key.endswith(".prepared.json")
    ]
    assert len({p.candidates[0].manifest.call_kind for p in prepared}) == 6
    mornings = [
        MorningReceipt.model_validate_json(record.audit.read(key)).outcome
        for key in keys
        if key.endswith(".morning.json")
    ]
    assert mornings == ["failed", "adopted"]
    interrupts = interruption_cases(directory, record, kwargs)
    unfit = branch(directory / "unfit", record, kwargs, directory / "opening.json")
    with patch.object(ProjectedRevision, "index_line", property(lambda _: "é" * 500000)):
        assert unfit.advance() is None
    (stopped,) = verify(directory / "unfit", unfit, kwargs, boundaries=1)
    assert stopped.boundary.stop.stop.reason == "stopped_unfit"
    return dict(
        ticks=count,
        closures=session.resident.period.number - 1,
        morning=mornings,
        recorded_attempts=captured_calls,
        replay_provider_dispatches=0,
        worlds=[r.boundary.world_hash for r in records],
        revisions=[h for r in records for h in r.revisions],
        stop=stopped.boundary.stop.stop.witness,
        interrupted=interrupts,
    )


def main(directory):
    directory = Path(directory)
    lock = directory / "li-heavy.lock"
    with ExitStack() as stack:
        stream = lock.open("x")
        stack.callback(lock.unlink)
        with stream:
            stream.write("P3.5-DL-05 " + datetime.now(UTC).isoformat())
        evidence = Path(mkdtemp(prefix="li-dl05-", dir=directory))
        print(evidence, flush=True)
        summary = capture(evidence)
        (evidence / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))


if __name__ == "__main__":
    main(sys.argv[1])
