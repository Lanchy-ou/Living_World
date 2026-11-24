"""World-rule demonstrations for starter CT-08 and CT-19."""

from itertools import count

from living_island.world.v2 import protocol as p
from living_island.world.v2.engine.chance import chance_roll
from living_island.world.v2.engine.items import place_payload
from living_island.world.v2.engine.state import Held, Inside, OnTile

from .fixture import (
    ACTOR,
    HOME,
    NEXT,
    SEED,
    WATCHER,
    Opening,
    Schedule,
    drop,
    ground,
    named,
    pickup,
    spring_schedule,
    target,
    turn,
)
from .observe import Frame, Witness
from .trial import Trial, trial

PHYSICAL = "CT-08"
BOUNDARIES = "CT-19"


def rule_value(opening: Opening, rule: str, check: str) -> int:
    value: int = next(
        row["value"]
        for row in opening.pack.source.rules[rule].data["conditions"]
        if row["id"] == check
    )
    return value


def period(opening: Opening, rule: str) -> int:
    return int(opening.pack.source.rules[rule].data["trigger"].split(":")[1])


def work(opening: Opening, rule: str) -> int:
    ticks: int = opening.pack.source.rules[rule].data["work_ticks"]
    return ticks


def deposit(opening: Opening, key: str, at: p.Coord, capacity: int, stock: int) -> None:
    opening.item(
        key,
        "deposit",
        OnTile(at),
        material="wood",
        components={
            "store": {"archetype": "branch", "capacity": capacity, "count": stock},
        },
    )


def regrowth() -> Trial:
    opening = Opening("regrowth", SEED)
    step = period(opening, "regrow_deadwood")
    opening.state.tick = step - 2
    opening.state.clock_minute = opening.state.clock.minute_at(opening.state.tick)
    deposit(opening, "space", HOME, 3, 2)
    deposit(opening, "full", NEXT, 3, 3)

    def inspect(frame: Frame) -> None:
        for key, stock in (("space", 2 + (frame.tick >= step)), ("full", 3)):
            store = frame.state.entities[key].components["store"]
            frame.check(store["count"] == stock, f"{key} deadwood stock must be {stock}")
        events = frame.rules("regrow_deadwood")
        frame.check(
            [event.target_id for event in events] == (["space"] if frame.tick == step else []),
            "only the due deposit with room regrows",
        )

    return trial(
        0,
        PHYSICAL,
        "regrowth",
        opening,
        3,
        {},
        Witness(
            inspect,
            {step - 1: "before-regrowth", step: "regrowth-at-capacity", step + 1: "after-regrowth"},
        ),
    )


def lighting(*, succeeds: bool) -> Trial:
    name = "light-success" if succeeds else "light-failure"
    opening = Opening(name, SEED, watcher=True)
    fire_ticks = opening.pack.source.data["archetype"]["campfire"]["components"]["fuel"][
        "ticks_left"
    ]
    bake_every = period(opening, "bake_pot")
    duration = work(opening, "light_fire")
    chance = opening.pack.source.rules["light_fire"].data["success_per_mille"]

    # Until light starts, the actor completes one real wait per boundary.
    starts = (
        start
        for start in count(0)
        if not succeeds or (start + duration + fire_ticks - 1) % bake_every == 0
    )
    start = next(
        tick
        for tick in starts
        if (chance_roll(SEED, tick + duration, "light_fire", f"{ACTOR}:t{tick:06d}:a") < chance)
        == succeeds
    )
    lit = start + duration
    out = lit + fire_ticks - 1
    opening.item("pile", "branch", OnTile(HOME), quantity=2)
    opening.item("striker", "flint_nodule")
    opening.item("hammer", "stone")
    opening.item("tinder", "grass_tuft")
    if succeeds:
        opening.item("pot", "unfired_pot")
    script = {
        (ACTOR, start): turn(
            "act",
            verb="light",
            at=target("pile"),
            instruments=("striker", "hammer"),
            inputs=(p.ActionInput(item=named("tinder"), quantity=1),),
        )
    }
    if succeeds:
        # Use the real fire ID already disclosed in the opening packet.
        from living_island.world.v2.engine.ids import entity_candidate

        drop_start = out - 1 - opening.pack.timing.durations["drop"]
        script[(ACTOR, drop_start)] = drop("pot", target(entity_candidate(SEED, 0, 0)))

    def inspect(frame: Frame) -> None:
        tick = frame.tick
        entities = frame.state.entities
        fires = [e for e in entities.values() if e.archetype_id == "campfire"]
        frame.check(("tinder" in entities) == (tick < lit), "tinder used exactly at settlement")
        frame.check(("pile" in entities) == (tick < lit or not succeeds), "branch pile fate")
        if "pile" in entities:
            frame.check(entities["pile"].quantity == 2, "both branches remain")
        if tick == lit:
            (settlement,) = frame.events("act_settled")
            frame.check(
                settlement.payload["phenomena"] == (["catches_fire"] if succeeds else ["smokes"]),
                "lighting outcome and chance feedback",
            )
        if not succeeds:
            frame.check(
                not fires and not frame.rules("fire_burns"), "failed lighting creates no fire"
            )
            return
        burns = frame.rules("fire_burns")
        frame.check(len(burns) == int(lit <= tick <= out), "one fuel debit per lit tick")
        frame.check(len(fires) == int(lit <= tick < out), "fire lifetime")
        if fires:
            frame.check(
                fires[0].components["fuel"]["ticks_left"] == out - tick,
                "lighting tick must already use one fuel",
            )
        bake = frame.rules("bake_pot")
        gone = frame.rules("fire_goes_out")
        frame.check(len(bake) == len(gone) == int(tick == out), "bake and extinguish on last fuel")
        if tick == out:
            frame.check(
                bake[0].seq_in_tick < burns[0].seq_in_tick < gone[0].seq_in_tick,
                "last fuel bake precedes burn and removal",
            )
            frame.check(
                any(
                    e.archetype_id == "clay_pot" and e.place == OnTile(HOME)
                    for e in entities.values()
                ),
                "baked pot is on the fire tile",
            )

    labels = {lit - 1: "before-lighting", lit: name, lit + 1: "after-lighting"}
    if succeeds:
        labels.update({out - 1: "before-last-fuel", out: "last-fuel-bake", out + 1: "after-fire"})
    return trial(
        1 if succeeds else 2,
        PHYSICAL,
        name,
        opening,
        out + 1 if succeeds else lit + 1,
        script,
        Witness(inspect, labels),
    )


def baking(insertion: int) -> Trial:
    index = {5: 3, 6: 10, 7: 11}[insertion]
    demo = PHYSICAL if insertion == 5 else BOUNDARIES
    name = f"bake-insert-{insertion}"
    opening = Opening(name, SEED, watcher=True)
    every = period(opening, "bake_pot")
    due = insertion + (-insertion % every)
    opening.item("fire", "campfire", OnTile(HOME), components={"fuel": {"ticks_left": due + 2}})
    opening.item("pot", "unfired_pot")
    script = {
        (ACTOR, insertion - opening.pack.timing.durations["drop"]): drop("pot", target("fire"))
    }

    def inspect(frame: Frame) -> None:
        tick = frame.tick
        entities = frame.state.entities
        frame.check(len(frame.rules("bake_pot", "fire")) == int(tick == due), "first due bake only")
        pots = [e for e in entities.values() if e.archetype_id == "clay_pot"]
        frame.check(len(pots) == int(tick >= due), "one baked pot")
        if tick < due:
            frame.check(
                entities["pot"].place == (Held(ACTOR) if tick < insertion else Inside("fire")),
                "unfired pot stays at its admitted place",
            )
        if tick == due:
            frame.check(
                "pot" not in entities and pots[0].place == OnTile(HOME),
                "bake consumes contents and creates a fired pot on the tile",
            )
            if due == insertion:
                (transfer,) = frame.events("item_transferred")
                frame.check(
                    transfer.seq_in_tick < frame.rules("bake_pot")[0].seq_in_tick,
                    "phase 3 insertion precedes phase 4 bake",
                )

    labels = {insertion - 1: "before-insertion", insertion: "insertion", due + 1: "after-bake"}
    if due != insertion:
        labels.update(
            {due - 1: "insertion-before-due" if due - 1 == insertion else "before-due", due: "bake"}
        )
    else:
        labels[due] = "phase-3-insertion-and-phase-4-bake"
    return trial(index, demo, name, opening, due + 1, script, Witness(inspect, labels))


def spilling(*, blocked: bool) -> Trial:
    name = "spill-blocked" if blocked else "spill-admitted"
    opening = Opening(name, SEED, watcher=True)
    cap = opening.pack.limits.max_entities_per_tile
    opening.item("fire", "campfire", OnTile(HOME), components={"fuel": {"ticks_left": 2}})
    opening.item("contents", "unfired_pot", Inside("fire"))
    script: Schedule = {}
    drop_ticks = opening.pack.timing.durations["drop"]
    pickup_ticks = opening.pack.timing.durations["pick_up"]
    release = 3 + pickup_ticks if blocked else 2
    if blocked:
        for i in range(cap - 1):
            opening.item(f"filler_{i:02d}", "clay_pot", OnTile(HOME))
        opening.item("drop_a", "clay_pot")
        opening.item("drop_b", "clay_pot")
        script.update(
            {
                (ACTOR, 0): drop("drop_a", ground(HOME)),
                (ACTOR, drop_ticks): drop("drop_b", ground(HOME)),
                (ACTOR, 3): pickup("drop_a"),
                (WATCHER, 3): pickup("drop_b"),
            }
        )

    def inspect(frame: Frame) -> None:
        tick = frame.tick
        entities = frame.state.entities
        inside = entities["contents"]
        frame.check(
            inside.quantity == 1 and inside.archetype_id == "unfired_pot",
            "exact contents survive spill",
        )
        frame.check(
            inside.place == (Inside("fire") if tick < release else OnTile(HOME)),
            "contents remain inside until spill admits",
        )
        frame.check(("fire" in entities) == (tick < release), "fire removal is atomic with spill")
        if tick < release:
            frame.check(
                entities["fire"].components["fuel"]["ticks_left"] == max(0, 2 - tick),
                "blocked fire remains unlit",
            )
            frame.check(inside.lineage[0].origin_id == "contents", "contents retain their identity")
        moves = [
            e
            for e in frame.boundary.result.events
            if e.type == "matter_moved" and e.payload["entity_id"] == "contents"
        ]
        frame.check(
            len(moves) == len(frame.rules("fire_goes_out")) == int(tick == release),
            "contents move exactly once and only with the removal event",
        )
        if blocked and 2 <= tick < release:
            load = sum(e.place == OnTile(HOME) for e in entities.values())
            frame.check(load - 1 > cap, "legal drops exceed cap even excluding the fire")
        if blocked and tick >= release:
            frame.check(
                sum(e.place == OnTile(HOME) for e in entities.values()) == cap,
                "freed space admits the whole spill at the cap",
            )

    labels = {
        1: "last-fuel-before-burn",
        2: "blocked-spill" if blocked else "admitted-spill",
        release + 1: "after-spill",
    }
    if blocked:
        labels.update({release - 1: "blocked-retry", release: "spill-after-pickups"})
    return trial(
        12 if blocked else 4,
        BOUNDARIES if blocked else PHYSICAL,
        name,
        opening,
        release + 1,
        script,
        Witness(inspect, labels),
    )


def fruit(*, split: bool = False, crumble: bool = False, short: bool = False) -> Trial:
    name = "fruit-split" if split else "fruit-crumble" if crumble else "fruit-rot"
    opening = Opening(name, SEED, watcher=split)
    archetype = "rotten_fruit" if crumble else "fruit"
    rule, check = ("rotten_fruit_crumbles", "gone") if crumble else ("fruit_rots", "old")
    age = rule_value(opening, rule, check)
    due = 2 if split or crumble or short else age
    opening.item("fruit", archetype, quantity=4, created=due - age)
    if split:
        # A single oldest unit leaves with the split. The younger remainder still
        # carries the stack's inherited oldest-unit timestamp.
        from living_island.world.v2.engine.state import Lineage

        opening.state.entities["fruit"].lineage = (
            Lineage("fruit", due - age, 1, 1),
            Lineage("fruit_later", due - age + 1, 3, 2),
        )
    horizon = due + int(split or crumble or short)
    script = spring_schedule(opening, horizon)
    if split:
        script[(ACTOR, 0)] = drop("fruit", ground(NEXT), 1)
    if not (split or crumble or short):
        # Short sleeps keep the resident awake for the final fruit boundary.
        sleep_ticks = opening.pack.source.vocabulary.verbs["sleep"]["params"][0]["min"]
        for tick in (80, 160, 240, 320, 400):
            script[(ACTOR, tick)] = turn(
                "act", verb="sleep", params={"duration_ticks": sleep_ticks}
            )

    places = {Held(ACTOR): 3, OnTile(NEXT): 1} if split else {Held(ACTOR): 4}

    def inspect(frame: Frame) -> None:
        tick = frame.tick
        expected = len(places) if tick == due else 0
        frame.check(len(frame.rules(rule)) == expected, "decay applies once per admitted stack")
        entities = frame.state.entities
        current = archetype if tick < due else None if crumble else "rotten_fruit"
        observed = [e for e in entities.values() if e.archetype_id in ("fruit", "rotten_fruit")]
        frame.check(
            {e.place: e.quantity for e in observed} == (places if current else {}),
            "quantities persist in their respective places until crumble",
        )
        for entity in observed:
            frame.check(entity.archetype_id == current, "stack archetype across age threshold")
            frame.check(
                entity.created_tick == (due - age if tick < due else due),
                "split keeps the original oldest-unit timestamp, rot creates a new one",
            )
        for packet in frame.state.pending_deliveries.values():
            pview = packet.perception
            frame.check(
                all(
                    descriptor.property_id != "age"
                    for item in (*pview.inventory, *pview.visible_entities)
                    for descriptor in item.descriptors
                ),
                "age stays private to world rules",
            )
        if split and tick == 1:
            frame.check(len(frame.events("stack_split")) == 1, "kernel drop splits at age 431")

    labels = {due - 1: "before-decay", due: name}
    if horizon > due:
        labels[due + 1] = "after-decay"
    return trial(
        13 if split else 6 if crumble else 5,
        BOUNDARIES if split else PHYSICAL,
        name,
        opening,
        horizon,
        script,
        Witness(inspect, labels),
    )


def wear() -> Trial:
    opening = Opening("axe-wear", SEED, watcher=True)
    cut_id = "cut_wood_with_axe"
    duration = work(opening, cut_id)
    failed = opening.pack.timing.attempts["cut"]
    debit = opening.pack.source.rules[cut_id].data["effects"][0]["quantity"]
    limit = opening.pack.source.data["archetype"]["stone_axe"]["components"]["durability"][
        "max_wear"
    ]
    thresholds = opening.pack.source.vocabulary.properties["wear_state"]["descriptors"]
    deposit(opening, "empty", HOME, debit, 0)
    deposit(opening, "wood", NEXT, limit * debit, limit * debit)
    opening.item("axe", "stone_axe", material="flint")
    drop_ticks = opening.pack.timing.durations["drop"]
    starts = [failed + index * (duration + drop_ticks) for index in range(limit)]
    finishes = {tick + duration for tick in starts}
    last = starts[-1] + duration
    script = {(ACTOR, 0): turn("act", verb="cut", at=target("empty"), instruments=("axe",))}
    for start in starts:
        script[(ACTOR, start)] = turn("act", verb="cut", at=target("wood"), instruments=("axe",))
        if start + duration != last:
            script[(ACTOR, start + duration)] = turn(
                "drop",
                at=ground(HOME),
                params={
                    "item": {"kind": "held", "archetype_id": "branch"},
                    "quantity": debit,
                },
            )

    def inspect(frame: Frame) -> None:
        tick = frame.tick
        entities = frame.state.entities
        done = sum(finish <= tick for finish in finishes)
        frame.check(
            entities["wood"].components["store"]["count"] == (limit - done) * debit,
            "stock is debited on each successful cut only",
        )
        if tick == failed:
            (failure,) = frame.events("act_settled")
            frame.check(failure.payload["failed_check"] == "stock", "empty cut fails without wear")
        frame.check(len(frame.rules("axe_breaks")) == int(tick == last), "axe breaks exactly once")
        if done < limit:
            frame.check(
                entities["axe"].components["durability"]["wear"] == done, "one wear per cut"
            )
            item = next(
                i
                for i in frame.state.pending_deliveries[ACTOR].perception.inventory
                if i.entity_id == "axe"
            )
            expected = next(
                (row["word"] for row in thresholds if limit - done <= row["upto"]),
                thresholds[-1]["word"],
            )
            frame.check(
                [entry.value for entry in item.descriptors if entry.property_id == "wear_state"]
                == [expected],
                f"wear band is {expected}",
            )
        else:
            frame.check("axe" not in entities, "broken axe is removed")
            if tick == last:
                (branch,) = [
                    e
                    for e in frame.boundary.result.events
                    if e.type == "entity_created" and e.payload["rule_id"] == "axe_breaks"
                ]
                frame.check(
                    branch.payload["archetype_id"] == "branch"
                    and branch.payload["quantity"] == 1
                    and branch.payload["place"] == place_payload(Held(ACTOR)),
                    "handle stays where the axe was",
                )

    labels = {failed: "failed-cut-no-wear", failed + 1: "before-first-success"}
    labels.update({finish: f"cut-{i:02d}" for i, finish in enumerate(sorted(finishes), 1)})
    labels.update({last - 1: "before-break", last + 1: "after-break"})
    return trial(7, PHYSICAL, "axe-wear", opening, last + 1, script, Witness(inspect, labels))
