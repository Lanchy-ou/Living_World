"""Storage: JSON snapshots, JSONL events, LLM call recording and replay.

Responsibility:
    Write and read snapshots at tick boundaries, append the event log, and record and
    replay LLM calls so a run can be reproduced without new model calls.

Must NOT:
    Use a database in v0.1, or contain world rules or resident logic.
"""
