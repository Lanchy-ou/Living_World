"""Read-only reconstruction of provider requests, resident revisions and WAP commits."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import cast

from living_island.agents.llm import provider as p3
from living_island.agents.v2.calls.contracts import Contract, digest, json_bytes, read_json
from living_island.agents.v2.calls.fake import FakeClock
from living_island.agents.v2.calls.guard import (
    Assembly,
    Part,
    Prepared,
    PreparedRecord,
    Settings,
    prepare,
)
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.calls.provider import Dispatch, Interrupted, Terminal, restore
from living_island.agents.v2.decision.caller import Caller, ResidentReply
from living_island.memory.v2.kinds import KindRegistry
from living_island.memory.v2.store import DecisionDispatch, MemoryStore
from living_island.persistence.v2.audit import AuditReader
from living_island.persistence.v2.journal import PacketJournal
from living_island.persistence.v2.manifest import RunManifest
from living_island.persistence.v2.replay import RecordedBoundary, RuleStore, replay
from living_island.sim.v2.harness.checkpoint import Boundary, Revision, Runtime, observe_revisions
from living_island.sim.v2.harness.consolidation.checkpoint import AttemptState
from living_island.sim.v2.harness.consolidation.coordinator import K
from living_island.sim.v2.harness.consolidation.workflow import CallDisposition, Workflow
from living_island.sim.v2.harness.loop import DecisionRecord
from living_island.sim.v2.harness.session import ResidentSession
from living_island.world.v2.engine import World
from living_island.world.v2.engine.snapshot import encode_snapshot, restore_snapshot
from living_island.world.v2.protocol import EnabledVerb


class InterruptedAttempt(RuntimeError):
    def __init__(self, disposition: Interrupted) -> None:
        self.disposition = disposition
        super().__init__(f"{disposition.reason}: {disposition.dispatch.prepared_cursor}")


@dataclass(frozen=True)
class History:
    audit: AuditReader
    through: int

    def read(self, key: str) -> bytes:
        return self.audit.read(key, self.through)

    def compare(self, key: str, body: bytes) -> None:
        expected = self.read(key)
        if expected != body:
            raise ValueError(f"{key}: expected {digest(expected)}, rebuilt {digest(body)}")

    def journal(self) -> Journal:
        return Journal(self.compare, self.compare)

    def request(self, key: str, verbs: tuple[EnabledVerb, ...]) -> Prepared:
        record = PreparedRecord.model_validate_json(self.read(key))
        full = record.candidates[0].manifest
        contract = Contract(full.call_kind, verbs)
        pins = Settings(
            prompt_version=contract.prompt_version,
            prompt_sha256=digest(contract.instructions.encode()),
            schema_sha256=digest(contract.schema),
        )
        for field in Settings.model_fields:
            old, new = getattr(record.settings, field), getattr(pins, field)
            if old != new:
                raise ValueError(f"{key}: {field} expected {old}, rebuilt {new}")
        parts = tuple(
            Part(section.section, entry.source, self.read(entry.sha256).decode())
            for section in full.sections
            for entry in section.entries
            if section.section not in ("system", "schema")
            and not (record.pressure_at is not None and entry.source.kind == "pressure")
        )
        assembly = Assembly(
            parts,
            record.omission_order,
            frozenset(range(len(parts))).difference(record.omission_order),
            record.pressure_at,
        )
        # prepare verifies every candidate body, notice and derived pressure by writing
        # into the comparison journal. Compare pins individually for actionable diagnostics.
        if Journal.cursor(record.call.call_id, "prepared") != key:
            raise ValueError(f"{key}: prepared call ID differs")
        return prepare(record.call, contract, assembly, self.journal())

    def attempts(self, prepared: Prepared) -> Iterator[tuple[Dispatch, Terminal | Interrupted]]:
        call = prepared.record.call
        n = 0
        while True:
            key = Journal.cursor(call.call_id, f"{n}.dispatch")
            try:
                raw = self.read(key)
            except KeyError:
                return
            dispatch = Dispatch.model_validate_json(raw)
            admitted = prepared.admitted
            if (
                admitted is None
                or dispatch.call != call
                or dispatch.n != n
                or dispatch.prepared_cursor != prepared.cursor
                or dispatch.sent != admitted.candidate
                or dispatch.request_sha256 != digest(admitted.wire.body)
                or dispatch.settings != prepared.record.settings
            ):
                raise ValueError(f"{key}: sent request differs from {prepared.cursor}")
            try:
                raw = self.read(Journal.cursor(call.call_id, f"{n}.terminal"))
            except KeyError:
                terminal = None
            else:
                terminal = Terminal.model_validate_json(raw)
                for ref in (terminal.raw_output_ref, terminal.parsed_ref, terminal.reasoning_ref):
                    if ref is not None:
                        self.read(ref)
            yield dispatch, restore(dispatch, terminal)
            n += 1

    def verify_calls(self, after: int, verbs: tuple[EnabledVerb, ...]) -> None:
        """A terminal or dispatch can land many boundaries after its preparation."""
        touched: dict[str, set[str]] = {}
        for key in self.audit.keys(after, self.through):
            if key.endswith((".prepared.json", ".dispatch.json", ".terminal.json")):
                prepared_key = key.split(".", 1)[0] + ".prepared.json"
                touched.setdefault(prepared_key, set()).add(key)
        for key, facts in touched.items():
            prepared = self.request(key, verbs)
            facts.discard(key)
            for claim, result in self.attempts(prepared):
                facts.discard(Journal.cursor(claim.call.call_id, f"{claim.n}.dispatch"))
                if isinstance(result, Terminal):
                    facts.discard(Journal.cursor(result.call_id, f"{result.n}.terminal"))
            if facts:
                raise ValueError(f"{key}: unlinked attempt facts {sorted(facts)}")

    def recover_flow(self, flow: Workflow, *, pending: bool = False) -> None:
        """Consume only this prefix. A later accounting terminal cannot reopen a sealed stage."""
        while flow.state.stage in ("selection", "change_set"):
            logical = flow.state.calls[-1]
            key = Journal.cursor(logical.call.call_id, "prepared")
            try:
                self.read(key)
            except KeyError:
                return
            prepared = self.request(key, ())
            if logical.prepared is None:
                flow.advance(_Disconnected(), FakeClock())  # prepare only
            try:
                sealed = CallDisposition.model_validate_json(
                    self.read(Journal.cursor(logical.call.call_id, "outcome"))
                )
            except KeyError:
                sealed = None
            advanced = False
            for dispatch, disposition in self.attempts(prepared):
                if dispatch.n < len(logical.attempts) and logical.attempts[dispatch.n].terminal:
                    continue
                terminal = disposition if isinstance(disposition, Terminal) else None
                abandoned = sealed is not None and sealed.outcome == "abandoned"
                if sealed is not None and sealed.attempts[dispatch.n][1] is None:
                    terminal = None  # A later terminal is accounting-only.
                if terminal is None and pending and not abandoned:
                    return
                parsed = (
                    self.read(terminal.parsed_ref) if terminal and terminal.parsed_ref else None
                )
                interrupted = flow.recover(dispatch, terminal, parsed)
                if interrupted:
                    if abandoned:
                        return
                    raise InterruptedAttempt(interrupted)
                advanced = True
            if not advanced:
                return


class _Disconnected:
    def exchange(self, body: bytes, timeout_ms: int) -> p3.TransportResponse:
        raise RuntimeError("replay attempted a provider exchange")


@dataclass(frozen=True)
class RecordedCaller(Caller):
    history: History

    @classmethod
    def offline(cls, history: History) -> "RecordedCaller":
        return cls(_Disconnected(), FakeClock(), lambda _: None, history)

    def dispatch(self, prepared: Prepared, journal: Journal, *, running: bool) -> ResidentReply:
        result = None
        for dispatch, outcome in self.history.attempts(prepared):
            # Replay the original durable claim through the normal use-credit port.
            journal.fact(dispatch.call.call_id, f"{dispatch.n}.dispatch", dispatch, exclusive=True)
            if isinstance(outcome, Interrupted):
                raise InterruptedAttempt(outcome)
            parsed = None
            text = None
            if outcome.parsed_ref is not None:
                envelope = read_json(self.history.read(cast(str, outcome.raw_output_ref)))
                text = p3._output_text(
                    [item for item in envelope["output"] if item.get("type") != "reasoning"]
                )
                if text is None:
                    raise ValueError(f"{outcome.raw_output_ref}: missing recorded response text")
                parsed = prepared.contract.parse(text, has_running_action=running)
                self.history.compare(
                    outcome.parsed_ref,
                    json_bytes(parsed.model_dump(mode="json", by_alias=True, exclude_unset=True)),
                )
            result = ResidentReply(
                dispatch,
                outcome,
                Journal.cursor(dispatch.call.call_id, f"{dispatch.n}.terminal"),
                parsed,
                text,
            )
        if result is None:
            raise ValueError(f"{prepared.cursor}: missing recorded dispatch")
        return result


def replay_revisions(history: History, after: int, store: MemoryStore) -> Iterator[str]:
    for key in history.audit.keys(after, history.through):
        if not key.endswith(".revision.json"):
            continue
        row = Revision.model_validate_json(history.read(key))
        if row.kind == "use":
            write = store.credit_dispatch(cast(DecisionDispatch, row.dispatch))
        else:
            write = store.apply(
                row.before,
                row.kind,
                (
                    edit.id
                    if edit.body is None
                    else store.registry.parse(read_json(history.read(edit.body)))
                    for edit in row.edits
                ),
            )
        if write is None or (write.before_version, write.after_version, write.store_hash) != (
            row.before,
            row.after,
            row.store_hash,
        ):
            raise ValueError(f"{key}: store hash differs at version {row.after}")
        yield write.store_hash


@dataclass(frozen=True)
class Replayed:
    boundary: Boundary
    decision: DecisionRecord | None
    revisions: tuple[str, ...]


class ReplayPackets(PacketJournal):
    ingest = PacketJournal.verify


def continue_offline(
    world: World,
    runtime: Runtime,
    packets: PacketJournal,
    audit: AuditReader,
    build: Callable[[World, Runtime, PacketJournal, Journal, Caller], ResidentSession],
    *,
    boundaries: int,
) -> ResidentSession:
    """Re-run the agent and binding logic from the saved boundary, checking its emitted facts."""
    history = History(audit, audit.cursor())
    session = build(
        world,
        runtime,
        ReplayPackets(packets.directory, packets.run_id),
        history.journal(),
        RecordedCaller.offline(history),
    )
    session.runner.manifest.stop = runtime.stop
    observe_revisions(session)
    for _ in range(boundaries):
        if session.incomplete:
            break
        key = Journal.cursor(world.run_id, f"{world.tick}.boundary")
        row = Boundary.model_validate_json(history.read(key))
        prefix = History(audit, row.through)
        session.resident.caller = RecordedCaller.offline(prefix)
        if flow := session.resident.period.workflow:
            attempt_state = cast(AttemptState, session.resident.period.checkpoint().attempt)
            prefix.recover_flow(flow, pending=world.tick < attempt_state.s_tick + K)
        session.stop_requested = (
            row.incomplete is not None and row.incomplete.reason == "operator_stop"
        )
        result = session.advance()
        if ((result is not None), session.runner.manifest.stop, session.incomplete) != (
            row.committed,
            row.stop,
            row.incomplete,
        ):
            raise ValueError(f"{key}: terminal disposition differs")
        if result is not None:
            commit = session.runner.manifest.boundaries[-1]
            if (commit.submissions, commit.fallback_turns, commit.event_lines) != (
                row.submissions,
                row.fallbacks,
                prefix.read(row.events),
            ):
                raise ValueError(f"{key}: replayed settlement differs")
        if (digest(encode_snapshot(world)), session.resident.period.store.snapshot.store_hash) != (
            row.world_hash,
            row.store_hash,
        ):
            raise ValueError(f"{key}: restored continuation differs")
    return session


def replay_resident(
    world: World,
    runtime: Runtime,
    manifest: RunManifest,
    packets: PacketJournal,
    rules: RuleStore,
    audit: AuditReader,
    *,
    registry: KindRegistry,
    boundaries: int,
) -> Iterator[Replayed]:
    """Replay a finite recording using the memory kinds registered for its live session."""
    manifest.check_content(world.pack.source)
    snapshot = encode_snapshot(world)
    tick, cursor = world.tick, runtime.cursor
    store = MemoryStore.from_snapshot(runtime.resident.period.store.restore(registry), registry)
    verbs = tuple(spec.shape for spec in world.pack.verbs.values())
    for _ in range(boundaries):
        key = Journal.cursor(world.run_id, f"{tick}.boundary")
        boundary = Boundary.model_validate_json(audit.read(key))
        history = History(audit, boundary.through)
        history.verify_calls(cursor, verbs)
        revisions = tuple(replay_revisions(history, cursor, store))
        decision = (
            DecisionRecord.model_validate_json(history.read(boundary.decision))
            if boundary.decision
            else None
        )
        if decision and decision.submission != next(
            (s for s in boundary.submissions if s.actor_id == decision.resident_id), None
        ):
            raise ValueError(f"{key}: decision submission differs")
        events = history.read(boundary.events)
        if boundary.committed:
            row = RecordedBoundary(
                boundary.submissions, events, tuple(f.fact() for f in boundary.fallbacks)
            )
            snapshot = next(
                replay(snapshot, manifest, world.pack.source, packets, rules, (row,))
            ).snapshot
        else:
            packets.verify(restore_snapshot(snapshot, world.pack.source))
        if (digest(snapshot), store.snapshot.store_hash, store.snapshot.version) != (
            boundary.world_hash,
            boundary.store_hash,
            boundary.store_version,
        ):
            raise ValueError(f"{key}: boundary world or memory hash differs")
        yield Replayed(boundary, decision, revisions)
        cursor = history.through
        if not boundary.committed:
            return
        tick += 1
