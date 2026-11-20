"""Phase hooks owned by P3.5-EN-06."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tick import SpeechAttempt, TickContext


def check_start(ctx: TickContext, attempt: SpeechAttempt) -> None:
    """Check an utterance before its actor starts or progresses."""


def settle_utterance(ctx: TickContext, attempt: SpeechAttempt) -> None:
    """Apply the second check and project accepted speech in settlement order."""
