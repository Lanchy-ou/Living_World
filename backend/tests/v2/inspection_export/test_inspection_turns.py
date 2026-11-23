import json
import re
import sqlite3

import pytest

from v2.decision_harness.resident_vectors import act
from v2.inspection_export.short_capture import seal_capture
from v2.resident_replay.replay_fixture import start


def test_ev17_off_arm_sources_failed_usage_and_morning_without_a_turn(tmp_path):
    from living_island.agents.llm.provider import TransportResponse
    from living_island.agents.v2.calls.guard import Call, Part, Ref
    from living_island.agents.v2.context.prefix import open_prefix
    from living_island.agents.v2.context.state import CurrentState
    from living_island.agents.v2.decision.caller import Caller
    from living_island.analysis.v2.export import export, fingerprint
    from living_island.analysis.v2.shards import InspectionArchive
    from living_island.sim.v2.harness.checkpoint import Recording
    from living_island.sim.v2.harness.composition import compose

    source = tmp_path / "off"
    seed, kwargs, _ = start(source)
    decisions = []

    class Replies:
        def exchange(self, body, timeout_ms):
            request = json.loads(body)
            kind = request["text"]["format"]["name"]
            decisions.append(kind)
            if len(decisions) == 1:
                output = act(intention={"set": "Look for water."})
            elif len(decisions) == 2:
                output = '{"step":"recall","query":"What were my plans?"}'
            elif len(decisions) == 3:
                output = json.loads(act())
                output["cite"] = [
                    re.search(r"Current intention (m:[^ ]+:\d+):", request["input"][1]["content"])[
                        1
                    ]
                ]
                output = json.dumps(output)
            else:
                return TransportResponse(
                    400,
                    b'{"usage":{"input_tokens":41,"output_tokens":3,"prompt_cache_hit_tokens":17,"prompt_cache_miss_tokens":24}}',
                    True,
                )
            return TransportResponse(
                200,
                json.dumps(
                    dict(
                        status="completed",
                        output=[
                            dict(
                                type="message",
                                role="assistant",
                                status="completed",
                                content=[dict(type="output_text", text=output)],
                            )
                        ],
                    )
                ).encode(),
                True,
            )

    kwargs.update(memory_on=False, caller=Caller(Replies(), kwargs["caller"].clock, lambda _: None))
    record = Recording.opening(compose(seed.session.world, **kwargs), seed.packets, seed.audit)
    for _ in range(3):
        assert record.advance() is not None
    paths = seal_capture(tmp_path, source, record, kwargs, "off")
    with sqlite3.connect(source / "resident.sqlite") as db:
        receipts = [
            json.loads(raw)
            for (raw,) in db.execute(
                "SELECT body FROM facts WHERE name LIKE '%.citations.json' ORDER BY seq"
            )
        ]
    receipt = next(r for r in receipts if r["valid"])
    fragment = receipt["valid"][0]["fragments"][0]
    check = dict(
        instance_id="choice_link:off",
        check="choice_link",
        ids=[receipt["turn_id"]],
        verdict="relevant",
        checker="owner-fixture",
        date="2026-11-23",
        note="Current intention",
        sent_fragment_sha256=[fragment["sha256"]],
        source_revision_ids=[fragment["source"]["version"]],
        member_ids=[],
        antecedent_event_ids=[],
        chosen_outcome_ids=[],
    )
    checks_path = source / "content-checks.json"

    def save_check():
        checks_path.write_text(json.dumps([check]), encoding="utf-8")
        seal = json.loads(paths[1].read_bytes())
        paths[1].write_text(
            json.dumps({**seal, "content_checks_sha256": fingerprint(checks_path)}),
            encoding="utf-8",
        )

    save_check()
    directory = tmp_path / "off-inspection"
    index = export(*paths, directory)
    reader = InspectionArchive.open(directory)
    d = reader.read(index.decisions[1].shard)
    assert d.calls[-1].adopted_citations[0].valid[0].id == d.record.valid_cites[0]
    (cite,) = d.record.cited_parts
    n, sha = cite.revision.split(":")
    from living_island.contract.inspection_v2 import RevisionRef

    assert reader.revision("ryan", RevisionRef(cite.id, int(n), sha)).text == "Look for water."
    assert any(e.ref.kind == "recall" and e.ref.mode == "off_empty" for e in d.entries)
    failed = reader.read(index.decisions[-1].shard)
    assert failed.record.origin == "fallback" and failed.calls[-1].outcome == "failed"
    assert failed.record.telemetry.stages[-1].full_tokens > 0
    charge = reader.read(index.cost).attempts[-1]
    assert (charge.cache_hit, charge.cache_miss) == (17, 24)
    assert reader.read(index.cost).attempts[0].input is None
    (checked,) = reader.read(index.metrics).checked_parts
    assert checked.sha256 == cite.sent_part_sha256 and "Look for water." in checked.text
    check["sent_fragment_sha256"] = ["f" * 64]
    save_check()
    with pytest.raises(ValueError, match="outside an adopted citation"):
        export(*paths, tmp_path / "bad-choice")

    # An independent waking selection with a measured unfit floor and no dispatch.
    morning_dir = tmp_path / "morning"
    run, opts, _ = start(morning_dir)
    assert run.advance() is not None
    period = run.session.resident.period
    state = CurrentState(
        (Part("current_state", Ref(kind="current_state", id="large", version=None), "é" * 500000),),
        0,
    )
    profile = opts["identity"].profile
    call = Call(call_id="p:ryan:2:morning", period_id="p:ryan:2", resident_id="ryan", tick=1)

    def no_exchange(_):
        raise AssertionError("unfit selection dispatched")

    open_prefix(
        call=call,
        identity=opts["identity"],
        verbs=(),
        traits=profile.document.traits,
        view=period.store.snapshot.resident(memory_on=True),
        store_version=period.store.snapshot.version,
        memory_on=True,
        waking=state,
        journal=period.journal,
        select=no_exchange,
    )
    paths = seal_capture(morning_dir, morning_dir, run, opts, "on")
    dest = tmp_path / "morning-inspection"
    morning = export(*paths, dest)
    ref = next(c for c in morning.calls if c.call_kind == "morning")
    receipt = InspectionArchive.open(dest).read(ref.shard)
    assert ref.turn_id is None and receipt.outcome == "stopped_unfit" and not receipt.attempts
    assert receipt.prepared.admitted_candidate is None and receipt.requests
    assert (
        receipt.prepared.candidates[receipt.prepared.floor_candidate].manifest.tokens_total > 992000
    )
