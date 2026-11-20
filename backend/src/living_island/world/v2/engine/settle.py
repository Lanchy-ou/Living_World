"""Phase hooks owned by P3.5-EN-02."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import ActiveAction, Part
    from .tick import TickContext


def start_act(ctx: TickContext, action: ActiveAction, groups: tuple[tuple[Part, ...], ...]) -> None:
    """Choose a rule, reserve bound parts and capture the start outcome."""


def record_act_started(ctx: TickContext, action: ActiveAction) -> None:
    """Emit objective item bindings immediately after action_started."""


def progress_act(ctx: TickContext, action: ActiveAction) -> None:
    """Apply a running rule's per-tick effects and record witnesses."""


def complete_act(ctx: TickContext, action: ActiveAction) -> None:
    """Settle the fixed or revalidated rule and record its result."""


def interrupt(ctx: TickContext, action: ActiveAction) -> None:
    """Apply the chosen rule's interruption policy and release reservations."""
