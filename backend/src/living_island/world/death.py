"""Death: corpse, atomic inventory drop and the death facts (World Rules §3, §6).

``apply_death`` is a pure function from a ``WorldState`` to a new ``WorldState`` plus the
facts, in catalog order. It does not allocate event IDs, emit the ``action_interrupted``
fact or build an ``ActionResult`` (the cancelled action is returned so P1-04 can), and sends
no global notification: other residents only learn of the death through perception.
"""

from __future__ import annotations

from dataclasses import dataclass

from living_island.world.content import EffectiveConfig
from living_island.world.facts import CorpseCreatedPayload, ItemDroppedPayload, ResidentDiedPayload
from living_island.world.perception import ground_fruit_id  # read-only reuse of P1-02
from living_island.world.resources import add_ground_fruit
from living_island.world.rulefacts import PendingFact
from living_island.world.state import (
    ActiveAction,
    CorpseState,
    UniqueCanteenState,
    WorldState,
)


def corpse_id(resident_id: str) -> str:
    """Stable corpse handle ``corpse@<resident_id>``; there is no respawn in v0.1."""
    return f"corpse@{resident_id}"


def deaths_due(config: EffectiveConfig, state: WorldState) -> list[str]:
    """Living residents at minimum health, ascending resident ID."""
    return [
        r.id
        for r in sorted(state.residents, key=lambda r: r.id)
        if r.alive and r.health <= config.needs.min_value
    ]


@dataclass(frozen=True)
class DeathResult:
    state: WorldState  # a deep copy; the input is untouched
    facts: list[PendingFact]  # resident_died, corpse_created, item_dropped (fruit, canteen)
    cancelled_action: ActiveAction | None  # for P1-04's ``action_interrupted(reason=DEATH)``


def apply_death(
    config: EffectiveConfig, state: WorldState, resident_id: str, tick: int
) -> DeathResult:
    """Kill a living resident whose health is at the minimum.

    Atomically: ``alive`` becomes false; the active action is cancelled; a corpse
    ``corpse@<resident_id>`` appears at the current tile (it blocks nothing and persists);
    all inventory drops to that tile, fruit merging into ``ground_fruit@<x>,<y>`` and the
    canteen keeping its servings. Facts: ``resident_died``, ``corpse_created``, then
    ``item_dropped`` for fruit followed by the canteen (Interface Contract §3.2, §6.2).
    """
    new = state.model_copy(deep=True)
    resident = next((r for r in new.residents if r.id == resident_id), None)
    if resident is None:
        raise ValueError(f"unknown resident {resident_id!r}")
    if not resident.alive:
        raise ValueError(f"{resident_id} is already dead")
    if resident.health > config.needs.min_value:
        raise ValueError(f"{resident_id} has not reached minimum health")
    cid = corpse_id(resident_id)
    if any(c.id == cid for c in new.corpses):
        raise ValueError(f"{cid} already exists")

    position = resident.position
    resident.alive = False

    cancelled = next((a for a in new.active_actions if a.intent.actor_id == resident_id), None)
    new.active_actions = [a for a in new.active_actions if a.intent.actor_id != resident_id]

    new.corpses = sorted(
        [
            *new.corpses,
            CorpseState(id=cid, resident_id=resident_id, position=position, death_tick=tick),
        ],
        key=lambda c: c.id,
    )

    facts = [
        PendingFact(
            type="resident_died",
            actor_id=resident_id,
            target_id=None,
            payload=ResidentDiedPayload(
                resident_id=resident_id, position=position, cause="DEPRIVATION"
            ),
        ),
        PendingFact(
            type="corpse_created",
            actor_id=resident_id,
            target_id=cid,
            payload=CorpseCreatedPayload(corpse_id=cid, resident_id=resident_id, position=position),
        ),
    ]

    fruit = resident.fruit_count
    if fruit > 0:
        new.ground_fruit = add_ground_fruit(new.ground_fruit, position, fruit)
        resident.fruit_count = 0
        facts.append(
            PendingFact(
                type="item_dropped",
                actor_id=resident_id,
                target_id=ground_fruit_id(position),
                payload=ItemDroppedPayload(
                    resident_id=resident_id,
                    position=position,
                    item_type="fruit",
                    quantity=fruit,
                    canteen_id=None,
                    canteen_servings=None,
                ),
            )
        )

    canteen = new.unique_canteen
    if canteen.holder_id == resident_id:
        new.unique_canteen = UniqueCanteenState(
            id=canteen.id, holder_id=None, ground_position=position, servings=canteen.servings
        )
        facts.append(
            PendingFact(
                type="item_dropped",
                actor_id=resident_id,
                target_id=canteen.id,
                payload=ItemDroppedPayload(
                    resident_id=resident_id,
                    position=position,
                    item_type="canteen",
                    quantity=1,
                    canteen_id=canteen.id,
                    canteen_servings=canteen.servings,
                ),
            )
        )
    return DeathResult(new, facts, cancelled)
