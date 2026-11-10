// The static terrain layer: a pure function from the bundle's map to pixels. It reads only
// `map.rows` and `map.terrain_legend`, so any map draws without code changes. Nothing here is a
// rule: coastline rounding, textures and decorations are display, and every entity position and
// hit test still uses the tile grid.
import type { ReplayBundle } from "../replay/types.ts";
import type { PixelSprite, Rgb } from "./assets/pixels.ts";
import { blit, emptySprite, hash01, hexToRgb } from "./assets/pixels.ts";
import {
  FRUIT_TREE_HEIGHT,
  FRUIT_TREE_WIDTH,
  ROCK_HEIGHT,
  ROCK_VARIANTS,
  SPRING_HEIGHT,
  SPRING_WIDTH,
  WOODS_TREE_HEIGHT,
  WOODS_VARIANTS,
  terrainSprite,
} from "./assets/terrainArt.ts";

export type Terrain = ReplayBundle["map"]["terrain_legend"][number]["terrain"];

export interface MapLike {
  width: number;
  height: number;
  rows: readonly string[];
  terrain_legend: readonly { symbol: string; terrain: Terrain }[];
}

/** Source pixels per tile at full detail. All sprite art is drawn for this size. */
export const TILE_PX = 16;

/** Largest side of the cached layer in pixels. Larger maps fall back to flat tiles. */
const MAX_LAYER_SIDE = 4096;

/** Source pixels per tile for this map: 16 with full art, or a smaller flat-colour fallback. */
export function terrainTilePx(map: { width: number; height: number }): number {
  const side = Math.max(map.width, map.height);
  if (side * TILE_PX <= MAX_LAYER_SIDE) return TILE_PX;
  return side * 4 <= MAX_LAYER_SIDE ? 4 : 1;
}

/** Row-major terrain per tile; null for a symbol that the legend does not define. */
export function terrainGrid(map: MapLike): (Terrain | null)[] {
  const legend = new Map(map.terrain_legend.map((e) => [e.symbol, e.terrain]));
  const grid: (Terrain | null)[] = [];
  for (let y = 0; y < map.height; y++) {
    const row = map.rows[y] ?? "";
    for (let x = 0; x < map.width; x++) grid.push(legend.get(row[x] ?? "") ?? null);
  }
  return grid;
}

const C = {
  seaDeep: hexToRgb("#1c8fa6"),
  seaMid: hexToRgb("#2ba6b7"),
  seaShallow: hexToRgb("#58c4c7"),
  foam: hexToRgb("#e8f8ee"),
  glint: hexToRgb("#7fd6d8"),
  sand: hexToRgb("#f1dba2"),
  sandLight: hexToRgb("#f9eac0"),
  sandDark: hexToRgb("#e2c685"),
  sandWet: hexToRgb("#d8bc7e"),
  grass: hexToRgb("#8cc25c"),
  grassLight: hexToRgb("#a0cf6b"),
  grassDark: hexToRgb("#76ae4e"),
  floor: hexToRgb("#6ea855"),
  floorDark: hexToRgb("#5d9649"),
  unknownA: hexToRgb("#ff00ff"),
  unknownB: hexToRgb("#1a1a1a"),
} as const;

/** One flat colour per terrain, for the small-tile fallback and for map-independent swatches. */
export const FLAT_COLOURS: Record<Terrain, string> = {
  sea: "#2ba6b7",
  beach: "#f1dba2",
  grass: "#8cc25c",
  woods: "#409250",
  rock: "#9c978d",
  spring: "#49bfe6",
  cave: "#3d2d27",
  fruit_tree: "#5fae4c",
  damp_moss: "#4c9070",
};

function bilinear(field: Float32Array, w: number, h: number, u: number, v: number): number {
  const x0 = Math.floor(u);
  const y0 = Math.floor(v);
  const tx = u - x0;
  const ty = v - y0;
  const xa = Math.min(w - 1, Math.max(0, x0));
  const xb = Math.min(w - 1, Math.max(0, x0 + 1));
  const ya = Math.min(h - 1, Math.max(0, y0));
  const yb = Math.min(h - 1, Math.max(0, y0 + 1));
  const top = (field[ya * w + xa] as number) * (1 - tx) + (field[ya * w + xb] as number) * tx;
  const bottom = (field[yb * w + xa] as number) * (1 - tx) + (field[yb * w + xb] as number) * tx;
  return top * (1 - ty) + bottom * ty;
}

/** Smooth value noise in [-1, 1] with a cell of `cell` pixels. Deterministic. */
function wobble(px: number, py: number, cell: number, seed: number): number {
  const u = px / cell;
  const v = py / cell;
  const x0 = Math.floor(u);
  const y0 = Math.floor(v);
  const sx = u - x0;
  const sy = v - y0;
  const fx = sx * sx * (3 - 2 * sx);
  const fy = sy * sy * (3 - 2 * sy);
  const a = hash01(x0, y0, seed);
  const b = hash01(x0 + 1, y0, seed);
  const c = hash01(x0, y0 + 1, seed);
  const d = hash01(x0 + 1, y0 + 1, seed);
  return ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy) * 2 - 1;
}

/** Distance in tiles from each tile to the nearest land tile, capped. Display shading only. */
function distanceToLand(land: Float32Array, w: number, h: number, cap: number): Float32Array {
  const dist = new Float32Array(w * h).fill(cap);
  let frontier: number[] = [];
  for (let i = 0; i < land.length; i++) {
    if (land[i] === 1) {
      dist[i] = 0;
      frontier.push(i);
    }
  }
  for (let d = 1; d < cap && frontier.length > 0; d++) {
    const next: number[] = [];
    for (const i of frontier) {
      const x = i % w;
      const y = (i - x) / w;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          const ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
          const j = ny * w + nx;
          if ((dist[j] as number) > d) {
            dist[j] = d;
            next.push(j);
          }
        }
      }
    }
    frontier = next;
  }
  return dist;
}

function put(out: PixelSprite, i: number, rgb: Rgb): void {
  out.data[i] = rgb[0];
  out.data[i + 1] = rgb[1];
  out.data[i + 2] = rgb[2];
  out.data[i + 3] = 255;
}

function flatLayer(map: MapLike, grid: (Terrain | null)[], tilePx: number): PixelSprite {
  const out = emptySprite(map.width * tilePx, map.height * tilePx);
  const colours = new Map<Terrain, Rgb>();
  for (const [t, hex] of Object.entries(FLAT_COLOURS)) colours.set(t as Terrain, hexToRgb(hex));
  for (let y = 0; y < map.height; y++) {
    for (let x = 0; x < map.width; x++) {
      const t = grid[y * map.width + x] ?? null;
      const rgb = t === null ? C.unknownA : (colours.get(t) as Rgb);
      for (let py = 0; py < tilePx; py++) {
        for (let px = 0; px < tilePx; px++) {
          put(out, ((y * tilePx + py) * out.width + x * tilePx + px) * 4, rgb);
        }
      }
    }
  }
  return out;
}

/**
 * Renders the whole map. `phase` (0 or 1) only moves water glints and foam, for a two-frame
 * ambient shimmer; it never changes where anything is.
 */
export function buildTerrainLayer(map: MapLike, phase: 0 | 1 = 0): PixelSprite {
  const grid = terrainGrid(map);
  const tilePx = terrainTilePx(map);
  if (tilePx !== TILE_PX) return flatLayer(map, grid, tilePx);

  const w = map.width;
  const h = map.height;
  const land = new Float32Array(w * h);
  const green = new Float32Array(w * h);
  const wood = new Float32Array(w * h);
  grid.forEach((t, i) => {
    land[i] = t !== "sea" ? 1 : 0;
    green[i] = t !== "sea" && t !== "beach" ? 1 : 0;
    wood[i] = t === "woods" || t === "fruit_tree" ? 1 : 0;
  });
  const depth = distanceToLand(land, w, h, 5);

  const out = emptySprite(w * TILE_PX, h * TILE_PX);
  for (let py = 0; py < out.height; py++) {
    const v = (py + 0.5) / TILE_PX - 0.5;
    const ty = py >> 4;
    for (let px = 0; px < out.width; px++) {
      const i = (py * out.width + px) * 4;
      const tx = px >> 4;
      if (grid[ty * w + tx] === null) {
        // An undefined symbol is shown as an obvious marker, never guessed.
        put(out, i, ((px >> 2) + (py >> 2)) % 2 === 0 ? C.unknownA : C.unknownB);
        continue;
      }
      const u = (px + 0.5) / TILE_PX - 0.5;
      const n = wobble(px, py, 6, 1) * 0.1;
      const speck = hash01(px, py, 3);
      const g = bilinear(green, w, h, u, v) + n;
      const l = bilinear(land, w, h, u, v) + n * 0.8;
      if (g > 0.5) {
        const f = bilinear(wood, w, h, u, v) + n;
        if (f > 0.5) put(out, i, speck < 0.08 ? C.floorDark : C.floor);
        else if (g < 0.57) put(out, i, C.grassDark);
        else put(out, i, speck < 0.012 ? C.grassDark : speck > 0.988 ? C.grassLight : C.grass);
      } else if (l > 0.5) {
        if (l < 0.6) put(out, i, C.sandWet);
        else put(out, i, speck < 0.03 ? C.sandDark : speck > 0.97 ? C.sandLight : C.sand);
      } else {
        const foamAt = phase === 0 ? 0.39 : 0.35;
        const d = bilinear(depth, w, h, u, v) + wobble(px, py, 9, 2) * 0.45;
        if (l > foamAt) put(out, i, C.foam);
        else if (d < 1.35) put(out, i, C.seaShallow);
        else if (d < 2.4) put(out, i, C.seaMid);
        else put(out, i, C.seaDeep);
      }
    }
  }

  // Open-water glints: short light dashes on some sea tiles, shifted between the two phases.
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (grid[y * w + x] !== "sea" || (depth[y * w + x] as number) < 2) continue;
      const pick = hash01(x, y, 7);
      const shown = pick < 0.1 || (phase === 0 ? pick >= 0.1 && pick < 0.15 : pick >= 0.15 && pick < 0.2);
      if (!shown) continue;
      const gx = x * TILE_PX + 2 + Math.floor(hash01(x, y, 8) * 9) + phase * 2;
      const gy = y * TILE_PX + 3 + Math.floor(hash01(x, y, 9) * 10);
      for (let k = 0; k < 3; k++) put(out, (gy * out.width + gx + k) * 4, C.glint);
    }
  }

  // Decorations, top row first, so a tree overlaps the tile above it.
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const t = grid[y * w + x];
      const left = x * TILE_PX;
      const top = y * TILE_PX;
      const pick = hash01(x, y, 11);
      switch (t) {
        case "grass": {
          const ox = 2 + Math.floor(hash01(x, y, 12) * 9);
          const oy = 3 + Math.floor(hash01(x, y, 13) * 9);
          if (pick < 0.1) blit(out, terrainSprite("tuft"), left + ox, top + oy);
          else if (pick > 0.975) blit(out, terrainSprite("flower_white"), left + ox, top + oy);
          else if (pick > 0.96) blit(out, terrainSprite("flower_pink"), left + ox, top + oy);
          break;
        }
        case "woods": {
          const variant = Math.floor(pick * WOODS_VARIANTS);
          const jx = Math.floor(hash01(x, y, 14) * 5) - 2;
          const jy = Math.floor(hash01(x, y, 15) * 3);
          blit(out, terrainSprite(`woods/${variant}`), left + jx, top + TILE_PX - WOODS_TREE_HEIGHT - jy);
          break;
        }
        case "rock":
          blit(out, terrainSprite(`rock/${Math.floor(pick * ROCK_VARIANTS)}`), left, top + TILE_PX - ROCK_HEIGHT);
          break;
        case "cave":
          blit(out, terrainSprite("cave"), left, top + TILE_PX - ROCK_HEIGHT);
          break;
        case "spring":
          blit(
            out,
            terrainSprite(`spring/${phase}`),
            left + TILE_PX / 2 - SPRING_WIDTH / 2,
            top + TILE_PX / 2 - SPRING_HEIGHT / 2,
          );
          break;
        case "damp_moss":
          blit(out, terrainSprite("moss"), left, top);
          break;
        case "fruit_tree":
          blit(
            out,
            terrainSprite("fruit_tree"),
            left + TILE_PX / 2 - FRUIT_TREE_WIDTH / 2,
            top + TILE_PX - FRUIT_TREE_HEIGHT,
          );
          break;
        default:
          break;
      }
    }
  }
  return out;
}

/** Pixel offset of the fruit-tree sprite's top-left corner from its tile's top-left corner. */
export const FRUIT_TREE_OFFSET = {
  x: TILE_PX / 2 - FRUIT_TREE_WIDTH / 2,
  y: TILE_PX - FRUIT_TREE_HEIGHT,
} as const;

/** A small sample of one terrain for the legend: the centre of a 3x3 patch of that terrain. */
export function terrainSwatch(terrain: Terrain): PixelSprite {
  const symbol = "x";
  const layer = buildTerrainLayer({
    width: 3,
    height: 3,
    rows: [symbol.repeat(3), symbol.repeat(3), symbol.repeat(3)],
    terrain_legend: [{ symbol, terrain }],
  });
  const size = TILE_PX + 8;
  const out = emptySprite(size, size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const si = ((y + TILE_PX - 6) * layer.width + x + TILE_PX - 4) * 4;
      out.data.set(layer.data.subarray(si, si + 4), (y * size + x) * 4);
    }
  }
  return out;
}
