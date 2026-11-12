"""Explicit profile loading, scalar boundaries and retained identity sources."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from living_island.agents.p3.prompts import RESIDENT_TEMPLATE
from living_island.agents.p3.types import (
    ContextProfile,
    IdentitySource,
    ProfileDocument,
    ResidentIdentity,
)
from living_island.memory.p3_types import canonical_bytes, canonical_sha256
from living_island.persistence.characters import load_profiles, resolve_identity

ROOT = Path(__file__).resolve().parents[3]


def profile(**updates):
    return {
        "profile_schema_version": "0.1",
        "profile_id": "explorer",
        "values": ["Observe before concluding."],
        **updates,
    }


def write_profile(path, data):
    path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    return path


def test_approved_profiles_and_exact_template_are_present():
    directory = ROOT / "content" / "characters"
    profiles = load_profiles(
        [directory / f"{name}.json" for name in ("explorer", "cautious", "cooperative")]
    )
    assert set(profiles) == {"explorer", "cautious", "cooperative"}
    assert profiles["explorer"].values == [
        "Seek new observations when immediate needs permit.",
        "Prefer plans that improve knowledge of sustainable resources.",
        "Treat unfamiliar places and heard claims as uncertain.",
    ]
    assert profiles["cautious"].values == [
        "Prefer dependable access to water and food.",
        "Avoid repeating a recently failed plan without new evidence.",
        "Keep commitments small enough to reassess after feedback.",
    ]
    assert profiles["cooperative"].values == [
        "Consider others' expressed needs alongside your own survival.",
        "Make clear requests and explicit refusals when necessary.",
        "Treat an agreement as a commitment to attempt, not proof of delivery.",
    ]
    assert (
        ROOT / "content" / "prompts" / "p3-v0.1" / "resident.txt"
    ).read_bytes() == RESIDENT_TEMPLATE


def test_resolved_source_hash_order_and_identity_are_exact():
    documents = {"explorer": ProfileDocument.model_validate(profile(values=["Second", "First"]))}
    identity, source = resolve_identity(
        actor_id="ella:custom",
        display_name=" Élla ",
        profile_id="explorer",
        initial_direction=" Look around. ",
        profiles=documents,
    )
    expected = {
        "actor_id": "ella:custom",
        "display_name": " Élla ",
        "profile": profile(values=["Second", "First"]),
        "initial_direction": " Look around. ",
    }
    assert source.model_dump(mode="json") == expected
    assert identity.source_sha256 == canonical_sha256(expected)
    assert identity.values == ["Second", "First"]
    assert ResidentIdentity.model_validate_json(canonical_bytes(identity)) == identity
    assert IdentitySource.model_validate_json(canonical_bytes(source)) == source
    documents["explorer"].values.append("Changed outside")
    assert identity.values == ["Second", "First"] and source.profile.values == ["Second", "First"]


def test_loader_uses_explicit_locator_not_profile_name(tmp_path):
    path = write_profile(tmp_path / "unrelated-name.json", profile())
    assert load_profiles([path])["explorer"].profile_id == "explorer"
    with pytest.raises(ValueError):
        load_profiles([path, tmp_path / "missing.json"])


def test_duplicate_and_mismatched_profiles_are_errors(tmp_path):
    a = write_profile(tmp_path / "a.json", profile())
    b = write_profile(tmp_path / "b.json", profile())
    with pytest.raises(ValueError, match="duplicate"):
        load_profiles([a, b])
    args = dict(
        actor_id="ella", display_name="Ella", profile_id="explorer", initial_direction="Explore"
    )
    with pytest.raises(ValueError, match="missing"):
        resolve_identity(**args, profiles={})
    with pytest.raises(ValueError, match="match"):
        resolve_identity(
            **args,
            profiles={"explorer": ProfileDocument.model_validate(profile(profile_id="wrong"))},
        )


@pytest.mark.parametrize(
    "data",
    [
        profile(profile_schema_version="0.2"),
        profile(extra="private memory"),
        profile(values=["same", "same"]),
        profile(values=[""]),
        profile(values=["a" * 161]),
        profile(values=[str(i) for i in range(9)]),
        profile(values=["\ud800"]),
        profile(values=[True]),
        profile(values=None),
    ],
)
def test_profile_closed_schema_and_bounds_fail_at_loading(tmp_path, data):
    path = write_profile(tmp_path / "profile.json", data)
    with pytest.raises(ValueError):
        load_profiles([path])


@pytest.mark.parametrize("values", [[], ["x" * 160], [str(i) for i in range(8)], ["🦉" * 160]])
def test_profile_exact_boundaries(values):
    assert ProfileDocument.model_validate(profile(values=values)).values == values


@pytest.mark.parametrize(
    "field,minimum,maximum", [("display_name", 1, 120), ("initial_direction", 1, 500)]
)
def test_identity_scalar_boundaries(field, minimum, maximum):
    args = dict(
        actor_id="ella",
        display_name="Ella",
        profile_id="explorer",
        initial_direction="Explore",
        profiles={"explorer": ProfileDocument.model_validate(profile())},
    )
    for size in (minimum, maximum):
        changed = {**args, field: "🦉" * size}
        identity, _ = resolve_identity(**changed)
        assert len(getattr(identity, field)) == size
    for invalid in ("", "x" * (maximum + 1), "\ud800"):
        with pytest.raises(ValueError):
            resolve_identity(**{**args, field: invalid})


def test_identity_source_forgery_is_rejected():
    identity, _ = resolve_identity(
        actor_id="ella",
        display_name="Ella",
        profile_id="explorer",
        initial_direction="Explore",
        profiles={"explorer": ProfileDocument.model_validate(profile())},
    )
    data = identity.model_dump(mode="json")
    data["values"] = ["Model rewrote identity"]
    with pytest.raises(ValidationError):
        ResidentIdentity.model_validate(data)
    with pytest.raises(ValidationError):
        identity.display_name = "Changed"


def test_loader_rejects_duplicate_json_fields_and_noninteger_or_nonobject_input(tmp_path):
    for raw in ('{"profile_id":"a","profile_id":"b"}', "[]", '{"x":1.5}'):
        path = tmp_path / "bad.json"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(ValueError):
            load_profiles([path])


def test_retained_production_context_profile_is_the_exact_frozen_row():
    raw = (ROOT / "content" / "prompts" / "p3-v0.1" / "context-profile.json").read_bytes()
    profile = ContextProfile.model_validate_json(raw)
    assert profile.model_dump(mode="json") == {
        "context_profile_schema_version": "0.1",
        "context_profile_id": "p3-context-v0",
        "retrieval_profile": "recent-relevant-v0",
        "projection_profile": "p3-context-v0",
    }
