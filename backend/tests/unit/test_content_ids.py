"""Cross-domain ID uniqueness and reserved prefixes (CR-002(b), World Rules §1.1)."""

from __future__ import annotations

import copy
import tomllib
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from world_builders import WORLDS

from living_island.world.content import WorldContent, build_world_content


def build(mutate: Callable[[dict[str, Any]], None]) -> WorldContent:
    with (WORLDS / "default.toml").open("rb") as f:
        data = copy.deepcopy(tomllib.load(f))
    mutate(data)
    return build_world_content(data, (WORLDS / "default-island.map").read_bytes())


def test_default_content_passes() -> None:
    build(lambda d: None)


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("tree vs resident", lambda d: d["world"]["fruit_trees"][0].update(id="ryan")),
        ("cue vs canteen", lambda d: d["world"]["cues"][0].update(id="canteen_01")),
        ("canteen vs resident", lambda d: d["canteen"].update(unique_item_id="ella")),
        ("cue vs tree", lambda d: d["world"]["cues"][0].update(id="fruit_01")),
        ("canteen vs tree", lambda d: d["canteen"].update(unique_item_id="fruit_02")),
    ],
)
def test_ids_must_be_unique_across_domains(
    name: str, mutate: Callable[[dict[str, Any]], None]
) -> None:
    with pytest.raises(ValidationError, match="unique across"):
        build(mutate)


def rename_resident(data: dict[str, Any], old: str, new: str) -> None:
    for r in data["residents"]:
        if r["id"] == old:
            r["id"] = new
    if data["canteen"]["initial_owner_id"] == old:
        data["canteen"]["initial_owner_id"] = new


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("resident", lambda d: rename_resident(d, "mia", "corpse@mia")),
        ("tree", lambda d: d["world"]["fruit_trees"][0].update(id="ground_fruit@1,1")),
        ("cue", lambda d: d["world"]["cues"][0].update(id="corpse@moss")),
        ("canteen", lambda d: d["canteen"].update(unique_item_id="ground_fruit@canteen")),
    ],
)
def test_reserved_derived_id_prefixes_are_rejected(
    name: str, mutate: Callable[[dict[str, Any]], None]
) -> None:
    with pytest.raises(ValidationError, match="reserved"):
        build(mutate)
