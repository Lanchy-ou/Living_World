"""Small synthetic packet journal with a real MF workflow, writes and immutable revisions."""

import json
from pathlib import Path

from v2.consolidation.conftest import sleeping
from v2.mechanical_memory.mechanical_skill_support import add_skill


def capture_formation(root, packet, fake_exchange):
    from living_island.agents.v2.calls.journal import Journal
    from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery
    from living_island.agents.v2.context.prefix import FrozenPrefix
    from living_island.analysis.v2.export import Batch, FinishedRun, fingerprint
    from living_island.contract import inspection_v2 as ia
    from living_island.persistence.v2.audit import AuditReader, AuditWriter
    from living_island.sim.v2.harness.checkpoint import Boundary, RecordingStore
    from living_island.sim.v2.harness.consolidation import PeriodCoordinator
    from living_island.world.v2.protocol import Intent, WorldEvent

    source = root / "run"
    (source / "packets").mkdir(parents=True)
    writer = AuditWriter(source / "resident.sqlite")
    journal = Journal(writer.keep, writer.create)
    store = RecordingStore("ella")
    store.journal = journal
    skill = add_skill(
        store,
        "active",
        dict(
            verb="bind",
            target=None,
            instruments=[],
            inputs=[
                dict(quantity=1, look=dict(archetype_id="cord", material_id="vine", descriptors=[]))
            ],
            expected=["snaps"],
            circumstances=None,
        ),
    )
    period = PeriodCoordinator(
        store,
        journal,
        FrozenPrefix("p:ella:1", (), (), (), None),
        phenomena={"snaps": "The cord snaps."},
    )
    pins = []

    def record(delivery, **kwargs):
        p = delivery.packet
        path = source / "packets" / f"{p.observed_tick}.json"
        path.write_text(
            Batch(
                run_id="island",
                schema_version="wap/0.1",
                observed_tick=p.observed_tick,
                packets=[p],
            ).model_dump_json(),
            encoding="utf-8",
        )
        pins.append(fingerprint(path))
        result = period.deliver(delivery, **kwargs)
        return result

    def boundary(tick, events=()):
        snap = store.snapshot
        body = b"".join(e.model_dump_json().encode() + b"\n" for e in events)
        journal.fact(
            "island",
            f"{tick}.boundary",
            Boundary(
                tick=tick,
                through=AuditReader(writer.path).cursor(),
                committed=True,
                submissions=(),
                fallbacks=(),
                events=journal.blob(body),
                world_hash="a" * 64,
                store_version=snap.version,
                store_hash=snap.store_hash,
                decision=None,
                stop=None,
                incomplete=None,
            ),
        )

    def report(kind, identity, addressed=None):
        return dict(
            kind=kind, subject_id=identity, addressed=addressed, band=None, threshold_id=None
        )

    def event(tick, name, payload, *, intent=None):
        return WorldEvent(
            schema_version="wap/0.1",
            run_id="island",
            event_id=f"island:{tick:010}:000000",
            tick=tick,
            seq_in_tick=0,
            type=name,
            actor_id="ella",
            target_id=None,
            intent_id=intent,
            llm_call_id=None,
            caused_by_event_ids=[],
            payload=payload,
        )

    told = dict(kind="told", utterance_id="u1", speaker_id="mia")
    heard = dict(
        utterance_id="u1",
        speaker_id="mia",
        heard_at_tick=0,
        text="The spring is poisoned.",
        speech_act="statement",
        terms=None,
        in_reply_to=None,
        addressee_id="ella",
    )
    record(
        FilteredDelivery(
            packet(heard_utterances=[heard], reports=[report("utterance_heard", "u1", True)])
        )
    )
    boundary(0, [event(0, "utterance_heard", dict(utterance_id="u1", listener_id="ella"))])
    tile = dict(position=dict(x=2, y=1), terrain="spring")
    cue = dict(
        cue_id="spring",
        position=tile["position"],
        detail_level="near",
        direction=None,
        physical_description="a bubbling spring",
    )
    intent = Intent(
        turn_id="ella:t000000",
        intent_id="ella:t000000:a",
        actor_id="ella",
        action="act",
        verb="bind",
        target=None,
        inputs=[],
        instruments=[],
        params={},
        reason=None,
    )
    feedback = dict(
        intent_id=intent.intent_id,
        status="done",
        failure_code=None,
        stop_reason=None,
        inspected=None,
        phenomena=["snaps"],
        start_target=None,
        items_used=[
            dict(
                role="input",
                entity_id="vine-cord",
                archetype_id="cord",
                material_id="vine",
                descriptors=[],
                quantity=1,
            )
        ],
    )
    result = record(
        FilteredDelivery(
            packet(
                tick=1,
                environmental_cues=[cue],
                visible_tiles=[tile],
                action_feedback=[feedback],
                reports=[
                    report("action_ended", intent.intent_id),
                    report("entity_first_seen", "spring"),
                ],
            ),
            {intent.intent_id: FeedbackSource("bind", 0)},
        ),
        intents={intent.intent_id: intent},
    )
    seen, snap = (
        dict(kind="observed", entry_id=next(e.id for e in result.entries if e.type == kind))
        for kind in ("observation", "action_result")
    )
    boundary(
        1,
        [
            event(
                1,
                "act_settled",
                dict(
                    verb="bind",
                    rule_id="bind_snaps",
                    kind="applied",
                    at="completion",
                    failed_check=None,
                    phenomena=["snaps"],
                ),
                intent=intent.intent_id,
            )
        ],
    )
    asleep, intents = sleeping(packet, tick=2, start=1)
    record(asleep, intents=intents)
    flow = period.workflow
    clock, transport = fake_exchange(['{"read":[]}'])
    flow.advance(transport, clock)
    flow.advance(transport, clock)
    change_id = flow.state.calls[-1].call.call_id

    def add(n, name, subject, sources, confidence):
        return dict(
            op="add",
            op_id=str(n),
            ref=f"new:{n}",
            record=dict(
                kind="belief",
                gist=name,
                content=dict(subject=subject, topics=[], stance="stable"),
                sources=sources,
                confidence=confidence,
            ),
        )

    spring = dict(kind="place", ref="2,1")
    cord = dict(kind="entity", ref="vine-cord")
    ops = [
        add(1, "The spring is poisoned", spring, [told, seen], 3),
        add(2, "The spring is poisoned", spring, [told, seen], 4),
        add(3, "The cord snapped", cord, [snap], 4),
        add(4, "The spring is poisoned", spring, [seen], 3),
        add(
            5,
            "Avoid that cord",
            cord,
            [dict(kind="inferred", call_id=change_id, memory_ids=["new:3"])],
            2,
        ),
        add(6, "The cord snapped", cord, [snap], 4),
        dict(op="update", op_id="at-four", id="new:6", gist="The cord snapped", add_sources=[told]),
        dict(op="confidence", op_id="lower", id="new:3", to=3),
        dict(
            op="update", op_id="at-three", id="new:3", gist="Mia also warned me", add_sources=[told]
        ),
    ]
    clock, transport = fake_exchange([json.dumps(dict(ops=ops))])
    flow.advance(transport, clock)
    flow.advance(transport, clock)
    boundary(2)
    for tick in range(3, 38):
        result = record(
            FilteredDelivery(packet(tick=tick, awareness="asleep" if tick < 37 else "awake"))
        )
        boundary(tick)
    # A display-only replay for the synthetic run, with a static map and a frame at every tick.
    fixture = Path(__file__).resolve().parents[2] / "fixtures/replay/mechanics.replay.json"
    display = json.loads(fixture.read_bytes())
    display["run_id"] = "island"
    first = display["frames"][0]
    init = display["events"][0]
    init.update(run_id="island", event_id="island:0000000000:000000")
    display["events"] = [init]
    display["frames"] = [
        dict(first, tick=t, event_range=dict(first_index=int(t > 0), count=int(t == 0)))
        for t in range(39)
    ]
    replay = root / "replay.json"
    replay.write_text(json.dumps(display), encoding="utf-8")
    checks = source / "content-checks.json"
    checks.write_text(
        json.dumps(
            [
                dict(
                    instance_id="told_event:sample",
                    check="told_event",
                    ids=["u1", "island:0000000000:000000"],
                    verdict="carries",
                    checker="fixture-owner",
                    date="2026-11-23",
                    note="Mia's statement names the spring.",
                )
            ]
        ),
        encoding="utf-8",
    )
    seal = FinishedRun(
        status="finished",
        run_id="island",
        arm="on",
        final_tick=38,
        packet_sha256=pins,
        pack_ids=[ia.PackPin(pack_id="fixture", sha256="a" * 64)],
        replay_sha256=fingerprint(replay),
        residents=[
            ia.Resident(resident_id=r["id"], profile_id="fixture") for r in display["residents"]
        ],
        audit_sha256=fingerprint(writer.path),
        content_checks_sha256=fingerprint(checks),
    )
    manifest = root / "manifest.json"
    manifest.write_text(seal.model_dump_json(), encoding="utf-8")
    return (source, manifest, replay), result.record, store.snapshot, skill
