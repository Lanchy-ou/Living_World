"""Contract models (placeholder)."""

from pydantic import BaseModel, ConfigDict


class SnapshotMeta(BaseModel):
    """Header of a world snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    tick: int
