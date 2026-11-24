"""Export a hash-pinned finished resident capture into a fresh inspection directory."""

import argparse
from collections import defaultdict
from collections.abc import Sequence
from hashlib import file_digest
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, TypeAdapter

from living_island.agents.v2.calls.journal import Journal
from living_island.analysis.canon import sha256_hex
from living_island.analysis.v2.continuity import History
from living_island.analysis.v2.cost import context_cost
from living_island.analysis.v2.joins import Audit, Events, calls, instance
from living_island.analysis.v2.learning import resident_analysis
from living_island.analysis.v2.shards import INDEX_LIMIT, encoded, write_shard
from living_island.contract import inspection_v2 as ia
from living_island.contract.replay import ReplayBundle


class FinishedRun(ia.View):
    """The verifier's immutable inputs. Packet pins are in observed-tick order."""

    status: Literal["finished"]
    run_id: str
    arm: ia.Arm
    pack_ids: list[ia.PackPin] = Field(min_length=1)
    residents: list[ia.Resident] = Field(min_length=1)
    final_tick: int = Field(ge=0)
    replay_sha256: ia.Digest
    audit_sha256: ia.Digest
    packet_sha256: list[ia.Digest]
    content_checks_sha256: ia.Digest | None


class Batch(ia.View):
    schema_version: Literal["wap/0.1"]
    run_id: str
    observed_tick: int
    packets: list[ia.BoundaryDelivery]


class PacketReceipt(ia.View):
    period_id: str
    delivery_id: str
    entries: list[str]
    writes: list[ia.Evidence]


class Boundary(ia.View):
    tick: int
    through: int
    committed: bool
    submissions: list[ia.TurnSubmission]
    fallbacks: list[dict[str, JsonValue]]
    events: str
    world_hash: ia.Digest
    store_version: int
    store_hash: ia.Digest
    decision: str | None
    stop: dict[str, JsonValue] | None
    incomplete: dict[str, JsonValue] | None


class Edit(ia.View):
    id: str
    body: str | None


class Delta(ia.View):
    kind: Literal["mechanical", "change_set", "use"]
    before: int
    after: int
    edits: list[Edit]
    dispatch: ia.Credit | None
    store_hash: ia.Digest


def history(
    audit: Audit, residents: list[ia.Resident], writes: Sequence[ia.Write]
) -> dict[tuple[str, str], ia.Revisions]:
    """Verify the history of heads, including dispatch-only changes of use counters."""
    snapshots = {}
    committed = {(w.owner_id, w.after_version): w for w in writes}
    for resident in residents:
        actor = resident.resident_id
        records: dict[str, ia.Record] = {}
        bodies: dict[str, ia.Record] = {}
        next_id = 1
        credited_turn = None
        credited: set[str] = set()
        for v in range(1, len(audit.facts) + 1):
            key = Journal.cursor(actor, f"v{v}.revision")
            if key not in audit.facts:
                break
            delta = Delta.model_validate_json(audit.facts[key], extra="forbid")
            if (delta.before, delta.after) != (v - 1, v):
                raise ValueError(f"{actor}: broken revision chain at {v}")
            write = committed.get((actor, v))
            if write:
                bodies.update(write.blobs)
                # The write holds normalized committed bodies. Delta.edits records
                # writer inputs, which can precede mechanical gist generation.
                for change in write.changes:
                    if change.after is None:
                        del records[change.id]
                        continue
                    if change.before is None:
                        next_id += 1
                    head = change.after
                    record = bodies[head.content_hash]
                    records[change.id] = record.model_copy(
                        update={"use_count": head.use_count, "last_used_tick": head.last_used_tick}
                    )
            else:
                for edit in delta.edits:
                    if edit.body is None:
                        del records[edit.id]
                        continue
                    rec = ia.Record.model_validate_json(audit.facts[edit.body], extra="forbid")
                    if (rec.owner_id, rec.id) != (actor, edit.id):
                        raise ValueError("edit has wrong memory identity")
                    if rec.id not in records:
                        next_id += 1
                    records[rec.id] = rec
                    bodies[rec.content_hash()] = rec
            if dispatch := delta.dispatch:
                if credited_turn != dispatch.turn_id:
                    credited_turn, credited = dispatch.turn_id, set()
                for ref in dispatch.revisions:
                    if ref.id not in credited:
                        rec = records[ref.id]
                        records[ref.id] = rec.model_copy(
                            update={"last_used_tick": dispatch.tick, "use_count": rec.use_count + 1}
                        )
                        credited.add(ref.id)
            rows = [
                ia.Revision(ref=ia.RevisionRef(r.id, v, r.content_hash()), record=r)
                for r in sorted(records.values(), key=lambda rec: rec.id)
            ]
            heads = [
                dict(
                    id=r.ref.id,
                    content_hash=r.ref.content_hash,
                    use_count=r.record.use_count,
                    last_used_tick=r.record.last_used_tick,
                )
                for r in rows
            ]
            store_hash = sha256_hex(
                encoded(
                    dict(
                        owner_id=actor,
                        version=v,
                        next_number=next_id,
                        credited_turn_id=credited_turn,
                        credited_ids=sorted(credited),
                        records=heads,
                    )
                )
            )
            if store_hash != delta.store_hash:
                raise ValueError(f"{actor}: recorded store hash differs at version {v}")
            snapshots[actor, store_hash] = ia.Revisions(
                resident_id=actor, store_version=v, records=rows
            )
    return snapshots


def index_lines(rows: ia.Revisions, arm: ia.Arm) -> list[str]:
    lines = []
    for revision in rows.records:
        record = revision.record
        if arm == "off" or record.archived:
            continue
        flags = list(record.content.flags())
        if record.history:
            flags.append("superseded")
        if record.needs_review:
            flags.append("needs_review")
        lines.append(
            f"{record.id} | {record.kind} | c{record.confidence} | "
            f"{','.join(sorted(flags)) or '-'} | {record.gist}"
        )
    return lines


def fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def all_parts(selected: Sequence[ia.CallInspection]) -> list[ia.StoredPart]:
    return list({p.sha256: p for call in selected for p in call.parts}.values())


def checked_parts(
    checks: list[ia.ContentCheck], calls: dict[str, ia.CallInspection]
) -> list[ia.StoredPart]:
    cited = {
        fragment.sha256
        for call in calls.values()
        for binding in call.adopted_citations
        for citation in binding.valid
        for fragment in citation.fragments
    }
    parts = {p.sha256: p for call in calls.values() for p in call.parts if p.sha256 in cited}
    selected = {
        digest
        for check in checks
        if isinstance(check, ia.ChoiceCheck)
        for digest in check.sent_fragment_sha256
    }
    if not selected.issubset(parts):
        raise ValueError("choice check names a fragment outside an adopted citation")
    return [parts[digest] for digest in sorted(selected)]


type Versions = dict[tuple[str, str], ia.Revisions]


def write_revisions(
    destination: Path, versions: Versions, consolidations: list[ia.ConsolidationRecord]
) -> list[ia.ShardRef]:
    intermediate: defaultdict[tuple[str, int], dict[ia.RevisionRef, ia.Record]] = defaultdict(dict)
    for row in consolidations:
        if row.result_version is not None:
            for effect in row.effects:
                for edit in effect.edits:
                    if isinstance(edit, ia.Record):
                        ref = ia.RevisionRef(edit.id, row.result_version, edit.content_hash())
                        intermediate[row.resident_id, row.result_version][ref] = edit
    revision_refs = []
    for v in versions.values():
        records = {r.ref: r.record for r in v.records}
        for ref, body in intermediate[v.resident_id, v.store_version].items():
            records.setdefault(ref, body)
        rows = [ia.Revision(ref=k, record=r) for k, r in records.items()]
        archive = v.model_copy(update={"records": rows})
        revision_refs.append(
            write_shard(destination, f"{v.resident_id}:{v.store_version}", archive)
        )
    return revision_refs


def write_calls(
    destination: Path, call_views: dict[str, ia.CallInspection]
) -> tuple[list[ia.CallRef], list[ia.Charge]]:
    call_refs = []
    charges = []
    for call in call_views.values():
        c = call.call
        call_refs.append(
            ia.CallRef(
                call_id=c.call_id,
                call_kind=call.call_kind,
                resident_id=c.resident_id,
                turn_id=c.turn_id,
                tick=c.tick,
                period_id=c.period_id,
                shard=write_shard(destination, c.call_id, call),
            )
        )
        for attempt in call.attempts:
            t = attempt.terminal
            charges.append(
                ia.Charge(
                    call_id=c.call_id,
                    n=attempt.dispatch.n,
                    input=t.tokens.input if t else None,
                    output=t.tokens.output if t else None,
                    cache_hit=t.tokens.cache_hit if t else None,
                    cache_miss=t.tokens.cache_miss if t else None,
                    latency_ms=t.latency_ms if t else None,
                    missing_usage_reason=attempt.missing_usage_reason,
                )
            )
    return call_refs, charges


def write_decisions(
    destination: Path,
    audit: Audit,
    decisions: list[ia.DecisionRecord],
    call_views: dict[str, ia.CallInspection],
    by_event: Events,
) -> list[ia.TurnRef]:
    turn_refs = []
    for d in decisions:
        selected = [call_views[k] for k in d.call_ids]
        for cite in d.cited_parts:
            if not any(
                e.sha256 == cite.sent_part_sha256 and e.source.version == cite.revision
                for a in call_views[cite.act_call_id].attempts
                for e in a.dispatch.sent.manifest.entries
            ):
                raise ValueError(f"{d.turn_id}: citation does not resolve to a sent fragment")
        action = d.submission.action if d.submission else None
        outcomes = (
            by_event.intents[action.intent.intent_id] if action and action.kind == "intent" else []
        )
        decision_view = ia.DecisionInspection(
            record=d,
            parts=all_parts(selected),
            calls=selected,
            entries=[audit.entries[key] for key in d.new_entries],
            outcome_event_ids=[e.event_id for e in outcomes],
            outcomes=outcomes,
        )
        turn_refs.append(
            ia.TurnRef(
                resident_id=d.resident_id,
                tick=d.tick,
                turn_id=d.turn_id,
                shard=write_shard(destination, d.turn_id, decision_view),
            )
        )
    return turn_refs


def write_deliveries(
    destination: Path,
    run_id: str,
    packet_files: list[Path],
    audit: Audit,
    receipts: dict[str, PacketReceipt],
    by_event: Events,
    refs: set[ia.RevisionRef],
) -> tuple[list[ia.ShardRef], list[ia.ShardRef], list[ia.Metric], dict[str, str]]:
    delivery_refs, evidence_refs, metrics = [], [], []
    latest_period: dict[str, str] = {}
    for tick, path in enumerate(packet_files):
        batch = Batch.model_validate_json(path.read_bytes(), extra="forbid")
        if (batch.run_id, batch.observed_tick) != (run_id, tick):
            raise ValueError("packet batch outside run boundary")
        for p in batch.packets:
            if p.delivery_id != f"{run_id}:perception:{tick:010d}:{p.actor_id}" or (
                p.observed_tick,
                p.perception.tick,
                p.perception.actor_id,
            ) != (tick, tick, p.actor_id):
                raise ValueError("packet identity differs from its boundary")
            receipt = receipts.get(p.delivery_id)
            joined = []
            if receipt:
                latest_period[p.actor_id] = receipt.period_id
                fields = p.model_dump(mode="json")
                for digest in receipt.entries:
                    entry = audit.entry_revisions[digest]
                    if entry.delivery_id != p.delivery_id:
                        raise ValueError("entry names a different delivery")
                    item = by_event.join(p, entry, fields)
                    joined.append(item)
                    metrics.append(
                        instance(
                            "delivery_source",
                            [p.delivery_id, digest, *item.event_ids],
                            None if item.missing_reason else len(item.members),
                            item.missing_reason,
                        )
                    )
                for w in receipt.writes:
                    if w.skill:
                        hypothesis = w.skill.hypothesis
                        settled = [
                            e.event_id
                            for e in by_event.intents[w.skill.intent_id]
                            if e.type == "act_settled"
                        ]
                        reason = (
                            "missing hypothesis revision"
                            if hypothesis not in refs
                            else "missing settlement"
                            if not settled
                            else None
                        )
                        metrics.append(
                            instance(
                                "hypothesis_source",
                                [
                                    hypothesis.id,
                                    str(hypothesis.store_version),
                                    hypothesis.content_hash,
                                    p.delivery_id,
                                    w.skill.intent_id,
                                    *settled,
                                ],
                                1 if reason is None else None,
                                reason,
                            )
                        )
                    evidence_refs.append(
                        write_shard(destination, f"{p.delivery_id}:{w.write.after_version}", w)
                    )
            delivery_refs.append(
                write_shard(
                    destination,
                    p.delivery_id,
                    ia.Delivery(
                        packet=p, period_id=receipt.period_id if receipt else None, entries=joined
                    ),
                )
            )
    return delivery_refs, evidence_refs, metrics, latest_period


def write_periods(
    destination: Path,
    seal: FinishedRun,
    consolidations: list[ia.ConsolidationRecord],
    versions: Versions,
    latest_period: dict[str, str],
    call_views: dict[str, ia.CallInspection],
) -> tuple[list[ia.PeriodRef], list[ia.StoreRef]]:
    periods, stores = [], []

    def store_view(actor: str, period: str, tick: int, version: ia.Revisions, label: str) -> None:
        flags = sorted(
            (
                f
                for row in consolidations
                if row.resident_id == actor
                for f in row.relabel_flags
                if f.store_version <= version.store_version
            ),
            key=lambda f: (f.flagged.id, f.store_version),
        )
        view = ia.StoreInspection(
            resident_id=actor,
            period_id=period,
            store_version=version.store_version,
            records=[r.record for r in version.records],
            index_lines=index_lines(version, seal.arm),
            relabel_flags=flags,
        )
        stores.append(
            ia.StoreRef(
                resident_id=actor,
                period_id=period,
                boundary_tick=tick,
                store_version=version.store_version,
                shard=write_shard(destination, label, view),
            )
        )

    for row in consolidations:
        selected = [call_views[k] for k in (row.selection_call_id, row.change_set_call_id) if k]
        view = ia.ConsolidationInspection(record=row, parts=all_parts(selected), calls=selected)
        key = f"{row.period_id}:{row.started_tick}"
        periods.append(
            ia.PeriodRef(
                resident_id=row.resident_id,
                period_id=row.period_id,
                boundary_tick=row.boundary_tick,
                shard=write_shard(destination, key, view),
            )
        )
        store_view(
            row.resident_id,
            row.period_id,
            row.boundary_tick,
            versions[row.resident_id, row.store_hash],
            key,
        )
    for actor in sorted({v.resident_id for v in versions.values()}):
        final = next(v for v in reversed(versions.values()) if v.resident_id == actor)
        store_view(actor, latest_period[actor], seal.final_tick, final, f"{actor}:end")
    return periods, stores


def action_intervals(
    boundaries: list[Boundary], by_event: Events
) -> tuple[list[ia.TurnSubmission], list[ia.Interval]]:
    submissions = [s for b in boundaries if b.committed for s in b.submissions]
    intervals = []
    for s in submissions:
        if s.action.kind != "intent":
            continue
        intent = s.action.intent.intent_id
        activity = by_event.intents[intent]
        end = next(
            (
                e.tick
                for e in activity
                if e.type in ("action_succeeded", "action_failed", "action_stopped")
            ),
            None,
        )
        intervals.append(
            ia.Interval(
                resident_id=s.actor_id,
                intent_id=intent,
                start_tick=s.observed_tick,
                end_tick=end,
                event_ids=[e.event_id for e in activity],
            )
        )
    return submissions, intervals


def export(run: Path, manifest: Path, replay: Path, destination: Path) -> ia.InspectionIndex:
    if destination.resolve().is_relative_to(run.resolve()) or destination.exists():
        raise ValueError("inspection needs a fresh destination outside the source run")
    raw_manifest = manifest.read_bytes()
    seal = FinishedRun.model_validate_json(raw_manifest, extra="forbid")
    packet_files = [run / "packets" / f"{n}.json" for n in range(len(seal.packet_sha256))]
    database = run / "resident.sqlite"
    checks_file = run / "content-checks.json"
    pins = {
        manifest: sha256_hex(raw_manifest),
        replay: seal.replay_sha256,
        database: seal.audit_sha256,
        **dict(zip(packet_files, seal.packet_sha256, strict=True)),
    }
    if seal.content_checks_sha256 is not None:
        pins[checks_file] = seal.content_checks_sha256

    def verify() -> None:
        for path, expected in pins.items():
            if fingerprint(path) != expected:
                raise ValueError(f"{path.name}: source hash differs")

    verify()
    bundle = ReplayBundle.model_validate_json(replay.read_bytes())
    if (
        bundle.run_id != seal.run_id
        or bundle.frames[-1].tick != seal.final_tick
        or sorted(r.id for r in bundle.residents) != sorted(r.resident_id for r in seal.residents)
    ):
        raise ValueError("replay does not match the verified run")
    audit = Audit(database)
    boundaries = []
    for name, boundary in audit.rows("boundary", Boundary):
        if name != Journal.cursor(seal.run_id, f"{boundary.tick}.boundary"):
            raise ValueError("boundary does not belong to the manifest run")
        boundaries.append(boundary)
    boundaries.sort(key=lambda b: b.tick)
    if (
        len(boundaries) != len(packet_files)
        or [b.tick for b in boundaries] != list(range(len(boundaries)))
        or sum(b.committed for b in boundaries) != seal.final_tick
        or any(not b.committed for b in boundaries[:-1])
    ):
        raise ValueError("finished range differs from recorded boundaries")
    checks = (
        TypeAdapter(list[ia.ContentCheck]).validate_json(checks_file.read_bytes())
        if seal.content_checks_sha256 is not None
        else []
    )
    events = [
        ia.WorldEvent.model_validate_json(line)
        for b in boundaries
        for line in audit.facts[b.events].splitlines()
    ]
    by_event = Events()
    for event in events:
        if event.run_id != seal.run_id:
            raise ValueError("foreign event in boundary")
        by_event.add(event)
    decisions = []
    for b in boundaries:
        if b.decision:
            turn = ia.DecisionRecord.model_validate_json(audit.facts[b.decision], extra="forbid")
            submitted = next((s for s in b.submissions if s.actor_id == turn.resident_id), None)
            if (
                turn.tick != b.tick
                or b.decision != Journal.cursor(turn.turn_id, "decision")
                or turn.submission != submitted
            ):
                raise ValueError("decision does not match the recorded boundary")
            decisions.append(turn)
    call_views = calls(audit, decisions)
    checked = checked_parts(checks, call_views)
    consolidations = [r for _, r in audit.rows("consolidation", ia.ConsolidationRecord)]
    receipts = {r.delivery_id: r for _, r in audit.rows("period_members", PacketReceipt)}
    versions = history(
        audit,
        seal.residents,
        [
            *(w.write for receipt in receipts.values() for w in receipt.writes),
            *(r.write for r in consolidations if r.write),
        ],
    )
    recorded_stores = {(store_hash, v.store_version) for (_, store_hash), v in versions.items()}
    if any((b.store_hash, b.store_version) not in recorded_stores for b in boundaries):
        raise ValueError("boundary names a missing store revision")
    refs = {r.ref for v in versions.values() for r in v.records}
    for row in consolidations:
        for flag in row.relabel_flags:
            if any(ref not in refs for ref in (flag.flagged, *flag.overlaps)):
                raise ValueError("relabel flag names an absent memory revision")

    # Each logical view is written independently. Publishing index.json last keeps a
    # partial export from being accepted after an I/O error.
    destination.mkdir()
    revision_refs = write_revisions(destination, versions, consolidations)
    call_refs, charges = write_calls(destination, call_views)
    turn_refs = write_decisions(destination, audit, decisions, call_views, by_event)
    delivery_refs, evidence_refs, metrics, latest_period = write_deliveries(
        destination, seal.run_id, packet_files, audit, receipts, by_event, refs
    )
    periods, stores = write_periods(
        destination, seal, consolidations, versions, latest_period, call_views
    )
    submissions, intervals = action_intervals(boundaries, by_event)
    archive = History.from_export(
        destination,
        delivery_refs,
        versions.values(),
        consolidations,
        {
            f"{r.delivery_id}:{w.write.after_version}": w
            for r in receipts.values()
            for w in r.writes
        },
        bundle.clock.tick_minutes,
    )
    analysis = resident_analysis(
        archive,
        decisions,
        call_views,
        events,
        checks,
        audit.entry_revisions,
        seal.residents,
        seal.pack_ids,
    )
    index = ia.InspectionIndex(
        inspection_schema_version="ia/0.1",
        run_id=seal.run_id,
        manifest_sha256=pins[manifest],
        replay_sha256=seal.replay_sha256,
        arm=seal.arm,
        pack_ids=seal.pack_ids,
        final_tick=seal.final_tick,
        residents=seal.residents,
        decisions=turn_refs,
        consolidations=periods,
        stores=stores,
        revisions=revision_refs,
        deliveries=delivery_refs,
        evidence_writes=evidence_refs,
        calls=call_refs,
        metrics=write_shard(
            destination,
            "metrics",
            ia.Metrics(
                instances=metrics,
                content_checks=checks,
                checked_parts=checked,
                resident_analysis=analysis,
            ),
        ),
        cost=write_shard(
            destination,
            "cost",
            context_cost(
                run, seal.run_id, call_views, charges, decisions, bundle.clock.tick_minutes
            ),
        ),
        time_use=write_shard(destination, "time_use", ia.TimeUse(intervals=intervals)),
        attempts=write_shard(
            destination, "attempts", ia.Attempts(events=events, submissions=submissions)
        ),
    )
    data = encoded(index.model_dump(mode="json"))
    if len(data) > INDEX_LIMIT:
        raise ValueError("inspection index exceeds 32 MiB")
    verify()
    (destination / "index.json").write_bytes(data)
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "manifest", "replay", "destination"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    export(args.run, args.manifest, args.replay, args.destination)


if __name__ == "__main__":
    main()
