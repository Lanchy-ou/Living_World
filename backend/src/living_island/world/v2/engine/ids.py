"""World-owned entity ID allocation and completion shuffle."""

from dataclasses import dataclass, field
from hashlib import sha256

from ..rules.schema import canonical_json_bytes

MAX_EXACT = 1 << 53
DOMAIN = 1 << 32
MASK = DOMAIN - 1


def entity_candidate(seed: int, n: int, k: int) -> str:
    content = canonical_json_bytes({"seed": seed, "stream": "entity", "n": n, "k": k})
    return "e:" + sha256(content).hexdigest()[:16]


@dataclass
class EntityCounter:
    n: int = 0
    issued: set[str] = field(default_factory=set)

    def allocate(self, seed: int) -> str:
        if self.n + 1 >= MAX_EXACT:
            raise OverflowError("entity creation counter exhausted")
        for k in range(MAX_EXACT):
            candidate = entity_candidate(seed, self.n, k)
            if candidate not in self.issued:
                self.issued.add(candidate)
                self.n += 1
                return candidate
        raise OverflowError("entity collision retry counter exhausted")


def corpse_id(resident_id: str) -> str:
    return f"corpse@{resident_id}"


def shuffle[T](entries: list[T], state: int) -> int:
    """Use the v1 xorshift32 stream and rejection-sampled Fisher–Yates."""
    for index in range(len(entries) - 1, 0, -1):
        size = index + 1
        limit = DOMAIN - DOMAIN % size
        while True:
            state ^= (state << 13) & MASK
            state ^= state >> 17
            state ^= (state << 5) & MASK
            if state < limit:
                break
        swap = state % size
        entries[index], entries[swap] = entries[swap], entries[index]
    return state
