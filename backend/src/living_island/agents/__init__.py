"""Resident interface and implementations (``rule_based/``, ``llm/``).

Responsibility:
    Turn a ``Perception`` into ``ActionPlan`` proposals: planning, task execution,
    prompt building and model adapters. Rule-based and LLM residents share one interface;
    the rule-based one is also the fallback when the LLM fails or exceeds budget.

Must NOT:
    Modify world state, or see full world state. Import ``living_island.world`` except
    via ``living_island.world.protocol``. Call another resident's model or read another
    resident's memory.
"""
