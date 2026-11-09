"""Content loader: default content loads; broken content is rejected (World Rules §1.1-§1.2)."""

import copy
import tomllib
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from living_island.persistence.content import load_world_content
from living_island.world.content import WorldContent, build_world_content

WORLDS = Path(__file__).resolve().parents[3] / "content" / "worlds"
TOML = WORLDS / "default.toml"


def _config() -> dict[str, Any]:
    with TOML.open("rb") as f:
        return tomllib.load(f)


def _map() -> bytes:
    return (WORLDS / "default-island.map").read_bytes()


def _rows() -> list[str]:
    return _map().decode("utf-8")[:-1].split("\n")


def _encode(rows: list[str]) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


def _set(rows: list[str], x: int, y: int, ch: str) -> list[str]:
    rows = list(rows)
    rows[y] = rows[y][:x] + ch + rows[y][x + 1 :]
    return rows


def _rejects(config: dict[str, Any] | None = None, raw: bytes | None = None) -> None:
    with pytest.raises((ValueError, ValidationError)):
        build_world_content(config if config is not None else _config(), raw or _map())


def test_default_content_loads() -> None:
    content = load_world_content(TOML)
    assert isinstance(content, WorldContent)
    assert len(content.map_rows) == 64
    assert len(content.config_hash) == 64 and len(content.map_hash) == 64


def test_same_content_identical_hashes() -> None:
    a, b = load_world_content(TOML), load_world_content(TOML)
    assert (a.config_hash, a.map_hash) == (b.config_hash, b.map_hash)
    changed = _config()
    changed["meta"]["seed"] = 7
    assert build_world_content(changed, _map()).config_hash != a.config_hash


def test_wrong_hash_rejected() -> None:
    content = load_world_content(TOML)
    data = content.model_dump()
    data["map_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        WorldContent.model_validate(data)


# (a) row count / width
def test_wrong_row_count() -> None:
    _rejects(raw=_encode(_rows()[:-1]))


def test_wrong_row_width() -> None:
    rows = _rows()
    rows[5] = rows[5] + "~"
    _rejects(raw=_encode(rows))


# (b) characters
def test_disallowed_character() -> None:
    _rejects(raw=_encode(_set(_rows(), 0, 0, "X")))


def test_tab() -> None:
    _rejects(raw=_encode(_set(_rows(), 1, 1, "\t")))


def test_trailing_space() -> None:
    rows = _rows()
    rows[3] = rows[3][:-1] + " "
    _rejects(raw=_encode(rows))


# (c) encoding
def test_crlf() -> None:
    _rejects(raw=_map().replace(b"\n", b"\r\n"))


def test_bom() -> None:
    _rejects(raw=b"\xef\xbb\xbf" + _map())


def test_missing_final_lf() -> None:
    _rejects(raw=_map()[:-1])


# (d) exactly one S / C / M
@pytest.mark.parametrize("symbol", ["S", "C", "M"])
def test_duplicate_marker(symbol: str) -> None:
    _rejects(raw=_encode(_set(_rows(), 20, 20, symbol)))


@pytest.mark.parametrize("pos", [(38, 30), (13, 32), (15, 32)])
def test_missing_marker(pos: tuple[int, int]) -> None:
    _rejects(raw=_encode(_set(_rows(), pos[0], pos[1], ",")))


# (e) F set and coordinate mismatches
def test_extra_fruit_tile() -> None:
    _rejects(raw=_encode(_set(_rows(), 20, 20, "F")))


def test_fruit_tree_config_not_on_f() -> None:
    config = _config()
    config["world"]["fruit_trees"][0]["position"] = [20, 20]
    _rejects(config=config)


def test_missing_fruit_tree_config() -> None:
    config = _config()
    del config["world"]["fruit_trees"][0]
    _rejects(config=config)


@pytest.mark.parametrize(
    ("path", "value"),
    [(("world", "spring"), [37, 30]), (("world", "initial_cave"), [12, 32])],
)
def test_spring_or_cave_mismatch(path: tuple[str, str], value: list[int]) -> None:
    config = _config()
    config[path[0]][path[1]] = value
    _rejects(config=config)


def test_cue_mismatch() -> None:
    config = _config()
    config["world"]["cues"][0]["position"] = [16, 32]
    _rejects(config=config)


# (f) spawns and border
def test_spawn_on_impassable() -> None:
    config = _config()
    config["residents"][0]["position"] = [0, 0]
    _rejects(config=config)


def test_non_ocean_border() -> None:
    _rejects(raw=_encode(_set(_rows(), 0, 10, ".")))


# configuration domains (World Rules §1.1)
@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("meta", "seed", 0),
        ("meta", "seed", 2**32),
        ("map", "width", 0),
        ("map", "step_cost_woods", 9),
        ("time", "tick_minutes", 7),
        ("time", "start_hour", 24),
        ("time", "day_end_hour", 6),
        ("needs", "min_value", 1),
        ("needs", "min_value", False),
        ("needs", "min_value", 0.0),
        ("needs", "initial_health", 10001),
        ("needs", "satiety_decay_per_tick", -1),
        ("fruit", "initial_stock_per_tree", 6),
        ("canteen", "initial_servings", 3),
        ("canteen", "initial_owner_id", "nobody"),
        ("actions", "sleep_ticks", 0),
        ("perception", "need_band_cutoffs", [2000, 2000, 6000, 8000]),
        ("perception", "day_radius_tiles", -1),
        ("agents", "max_plan_actions", 0),
        ("inventory", "slot_capacity", 1.5),
        ("needs", "max_value", 10000.0),
        ("map", "width", True),
        ("map", "unknown_key", 1),
    ],
)
def test_bad_domain(section: str, key: str, value: object) -> None:
    config = copy.deepcopy(_config())
    config[section][key] = value
    _rejects(config=config)


def test_phase_offset_out_of_range() -> None:
    config = _config()
    config["world"]["fruit_trees"][0]["regrow_phase_offset_ticks"] = 144
    _rejects(config=config)


def test_duplicate_resident_id() -> None:
    config = _config()
    config["residents"][1]["id"] = "ella"
    _rejects(config=config)


def test_unknown_section() -> None:
    config = _config()
    config["extra"] = {}
    _rejects(config=config)


def test_bool_and_float_min_value_rejected_from_toml(tmp_path: Path) -> None:
    text = TOML.read_text(encoding="utf-8")
    assert "min_value = 0" in text
    (tmp_path / "default-island.map").write_bytes(_map())
    for literal in ("false", "0.0"):
        path = tmp_path / f"min-{literal}.toml"
        path.write_text(text.replace("min_value = 0", f"min_value = {literal}", 1), "utf-8")
        with pytest.raises(ValidationError):
            load_world_content(path)


def test_parent_relative_map_path_allowed(tmp_path: Path) -> None:
    (tmp_path / "default-island.map").write_bytes(_map())
    sub = tmp_path / "worlds"
    sub.mkdir()
    text = TOML.read_text(encoding="utf-8")
    assert 'layout_file = "default-island.map"' in text
    text = text.replace(
        'layout_file = "default-island.map"', 'layout_file = "../default-island.map"'
    )
    (sub / "w.toml").write_text(text, "utf-8")
    assert load_world_content(sub / "w.toml").map_hash == load_world_content(TOML).map_hash


def test_shared_spawn_tile_allowed() -> None:
    config = _config()
    config["residents"][1]["position"] = list(config["residents"][0]["position"])
    build_world_content(config, _map())
