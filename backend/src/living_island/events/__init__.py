"""Authoritative event log handling and the read-only narrative projection.

Responsibility:
    Define and append objective events (tick, sequence number, failure code, LLM call id)
    and project them into timelines and stories (``narrative``).

Must NOT:
    Let the narrative invent facts that are not in the event log. Let narrative code
    import ``living_island.sim`` or ``living_island.persistence`` (keep it read-only).
"""
