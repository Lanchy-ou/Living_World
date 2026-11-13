"""Versioned Unicode schema compatibility without provider calls or old-pin rewrites."""

from __future__ import annotations

import re
from typing import Annotated

import pytest
from pydantic import StringConstraints, TypeAdapter, ValidationError
from test_cognition import assembly, config, request

from living_island.agents.p3.prompts import (
    RESIDENT_TEMPLATE,
    build_model_action_contract,
    render_provider_request,
)
from living_island.agents.p3.types import ModelActionContract, P3PolicyConfig, scalar_text
from living_island.memory.p3_types import canonical_sha256

OLD_PATTERN = r"^[^\uD800-\uDFFF]*$"
NEW_PATTERN = r"^(?:[\u0000-\uD7FF\uE000-\uFFFF]|[^\u0000-\uFFFF])*$"
OLD_CONTRACT_HASH = "d0afdce30059d5b1f24dfd418a34a489d5ff25c3e070c26c280e67cd6fc06c98"


def text_constraints():
    def walk(value):
        if isinstance(value, dict):
            if "pattern" in value:
                yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    return list(walk(build_model_action_contract().proposal_schema))


def test_new_contract_changes_only_version_and_authored_text_pattern():
    contract = build_model_action_contract()
    assert contract.action_schema_version == "p3-actions/0.2"
    historical = contract.model_dump(mode="json")
    historical["action_schema_version"] = "p3-actions/0.1"

    def restore(value):
        if isinstance(value, dict):
            if "pattern" in value:
                assert value["pattern"] == NEW_PATTERN
                value["pattern"] = OLD_PATTERN
            for child in value.values():
                restore(child)
        elif isinstance(value, list):
            for child in value:
                restore(child)

    restore(historical)
    assert canonical_sha256(historical) == OLD_CONTRACT_HASH
    assert canonical_sha256(contract) != OLD_CONTRACT_HASH
    assert NEW_PATTERN.isascii()
    assert {(c["minLength"], c["maxLength"]) for c in text_constraints()} == {
        (0, 240),
        (0, 500),
        (1, 240),
    }


def test_pattern_exhaustively_preserves_unicode_scalar_membership():
    old, new = re.compile(OLD_PATTERN), re.compile(NEW_PATTERN)
    # Rust compilation is an independent engine check, not hosted API validation.
    rust = TypeAdapter(Annotated[str, StringConstraints(pattern=NEW_PATTERN)])
    scalar_chunks = []
    for point in range(0x110000):
        text = chr(point)
        valid = not 0xD800 <= point <= 0xDFFF
        assert bool(old.fullmatch(text)) == bool(new.fullmatch(text)) == valid
        if valid:
            scalar_chunks.append(text)
            if len(scalar_chunks) == 4096:
                joined = "".join(scalar_chunks)
                assert rust.validate_python(joined) == joined
                scalar_chunks.clear()
        else:
            with pytest.raises(ValidationError):
                rust.validate_python(text)
    if scalar_chunks:
        joined = "".join(scalar_chunks)
        assert rust.validate_python(joined) == joined


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n",
        "a\n",
        "\r\n",
        "\x00\t",
        "中文🦉",
        "a\U0010ffff\n",
        "\ud800",
        "\udfff",
        "\ud800\udc00",
        "a\ud800\n",
        "\udfff\na",
        "a\n\ud800",
    ],
)
def test_entire_string_matches_local_scalar_and_length_validation(text):
    for constraint in text_constraints():
        lower, upper = constraint["minLength"], constraint["maxLength"]
        rust = TypeAdapter(
            Annotated[
                str,
                StringConstraints(
                    pattern=constraint["pattern"], min_length=lower, max_length=upper
                ),
            ]
        )
        valid = lower <= len(text) <= upper and not any(0xD800 <= ord(c) <= 0xDFFF for c in text)
        assert bool(re.search(OLD_PATTERN, text)) == bool(re.search(NEW_PATTERN, text))
        if valid:
            assert scalar_text(text, lower, upper) == rust.validate_python(text) == text
        else:
            with pytest.raises(ValueError):
                scalar_text(text, lower, upper)
            with pytest.raises(ValidationError):
                rust.validate_python(text)


@pytest.mark.parametrize("unit", ["a", "🦉", "\n", "\x00"])
def test_existing_text_length_limits_count_scalars(unit):
    for constraint in text_constraints():
        lower, upper = constraint["minLength"], constraint["maxLength"]
        rust = TypeAdapter(
            Annotated[
                str,
                StringConstraints(
                    pattern=constraint["pattern"], min_length=lower, max_length=upper
                ),
            ]
        )
        for length in {0, lower, upper, upper + 1}:
            text = unit * length
            if lower <= length <= upper:
                assert rust.validate_python(text) == scalar_text(text, lower, upper)
            else:
                with pytest.raises(ValidationError):
                    rust.validate_python(text)


def test_old_contract_and_policy_versions_are_not_silently_reinterpreted():
    old_contract = build_model_action_contract().model_dump(mode="json")
    old_contract["action_schema_version"] = "p3-actions/0.1"
    with pytest.raises(ValidationError):
        ModelActionContract.model_validate(old_contract)
    req = request()
    current = config(req)
    old_policy = current.model_dump(mode="json")
    old_policy.update(
        action_schema_version="p3-actions/0.1", action_schema_sha256=OLD_CONTRACT_HASH
    )
    with pytest.raises(ValidationError):
        P3PolicyConfig.model_validate(old_policy)
    with pytest.raises(ValueError):
        render_provider_request(
            assembly(req),
            req,
            current.model_copy(
                update={
                    "action_schema_version": "p3-actions/0.1",
                    "action_schema_sha256": OLD_CONTRACT_HASH,
                }
            ),
            RESIDENT_TEMPLATE,
        )


def test_new_version_and_hash_bind_the_exact_shared_schema():
    req = request()
    cfg = config(req)
    contract = build_model_action_contract()
    rendered = render_provider_request(assembly(req), req, cfg, RESIDENT_TEMPLATE)
    assert cfg.action_schema_version == contract.action_schema_version == "p3-actions/0.2"
    assert cfg.action_schema_sha256 == canonical_sha256(contract)
    assert rendered.response_schema == contract.proposal_schema
