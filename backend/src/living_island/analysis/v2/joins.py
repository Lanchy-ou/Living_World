"""Resolve immutable resident facts and request parts from the recorded audit."""

import json
import re
import sqlite3
from base64 import b64encode
from collections import defaultdict
from collections.abc import Iterator, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from living_island.agents.v2.calls.contracts import CallKind
from living_island.agents.v2.calls.guard import Assembly, Call, PreparedRecord, rebuild
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.calls.provider import Dispatch, Terminal, restore
from living_island.agents.v2.context.entries import DayEntry
from living_island.agents.v2.context.prefix import MorningReceipt
from living_island.agents.v2.recall.attribution import ActCitations
from living_island.agents.v2.recall.sequence import RecallReceipt
from living_island.analysis.canon import canonical_bytes_of_data, sha256_hex
from living_island.contract import inspection_v2 as ia


class Audit:
    """A single sealed SQLite artifact. Never open a writable connection."""

    def __init__(self, path: Path) -> None:
        self.facts: dict[str, bytes] = {}
        self.entries: dict[str, DayEntry] = {}
        self.entry_revisions: dict[str, DayEntry] = {}
        with closing(sqlite3.connect(path.resolve().as_uri() + "?immutable=1", uri=True)) as db:
            for name, digest, raw in db.execute("SELECT name, hash, body FROM facts ORDER BY seq"):
                if sha256_hex(raw) != digest or ("." not in name and name != digest):
                    raise ValueError(f"corrupt audit fact {name}")
                self.facts[name] = raw
                # Own responses can be the last entry in a run. They have no subsequent
                # manifest in that case, but their canonical blobs carry the full entry ID.
                if "." not in name and raw.startswith(b'{"about":'):
                    # The blob table also stores arbitrary provider bytes. Only a
                    # complete day entry belongs in this secondary lookup.
                    try:
                        entry = DayEntry.model_validate_json(raw)
                    except ValidationError:
                        continue
                    self.entries[entry.id] = entry
                    self.entry_revisions[name] = entry

    def rows[T: BaseModel](self, slot: str, model: type[T]) -> Iterator[tuple[str, T]]:
        for key, raw in self.facts.items():
            if key.endswith("." + slot + ".json"):
                yield key, model.model_validate_json(raw, extra="forbid")


class Authorized(ia.View):
    call: Call
    kind: Literal["consolidation_selection", "consolidation_change_set"]
    assembly: Assembly


def calls(audit: Audit, decisions: Sequence[ia.DecisionRecord]) -> dict[str, ia.CallInspection]:
    prepared = {row.call.call_id: row for _, row in audit.rows("prepared", PreparedRecord)}
    authorized = {row.call.call_id: row for _, row in audit.rows("authorized", Authorized)}
    dispositions = dict(audit.rows("outcome", ia.Disposition))
    mornings = {row.call_id: row for _, row in audit.rows("morning", MorningReceipt)}
    deliberate = dict(audit.rows("deliberate", RecallReceipt))
    citations: defaultdict[str, list[ActCitations]] = defaultdict(list)
    for _, binding in audit.rows("citations", ActCitations):
        citations[binding.call_id].append(binding)
    parent = {key: row for row in decisions for key in row.call_ids}
    claims: defaultdict[str, list[Dispatch]] = defaultdict(list)
    for _, claim in audit.rows("dispatch", Dispatch):
        claims[claim.call.call_id].append(claim)
    result = {}
    for key in sorted(prepared.keys() | authorized.keys()):
        auth = authorized.get(key)
        prep = prepared.get(key)
        parts: dict[str, ia.StoredPart] = {}
        wires = []
        kind: CallKind
        if prep is None:
            stage = authorized[key]
            call, kind = stage.call, stage.kind
        else:
            call, kind = prep.call, prep.candidates[0].manifest.call_kind
            for candidate in prep.candidates:
                entries = candidate.manifest.entries
                resolved = tuple(audit.facts[e.sha256] for e in entries)
                wire = rebuild(candidate, prep.settings, resolved)
                wires.append(ia.StoredPart(sha256=candidate.wire_sha256, text=wire.body.decode()))
                for entry, raw in zip(entries, resolved, strict=True):
                    parts[entry.sha256] = ia.StoredPart(sha256=entry.sha256, text=raw.decode())
        attempts = []
        for n, claim in enumerate(claims[key]):
            if (
                prep is None
                or prep.admitted_candidate is None
                or claim.n != n
                or claim.call != call
                or claim.settings != prep.settings
                or claim.sent != prep.candidates[prep.admitted_candidate]
                or claim.request_sha256 != claim.sent.wire_sha256
            ):
                raise ValueError(f"{key}: dispatch differs from prepared candidate")
            terminal_raw = audit.facts.get(Journal.cursor(key, f"{n}.terminal"))
            terminal = Terminal.model_validate_json(terminal_raw) if terminal_raw else None
            returned = restore(claim, terminal)
            attempts.append(
                ia.Attempt(
                    dispatch=claim,
                    terminal=terminal,
                    missing_usage_reason=returned.missing_usage_reason,
                    raw_output_base64=(
                        b64encode(audit.facts[terminal.raw_output_ref]).decode()
                        if terminal and terminal.raw_output_ref
                        else None
                    ),
                    parsed_output=(
                        json.loads(audit.facts[terminal.parsed_ref])
                        if terminal and terminal.parsed_ref
                        else None
                    ),
                )
            )
        outcome: Literal["adopted", "not_adopted", "failed", "abandoned", "stopped_unfit"]
        disposition = dispositions[Journal.cursor(key, "outcome")] if auth else None
        if disposition:
            outcome = disposition.outcome
        elif kind == "morning":
            outcome = mornings[key].outcome
        elif prep and prep.reason:
            outcome = prep.reason
        elif not attempts or attempts[-1].terminal is None or attempts[-1].terminal.error_class:
            outcome = "failed"
        elif key == parent[key].call_ids[-1] and parent[key].origin != "model":
            outcome = "not_adopted"
        else:
            outcome = "adopted"
        result[key] = ia.CallInspection(
            call=call,
            call_kind=kind,
            outcome=outcome,
            prepared=prep,
            full_manifest=prep.candidates[0].manifest if prep else None,
            sent_manifest=attempts[0].dispatch.sent.manifest if attempts else None,
            disposition=disposition,
            authorized_parts=list(auth.assembly.parts) if auth else [],
            parts=list(parts.values()),
            attempts=attempts,
            requests=wires,
            morning=mornings.get(key),
            deliberate_recall=deliberate.get(Journal.cursor(key, "deliberate")),
            adopted_citations=citations[key],
        )
    return result


def instance(metric: str, trace: list[str], value: int | None, reason: str | None) -> ia.Metric:
    trace = sorted(trace)
    key = sha256_hex(canonical_bytes_of_data(trace))[:16]
    return ia.Metric(
        instance_id=f"{metric}:{key}", metric=metric, trace=trace, value=value, reason=reason
    )


_MEMBER = re.compile(r"([a-z_]+)(?:\[(\d+)\])?")


def member(packet: dict[str, Any], path: str) -> Any:
    value: Any = packet
    for step in path.split("."):
        match = _MEMBER.fullmatch(step)
        if match is None:
            raise ValueError(f"invalid packet member path {path}")
        value = value[match[1]]
        if match[2] is not None:
            value = value[int(match[2])]
    return value


@dataclass
class Events:
    heard: dict[tuple[str, str], str] = field(default_factory=dict)
    intents: defaultdict[str, list[ia.WorldEvent]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add(self, event: ia.WorldEvent) -> None:
        if event.intent_id is not None:
            self.intents[event.intent_id].append(event)
        if event.type == "utterance_heard":
            self.heard[str(event.payload["utterance_id"]), str(event.payload["listener_id"])] = (
                event.event_id
            )

    def join(
        self, packet: ia.BoundaryDelivery, entry: DayEntry, fields: dict[str, Any]
    ) -> ia.JoinedEntry:
        ref = entry.ref
        ids = []
        missing = None
        if ref.kind == "utterance":
            event_id = self.heard.get((ref.utterance_id, packet.actor_id))
            if event_id:
                ids.append(event_id)
            else:
                missing = "missing utterance_heard event for listener"
        elif ref.kind == "feedback":
            ids = [
                e.event_id
                for e in self.intents[ref.intent_id]
                if e.type in ("act_settled", "action_succeeded", "action_failed", "action_stopped")
            ]
            if not ids:
                missing = "missing action outcome for intent"
        elif ref.kind == "observed_action":
            missing = "watched-phase objective join pending EN-10"
        return ia.JoinedEntry(
            entry=entry,
            members=[member(fields, p) for p in entry.member_paths],
            event_ids=ids,
            missing_reason=missing,
        )
