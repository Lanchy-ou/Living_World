"""Packet-driven fatigue and metabolism demonstrations for CT-09 through CT-11."""

from living_island.world.v2 import protocol as p
from living_island.world.v2.engine.state import OnTile
from living_island.world.v2.engine.validate import MentalFatigue, NeedMetabolism

from .fixture import ACTOR, SEED, WATCHER, Opening, ground, sleep, spring_schedule, turn
from .observe import Frame, Witness
from .trial import Trial, trial

FATIGUE = "CT-09"
WAKING = "CT-10"
RATES = "CT-11"


def fatigue(opening: Opening) -> MentalFatigue:
    value = opening.pack.physiology.mental_fatigue
    assert value is not None  # Enabled by the admitted starter pack.
    return value


def metabolism(opening: Opening, need: str) -> NeedMetabolism:
    value = (
        opening.pack.physiology.satiety if need == "satiety" else opening.pack.physiology.hydration
    )
    assert value is not None  # Both needs are enabled by the admitted starter pack.
    return value


def sleep_duration(opening: Opening) -> int:
    ticks: int = opening.pack.source.data["timing"]["sleep_ticks"]
    return ticks


def validate_survival(frame: Frame) -> None:
    frame.check(
        all(actor.alive for actor in frame.state.residents.values()), "residents stay alive"
    )


def fatigue_day(*, short: bool = False) -> Trial:
    name = "fatigue-day"
    opening = Opening(name, SEED, watcher=True)
    config = fatigue(opening)
    horizon = 3 if short else 96
    # The first move reveals nineteen pots and their nearby speaker. The
    # initial packet has no prior interval and emits no first-sighting reports.
    far = p.Coord(x=7, y=3)
    opening.state.residents[WATCHER].position = far
    opening.state.needs[WATCHER]["hydration"] = opening.pack.needs["hydration"].maximum
    for i in range(19):
        point = far if i < 10 else p.Coord(x=6, y=4)
        opening.item(f"sighting_{i:02d}", "clay_pot", OnTile(point))
    statement = p.Utterance(
        addressee_id=None, speech_act="statement", text="I am here.", terms=None, in_reply_to=None
    )
    script = spring_schedule(opening, horizon)
    script[(ACTOR, 0)] = turn("move_to", at=ground(p.Coord(x=6, y=3)))
    script.update(
        {(WATCHER, tick): turn("wait", utterance=statement) for tick in range(min(50, horizon - 1))}
    )

    def inspect(frame: Frame) -> None:
        validate_survival(frame)
        tick = frame.tick
        packet = frame.opening[ACTOR]
        sightings = sum(report.kind == "entity_first_seen" for report in packet.reports)
        heard = sum(report.kind == "utterance_heard" for report in packet.reports)
        frame.check(sightings == 20 * (tick == 2), "twenty first sightings counted once at opening")
        frame.check(
            heard == int(2 <= tick <= 51) == len(packet.perception.heard_utterances),
            "one genuine heard utterance at each scheduled opening",
        )
        expected = (
            tick * config.awake_per_tick
            + min(tick - 1, 50) * config.per_utterance_heard
            + 20 * config.per_first_sighting * (tick >= 2)
        )
        frame.check(
            frame.state.needs[ACTOR]["mental_fatigue"] == expected,
            f"opening packet inputs total {expected} fatigue",
        )
        frame.check(frame.state.awareness[ACTOR].kind == "awake", "awake throughout the day")

    labels = {
        1: "first-move-reveals-scene",
        2: "opening-sightings-and-first-heard",
        horizon: "day-end",
    }
    if not short:
        labels.update({51: "fiftieth-heard-utterance", 52: "silent-after-speech"})
    return trial(20, FATIGUE, name, opening, horizon, script, Witness(inspect, labels))


def fainting(*, short: bool = False) -> Trial:
    name = "fatigue-faint"
    opening = Opening(name, SEED)
    config = fatigue(opening)
    maximum = opening.pack.needs["mental_fatigue"].maximum
    full_awake = (maximum + config.awake_per_tick - 1) // config.awake_per_tick
    rested = opening.pack.source.vocabulary.verbs["sleep"]["params"][0]["min"]
    rehearsal_ticks = (rested * config.recovery_per_tick_asleep + config.awake_per_tick - 1) // (
        config.awake_per_tick
    )
    awake = min(full_awake, rehearsal_ticks + 3) if short else full_awake
    faint = rested + awake
    wake = faint + config.faint_ticks
    before_awake = 0
    if short:
        before_awake = (full_awake - awake) * config.awake_per_tick
        opening.state.needs[ACTOR]["mental_fatigue"] = before_awake + (
            rested * config.recovery_per_tick_asleep
        )
        # The short vector uses the same tail but stands in for the earlier hydrated ticks.
        opening.state.needs[ACTOR]["hydration"] = opening.pack.needs["hydration"].maximum

    script = spring_schedule(opening, faint - 2)
    script[(ACTOR, 0)] = sleep(rested)
    script[(ACTOR, faint - 2)] = turn("act", verb="rest")
    # Gate 1 includes the first new choice after wake. The final run ends at waking.
    horizon = wake + int(short)

    def inspect(frame: Frame) -> None:
        validate_survival(frame)
        tick = frame.tick
        state = frame.state
        after = state.pending_deliveries[ACTOR]
        frame.check(state.needs[ACTOR]["hydration"] > 0, "spring water keeps hydration above zero")
        if rested <= frame.boundary.tick < faint:
            opening_packet = frame.opening[ACTOR]
            frame.check(
                opening_packet.perception.awareness == "awake", "count only awake intervals"
            )
            frame.check(
                not any(
                    r.kind in ("entity_first_seen", "utterance_heard")
                    for r in opening_packet.reports
                ),
                "silent awake opening has no inputs",
            )
        if rested <= tick <= faint:
            expected = min(maximum, before_awake + (tick - rested) * config.awake_per_tick)
            frame.check(
                state.needs[ACTOR]["mental_fatigue"] == expected,
                "fatigue reaches its maximum on the expected silent boundary",
            )
        if tick > faint:
            frame.check(
                state.needs[ACTOR]["mental_fatigue"]
                == max(
                    0,
                    maximum
                    - min(tick - faint, config.faint_ticks) * config.recovery_per_tick_asleep,
                )
                + config.awake_per_tick * (tick > wake),
                "unconscious interval uses recovery",
            )
        frame.check(len(frame.events("resident_fainted")) == int(tick == faint), "one faint")
        frame.check(
            state.awareness[ACTOR].kind
            == ("asleep" if tick < rested else "unconscious" if faint <= tick < wake else "awake"),
            "awareness follows settled boundaries",
        )
        if tick == faint:
            (stop,) = frame.events("action_stopped")
            frame.check(stop.payload["reason"] == "FAINTED", "running rest stops at faint")
            feedback = after.perception.action_feedback
            frame.check(
                [(item.intent_id, item.stop_reason) for item in feedback]
                == [(stop.intent_id, "FAINTED")],
                "the faint boundary delivers the stop feedback once",
            )
            frame.check(
                frame.opening[ACTOR].perception.running_action is not None,
                "rest was still running at the opening",
            )
        if faint < tick <= wake:
            frame.check(
                all(turn.actor_id != ACTOR for turn in frame.boundary.turns.submissions),
                "no choice while unconscious, including the last interval",
            )
        if tick == wake:
            (event,) = frame.events("resident_woke")
            frame.check(
                event.payload["early"] is False and any(r.kind == "woke" for r in after.reports),
                "wake event and resident-visible wake delivery",
            )
            frame.check(not after.perception.action_feedback, "wake does not repeat the faint stop")
        if tick == wake + 1:
            frame.check(
                [turn.actor_id for turn in frame.boundary.turns.submissions] == [ACTOR],
                "waking re-enables choices on the next opening",
            )

    labels = {
        rested: "rested-opening",
        faint - 1: "before-faint",
        faint: "fainted-action-stop",
        faint + 1: "first-unconscious-interval",
        wake - 1: "before-faint-wake",
        wake: "faint-wake",
    }
    if short:
        labels[wake + 1] = "first-choice-after-wake"
    return trial(21, FATIGUE, name, opening, horizon, script, Witness(inspect, labels))


def night(*, short: bool = False) -> Trial:
    name = "fatigue-sleep"
    opening = Opening(name, SEED)
    config = fatigue(opening)
    duration = (
        opening.pack.source.vocabulary.verbs["sleep"]["params"][0]["min"]
        if short
        else sleep_duration(opening)
    )
    initial = min(
        opening.pack.needs["mental_fatigue"].maximum,
        duration * config.recovery_per_tick_asleep + 400,
    )
    opening.state.needs[ACTOR]["mental_fatigue"] = initial
    for need in ("hydration", "satiety"):
        opening.state.needs[ACTOR][need] = opening.pack.needs[need].maximum

    def inspect(frame: Frame) -> None:
        validate_survival(frame)
        tick = frame.tick
        frame.check(
            frame.state.needs[ACTOR]["mental_fatigue"]
            == max(0, initial - tick * config.recovery_per_tick_asleep),
            "every asleep interval contributes recovery, including the last",
        )
        frame.check(
            frame.state.awareness[ACTOR].kind == ("asleep" if tick < duration else "awake"),
            "ordinary sleep finishes on the requested boundary",
        )
        frame.check(
            len(frame.events("resident_woke")) == int(tick == duration), "ordinary wake once"
        )

    return trial(
        22,
        FATIGUE,
        name,
        opening,
        duration,
        {(ACTOR, 0): sleep(duration)},
        Witness(
            inspect,
            {
                1: "first-asleep-recovery",
                duration - 1: "before-night-wake",
                duration: "night-recovery-and-wake",
            },
        ),
    )


def early_wake(need: str, *, critical: bool) -> Trial:
    threshold = "critical" if critical else "urgent"
    name = f"wake-{need}-{threshold}"
    opening = Opening(name, SEED)
    rate = metabolism(opening, need)
    cutoff = next(row.at for row in opening.pack.needs[need].thresholds if row.id == threshold)
    initial = cutoff + 2 * rate.asleep_decay
    duration = opening.pack.source.vocabulary.verbs["sleep"]["params"][0]["min"]
    for key in ("hydration", "satiety"):
        opening.state.needs[ACTOR][key] = opening.pack.needs[key].maximum
    opening.state.needs[ACTOR][need] = initial

    def inspect(frame: Frame) -> None:
        validate_survival(frame)
        tick = frame.tick
        after = frame.state.pending_deliveries[ACTOR]
        woke = critical and tick >= 2
        expected = initial - min(tick, 2) * rate.asleep_decay
        if tick == 3:
            expected -= rate.awake_decay if woke else rate.asleep_decay
        frame.check(
            frame.state.needs[ACTOR][need] == expected, "metabolism on each side of threshold"
        )
        frame.check(
            frame.state.awareness[ACTOR].kind == ("awake" if woke else "asleep"),
            "urgent permits sleep and critical wakes it early",
        )
        frame.check(
            [
                r.threshold_id
                for r in after.reports
                if r.kind == "need_threshold_crossed" and r.subject_id == need
            ]
            == ([threshold] if tick == 2 else []),
            "resident receives the exact crossing once",
        )
        events = frame.events("resident_woke")
        frame.check(
            len(events) == int(critical and tick == 2), "critical wakes once, urgent never wakes"
        )
        if events:
            frame.check(
                events[0].payload["early"] is True and any(r.kind == "woke" for r in after.reports),
                "critical wake is early and delivered",
            )

    index = 30 + 2 * (need == "hydration") + critical
    return trial(
        index,
        WAKING,
        name,
        opening,
        3,
        {(ACTOR, 0): sleep(duration)},
        Witness(
            inspect,
            {1: f"before-{threshold}", 2: f"{threshold}-crossing", 3: f"after-{threshold}"},
        ),
    )


def rate_control() -> Trial:
    name = "asleep-awake-rates"
    opening = Opening(name, SEED, watcher=True)
    duration = opening.pack.source.vocabulary.verbs["sleep"]["params"][0]["min"]
    needs = {
        key: (opening.pack.needs[key].maximum, metabolism(opening, key))
        for key in ("satiety", "hydration")
    }
    for actor in (ACTOR, WATCHER):
        opening.state.needs[actor].update({key: initial for key, (initial, _) in needs.items()})

    def inspect(frame: Frame) -> None:
        validate_survival(frame)
        tick = frame.tick
        for key, (initial, rate) in needs.items():
            asleep = min(tick, duration)
            frame.check(
                frame.state.needs[ACTOR][key]
                == (initial - asleep * rate.asleep_decay - (tick - asleep) * rate.awake_decay),
                f"sleeper's {key} uses the asleep rate including the last sleep interval",
            )
            frame.check(
                frame.state.needs[WATCHER][key] == initial - tick * rate.awake_decay,
                f"awake control uses the awake {key} rate",
            )
        frame.check(
            frame.state.awareness[ACTOR].kind == ("asleep" if tick < duration else "awake"),
            "rate follows interval awareness rather than closing awareness",
        )

    return trial(
        40,
        RATES,
        name,
        opening,
        duration + 1,
        {(ACTOR, 0): sleep(duration)},
        Witness(
            inspect,
            {
                1: "first-sleep-and-awake-control",
                duration - 1: "before-final-sleep",
                duration: "final-sleep-interval",
                duration + 1: "first-awake-interval",
            },
        ),
    )
