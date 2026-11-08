"""Read world content files, then validate them through ``living_island.world.content``.

No rule implementation lives here (implementation plan §2.1).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from living_island.world.content import WorldContent, build_world_content


def load_world_content(config_path: Path) -> WorldContent:
    """Load a world TOML and its ``map.layout_file`` (resolved next to the TOML)."""
    with config_path.open("rb") as f:
        config_data = tomllib.load(f)
    layout = config_data.get("map", {}).get("layout_file")
    if not isinstance(layout, str):
        raise ValueError("map.layout_file must be a string")
    layout_path = Path(layout)
    if layout_path.is_absolute() or ".." in layout_path.parts:
        raise ValueError("map.layout_file must be a relative path inside the content folder")
    map_raw = (config_path.parent / layout_path).read_bytes()
    return build_world_content(config_data, map_raw)
