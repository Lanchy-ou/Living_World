"""Rule-based residents: the deterministic rule-based-v0 policy (control group and LLM fallback).

Must NOT: modify world state or import ``living_island.world`` except via its protocol.
"""

from .policy import RuleBasedPolicy

__all__ = ["RuleBasedPolicy"]
