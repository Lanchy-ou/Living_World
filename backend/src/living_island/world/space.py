"""Static map, terrain classification, clock/radius and line of sight (World Rules §1, §5.1).

Pure integer functions over the validated static map. No state, no IO, no RNG.
"""

from __future__ import annotations

from collections.abc import Iterator

from living_island.world.content import EffectiveConfig, WorldContent
from living_island.world.protocol import TERRAIN_BY_SYMBOL, Coord, Terrain

# Symbols whose tiles stop sight when they lie between observer and target (WR §5.1 step 3).
OPAQUE_SYMBOLS = frozenset("WF^")


class StaticMap:
    """The authored static map: terrain, movement costs and opacity per tile.

    ``F`` is passable woods (opaque); ``M`` is passable grass (clear). Costs come from the
    effective config; ``~``, ``^`` and ``S`` are impassable.
    """

    def __init__(self, config: EffectiveConfig, rows: list[str]):
        self.width = config.map.width
        self.height = config.map.height
        self._rows = tuple(rows)
        m = config.map
        self._cost_by_symbol: dict[str, int] = {
            ".": m.step_cost_beach,
            ",": m.step_cost_grass,
            "W": m.step_cost_woods,
            "C": m.step_cost_cave,
            "M": m.step_cost_damp_moss,
            "F": m.step_cost_fruit_tree,
        }
        self.grass_cost = m.step_cost_grass

    @classmethod
    def from_content(cls, content: WorldContent) -> StaticMap:
        return cls(content.config, content.map_rows)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def coord(self, index: int) -> Coord:
        return Coord(x=index % self.width, y=index // self.width)

    def symbol(self, x: int, y: int) -> str:
        return self._rows[y][x]

    def terrain(self, x: int, y: int) -> Terrain:
        return TERRAIN_BY_SYMBOL[self._rows[y][x]]

    def step_cost(self, x: int, y: int) -> int | None:
        """Integer entry cost, or ``None`` when the tile cannot be entered."""
        return self._cost_by_symbol.get(self._rows[y][x])

    def blocks_sight(self, x: int, y: int) -> bool:
        return self._rows[y][x] in OPAQUE_SYMBOLS


# ---------------------------------------------------------------------------
# Clock and sight radius (WR §1.3, [A1] sampling clock in §5.1 step 5)
# ---------------------------------------------------------------------------


def clock_minutes(config: EffectiveConfig, tick: int) -> int:
    """Local game clock in minutes since midnight at ``tick``."""
    return (config.time.start_hour * 60 + tick * config.time.tick_minutes) % 1440


def is_daylight(config: EffectiveConfig, tick: int) -> bool:
    """Daylight is ``[day_start_hour, day_end_hour)``; the end hour itself is night."""
    minutes = clock_minutes(config, tick)
    return config.time.day_start_hour * 60 <= minutes < config.time.day_end_hour * 60


def sight_radius(config: EffectiveConfig, completed_tick: int) -> int:
    """Manhattan sight radius using the completed tick's clock (no sub-tick clock)."""
    if is_daylight(config, completed_tick):
        return config.perception.day_radius_tiles
    return config.perception.night_radius_tiles


# ---------------------------------------------------------------------------
# Line of sight (WR §5.1 steps 1-4)
# ---------------------------------------------------------------------------


def line_points(x0: int, y0: int, x1: int, y1: int) -> Iterator[tuple[int, int]]:
    """Standard integer Bresenham: the tiles after ``(x0, y0)`` up to and including the target.

    ``e2`` is computed once per iteration and shared by both axis updates (World Rules §5.1
    step 2); there is no supercover or corner rule.
    """
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = (x1 > x0) - (x1 < x0)
    sy = (y1 > y0) - (y1 < y0)
    err = dx + dy
    x, y = x0, y0
    while (x, y) != (x1, y1):
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
        yield x, y


def has_line_of_sight(smap: StaticMap, x0: int, y0: int, x1: int, y1: int) -> bool:
    """Whether the observer's center sees the target's center.

    Intervening tiles with ``W``, ``F`` or ``^`` block; the target tile itself is visible
    even if opaque, and the observer's start tile never blocks.
    """
    for x, y in line_points(x0, y0, x1, y1):
        if (x, y) != (x1, y1) and smap.blocks_sight(x, y):
            return False
    return True


def visible_tile_indices(smap: StaticMap, x0: int, y0: int, radius: int) -> list[int]:
    """Tile indices visible from ``(x0, y0)``, ascending ``(y, x)`` (equals ascending index).

    Candidates lie inside the map within Manhattan ``radius``; a tile at the radius edge is
    visible when not occluded. The observer's own tile is always visible.
    """
    out: list[int] = []
    for y in range(max(0, y0 - radius), min(smap.height - 1, y0 + radius) + 1):
        span = radius - abs(y - y0)
        for x in range(max(0, x0 - span), min(smap.width - 1, x0 + span) + 1):
            if has_line_of_sight(smap, x0, y0, x, y):
                out.append(smap.index(x, y))
    return out
