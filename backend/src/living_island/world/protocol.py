"""Placeholder types forming the boundary between the world and its residents.

Agents and memory may import from ``living_island.world`` only through this module.
This module must stay free of imports from the rest of ``living_island.world``.
"""


class Perception:
    """What a resident perceives at a decision point; never the full world state."""


class ActionPlan:
    """A resident's proposed sequence of action intents (placeholder)."""


class ActionIntent:
    """A resident's proposal: action type, target, parameters, optional reason, plan id."""


class ActionResult:
    """The world's verdict on an intent: success or failure code, changes, feedback."""
