"""Read world content files, then validate them through ``living_island.world.content``.

No rule implementation lives here (implementation plan §2.1).
"""

from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath, PureWindowsPath

from living_island.world.content import (
    EffectiveConfig,
    WorldContent,
    build_world_content,
    check_map,
    config_hash,
    map_bytes_from_rows,
    map_hash,
    parse_map_bytes,
)

from ._codec import (
    PersistenceError,
    decode_model,
    encode,
    read_bytes,
    require_version,
    verify_identity,
)
from ._files import atomic_create

CONFIG_FILENAME = "config.json"
MAP_FILENAME = "map.txt"


def load_world_content(config_path: Path) -> WorldContent:
    """Load a world TOML and its ``map.layout_file`` (resolved next to the TOML)."""
    with config_path.open("rb") as f:
        config_data = tomllib.load(f)
    layout = config_data.get("map", {}).get("layout_file")
    if not isinstance(layout, str):
        raise ValueError("map.layout_file must be a string")
    # Plan §2.1: a relative map reference. Reject every anchor on any platform: POSIX
    # absolute, Windows drive (``D:x``, ``D:\x``), rooted (``\x``) and UNC paths.
    win = PureWindowsPath(layout)
    if win.drive or win.root or PurePosixPath(layout).is_absolute():
        raise ValueError("map.layout_file must be a relative path")
    layout_path = Path(layout)
    map_raw = (config_path.parent / layout_path).read_bytes()
    return build_world_content(config_data, map_raw)


def load_run_content(
    directory: Path, *, expected_config_hash: str, expected_map_hash: str
) -> WorldContent:
    """Read retained content and check its identities against a checkpoint or manifest."""
    config_path = directory / CONFIG_FILENAME
    config = decode_model(read_bytes(config_path), EffectiveConfig, config_path)
    require_version(config_path, "meta.schema_version", config.meta.schema_version)
    cfg_hash = config_hash(config)
    verify_identity(config_path, "config_hash", cfg_hash, expected_config_hash)

    map_path = directory / MAP_FILENAME
    try:
        rows = parse_map_bytes(read_bytes(map_path))
        check_map(config, rows)
    except PersistenceError:
        raise
    except ValueError as exc:
        raise PersistenceError(map_path, "map", str(exc)) from exc
    layout_hash = map_hash(rows)
    verify_identity(map_path, "map_hash", layout_hash, expected_map_hash)
    return WorldContent(config=config, map_rows=rows, config_hash=cfg_hash, map_hash=layout_hash)


def retain_run_content(directory: Path, content: WorldContent) -> None:
    """Write the effective typed config and map under their stable run-relative names."""
    config_path, map_path = directory / CONFIG_FILENAME, directory / MAP_FILENAME
    require_version(config_path, "meta.schema_version", content.config.meta.schema_version)
    raw_config = encode(content.config, config_path)
    raw_map = map_bytes_from_rows(content.map_rows)
    verify_identity(config_path, "config_hash", config_hash(content.config), content.config_hash)
    verify_identity(map_path, "map_hash", map_hash(content.map_rows), content.map_hash)
    atomic_create(config_path, raw_config)
    atomic_create(map_path, raw_map)
