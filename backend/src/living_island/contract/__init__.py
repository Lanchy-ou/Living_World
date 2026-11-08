"""Pydantic models shared with the frontend (snapshots, events, panels, commands).

Responsibility:
    Single definition of frontend-facing data. ``scripts/gen_types.py`` exports these models
    to JSON Schema and then to TypeScript.

Must NOT:
    Contain game logic. Be edited without regenerating
    ``frontend/src/api/generated/``.
"""

from living_island.contract.models import SnapshotMeta

__all__ = ["SnapshotMeta"]
