"""Plan change-set evictions on a candidate store without publishing any writes."""

from collections.abc import Iterable, Set
from dataclasses import dataclass
from operator import attrgetter

from living_island.memory.v2.kinds import KindRegistry
from living_island.memory.v2.projections import ProjectedRevision, ResidentView
from living_island.memory.v2.records import MemoryRecord


@dataclass(frozen=True)
class CapacityPlan:
    victims: tuple[str, ...]
    fits: bool


def eligible_skills(view: ResidentView) -> tuple[ProjectedRevision, ...]:
    """Live skill revisions that can supply a recipe or receive new evidence."""
    return tuple(
        entry
        for entry in view.live()
        if entry.record.kind == "skill" and "refuted" not in entry.flags
    )


def _belief_priority(record: MemoryRecord) -> tuple[int, int, str]:
    # All actual use ticks are nonnegative, including a use at tick zero.
    used = -1 if record.last_used_tick is None else record.last_used_tick
    return record.confidence, used, record.id


def plan_capacity(
    kind: str,
    records: Iterable[MemoryRecord],
    registry: KindRegistry,
    protected: Set[str],
    *,
    added_live: int = 0,
) -> CapacityPlan:
    """Count a pending producer even if its fields are invalid and it has no record yet."""
    policy = registry[kind]
    if policy.operations.isdisjoint({"add", "merge", "supersede"}):
        return CapacityPlan((), True)

    live: list[MemoryRecord] = []
    history: list[MemoryRecord] = []
    for record in records:
        if record.kind == kind:
            (history if record.history else live).append(record)
    live_excess = (
        max(0, len(live) + added_live - policy.live_capacity)
        if policy.live_capacity is not None
        else 0
    )
    history_excess = max(0, len(history) - policy.history_capacity)
    oldest_first = attrgetter("created_tick", "id")

    victims: list[MemoryRecord] = []
    if live_excess:
        eligible = (record for record in live if record.id not in protected)
        if kind == "belief":
            victims = sorted(eligible, key=_belief_priority)[:live_excess]
        elif kind == "skill":
            refuted = (record for record in eligible if "refuted" in record.content.flags())
            victims = sorted(refuted, key=oldest_first)[:live_excess]
    if history_excess:
        eligible = (record for record in history if record.id not in protected)
        victims.extend(sorted(eligible, key=oldest_first)[:history_excess])

    ids = tuple(record.id for record in victims)
    return CapacityPlan(ids, len(ids) == live_excess + history_excess)
