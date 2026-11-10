// Static terrain decorations: trees, rocks, the cave, the spring and the damp-moss patch.
// Project-made art. Shapes are built from a few overlapping discs by small deterministic
// generator functions, so they stay consistent with each other and need no image files.
import type { PixelSprite, Rgb } from "./pixels.ts";
import { emptySprite, hash01, hexToRgb, setPixel, spriteFromRows } from "./pixels.ts";

interface Lobe {
  x: number;
  y: number;
  r: number;
}

interface BlobColours {
  outline: string;
  light: string;
  mid: string;
  dark: string;
}

function blobMask(width: number, height: number, lobes: readonly Lobe[]): Uint8Array {
  const mask = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      for (const l of lobes) {
        const dx = x + 0.5 - l.x;
        const dy = y + 0.5 - l.y;
        if (dx * dx + dy * dy <= l.r * l.r) {
          mask[y * width + x] = 1;
          break;
        }
      }
    }
  }
  return mask;
}

/**
 * Paints a lit blob: outline on the rim, highlights towards the top left of each lobe and
 * shade towards the bottom right. `texture` adds a little dithering (leaves); 0 gives flat
 * facets (rock).
 */
function paintBlob(
  out: PixelSprite,
  lobes: readonly Lobe[],
  colours: BlobColours,
  texture: number,
  seed: number,
): void {
  const { width, height } = out;
  const mask = blobMask(width, height, lobes);
  const inside = (x: number, y: number) => x >= 0 && y >= 0 && x < width && y < height && mask[y * width + x] === 1;
  let minX = width;
  let maxX = 0;
  let minY = height;
  let maxY = 0;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (!inside(x, y)) continue;
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    }
  }
  const cx = (minX + maxX + 1) / 2;
  const cy = (minY + maxY + 1) / 2;
  const rx = Math.max(1, (maxX - minX + 1) / 2);
  const ry = Math.max(1, (maxY - minY + 1) / 2);
  const outline = hexToRgb(colours.outline);
  const light = hexToRgb(colours.light);
  const mid = hexToRgb(colours.mid);
  const dark = hexToRgb(colours.dark);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (!inside(x, y)) continue;
      const rim = !inside(x - 1, y) || !inside(x + 1, y) || !inside(x, y - 1) || !inside(x, y + 1);
      if (rim) {
        setPixel(out, x, y, outline);
        continue;
      }
      const lit = -((x + 0.5 - cx) / rx) * 0.45 - ((y + 0.5 - cy) / ry) * 0.8;
      let highlight = false;
      for (const l of lobes) {
        const dx = x + 0.5 - (l.x - l.r * 0.25);
        const dy = y + 0.5 - (l.y - l.r * 0.32);
        if (dx * dx + dy * dy < l.r * l.r * 0.25) {
          highlight = true;
          break;
        }
      }
      const noise = hash01(x, y, seed);
      let rgb: Rgb = mid;
      if (highlight && lit > -0.15) rgb = light;
      else if (lit < -0.36 || !inside(x, y + 2)) rgb = dark;
      else if (texture > 0 && lit < 0.1 && noise < texture) rgb = dark;
      else if (texture > 0 && lit > 0.25 && noise < texture * 0.6) rgb = light;
      setPixel(out, x, y, rgb);
    }
  }
}

function paintTrunk(out: PixelSprite, x: number, top: number, bottom: number): void {
  const o = hexToRgb("#3f2a1c");
  const t = hexToRgb("#6f4a2a");
  const T = hexToRgb("#916238");
  for (let y = top; y <= bottom; y++) {
    setPixel(out, x, y, o);
    setPixel(out, x + 1, y, y === bottom ? o : t);
    setPixel(out, x + 2, y, y === bottom ? o : T);
    setPixel(out, x + 3, y, o);
  }
}

const WOODS_COLOURS: readonly BlobColours[] = [
  { outline: "#1f5236", light: "#63b25e", mid: "#409250", dark: "#2d7544" },
  { outline: "#1d4f3a", light: "#58a863", mid: "#378855", dark: "#276c47" },
];

const WOODS_LOBES: readonly (readonly Lobe[])[] = [
  [
    { x: 5, y: 6, r: 4.6 },
    { x: 10.5, y: 5.5, r: 4.6 },
    { x: 8, y: 10, r: 5.6 },
    { x: 4.6, y: 10.5, r: 3.9 },
    { x: 11.4, y: 10.6, r: 3.9 },
    { x: 8, y: 4, r: 3.6 },
  ],
  [
    { x: 6, y: 5.2, r: 4.5 },
    { x: 10.2, y: 7, r: 5.2 },
    { x: 5, y: 10.2, r: 4.6 },
    { x: 10.6, y: 11, r: 4.3 },
    { x: 8, y: 8, r: 4.6 },
  ],
  [
    { x: 8, y: 5, r: 5 },
    { x: 4.8, y: 9.2, r: 4.3 },
    { x: 11.2, y: 9.2, r: 4.3 },
    { x: 8, y: 11, r: 5 },
  ],
];

export const WOODS_VARIANTS = WOODS_LOBES.length * WOODS_COLOURS.length;
export const WOODS_TREE_HEIGHT = 20;

/** A woodland tree, 16x20, anchored to the bottom of its tile so it overlaps the tile above. */
function woodsTree(variant: number): PixelSprite {
  const out = emptySprite(16, WOODS_TREE_HEIGHT);
  paintTrunk(out, 6, 14, 19);
  paintBlob(
    out,
    WOODS_LOBES[variant % WOODS_LOBES.length] as readonly Lobe[],
    WOODS_COLOURS[Math.floor(variant / WOODS_LOBES.length) % WOODS_COLOURS.length] as BlobColours,
    0.16,
    variant + 1,
  );
  return out;
}

export const FRUIT_TREE_WIDTH = 24;
export const FRUIT_TREE_HEIGHT = 28;

/**
 * Fruit slots inside the fruit-tree canopy, as top-left pixel offsets within the sprite. The
 * renderer fills the first `min(stock, slots)` of them; the exact stock is the text badge.
 */
export const FRUIT_SLOTS: readonly (readonly [number, number])[] = [
  [5, 8],
  [16, 6],
  [10, 12],
  [3, 13],
  [18, 13],
  [11, 4],
  [7, 17],
  [14, 17],
];

/** The fruit tree is larger and lighter than a woodland tree so it reads at island scale. */
function fruitTree(): PixelSprite {
  const out = emptySprite(FRUIT_TREE_WIDTH, FRUIT_TREE_HEIGHT);
  paintTrunk(out, 10, 20, 27);
  paintBlob(
    out,
    [
      { x: 8, y: 8, r: 6.5 },
      { x: 15.5, y: 7, r: 6.5 },
      { x: 12, y: 13, r: 8 },
      { x: 6, y: 14.5, r: 5.5 },
      { x: 18, y: 14.5, r: 5.5 },
      { x: 12, y: 5.5, r: 5 },
    ],
    { outline: "#24573a", light: "#8dce5e", mid: "#5fae4c", dark: "#418c46" },
    0.12,
    91,
  );
  return out;
}

const ROCK_COLOURS: BlobColours = { outline: "#4d4944", light: "#c3beb3", mid: "#9c978d", dark: "#746f69" };

const ROCK_LOBES: readonly (readonly Lobe[])[] = [
  [
    { x: 8, y: 11, r: 6.4 },
    { x: 4.8, y: 13, r: 4.4 },
    { x: 11.4, y: 13.2, r: 4.4 },
    { x: 8.4, y: 6.4, r: 4.2 },
  ],
  [
    { x: 6, y: 10, r: 5 },
    { x: 10.6, y: 11, r: 5.4 },
    { x: 8, y: 13.4, r: 5.6 },
  ],
];

export const ROCK_VARIANTS = ROCK_LOBES.length;
export const ROCK_HEIGHT = 18;

function rock(variant: number): PixelSprite {
  const out = emptySprite(16, ROCK_HEIGHT);
  paintBlob(out, ROCK_LOBES[variant % ROCK_LOBES.length] as readonly Lobe[], ROCK_COLOURS, 0, 5);
  return out;
}

/** A rock mound with a dark opening. The opening shape is the non-colour cue for the cave. */
function cave(): PixelSprite {
  const out = emptySprite(16, ROCK_HEIGHT);
  paintBlob(
    out,
    [
      { x: 8, y: 10, r: 7.2 },
      { x: 4.4, y: 13, r: 4.6 },
      { x: 11.6, y: 13, r: 4.6 },
    ],
    ROCK_COLOURS,
    0,
    9,
  );
  const rim = hexToRgb("#4d4944");
  const dark = hexToRgb("#231a18");
  const inner = hexToRgb("#3d2d27");
  for (let y = 9; y <= 17; y++) {
    const half = y === 9 ? 1 : y === 10 ? 2 : 3;
    for (let x = 8 - half - 1; x <= 7 + half + 1; x++) {
      const edge = x === 8 - half - 1 || x === 7 + half + 1 || y === 9;
      setPixel(out, x, y, edge ? rim : y <= 11 ? inner : dark);
    }
  }
  return out;
}

export const SPRING_WIDTH = 22;
export const SPRING_HEIGHT = 18;

/**
 * The spring: a ring of stones around water, a little wider than its tile so the one water
 * source reads at island scale. `phase` moves the glints (display only).
 */
function spring(phase: number): PixelSprite {
  const out = emptySprite(SPRING_WIDTH, SPRING_HEIGHT);
  const outline = hexToRgb("#4d4944");
  const stones = [hexToRgb("#c3beb3"), hexToRgb("#9c978d"), hexToRgb("#b0aba0")];
  const water = hexToRgb("#49bfe6");
  const deep = hexToRgb("#2f9bcb");
  const glint = hexToRgb("#d6f4ff");
  const cx = SPRING_WIDTH / 2;
  const cy = SPRING_HEIGHT / 2 + 0.5;
  for (let y = 0; y < SPRING_HEIGHT; y++) {
    for (let x = 0; x < SPRING_WIDTH; x++) {
      const dx = (x + 0.5 - cx) / 10.4;
      const dy = (y + 0.5 - cy) / 7.6;
      const d = dx * dx + dy * dy;
      if (d > 1) continue;
      const wx = (x + 0.5 - cx) / 7.6;
      const wy = (y + 0.5 - cy) / 5;
      const w = wx * wx + wy * wy;
      if (w <= 1) {
        setPixel(out, x, y, wy < -0.5 ? deep : water);
      } else if (d > 0.84) {
        setPixel(out, x, y, outline);
      } else {
        const angle = Math.atan2(dy, dx);
        const stone = Math.floor(((angle + Math.PI) / (2 * Math.PI)) * 14);
        setPixel(out, x, y, stones[stone % stones.length] as Rgb);
      }
    }
  }
  const glints: readonly (readonly [number, number])[] =
    phase === 0
      ? [
          [7, 9],
          [8, 9],
          [9, 9],
          [13, 12],
          [14, 12],
        ]
      : [
          [8, 10],
          [9, 10],
          [10, 10],
          [13, 8],
          [14, 8],
        ];
  for (const [gx, gy] of glints) setPixel(out, gx, gy, glint);
  return out;
}

/** Damp moss: a dark, wet-looking flat patch with droplets. Speckles are the non-colour cue. */
function moss(): PixelSprite {
  const out = emptySprite(16, 16);
  const lobes: Lobe[] = [
    { x: 6, y: 8, r: 4.7 },
    { x: 10.2, y: 7.6, r: 4.3 },
    { x: 9.4, y: 10.8, r: 4 },
    { x: 5, y: 10.6, r: 3.1 },
  ];
  const mask = blobMask(16, 16, lobes);
  const inside = (x: number, y: number) => x >= 0 && y >= 0 && x < 16 && y < 16 && mask[y * 16 + x] === 1;
  const base = hexToRgb("#4c9070");
  const dark = hexToRgb("#39795f");
  const drop = hexToRgb("#bdeedd");
  for (let y = 0; y < 16; y++) {
    for (let x = 0; x < 16; x++) {
      if (!inside(x, y)) continue;
      const rim = !inside(x - 1, y) || !inside(x + 1, y) || !inside(x, y - 1) || !inside(x, y + 1);
      setPixel(out, x, y, rim || hash01(x, y, 31) < 0.28 ? dark : base);
    }
  }
  for (const [x, y] of [
    [5, 7],
    [9, 6],
    [11, 9],
    [7, 11],
  ] as const) {
    setPixel(out, x, y, drop);
  }
  return out;
}

const GROUND_PALETTE = { d: "#6aa548", w: "#fff8e6", y: "#f3c93f", p: "#f29bb0" };
const TUFT = spriteFromRows(["d..d.", ".dd.d", ".ddd."], GROUND_PALETTE, "tuft");
const FLOWER_WHITE = spriteFromRows([".w.", "wyw", ".w."], GROUND_PALETTE, "flower_white");
const FLOWER_PINK = spriteFromRows([".p.", "pyp", ".p."], GROUND_PALETTE, "flower_pink");

const cache = new Map<string, PixelSprite>();

/** Terrain decoration by key: `woods/<n>`, `rock/<n>`, `cave`, `spring/<phase>`, `fruit_tree`, ... */
export function terrainSprite(key: string): PixelSprite {
  let s = cache.get(key);
  if (s !== undefined) return s;
  const [name, arg] = key.split("/");
  const n = Number(arg ?? 0);
  switch (name) {
    case "woods":
      s = woodsTree(n);
      break;
    case "rock":
      s = rock(n);
      break;
    case "cave":
      s = cave();
      break;
    case "spring":
      s = spring(n);
      break;
    case "fruit_tree":
      s = fruitTree();
      break;
    case "moss":
      s = moss();
      break;
    case "tuft":
      s = TUFT;
      break;
    case "flower_white":
      s = FLOWER_WHITE;
      break;
    case "flower_pink":
      s = FLOWER_PINK;
      break;
    default:
      throw new Error(`unknown terrain sprite ${key}`);
  }
  cache.set(key, s);
  return s;
}
