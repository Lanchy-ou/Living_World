"""Seal resident-local audit views against the shared world and verify the exported evidence."""

import base64
import json
import os
from collections import Counter
from decimal import Decimal
from shutil import copyfile

from living_island.agents.v2.calls.contracts import digest
from living_island.agents.v2.calls.wire import part_tokens
from living_island.analysis.v2.export import FinishedRun, export, fingerprint
from living_island.analysis.v2.shards import SHARD_LIMIT, InspectionArchive
from living_island.contract import inspection_v2 as ia
from living_island.persistence.v2.manifest import read_manifest
from living_island.persistence.v2.replay import RuleStore
from living_island.sim.v2.harness.checkpoint import load
from living_island.sim.v2.harness.replay import replay_resident
from living_island.world.v2.engine.snapshot import encode_snapshot


def save(path, value):
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )


def day_row():
    return dict(
        calls=Counter(),
        attempts=Counter(),
        section_bytes=Counter(),
        retries=0,
        largest_guarded_bytes=0,
        largest_sent_bytes=0,
        input_token_bound=0,
        scripted_output_tokens_bound=0,
        output_reserve=0,
        positive_log_growth=0,
    )


def day_cost(row):
    # Frozen M9 historical peak rates, CNY/million. DL-06 replaces these planning proxies.
    input_cost = 2 * row["input_token_bound"]
    row["forecast_cny"] = str(Decimal(input_cost + 8 * row["scripted_output_tokens_bound"]) / 10**6)
    row["reserved_output_forecast_cny"] = str(
        Decimal(input_cost + 8 * row["output_reserve"]) / 10**6
    )


def compare_days(week, ella):
    """Compare like-numbered days; keep Ella's two different rosters visible."""
    rows = []
    for day, paid in sorted(ella["actors"]["ella"]["days"].items()):
        five = [a["days"][day] for a in week["actors"].values()]
        rows.append(
            {
                "day": day,
                "five_model_forecast_cny": str(sum(Decimal(r["forecast_cny"]) for r in five)),
                "ella_with_fake_companions_cny": week["actors"]["ella"]["days"][day][
                    "forecast_cny"
                ],
                "ella_with_rule_companions_cny": paid["forecast_cny"],
                "ella_calls": sum(paid["calls"].values()),
                "ella_attempts": sum(paid["attempts"].values()),
                "ella_largest_sent_bytes": paid["largest_sent_bytes"],
            }
        )
    return rows


def inspect_archive(directory, hashes):
    archive = InspectionArchive.open(directory)
    index = archive.index
    days, periods, sample, previous = {}, [], {}, {}
    terminals, operations, forms, dispatches = Counter(), Counter(), Counter(), Counter()
    fallbacks = []
    handbacks = []
    pending_handback = False
    refs = [
        *index.deliveries,
        *index.revisions,
        *index.evidence_writes,
        index.attempts,
        index.time_use,
        index.metrics,
        index.cost,
        *(v.shard for v in (*index.decisions, *index.calls, *index.consolidations, *index.stores)),
    ]
    for ref in refs:
        assert all(p.size <= SHARD_LIMIT for p in ref.parts)
        view = archive.read(ref)
        if isinstance(view, ia.ConsolidationInspection):
            rec = view.record
            periods.append(
                dict(
                    period=rec.period_id,
                    tick=rec.boundary_tick,
                    outcome=rec.outcome,
                    reason=rec.reason,
                    pending_after=rec.pending_after,
                    pending=[p.model_dump() for p in rec.pending],
                )
            )
            operations.update(v.result for v in rec.verdicts)
        elif isinstance(view, ia.DecisionInspection):
            if view.record.origin == "fallback":
                fallbacks.append(view.record.turn_id)
                pending_handback = True
            elif view.record.output:
                if pending_handback:
                    handbacks.append(view.record.turn_id)
                    pending_handback = False
                output = view.record.output
                forms[output.action.kind] += 1
                if output.utterance:
                    forms["utterance"] += 1
                if output.mute:
                    forms["mute"] += 1
                if output.intention:
                    forms.update(output.intention.model_dump().keys())
                if view.record.valid_cites:
                    forms["valid_citation"] += 1
        elif isinstance(view, ia.CallInspection):
            kind = view.call_kind
            row = days.setdefault(1 + view.call.tick // 144, day_row())
            row["calls"][kind] += 1
            wires = {r.sha256: r.text.encode() for r in view.requests}
            for wire in wires.values():
                row["largest_guarded_bytes"] = max(row["largest_guarded_bytes"], len(wire))
            for a in view.attempts:
                d, t = a.dispatch, a.terminal
                assert t is not None
                dispatches[d.request_sha256] += 1
                sent = wires[d.request_sha256]
                row["largest_sent_bytes"] = max(row["largest_sent_bytes"], len(sent))
                row["attempts"][kind] += 1
                row["retries"] += int(d.n > 0)
                row["input_token_bound"] += d.sent.manifest.tokens_total
                row["output_reserve"] += d.settings.max_output_tokens
                terminals[t.error_class or "success"] += 1
                if a.parsed_output is not None:
                    # Match the exact fake assistant string; no provider usage is imputed.
                    envelope = json.loads(base64.b64decode(a.raw_output_base64))
                    answer = envelope["output"][0]["content"][0]["text"]
                    row["scripted_output_tokens_bound"] += part_tokens(answer)
                    sample.setdefault(
                        kind,
                        dict(
                            call_id=view.call.call_id,
                            attempt=d.n,
                            wire_sha256=d.request_sha256,
                            settings=d.settings.model_dump(),
                        ),
                    )
                sizes = {p.sha256: len(p.text.encode()) for p in view.parts}
                for section in d.sent.manifest.sections:
                    row["section_bytes"][section.section] += sum(
                        sizes[e.sha256] for e in section.entries
                    )
            if view.full_manifest and kind in ("decision", "decision_after_recall"):
                n = sum(
                    e.tokens
                    for s in view.full_manifest.sections
                    if s.section == "day_log"
                    for e in s.entries
                )
                period = view.call.period_id
                if period in previous and n > previous[period]:
                    row["positive_log_growth"] += 1
                previous[period] = n
    assert dispatches == hashes, "dispatched wires differ from fake transport's actual wire hashes"
    for row in days.values():
        day_cost(row)
    return dict(
        index_sha256=fingerprint(directory / "index.json"),
        shards=len(refs),
        periods=periods,
        operations=operations,
        fallback_turns=fallbacks,
        model_handbacks=handbacks,
        forms=forms,
        terminal_counts=terminals,
        days=days,
        single_copy_samples=sample,
    )


def finish_actor(island, actor, recording, ticks):
    home = island.directory / actor
    opening = home / "opening.json"
    recording.save(home / "finished.json")
    pack = island.compat.pack
    world, runtime = load(opening, pack, island.packets, recording.audit)
    manifest = read_manifest(island.directory / "wap-manifest.json")
    # Production replay verifies every prepared/attempted wire, revision, packet,
    # submission and event line before yielding the reconstructed boundary.
    count = revisions = 0
    for result in replay_resident(
        world,
        runtime,
        manifest,
        island.packets,
        RuleStore(home),
        recording.audit,
        registry=recording.session.resident.period.store.registry,
        boundaries=ticks,
    ):
        count += 1
        revisions += len(result.revisions)
    assert count == ticks
    end, saved = load(home / "finished.json", pack, island.packets, recording.audit)
    assert result.boundary.world_hash == digest(encode_snapshot(end))
    registry = recording.session.resident.period.store.registry
    assert result.boundary.store_hash == saved.resident.period.store.restore(registry).store_hash
    replay = island.directory / "replay.json"
    packet_dir = home / "packets"
    packet_dir.mkdir()
    pins = []
    for tick in range(ticks):
        origin = island.packets.directory / f"{tick}.json"
        target = packet_dir / origin.name
        try:
            os.link(origin, target)
        except OSError:
            copyfile(origin, target)
        pins.append(fingerprint(target))
    seal = FinishedRun(
        status="finished",
        run_id=world.run_id,
        arm="on",
        pack_ids=[ia.PackPin(pack_id=p.pack_id, sha256=p.pack_hash) for p in manifest.packs],
        residents=[
            ia.Resident(resident_id=k, profile_id=v.profile_id) for k, v in island.profiles.items()
        ],
        replay_sha256=fingerprint(replay),
        final_tick=ticks,
        audit_sha256=fingerprint(recording.audit.path),
        packet_sha256=pins,
        content_checks_sha256=None,
    )
    manifest_path = home / "finished-run.json"
    manifest_path.write_text(seal.model_dump_json(), encoding="utf-8")
    destination = island.directory / f"inspection-{actor}"
    export(home, manifest_path, replay, destination)
    return {
        **inspect_archive(destination, island.fakes[actor].attempt_hashes),
        "export": destination.name,
        "seal_sha256": fingerprint(manifest_path),
        "replayed_ticks": count,
        "verified_revisions_after_opening": revisions,
        "world_sha256": result.boundary.world_hash,
        "store_sha256": result.boundary.store_hash,
    }
