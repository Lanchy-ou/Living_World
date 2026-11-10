"""Rule-based residents: simple utility rules, control group and LLM fallback.

Must NOT: modify world state or import ``living_island.world`` except via its protocol.
"""

from .stub import RuleBasedPolicy

__all__ = ["RuleBasedPolicy"]
