"""CT-20's private feedback boundary through the stand-alone calibration entry point."""

from dataclasses import replace


def _run(case, mode, directory, monkeypatch, *, alternate_settlement=False):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.scenarios.calibration.comparison import TraceBoundary
    from living_island.sim.v2.scenarios.calibration.recording import scenario
    from living_island.sim.v2.scenarios.runtime import Boundary

    setup = case.prepare(directory / "inputs")
    world = setup.world
    if alternate_settlement:
        step = world.step

        def vary_objective(*args, **kwargs):
            result = step(*args, **kwargs)
            if world.tick == 1:
                # Change only the objective result returned to the coordinator.
                # The engine has already committed the resident's pending packet.
                actions = []
                for action in result.actions:
                    if action.actor_id == "ella":
                        assert action.settlement.failed_check == "stock"
                        changed = action.settlement.model_copy(update={"failed_check": "room"})
                        action = action.model_copy(update={"settlement": changed})
                    actions.append(action)
                return replace(result, actions=tuple(actions))
            return result

        monkeypatch.setattr(world, "step", vary_objective)
    trace = directory / "trace"
    arm = scenario(setup, mode, trace)
    journal = PacketJournal(directory / "packets", world.run_id)
    controller = arm.session(world, journal, None)
    rows = []
    for tick in range(case.start, case.end):
        result = controller.advance()
        boundary = controller.runner.manifest.boundaries[-1].for_replay()
        arm.observe({}, Boundary(tick, boundary, result, lambda t=tick: journal.read(t), bytes))
        rows.append(TraceBoundary.model_validate_json((trace / f"{tick}.json").read_bytes()))
    return rows, journal


def test_ct20_feedback_isolation_and_transitions(tmp_path, monkeypatch):
    from living_island.sim.v2.scenarios.calibration.fixtures import (
        calibration_cases,
        generic_failure_difference,
    )

    cases = {case.name: case for case in calibration_cases(tmp_path / "inputs")}
    empty = cases["wap23-gather-empty-at-start"]
    ordinary, journal = _run(empty, "visible", tmp_path / "stock", monkeypatch)
    hidden, other_journal = _run(
        empty, "visible", tmp_path / "hidden", monkeypatch, alternate_settlement=True
    )
    assert ordinary[0].trajectory.actions != hidden[0].trajectory.actions
    assert journal.read(1) == other_journal.read(1)
    assert [row.actors for row in ordinary] == [row.actors for row in hidden]
    [backoff] = ordinary[1].actors["ella"].policy_state.failed_targets
    assert (backoff.target.kind, backoff.code, backoff.retry_after_tick) == (
        "tile",
        "RESOURCE_TAKEN",
        37,
    )
    public, _ = _run(cases["wap23-gather-no-room"], "visible", tmp_path / "public", monkeypatch)
    [backoff] = public[1].actors["ella"].policy_state.failed_targets
    assert (backoff.target.kind, backoff.code, backoff.retry_after_tick) == (
        "self",
        "INVENTORY_FULL",
        37,
    )

    for mode in ("bridge", "visible"):
        [row], _ = _run(
            cases["dl25-generic-act-no-item"], mode, tmp_path / "generic" / mode, monkeypatch
        )
        assert generic_failure_difference(row) is None
        # Both modes could lose the same generic failure. The vector still fails.
        planted = row.model_copy(deep=True)
        planted.trajectory.actions = [a for a in planted.trajectory.actions if a.actor_id != "ella"]
        mismatch = generic_failure_difference(planted)
        assert (mismatch.tick, mismatch.actor, mismatch.field) == (
            1,
            "ella",
            "dl25.action_feedback.length",
        )

        failed, _ = _run(
            cases["wap23-reply-dialogue-limit"], mode, tmp_path / "reply" / mode, monkeypatch
        )
        pending = failed[1].actors["ryan"].queue
        assert [i.action_type for i in pending] == ["give"]
        assert failed[1].trajectory.utterances["ryan"].failure_code == "DIALOGUE_LIMIT"
        ending = failed[2].actors["ryan"]
        [joined] = ending.boundary_results
        assert (joined.intent_id, joined.failure_code) == ("ryan:p000001:i0", "DIALOGUE_LIMIT")
        assert ending.decision.triggers.count("ACTION_FAILED") == 1
        assert all(i.intent_id != pending[0].intent_id for i in ending.decision.plan.intents)
        assert "ACTION_FAILED" not in failed[3].actors["ryan"].boundary_triggers

        for name, stop_reason, result_field, private_code in (
            ("wap23-wap33-en23-gather-exhaustion", "EXHAUSTED", "failure_code", "EXHAUSTED"),
            ("wap23-wap32-early-wake-no-speech", "WOKEN", "interruption_reason", "URGENT_NEED"),
        ):
            stopped, _ = _run(cases[name], mode, tmp_path / name / mode, monkeypatch)
            result = next(r for r in stopped[0].trajectory.actions if r.actor_id == "ella")
            assert (result.visible_feedback.status, result.visible_feedback.stop_reason) == (
                "stopped",
                stop_reason,
            )
            ending = stopped[1].actors["ella"]
            [joined] = ending.boundary_results
            assert getattr(joined, result_field) == private_code
            assert ending.decision.decision_ordinal == 1
