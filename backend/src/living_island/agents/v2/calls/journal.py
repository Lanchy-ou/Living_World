"""Write-only audit capability. The coordinator supplies the durable primitives."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from .contracts import digest, json_bytes


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


@dataclass(frozen=True)
class Journal:
    """Both writes must be durable on return. keep is immutable/idempotent,
    create is exclusive even for identical bytes. Keys are flat within one run.
    The existing persistence store_once and atomic_create satisfy these contracts.
    """

    keep: Callable[[str, bytes], None]
    create: Callable[[str, bytes], None]

    def blob(self, data: bytes) -> str:
        address = digest(data)
        self.keep(address, data)
        return address

    @staticmethod
    def cursor(call_id: str, slot: str) -> str:
        return f"{digest(call_id.encode())}.{slot}.json"

    def fact(self, call_id: str, slot: str, fact: Fact, *, exclusive: bool = False) -> str:
        cursor = self.cursor(call_id, slot)
        publish = self.create if exclusive else self.keep
        publish(cursor, json_bytes(fact.model_dump(mode="json", by_alias=True)))
        return cursor
