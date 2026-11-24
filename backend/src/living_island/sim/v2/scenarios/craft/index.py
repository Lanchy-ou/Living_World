"""Read the CT-04 observer checkpoint and verify the witnesses before publication."""

from collections import Counter
from collections.abc import Iterable
from itertools import pairwise

from living_island.world.v2 import protocol as p
from living_island.world.v2.rules import Pack

from .observer import Frame
from .route import SITE


def require(passed: bool, witness: str) -> None:
    if not passed:
        raise ValueError(f"missing craft witness: {witness}")


def by_kind(views: Iterable[p.InspectView]) -> dict[str | None, p.InspectView]:
    return {v.archetype_id: v for v in views}


def descriptor(view: p.InspectView, name: str) -> str:
    return next(d.value for d in view.descriptors if d.property_id == name)


class Story:
    def __init__(self, frames: Iterable[Frame], pack: Pack):
        self.frames = {f.tick: f for f in sorted(frames, key=lambda f: f.tick)}
        self.pack = pack
        self.actions = [a for f in self.frames.values() for a in f.actions]
        self.events = [e for f in self.frames.values() for e in f.events]

    def settled(
        self, rule: str, *, kind: str = "applied", target: str | None = None
    ) -> p.ActionResult:
        return next(
            a
            for a in self.actions
            if a.actor_id == "ella"
            and a.settlement
            and a.settlement.rule_id == rule
            and a.settlement.kind == kind
            and (target is None or getattr(a.visible_feedback.start_target, "id", None) == target)
        )

    def receipt(self, a: p.ActionResult) -> dict[str, object]:
        f = self.frames[a.tick_finished]
        effects = [
            e.model_dump(mode="json", include={"event_id", "type", "payload"})
            for e in f.events
            if e.intent_id == a.intent_id
        ]
        return {
            "actor": a.actor_id,
            "intent": a.intent_id,
            "opening": a.tick_started,
            "settled": f.tick,
            "events": list(a.event_ids),
            "turn": f"turns/{a.tick_started}.json",
            "actor_packet": f.packet_ids[a.actor_id],
            "phenomena": list(a.visible_feedback.phenomena),
            "items_used": a.visible_feedback.model_dump(mode="json")["items_used"],
            "effects": effects,
        }

    def matching(self, event: str, rule: str) -> list[p.WorldEvent]:
        return [e for e in self.events if e.type == event and e.payload.get("rule_id") == rule]

    def craft(self) -> dict[str, object]:
        order = [
            "knap_flake",
            "twist_cord",
            "bind_snaps",
            "make_stone_axe",
            "cut_wood_with_axe",
            "light_fire",
            "shape_pot",
            "fill_pot",
            "drink_from_pot",
            "mark_shelter_site",
            "sleep_in_shelter",
        ]
        steps = [self.settled(rule) for rule in order]
        require(
            all(x.tick_finished <= y.tick_started for x, y in pairwise(steps)),
            "chronology from strike through shelter sleep",
        )
        strike = steps[0]
        (nodule,) = [
            v
            for v in self.frames[strike.tick_started].inventory
            if v.archetype_id == "flint_nodule"
        ]
        (flakes,) = [
            v
            for v in self.frames[strike.tick_finished].inventory
            if v.archetype_id == "sharp_flake"
        ]
        (used,) = self.matching("entity_consumed", "knap_flake")
        require(
            nodule.quantity == 1
            and used.payload["entity_id"] == nodule.entity_id
            and flakes.quantity == 2
            and "splits" in strike.visible_feedback.phenomena,
            "one held nodule consumed for two flakes",
        )
        require(
            all(a.failure_code is None for a in self.actions), "all kernel submissions admitted"
        )

        twists = [
            self.receipt(a)
            for a in self.actions
            if a.settlement
            and a.settlement.rule_id == "twist_cord"
            and any(
                v.material_id == "grass" and v.quantity == 3 for v in a.visible_feedback.items_used
            )
        ]
        require(len(twists) == 2, "three grass fibres twisted for each binding")
        return {
            **{rule: self.receipt(a) for rule, a in zip(order, steps, strict=True)},
            "twist_grass": twists,
        }

    def binding(self, rule: str, word: str) -> dict[str, object]:
        action = self.settled(rule)
        looks = [
            (f, w)
            for f in self.frames.values()
            for w in f.watcher
            if w.intent_id == action.intent_id
        ]
        (first, start), (last, end) = looks
        inputs = by_kind(start.visible_items)
        require(
            (start.phase, end.phase) == ("start", "settle")
            and set(inputs) == {"cord", "sharp_flake", "branch"},
            f"{rule} watcher start",
        )
        actor = next(f for f in last.feedback if f.intent_id == action.intent_id)
        require(
            descriptor(inputs["cord"], "strength") == word
            and descriptor(by_kind(actor.items_used)["cord"], "strength") == word,
            f"{rule} apparent strength in both packets",
        )
        require(
            all(
                self.pack.vocabulary.properties[d.property_id]["observability"] == "visible"
                for w in (start, end)
                for item in w.visible_items
                for d in item.descriptors
                if item.archetype_id in {"cord", "sharp_flake", "branch"}
            ),
            "watcher sees only public material descriptors",
        )
        outputs = by_kind(end.visible_items)
        if rule == "bind_snaps":
            require(
                set(outputs) == {"sharp_flake", "branch"}
                and "snaps" in actor.phenomena
                and "snaps" in end.phenomena,
                "snaps and no surviving cord",
            )
            held = by_kind(last.inventory)
            for key, returned in outputs.items():
                require(
                    returned.material_id == inputs[key].material_id
                    and returned.entity_id != inputs[key].entity_id
                    and held[key].entity_id == returned.entity_id,
                    f"new held {key}",
                )
            require(
                inputs["cord"].entity_id not in {v.entity_id for v in last.inventory},
                "consumed vine cord",
            )
        else:
            require(
                "holds_firm" in actor.phenomena
                and "stone_axe" in outputs
                and inputs["cord"].material_id == "grass",
                "grass-bound axe",
            )
        return {
            **self.receipt(action),
            "actor_items": actor.model_dump(mode="json")["items_used"],
            "watcher_start": first.packet_ids["mia"],
            "watcher_settle": last.packet_ids["mia"],
            "start_look": start.model_dump(mode="json"),
            "settle_look": end.model_dump(mode="json"),
        }

    def cooperation(self) -> dict[str, object]:
        (site,) = self.matching("entity_created", "mark_shelter_site")
        (closure,) = self.matching("world_rule_applied", "finish_shelter")
        (shelter,) = self.matching("entity_created", "finish_shelter")
        consumed = self.matching("entity_consumed", "finish_shelter")
        site_id = site.target_id
        assert site_id is not None
        require(
            closure.target_id == site_id
            and shelter.payload["process_id"] == site_id
            and sum(e.payload["entity_id"] == site_id for e in consumed) == 1,
            "one site closure",
        )
        contributions = [e for e in self.events if e.type == "process_progressed"]
        first = contributions[0].tick
        blocked = next(
            f
            for f in self.frames.values()
            if any(i.action == "contribute" and i.actor_id == "ella" for i in f.intents)
        )
        stock = {v.archetype_id: v for v in blocked.visible if (v.position.x, v.position.y) == SITE}
        require(
            stock["branch"].quantity == stock["grass_tuft"].quantity == 4
            and stock["cord"].material_id == "vine"
            and blocked.work[site_id] == 0
            and first > blocked.tick
            and not any(e.type == "process_progressed" for e in blocked.events),
            "vine with frame and cover yields zero work",
        )
        ready = self.frames[first - 1]
        require(
            any(
                v.material_id == "grass"
                and v.archetype_id == "cord"
                and (v.position.x, v.position.y) == SITE
                for v in ready.visible
            ),
            "grass tie delivered",
        )
        required = self.pack.data["archetype"]["shelter_site"]["components"]["process"][
            "work_required"
        ]
        counts = Counter((e.tick, str(e.payload["contributor_id"])) for e in contributions)
        require(
            [e.payload["work_done"] for e in contributions] == list(range(1, required + 1))
            and all(
                counts[t, actor] == 1
                for t in range(first, closure.tick + 1)
                for actor in ("ella", "mia", "ryan")
            ),
            "three one-unit contributions per tick",
        )
        progress = {
            str(f.tick): descriptor(v, "progress")
            for f in self.frames.values()
            for v in f.visible
            if v.entity_id == site_id
        }
        require(set(progress.values()) == {"started", "halfway", "nearly_done"}, "visible progress")
        return {
            "site": site_id,
            "blocked_tick": blocked.tick,
            "blocked_packet": blocked.packet_ids["ella"],
            "grass_tie_packet": ready.packet_ids["ella"],
            "units": required,
            "progress": progress,
            "contributors": [
                e.model_dump(mode="json", include={"event_id", "tick", "payload"})
                for e in contributions
            ],
            "closure_event": closure.event_id,
            "shelter_event": shelter.event_id,
        }

    def pot(self) -> dict[str, object]:
        fill = self.settled("fill_pot")
        full = self.settled("fill_pot", kind="unmet")
        drink = self.settled("drink_from_pot")
        target = fill.visible_feedback.start_target
        assert isinstance(target, p.SubjectStartTarget)
        key = target.id
        frames = [
            self.frames[t]
            for t in (
                fill.tick_started,
                fill.tick_finished,
                full.tick_finished,
                drink.tick_finished,
            )
        ]
        servings = [f.water.get(key, 0) for f in frames]
        require(
            servings == [0, 1, 1, 0]
            and all(key in {v.entity_id for v in f.inventory} for f in frames)
            and all(f.slots[key] == 3 for f in frames),
            "held three-slot pot water trajectory",
        )
        require(
            ["fills_up", "already_full", "drinks"]
            == [f.feedback[0].phenomena[0] for f in frames[1:]],
            "first fill, full refusal and drinking feedback",
        )
        canteen = [f.water["canteen_01"] for f in frames]
        require(len(set(canteen)) == 1, "separate canteen water")
        return {
            "item": key,
            "slots": frames[0].slots[key],
            "servings": servings,
            "canteen_01": canteen,
            "actions": [self.receipt(a) for a in (fill, full, drink)],
        }

    def benefits(self) -> dict[str, object]:
        gather = self.settled("gather_deposit", target="deadwood_01")
        cut = self.settled("cut_wood_with_axe")
        harvesting = []
        for a in (gather, cut):
            (change,) = [
                e
                for e in self.events
                if e.type == "store_count_changed" and e.intent_id == a.intent_id
            ]
            before, after = (
                sum(v.quantity for v in self.frames[t].inventory if v.archetype_id == "branch")
                for t in (a.tick_started, a.tick_finished)
            )
            amount = after - before
            require(change.target_id == "deadwood_01", "both harvests from the same store")
            harvesting.append(
                {
                    "units": amount,
                    "ticks": a.tick_finished - a.tick_started,
                    "event": change.event_id,
                    "action": self.receipt(a),
                }
            )
        require(
            [(v["units"], v["ticks"]) for v in harvesting] == [(1, 3), (2, 2)],
            "deadwood harvest rates",
        )
        light = self.settled("light_fire")
        (bake,) = self.matching("world_rule_applied", "bake_pot")
        (gone,) = self.matching("world_rule_applied", "fire_goes_out")
        burns = self.matching("world_rule_applied", "fire_burns")
        duration = self.pack.data["archetype"]["campfire"]["components"]["fuel"]["ticks_left"]
        interval = int(self.pack.rules["bake_pot"].data["trigger"].split(":")[1])
        (insert,) = [
            e
            for e in self.events
            if e.type == "item_transferred" and e.payload["archetype_id"] == "unfired_pot"
        ]
        require(
            [e.tick for e in burns]
            == list(range(light.tick_finished, light.tick_finished + duration))
            and gone.tick == burns[-1].tick
            and bake.tick == insert.tick + (-insert.tick % interval)
            and bake.target_id == gone.target_id,
            "fire lifetime and first due bake",
        )
        sleep: dict[str, object] = {}
        sleep_rules = {
            "ella": "sleep_in_shelter",
            "mia": "compat_sleep",
            "ryan": "compat_sleep_cave",
        }
        for a in self.actions:
            if not a.settlement or a.settlement.rule_id != sleep_rules[a.actor_id]:
                continue
            actor = a.actor_id
            before = (
                self.frames[a.tick_started].stamina[actor]
                if a.tick_started
                else int(self.pack.data["needs"]["stamina"]["initial"])
            )
            values = [
                before,
                *(
                    self.frames[t].stamina[actor]
                    for t in range(a.tick_started + 1, a.tick_finished + 1)
                ),
            ]
            gains = [y - x for x, y in pairwise(values)]
            expected = 180 if actor == "mia" else 220
            require(gains == [expected] * 6, f"{actor} unclamped stamina gain")
            sleep[actor] = {
                **self.receipt(a),
                "rule": a.settlement.rule_id,
                "stamina": values,
                "gain_per_tick": expected,
            }
        require(set(sleep) == {"ella", "mia", "ryan"}, "sleep at shelter, ordinary ground and cave")
        return {
            "sharp_flake": self.receipt(self.settled("make_stone_axe")),
            "cord": {"axe": self.binding("make_stone_axe", "weak"), "shelter": self.cooperation()},
            "stone_axe": harvesting,
            "campfire": {
                "light": self.receipt(light),
                "fuel_ticks": duration,
                "burn_ticks": [e.tick for e in burns],
                "bake_interval": interval,
                "insert": insert.event_id,
                "bake": bake.event_id,
                "extinguished": gone.event_id,
            },
            "clay_pot": self.pot(),
            "shelter": sleep,
        }
