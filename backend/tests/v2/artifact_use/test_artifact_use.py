from v2.artifact_use.journal import Journal, family, one_part, portions, totals


def test_ev22_applied_nonmaker_use_and_witnessed_sleep():
    j = Journal()
    cord = j.create(1, "cord", "A", 3)
    for key in ("left", "right"):
        j.event(2, "stack_split", from_id="cord", new_id=key, quantity=1, cause="transfer")
    make, items = j.start(3, "B", "combine", one_part("input", "cord"))
    j.event(3, "entity_consumed", actor="B", intent=make, entity_id="cord", quantity=1)
    axe = j.create(3, "axe", "B", intent=make, made_from=[{"physical_id": "cord", "quantity": 1}])
    settled = j.settle(3, "B", "combine", make)
    j.act(4, "B", "cut", one_part("instrument", "axe"))
    j.act(4, "A", "use", one_part("instrument", "left"))
    j.act(4, "C", "use", one_part("instrument", "left"), origin="fallback")
    j.act(4, "C", "use", one_part("instrument", "left"), kind="unmet")
    split_intent, *parts_events = j.act(
        5, "B", "combine", [("input", [("left", "cord", 1), ("right", "cord", 1)])]
    )
    for verb in ("feed", "strike"):
        j.act(6, "C", verb, one_part("target", "axe"))
    rows = j.metrics()
    assert totals(rows) == (2, 0, 0)
    uses = family(rows, "artifact_use")
    (first,) = [r for r in uses if make in r.trace]
    assert {cord.event_id, items.event_id, settled.event_id, "cord"} <= set(first.trace)
    assert portions(first)[0]["makers"] == ["A"]
    (two,) = [r for r in uses if split_intent in r.trace]
    assert {p["physical_id"] for p in portions(two)} == {"left", "right"}
    assert all(e.event_id in two.trace for e in parts_events)
    targets = family(rows, "artifact_target_only")
    assert len(targets) == 2 and all(r.value == 0 and axe.event_id in r.trace for r in targets)
    assert all(portions(r)[0]["makers"] == ["B"] and cord.event_id not in r.trace for r in targets)

    # Two sites close on the same tick. Their process IDs partition the work.
    for site, contributors in [("p1", "ACA"), ("p2", "D"), ("p3", "B")]:
        for n, actor in enumerate(contributors, 1):
            j.event(
                8,
                "process_progressed",
                actor=actor,
                process_id=site,
                contributor_id=actor,
                work_done=n,
            )
    for site, shelter in [("p1", "old"), ("p2", "replacement"), ("p3", "own")]:
        j.create(9, shelter, None, process=site)
    sleep = j.turn(10, "B", "sleep")
    j.event(
        11, "act_items", actor="B", intent=sleep, rule_id="sleep_in_shelter", slots=[], target=None
    )
    j.event(
        11, "resident_fell_asleep", actor="B", intent=sleep, resident_id="B", duration_ticks=140
    )

    def witness(tick, physical, timing="per_tick"):
        return j.event(
            tick,
            "condition_witness",
            actor="B",
            intent=sleep,
            entity_id=physical,
            condition_id="shelter",
            tick=tick,
            timing=timing,
        )

    w1 = witness(12, "old")
    w2 = witness(13, "old")
    j.event(14, "entity_consumed", entity_id="old", quantity=1)
    witness(14, "own")
    witness(15, None)
    witness(16, "replacement", "completion")  # No delivered completion gain.
    assert totals(j.metrics()) == (3, 0, 0)
    w3 = witness(144, "replacement")
    j.event(145, "act_settled", actor="B", intent=sleep, verb="sleep", kind="unmet")
    (row,) = [r for r in family(j.metrics(), "artifact_use") if sleep in r.trace]
    assert {
        (p["physical_id"], tuple(p["makers"]), p["creation_day"], p["use_day"], p["binding_event"])
        for p in portions(row)
    } == {
        ("old", ("A", "C"), 1, 1, w1.event_id),
        ("old", ("A", "C"), 1, 1, w2.event_id),
        ("replacement", ("D",), 1, 2, w3.event_id),
    }
    assert totals(j.metrics()) == (3, 1, 1)

    # Remove the distinct two-part action, keeping the later-day sleep.
    j.events = [e for e in j.events if e.intent_id != split_intent]
    assert totals(j.metrics()) == (2, 1, 0)

    # A positive completion effect supports the witness on its own tick.
    completion = j.turn(145, "C", "sleep")
    witness_event = j.event(
        146,
        "condition_witness",
        actor="C",
        intent=completion,
        entity_id="replacement",
        condition_id="shelter",
        tick=146,
        timing="completion",
    )
    gain = j.event(
        146,
        "needs_changed",
        actor="C",
        intent=completion,
        causes=["sleep_in_shelter"],
        changes=[{"need_id": "stamina", "before": 4, "after": 5}],
    )
    (row,) = [r for r in family(j.metrics(), "artifact_use") if completion in r.trace]
    assert row.value == 1 and {witness_event.event_id, gain.event_id} <= set(row.trace)


def test_ev24_en36_reservation_and_disjoint_returns(world, monkeypatch):
    from v2.engine.settle import test_settlement as en36

    j = Journal(world.state.run_id, tick_minutes=360)
    # EN-36 seeds two constituent histories directly. Supply their creation
    # and merge evidence before running the original, unchanged partial vector.
    for _ in range(4):
        world.step()
    a, b = en36.A, en36.B
    older = j.create(1, "inst_a", a)
    newer = j.create(4, "newer", b)
    merge = j.event(4, "stack_merged", from_id="newer", into_id="inst_a", quantity=1)
    step = type(world).step

    def record(self, *args, **kwargs):
        boundary = step(self, *args, **kwargs)
        if self is world:
            j.events.extend(boundary.events)
        return boundary

    monkeypatch.setattr(type(world), "step", record)
    en36.test_en35_split_release_and_progress(world, "partial", "stopped")
    engine_events = [e for e in j.events if e.tick > 4]
    split = next(e for e in engine_events if e.type == "stack_split")
    reserved = split.payload["new_id"]
    items = next(e for e in engine_events if e.type == "act_items")
    part = items.payload["slots"][0]["parts"][0]
    assert (part["entity_id"], part["physical_id"]) == ("inst_a", reserved)
    consumed = next(e for e in engine_events if e.type == "entity_consumed")
    returned = next(e for e in engine_events if e.type == "entity_created")
    head = returned.payload["entity_id"]
    assert returned.payload["recreated_from"] == [{"physical_id": reserved, "quantity": 1}]
    # If the return coalesced, reserve its oldest unit before the later use.
    live_head = head
    for e in engine_events:
        if e.type == "stack_merged" and e.payload["from_id"] == head:
            live_head = "reserved-again"
            j.event(
                7,
                "stack_split",
                from_id=e.payload["into_id"],
                new_id=live_head,
                quantity=1,
                cause="reservation",
            )
    later, bound, result = j.act(7, b, "strike", one_part("instrument", live_head))
    j.act(7, b, "strike", one_part("instrument", "inst_a"))
    # The unspent constituent is B's newer flake: a different actor can use it,
    # but that is a same-day use. B cannot use the whole pre-split merged stack.
    j.act(4, b, "strike", one_part("instrument", "inst_a", 2))
    remainder, *_ = j.act(7, a, "strike", one_part("instrument", "inst_a"))
    rows = j.metrics()
    assert totals(rows) == (2, 1, 0)
    (r,) = [r for r in family(rows, "artifact_use") if later in r.trace]
    assert {
        older.event_id,
        merge.event_id,
        split.event_id,
        items.event_id,
        items.intent_id,
        consumed.event_id,
        returned.event_id,
        bound.event_id,
        result.event_id,
        head,
        reserved,
        live_head,
    } <= set(r.trace)
    assert all((p["makers"], p["creation_day"], p["use_day"]) == ([a], 1, 2) for p in portions(r))
    (other,) = [r for r in family(rows, "artifact_use") if remainder in r.trace]
    assert newer.event_id in other.trace and all(
        (p["makers"], p["creation_day"], p["use_day"]) == ([b], 2, 2) for p in portions(other)
    )
    assert rows == j.metrics()
    assert rows == sorted(rows, key=lambda r: r.instance_id)
    assert all(r.trace == sorted(r.trace) for r in rows)

    # Two outputs cite the same ingredients but return disjoint physical debits.
    j.create(8, "handle", b)
    sources = [{"physical_id": live_head, "quantity": 1}, {"physical_id": "handle", "quantity": 1}]
    for s in sources:
        j.event(8, "entity_consumed", entity_id=s["physical_id"], quantity=1)
    for s, key in zip(sources, ("second-head", "second-handle"), strict=True):
        j.create(8, key, b, made_from=sources, recreated_from=[s])
    j.act(9, b, "use", one_part("instrument", "second-handle"))
    j.act(9, b, "use", one_part("instrument", "second-head"))
    assert totals(j.metrics()) == (3, 2, 1)

    # Old raw material does not give a newly crafted constituent a later-day use.
    mixed = Journal()

    def gathered(tick, dest):
        mixed.event(
            tick,
            "matter_moved",
            entity_id=dest,
            quantity=1,
            **{
                "from": {"kind": "store", "entity_id": "deposit"},
                "to": {"kind": "held", "holder_id": b},
            },
        )

    gathered(1, "stack")
    mixed.create(144, "crafted", a)
    mixed.event(144, "stack_merged", from_id="crafted", into_id="stack", quantity=1)
    mixed.event(144, "stack_merged", from_id="withdrawn", into_id="stack", quantity=1)
    gathered(144, "stack")
    mixed.act(144, b, "strike", one_part("instrument", "stack", 3))
    assert totals(mixed.metrics()) == (1, 0, 0)
    (row,) = family(mixed.metrics(), "artifact_use")
    assert [p["origin_id"] for p in portions(row)] == ["crafted"]


def test_artifact_use_missing_references_are_unknown():
    j = Journal()
    older = j.create(1, "older", "A")
    j.create(144, "newer", "B")
    j.event(144, "stack_merged", from_id="older", into_id="newer", quantity=1)
    j.act(145, "C", "strike", one_part("instrument", "newer", 2))
    (row,) = family(j.metrics(), "artifact_use")
    assert {tuple(p["makers"]) for p in portions(row)} == {("A",), ("B",)}
    assert {p["creation_day"] for p in portions(row)} == {1, 2}
    assert totals(j.metrics()) == (1, 1, 0)
    j.events.remove(older)
    (missing,) = family(j.metrics(), "artifact_use")
    assert missing.value is None and "older" in missing.reason
    assert totals(j.metrics()) == (None, None, None)

    # Losing the producer's physical debit invalidates the recreated part.
    j.events.append(older)
    returned = [{"physical_id": "newer", "quantity": 1}]
    j.create(146, "returned", "C", made_from=returned, recreated_from=returned)
    j.act(147, "B", "use", one_part("instrument", "returned"))
    (missing,) = [r for r in family(j.metrics(), "artifact_use") if r.value is None]
    assert "newer" in missing.reason
    j.create(148, "shelter", None, process="absent-site")
    _, _, settled = j.act(149, "C", "sleep", one_part("instrument", "shelter"))
    (missing,) = [r for r in family(j.metrics(), "artifact_use") if settled.event_id in r.trace]
    assert "missing process contributions" in missing.reason

    # A delivered gain with no physical witness stays unknown even if a shelter exists.
    sleeper = j.turn(150, "C", "sleep")
    j.event(
        151, "resident_fell_asleep", actor="C", intent=sleeper, resident_id="C", duration_ticks=2
    )
    gain = j.event(
        151,
        "needs_changed",
        actor="C",
        resident_id="C",
        causes=["physiology", "sleep_in_shelter"],
        changes=[{"need_id": "stamina", "before": 2, "after": 3}],
    )
    (missing,) = [r for r in family(j.metrics(), "artifact_use") if sleeper in r.trace]
    assert gain.event_id in missing.trace and "missing shelter condition_witness" in missing.reason
    # No decision record can be reconstructed from a public actor or intent ID.
    j.decisions.pop(0)
    (missing,) = [r for r in family(j.metrics(), "artifact_use") if "C:t000001:a" in r.trace]
    assert missing.reason == "missing decision origin"
    j.events = [e for e in j.events if e.type != "act_items" or e.intent_id != settled.intent_id]
    (missing,) = [r for r in family(j.metrics(), "artifact_use") if settled.event_id in r.trace]
    assert missing.reason == "missing act_items for applied act"

    # A public ID with an absent physical binding cannot identify the portion.
    j = Journal()
    j.create(1, "public", "A")
    _, bindings, _ = j.act(
        2, "B", "strike", one_part("instrument", "public") + one_part("target", "public")
    )
    for slot in bindings.payload["slots"]:
        del slot["parts"][0]["physical_id"]
    for metric in ("artifact_use", "artifact_target_only"):
        (row,) = family(j.metrics(), metric)
        assert row.value is None and "missing act_items physical_id" in row.reason

    # A previous settlement's debit cannot fill a later return's missing reference.
    j.event(3, "entity_consumed", entity_id="public", quantity=1)
    j.create(4, "bad-return", "A", recreated_from=[{"physical_id": "public", "quantity": 1}])
    _, _, finish = j.act(5, "B", "use", one_part("instrument", "bad-return"))
    (row,) = [r for r in family(j.metrics(), "artifact_use") if finish.event_id in r.trace]
    assert row.value is None and "public" in row.reason


def test_artifact_use_export_repeats_the_same_recorded_rows(tmp_path, monkeypatch):
    from dataclasses import replace

    from living_island.analysis.v2.artifact_use import artifact_use_metrics
    from living_island.analysis.v2.export import export, fingerprint
    from living_island.analysis.v2.shards import InspectionArchive
    from living_island.contract.replay import ReplayBundle
    from v2.inspection_export.short_capture import seal_capture
    from v2.resident_replay.replay_fixture import start

    source = tmp_path / "run"
    recording, kwargs, _ = start(source)
    world = recording.session.world
    step = world.step

    # Supply objective facts at the fake producer, before the recording is sealed.
    def benefit(*args, **kwargs):
        result = step(*args, **kwargs)
        sleep = next(
            e for e in result.events if e.actor_id == "ryan" and e.type == "resident_fell_asleep"
        )
        j = Journal(world.run_id)
        j.sequence[sleep.tick] = result.events[-1].seq_in_tick + 1
        j.event(
            sleep.tick,
            "process_progressed",
            actor="ella",
            process_id="site",
            contributor_id="ella",
            work_done=1,
        )
        j.create(sleep.tick, "roof", None, process="site")
        j.event(
            sleep.tick,
            "condition_witness",
            actor="ryan",
            intent=sleep.intent_id,
            entity_id="roof",
            condition_id="shelter",
            tick=sleep.tick,
            timing="per_tick",
        )
        return replace(result, events=(*result.events, *j.events))

    monkeypatch.setattr(world, "step", benefit)
    assert recording.advance() is not None
    inputs = seal_capture(tmp_path, source, recording, kwargs, "on")
    clock = ReplayBundle.model_validate_json(inputs[2].read_bytes()).clock
    originals = {p: fingerprint(p) for p in source.rglob("*") if p.is_file()}

    def read_again(name):
        destination = tmp_path / name
        index = export(*inputs, destination)
        archive = InspectionArchive.open(destination)
        return artifact_use_metrics(
            index.run_id,
            archive.read(index.attempts).events,
            [archive.read(ref.shard).record for ref in index.decisions],
            tick_minutes=clock.tick_minutes,
        )

    first = read_again("first")
    assert totals(first) == (1, 0, 0)
    assert portions(family(first, "artifact_use")[0])[0]["physical_id"] == "roof"
    assert first == read_again("second")
    assert all(fingerprint(p) == digest for p, digest in originals.items())
