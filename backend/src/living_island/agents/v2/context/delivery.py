"""The resident's filtered packet and sim's joins to its own adopted choices."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from living_island.world.v2.protocol import BoundaryDelivery, Utterance, UtteranceFeedback


@dataclass(frozen=True)
class FeedbackSource:
    """Original packet slot and the submitted verb (or kernel action)."""

    action: str
    position: int


@dataclass(frozen=True)
class OwnSpeech:
    feedback: UtteranceFeedback
    utterance: Utterance


@dataclass(frozen=True)
class FilteredDelivery:
    """Sim removes fallback-owned results before constructing this projection.

    Feedback IDs join to the retained result's original position even if a
    preceding result was dropped. Reports normally retain their original
    order and positions, including the neutral action-ended signal.
    """

    packet: BoundaryDelivery
    feedback_sources: Mapping[str, FeedbackSource] = field(default_factory=dict)
    own_speech: OwnSpeech | None = None
    report_positions: tuple[int, ...] | None = None

    def report_path(self, index: int) -> str:
        original = index if self.report_positions is None else self.report_positions[index]
        return f"reports[{original}]"
