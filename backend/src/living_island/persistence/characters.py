"""Explicit P3 profile-file loading; legacy startup does not call this module."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from living_island.agents.p3.types import IdentitySource, ProfileDocument, ResidentIdentity
from living_island.memory.p3_types import canonical_sha256

from ._codec import PersistenceError, decode_model, read_bytes


def load_profiles(explicit_paths: Sequence[Path]) -> dict[str, ProfileDocument]:
    """Load only supplied locators; reject duplicate IDs rather than choosing one."""
    result: dict[str, ProfileDocument] = {}
    for path in explicit_paths:
        profile = decode_model(
            read_bytes(path),
            ProfileDocument,
            path,
            canonical=False,
            version_field="profile_schema_version",
        )
        if profile.profile_id in result:
            raise PersistenceError(path, "profile_id", "duplicate profile identity")
        result[profile.profile_id] = profile.model_copy(deep=True)
    return result


def resolve_identity(
    *,
    actor_id: str,
    display_name: str,
    profile_id: str,
    initial_direction: str,
    profiles: Mapping[str, ProfileDocument],
) -> tuple[ResidentIdentity, IdentitySource]:
    """Resolve and retain one resident's exact configured source, without path inference."""
    if profile_id not in profiles:
        raise ValueError(f"missing profile {profile_id!r}")
    profile = ProfileDocument.model_validate(profiles[profile_id].model_dump(mode="json"))
    if profile.profile_id != profile_id:
        raise ValueError("configured profile ID does not match the supplied document")
    source = IdentitySource(
        actor_id=actor_id,
        display_name=display_name,
        profile=profile.model_copy(deep=True),
        initial_direction=initial_direction,
    )
    identity = ResidentIdentity(
        identity_schema_version="0.1",
        actor_id=source.actor_id,
        display_name=source.display_name,
        profile_id=profile.profile_id,
        values=list(profile.values),
        initial_direction=source.initial_direction,
        source_sha256=canonical_sha256(source),
    )
    return identity, source
