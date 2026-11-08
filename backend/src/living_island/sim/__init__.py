"""Simulation coordinator.

Responsibility:
    Run the tick loop, decide when residents must decide (decision triggers), enforce the
    LLM call budget and fallback, and connect the world, residents, events and persistence.

Must NOT:
    Contain world rules (those live in ``world``) or resident decision logic (``agents``).
    Advance a tick while a synchronous LLM decision is outstanding.
"""
