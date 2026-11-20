"""Phase hooks owned by P3.5-EN-03."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import ActiveAction
    from .tick import TickContext


def contribute(ctx: TickContext, action: ActiveAction) -> None:
    """Advance this action's open process when its work is eligible."""


def world_rules(ctx: TickContext) -> None:
    """Run phase 4a in rule ID then subject ID order."""


def finish_processes(ctx: TickContext) -> None:
    """Run phase 4b over the open-process snapshot, in process ID order."""
