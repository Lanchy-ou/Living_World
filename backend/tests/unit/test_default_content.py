import tomllib
from pathlib import Path
from typing import Any

WORLDS_DIR = Path(__file__).resolve().parents[3] / "content" / "worlds"
IMPASSABLE = set("~^S")


def _load_config() -> dict[str, Any]:
    with (WORLDS_DIR / "default.toml").open("rb") as f:
        return tomllib.load(f)


def _load_rows(config: dict[str, Any]) -> list[str]:
    raw = (WORLDS_DIR / config["map"]["layout_file"]).read_bytes()
    assert b"\r" not in raw, "map must use LF line endings"
    text = raw.decode("utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    return text.split("\n")


def _positions(rows: list[str], symbol: str) -> list[tuple[int, int]]:
    return [(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == symbol]


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_float(v) for v in value)
    return False


def test_toml_parses_and_has_no_floats() -> None:
    assert not _contains_float(_load_config())


def test_map_dimensions_and_line_endings() -> None:
    config = _load_config()
    rows = _load_rows(config)
    assert len(rows) == config["map"]["height"]
    assert all(len(row) == config["map"]["width"] for row in rows)


def test_single_markers_at_configured_coordinates() -> None:
    config = _load_config()
    rows = _load_rows(config)
    moss = [c for c in config["world"]["cues"] if c["kind"] == "damp_moss"]
    assert len(moss) == 1
    expected = {
        "S": tuple(config["world"]["spring"]),
        "C": tuple(config["world"]["initial_cave"]),
        "M": tuple(moss[0]["position"]),
    }
    for symbol, position in expected.items():
        assert _positions(rows, symbol) == [position], symbol


def test_fruit_tiles_match_configured_trees() -> None:
    config = _load_config()
    rows = _load_rows(config)
    configured = {tuple(tree["position"]) for tree in config["world"]["fruit_trees"]}
    assert len(configured) == len(config["world"]["fruit_trees"])
    assert set(_positions(rows, "F")) == configured


def test_residents_start_on_passable_tiles() -> None:
    config = _load_config()
    rows = _load_rows(config)
    assert config["residents"]
    for resident in config["residents"]:
        x, y = resident["position"]
        assert rows[y][x] not in IMPASSABLE, resident["id"]
