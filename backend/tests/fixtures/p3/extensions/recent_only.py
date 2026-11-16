"""Tracked VF-20 selector implementation for source-pinned fake trials."""

from __future__ import annotations

from living_island.memory.p3_types import (
    MAX_RECALLED_RECORDS,
    ExperienceState,
    RetrievalQuery,
    RetrievalResult,
)


class RecentOnlySelector:
    retrieval_profile = "recent-only-fixture-v0"

    def __init__(self, implementation_sha256: str) -> None:
        self.implementation_sha256 = implementation_sha256

    def retrieve(self, state: ExperienceState, query: RetrievalQuery) -> RetrievalResult:
        """Rank the complete retained set by descending capture sequence."""
        del query
        ordered = sorted(state.records, key=lambda record: -record.sequence)
        return RetrievalResult(
            ranked_experience_ids=[record.experience_id for record in ordered],
            selected_records=ordered[:MAX_RECALLED_RECORDS],
        )
