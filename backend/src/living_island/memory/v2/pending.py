"""Failed periods owned by a single resident's consolidation coordinator."""

from collections.abc import Collection
from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class PendingPeriod[T]:
    owner_id: str
    period_id: str
    context: T


class PendingPeriods[T]:
    """Store the input builder's frozen context type without importing the decision loop."""

    def __init__(self, owner_id: str) -> None:
        self.owner_id = owner_id
        self._periods: dict[str, PendingPeriod[T]] = {}

    def append(self, period: PendingPeriod[T]) -> PendingPeriod[T] | None:
        """Return the oldest evicted period to the coordinator for its journal."""
        if period.owner_id != self.owner_id:
            raise ValueError("pending period belongs to another resident")
        if period.period_id in self._periods:
            raise ValueError(f"period already pending: {period.period_id}")
        self._periods[period.period_id] = deepcopy(period)
        if len(self._periods) > 2:
            return self._periods.pop(next(iter(self._periods)))
        return None

    def read(self) -> tuple[PendingPeriod[T], ...]:
        return deepcopy(tuple(self._periods.values()))

    def consume(self, sent_period_ids: Collection[str]) -> tuple[PendingPeriod[T], ...]:
        """After commit, consume only periods included in the actual change-set request."""
        included = [key for key in self._periods if key in sent_period_ids]
        return tuple(self._periods.pop(key) for key in included)
