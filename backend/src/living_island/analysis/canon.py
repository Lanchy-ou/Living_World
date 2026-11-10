"""Canonical JSON bytes and digests over parsed models (no file IO).

The bytes match the persistence encoder (sorted keys, no whitespace, UTF-8), so a digest here
equals the digest of the canonical file the run wrote. Analysis may not import persistence or
world internals (P2 experiments §7), so the few lines are repeated instead of imported.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from pydantic import BaseModel


def canonical_bytes_of_data(value: Any) -> bytes:
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def canonical_bytes(model: BaseModel) -> bytes:
    """Canonical UTF-8 JSON of a parsed model."""
    return canonical_bytes_of_data(model.model_dump(mode="json", warnings="error"))


def sha256_hex(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def canonical_sha256(model: BaseModel) -> str:
    return sha256_hex(canonical_bytes(model))
