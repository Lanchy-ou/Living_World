"""Resident-local evidence and guard exposure over the verified inspection inputs."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from living_island.agents.v2.calls.guard import Ref
from living_island.agents.v2.context.entries import DayEntry
from living_island.analysis.v2.joins import instance
from living_island.analysis.v2.shards import read_shard
from living_island.contract import inspection_v2 as ia


def game_day(tick: int, tick_minutes: int) -> int:
    """Use the replay clock's one-based day number."""
    return 1 + tick * tick_minutes // 1440


def link(
    family: ia.Family, identity: str, label: str, member: str | None = None
) -> ia.AnalysisLink:
    return ia.AnalysisLink(family=family, id=identity, label=label, member=member)


def revision_link(actor: str, ref: ia.RevisionRef) -> ia.AnalysisLink:
    return link(
        "revisions",
        f"{actor}:{ref.store_version}",
        f"{ref.id} at v{ref.store_version} ({ref.content_hash})",
        ref.content_hash,
    )


def row_fields(
    actor: str, metric: str, trace: Iterable[str], links: Iterable[ia.AnalysisLink]
) -> ia.AnalysisRow:
    proof = instance(metric, sorted(set(trace)), 1, None)
    unique = {(item.family, item.id, item.label): item for item in links}
    return ia.AnalysisRow(
        resident_id=actor,
        instance_id=proof.instance_id,
        trace=proof.trace,
        links=list(unique.values()),
    )


class History:
    def __init__(
        self,
        deliveries: Iterable[ia.Delivery],
        revisions: Iterable[ia.Revisions],
        consolidations: Sequence[ia.ConsolidationRecord],
        evidence: dict[str, ia.Evidence],
        tick_minutes: int,
    ) -> None:
        self.tick_minutes = tick_minutes
        self.evidence = evidence
        self.consolidations = consolidations
        self.periods: dict[tuple[str, int], str] = {}
        self.entries: dict[tuple[str, str], ia.JoinedEntry] = {}
        self.by_revision: dict[str, ia.JoinedEntry] = {}
        self.feedback: dict[tuple[str, str], ia.Delivery] = {}
        self.records: dict[ia.RevisionRef, ia.Record] = {}
        self.first: dict[str, ia.RevisionRef] = {}
        self.latest: dict[str, ia.Record] = {}
        self.creation: dict[str, ia.ConsolidationRecord] = {}
        self.record_writes: defaultdict[str, list[tuple[int, str]]] = defaultdict(list)
        for key, write in evidence.items():
            for change in write.write.changes:
                self.record_writes[change.id].append((write.write.after_version, key))
        self.bindings: defaultdict[
            tuple[str, str], list[tuple[int, tuple[ia.RevisionRef, ...]]]
        ] = defaultdict(list)
        for delivery in deliveries:
            p = delivery.packet
            for result in p.perception.action_feedback:
                self.feedback[p.actor_id, result.intent_id] = delivery
            if delivery.period_id is not None:
                self.periods[p.actor_id, p.observed_tick] = delivery.period_id
            for joined in delivery.entries:
                self.entries[p.actor_id, joined.entry.id] = joined
                self.by_revision[joined.entry.revision] = joined
        for snapshot in revisions:
            for rev in snapshot.records:
                self.records[rev.ref] = rev.record
                self.first.setdefault(rev.ref.id, rev.ref)
                self.latest[rev.ref.id] = rev.record
        for row in consolidations:
            if row.result_version is None:
                continue
            for effect in row.effects:
                for edit in effect.edits:
                    if isinstance(edit, ia.Record):
                        ref = ia.RevisionRef(edit.id, row.result_version, edit.content_hash())
                        self.records[ref] = edit
                        if edit.id == effect.produced_id:
                            self.creation[edit.id] = row
                            self.first[edit.id] = ref
                        for binding in effect.bindings:
                            if binding.source in edit.sources:
                                self.bindings[edit.id, binding.source.model_dump_json()].append(
                                    (row.result_version, binding.revisions)
                                )

    @classmethod
    def from_export(
        cls,
        directory: Path,
        delivery_refs: Sequence[ia.ShardRef],
        revisions: Iterable[ia.Revisions],
        consolidations: Sequence[ia.ConsolidationRecord],
        evidence: dict[str, ia.Evidence],
        tick_minutes: int,
    ) -> "History":
        # These refs came directly from write_deliveries in the same export.
        deliveries = (cast(ia.Delivery, read_shard(directory, ref)) for ref in delivery_refs)
        return cls(deliveries, revisions, consolidations, evidence, tick_minutes)

    def created_period(self, record: ia.Record) -> str | None:
        creator = self.creation.get(record.id)
        if creator:
            return creator.period_id
        return self.periods.get((record.owner_id, record.created_tick))

    def ancestors(self, ref: ia.RevisionRef) -> Iterable[tuple[ia.RevisionRef, ia.Record]]:
        pending = [ref]
        seen = set()
        while pending:
            current = pending.pop()
            if current in seen or current not in self.records:
                continue
            seen.add(current)
            record = self.records[current]
            yield current, record
            for source in record.sources:
                bindings = self.bindings[record.id, source.model_dump_json()]
                binding = next(
                    (b for v, b in reversed(bindings) if v <= current.store_version), None
                )
                if binding:
                    pending.extend(binding)


def omitted(call: ia.CallInspection) -> list[Ref]:
    if call.attempts:
        return list(call.attempts[0].dispatch.sent.omitted)
    prep = call.prepared
    if prep is None:
        return []
    position = (
        prep.admitted_candidate if prep.admitted_candidate is not None else prep.floor_candidate
    )
    return list(prep.candidates[position].omitted)


def exposure(call: ia.CallInspection, retrieved: Iterable[str] = ()) -> ia.ExposureCall:
    selected = list(retrieved)
    if call.morning:
        selected.extend(call.morning.selected_ids)
    if call.deliberate_recall:
        selected.extend(e.retrieved.id for e in call.deliberate_recall.entries if e.retrieved)
    return ia.ExposureCall(
        call_id=call.call.call_id,
        call_kind=call.call_kind,
        turn_id=call.call.turn_id,
        outcome=call.outcome,
        omitted=omitted(call),
        retrieved=list(dict.fromkeys(selected)),
    )


@dataclass
class Continuity:
    uses: list[ia.MemoryUse]
    periods: list[ia.PeriodExposure]
    consolidations: list[ia.ConsolidationExposure]


def continuity(
    history: History,
    decisions: Sequence[ia.DecisionRecord],
    calls: dict[str, ia.CallInspection],
    entries: dict[str, DayEntry],
) -> Continuity:
    uses = []
    for decision in decisions:
        for use in decision.use_updates:
            record = history.records.get(use.revision)
            actor = decision.resident_id
            links = [
                link("decisions", decision.turn_id, "Decision " + decision.turn_id),
                link("calls", use.call_id, "First dispatch " + use.call_id),
                revision_link(actor, use.revision),
            ]
            creator = history.creation.get(use.record_id)
            if creator:
                key = f"{creator.period_id}:{creator.started_tick}"
                links.append(link("consolidations", key, "Creating consolidation " + key))
            for version, key in history.record_writes[use.record_id]:
                if version <= use.revision.store_version:
                    links.append(link("evidence_writes", key, "Evidence write " + key))
            for ancestor, body in history.ancestors(use.revision):
                if ancestor != use.revision:
                    links.append(revision_link(actor, ancestor))
                for source in body.sources:
                    if source.kind == "observed":
                        joined = history.entries.get((actor, source.entry_id))
                        if joined and joined.entry.delivery_id:
                            links.append(
                                link(
                                    "deliveries",
                                    joined.entry.delivery_id,
                                    "Source " + source.entry_id,
                                )
                            )
            trace = [
                decision.turn_id,
                use.call_id,
                use.record_id,
                str(use.revision.store_version),
                use.revision.content_hash,
                *(source.id for source in links),
            ]
            base = row_fields(actor, "memory_use", trace, links)
            uses.append(
                ia.MemoryUse(
                    **base.model_dump(),
                    revision=use.revision,
                    day=game_day(decision.tick, history.tick_minutes),
                    period_id=decision.period_id,
                    created_period=history.created_period(record) if record else None,
                    created_day=game_day(record.created_tick, history.tick_minutes)
                    if record
                    else None,
                    turn_id=decision.turn_id,
                    call_id=use.call_id,
                    before_version=use.before_version,
                    after_version=use.after_version,
                    kind=record.kind if record else None,
                    cited=any(
                        f.memory_revision == use.revision
                        for call_id in decision.call_ids
                        for binding in calls[call_id].adopted_citations
                        for cite in binding.valid
                        for f in cite.fragments
                    ),
                )
            )

    periods: dict[tuple[str, str], list[ia.ExposureCall]] = {
        (actor, period): [] for (actor, _), period in history.periods.items()
    }
    turns: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for d in decisions:
        turns[d.resident_id, d.period_id].append(d.turn_id)
    for call in sorted(calls.values(), key=lambda c: (c.call.tick, c.call.call_id)):
        if call.call_kind.startswith("consolidation_"):
            continue
        # Recipe recall has no model call. Its selected entry may be absent from sent context.
        retrieved = [
            entry.retrieved.id
            for item in (call.full_manifest.entries if call.full_manifest else ())
            if item.source.kind == "day_log"
            and (entry := entries.get(item.source.version or ""))
            and entry.retrieved
        ]
        periods.setdefault((call.call.resident_id, call.call.period_id), []).append(
            exposure(call, retrieved)
        )

    attempts = []
    inherited: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for row in sorted(
        history.consolidations, key=lambda r: (r.boundary_tick, r.resident_id, r.started_tick)
    ):
        actor, period = row.resident_id, row.period_id
        key = f"{period}:{row.started_tick}"
        stages = [exposure(calls[c]) for c in (row.selection_call_id, row.change_set_call_id) if c]
        # At K the coordinator closes the old period before writing the SAME boundary's
        # packet receipt. This exact resident/tick join records which period it supplied.
        supplied = (
            history.periods.get((actor, row.boundary_tick)) if row.outcome == "committed" else None
        )
        if supplied == period:
            supplied = None
        attempts.append(
            ia.ConsolidationExposure(
                resident_id=actor,
                period_id=period,
                attempt_id=key,
                calls=stages,
                outcome=row.outcome,
                supplies_period=supplied,
            )
        )
        if supplied:
            inherited[actor, supplied].extend(inherited[actor, period])
            if any(c.omitted for c in stages):
                inherited[actor, supplied].append(key)

    rows = []
    for (actor, period), stages in periods.items():
        prior = inherited[actor, period]
        ambient = bool(prior) or any(c.call_kind == "morning" and c.omitted for c in stages)
        exposed = (
            turns[actor, period]
            if ambient
            else sorted({c.turn_id for c in stages if c.turn_id and c.omitted})
        )
        rows.append(
            ia.PeriodExposure(
                resident_id=actor,
                period_id=period,
                calls=stages,
                inherited_from=prior,
                exposed=ambient or any(c.omitted for c in stages),
                exposed_turns=exposed,
            )
        )
    return Continuity(uses, rows, attempts)
