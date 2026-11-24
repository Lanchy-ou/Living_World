"""P2 water and deprivation joins on a terminal interval with both drink sources."""

from pathlib import Path


def test_ct13_terminal_frame_and_drink_sources(tmp_path: Path):
    from living_island.analysis.data import RunData
    from living_island.analysis.metrics import resident_metrics
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.scenarios.balance.measurement import _events, _frame
    from living_island.sim.v2.scenarios.balance.observations import (
        Interval,
        Opening,
        Start,
        scenario,
    )
    from living_island.sim.v2.scenarios.runtime import Boundary
    from living_island.world import protocol as legacy
    from living_island.world.v2 import protocol as v2

    setup = scenario(tmp_path, 20261108, "compat-v1")
    session = setup.session(
        setup.world, PacketJournal(tmp_path / "packets", setup.world.run_id), None
    )
    result = session.advance()
    boundary = session.runner.manifest.boundaries[-1].for_replay()
    setup.observe({}, Boundary(0, boundary, result, lambda: (), lambda: b""))
    folder = tmp_path / "observations"
    opening = Opening.model_validate_json((folder / "opening.json").read_bytes())
    row = Interval.model_validate_json((folder / "0.json").read_bytes())
    actor, original = next(iter(row.starts.items()))
    x, y = next(
        (x, y) for y, line in enumerate(opening.map_rows) for x, c in enumerate(line) if c == "S"
    )
    pos = v2.Coord(x=x - 1, y=y)
    frames = []
    events = []
    prior = opening.frame
    for tick, source in enumerate((None, "canteen", "spring")):
        frame = prior.model_copy(deep=True)
        frame.tick = tick
        person = next(r for r in frame.residents if r.id == actor)
        person.position.x, person.position.y = x - 1, y
        if tick == 2:
            person.satiety = 0
        frames.append(_frame(frame, opening))
        if source:
            intent = original.intent.model_copy(
                update={
                    "action_type": "drink",
                    "target": None,
                    "parameters": legacy.DrinkParameters(source=source),
                }
            )
            start = Start(
                intent=intent,
                verb="drink",
                position=pos,
                target=None,
                item=None,
                utterance=False,
                intent_id=original.intent_id,
            )
            event = row.events[0].model_copy(
                update={
                    "type": "act_settled",
                    "actor_id": actor,
                    "intent_id": start.intent_id,
                    "seq_in_tick": 0,
                    "tick": tick,
                    "event_id": f"{setup.world.run_id}:{tick:010d}:000000",
                }
            )
            feedback = v2.ActionFeedback(
                intent_id=start.intent_id,
                status="done",
                failure_code=None,
                stop_reason=None,
                phenomena=["drinks"],
                inspected=None,
                start_target=None,
                items_used=[],
            )
            action = v2.ActionResult(
                intent_id=start.intent_id,
                actor_id=actor,
                tick_started=tick - 1,
                tick_finished=tick,
                outcome="settled",
                failure_code=None,
                stop=None,
                settlement=v2.Settlement(
                    rule_id=f"compat_drink_{source}",
                    kind="applied",
                    at="completion",
                    failed_check=None,
                ),
                state_delta=[
                    v2.StateDelta(
                        path=f"/residents/{actor}/needs/hydration", before=3000, after=9000
                    )
                ],
                visible_feedback=feedback,
                event_ids=[event.event_id],
            )
            interval = row.model_copy(
                update={"frame": frame, "events": (event,), "outcomes": (action,)}
            )
            events.extend(_events(interval, prior, opening, {start.intent_id: start}))
        prior = frame
    data = RunData(setup.world.run_id, frames, events, [], opening.map_rows, opening.limits)
    metrics = resident_metrics(data, actor)
    assert metrics.first_drink_tick == 1 and metrics.first_spring_drink_tick == 2
    assert metrics.canteen_drinks == metrics.spring_drinks == metrics.dedicated_water_trips == 1
    assert metrics.ticks_deprived == 1 and metrics.alive_at_T
