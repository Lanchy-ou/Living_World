"""Explicit, hash-pinned schema 0.2 character profiles and run-start personality."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal, Self, get_args

from pydantic import Field, field_validator

from living_island.memory.v2.records import (
    Innate,
    MemoryRecord,
    Model,
    Personality,
    Rating,
    Trait,
    TraitId,
)
from living_island.memory.v2.store import MemoryStore, StoreWrite


class TraitValues(Model):
    curiosity: Rating
    caution: Rating
    sociability: Rating
    trustfulness: Rating
    diligence: Rating

    def personality(self) -> Personality:
        traits = []
        for name in get_args(TraitId):
            base = getattr(self, name)
            traits.append(
                Trait(
                    trait_id=name,
                    base=base,
                    value=base,
                    min=max(0, base - 1),
                    max=min(4, base + 1),
                    changes=[],
                )
            )
        return Personality(traits=traits)


class Profile(Model):
    profile_schema_version: Literal["0.2"]
    profile_id: str
    values: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=160)]], Field(max_length=8)
    ]
    traits: TraitValues

    @field_validator("values")
    @classmethod
    def distinct_values(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("profile values must be unique")
        return values


@dataclass(frozen=True)
class SelectedProfile:
    document: Profile
    sha256: str

    @classmethod
    def load(cls, path: Path, *, expected_sha256: str | None = None) -> Self:
        data = path.read_bytes()
        fingerprint = sha256(data).hexdigest()
        if expected_sha256 is not None and fingerprint != expected_sha256:
            raise ValueError("profile file differs from pinned SHA-256")
        return cls(Profile.model_validate_json(data), fingerprint)

    def initialize(self, store: MemoryStore) -> StoreWrite:
        """Seed one explicitly selected resident at the start of a run."""
        base = store.snapshot
        record = MemoryRecord(
            id=base.next_id(),
            owner_id=base.owner_id,
            kind="personality",
            created_tick=0,
            updated_tick=0,
            about_tick=None,
            sources=[Innate()],
            confidence=4,
            speech_derived=False,
            last_used_tick=None,
            use_count=0,
            supersedes=None,
            superseded_by=None,
            needs_review=False,
            gist="My personality",
            text=None,
            content=self.document.traits.personality(),
        )
        return store.apply(0, "mechanical", [record])
