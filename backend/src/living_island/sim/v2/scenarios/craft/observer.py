"""Index objective state beside the looks actually delivered to Ella and Mia."""

from pydantic import BaseModel

from living_island.sim.v2.scenarios.receipts import State
from living_island.sim.v2.scenarios.runtime import Boundary
from living_island.world.v2 import protocol as p
from living_island.world.v2.engine.state import Entity, Inside


class Snapshot(BaseModel):
    entities: dict[str, Entity]
    needs: dict[str, dict[str, int]]
    pending_deliveries: dict[str, p.BoundaryDelivery]


class Frame(BaseModel):
    tick: int
    intents: list[p.Intent]
    actions: list[p.ActionResult]
    events: list[p.WorldEvent]
    packet_ids: dict[str, str]
    inventory: list[p.ItemView]
    feedback: list[p.ActionFeedback]
    watcher: list[p.ObservedAction]
    visible: list[p.EntityView]
    stamina: dict[str, int]
    water: dict[str, int]
    work: dict[str, int]
    slots: dict[str, int]


def observe(state: State, boundary: Boundary) -> State:
    snap = Snapshot.model_validate_json(boundary.closing_snapshot())
    ella = snap.pending_deliveries["ella"].perception
    mia = snap.pending_deliveries["mia"].perception
    events = boundary.result.events
    frame = Frame(
        tick=ella.tick,
        intents=[
            s.action.intent
            for s in boundary.turns.submissions
            if s.action.kind == "intent" and s.action.intent.action != "wait"
        ],
        actions=[a for a in boundary.result.actions if a.settlement or a.failure_code],
        events=[
            e
            for e in events
            if e.type
            in {
                "entity_created",
                "entity_consumed",
                "item_transferred",
                "process_progressed",
                "store_count_changed",
                "world_rule_applied",
                "entity_state_changed",
            }
        ],
        packet_ids={k: v.delivery_id for k, v in snap.pending_deliveries.items()},
        inventory=ella.inventory,
        feedback=[f for f in ella.action_feedback if f.phenomena],
        watcher=[w for w in mia.observed_actions if w.actor_id == "ella" and w.verb == "combine"],
        visible=[
            v
            for v in ella.visible_entities
            if v.archetype_id in {"shelter_site", "shelter", "campfire", "clay_pot"}
            or (v.position.x, v.position.y) == (39, 31)
        ],
        stamina={a: needs["stamina"] for a, needs in snap.needs.items()},
        water={
            e.place.container_id: e.quantity
            for e in snap.entities.values()
            if e.archetype_id == "water" and isinstance(e.place, Inside)
        },
        slots={
            e.entity_id: e.components["portable"]["slots_per_unit"]
            for e in snap.entities.values()
            if e.archetype_id == "clay_pot"
        },
        work={
            e.entity_id: e.components["process"]["work_done"]
            for e in snap.entities.values()
            if e.archetype_id == "shelter_site"
        },
    )
    state[str(frame.tick)] = frame.model_dump(mode="json")
    return state
