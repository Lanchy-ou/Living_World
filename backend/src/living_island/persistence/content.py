"""Read world content files, then validate them through ``living_island.world.content``.

No rule implementation lives here (implementation plan §2.1).
"""

from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath, PureWindowsPath

from living_island.world.content import WorldContent, build_world_content


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
