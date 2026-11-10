// Resident sprites: 16x20 pixels, three views (down, up, right; left is the mirror of right)
// and three frames (idle, walk_a, walk_b). Project-made art, written as character grids.
//
// A resident's look depends only on its index in the bundle's declared resident list. Names
// and IDs are never matched. Hair shape, hair colour and shirt colour differ per resident, and
// the letter label is the non-colour cue.
import type { Palette, PixelSprite } from "./pixels.ts";
import { desaturate, mirror, rotateClockwise, spriteFromRows } from "./pixels.ts";

export const RESIDENT_WIDTH = 16;
export const RESIDENT_HEIGHT = 20;

export const FACINGS = ["down", "up", "left", "right"] as const;
export type Facing = (typeof FACINGS)[number];
export const RESIDENT_FRAMES = ["idle", "walk_a", "walk_b"] as const;
export type ResidentFrameName = (typeof RESIDENT_FRAMES)[number];

type View = "front" | "back" | "side";

// Characters: o outline, h/i/j hair (base, light, dark), s/t skin (base, shade), e eye,
// c/d shirt (base, shade), p/q trousers (base, shade), b shoes.

/** Rows 0-9: head. One block per hair design and view. */
const HEADS: Record<View, readonly string[]>[] = [
  // Design 0: short hair.
  {
    front: [
      "....oooooooo....",
      "...ohhhhhhhho...",
      "..ohhihhhhhhho..",
      "..ohhhsssshhho..",
      "..ohssssssssho..",
      "..ohsessssesho..",
      "..otsessssesto..",
      "..otssssssssto..",
      "...otssssssto...",
      "...oooccccooo...",
    ],
    back: [
      "....oooooooo....",
      "...ohhhhhhhho...",
      "..ohhhhhhihhho..",
      "..ohhhhhhhhhho..",
      "..ohhhhhhhhhho..",
      "..ohhhhhhhhhho..",
      "..otjhhhhhhjto..",
      "..otsjjjjjjsto..",
      "...otssssssto...",
      "...oooccccooo...",
    ],
    side: [
      "....ooooooo.....",
      "...ohhhhhhho....",
      "..ohhhihhhhho...",
      "..ohhhhhhhsso...",
      "..ohhhhhsssso...",
      "..ohhhhssseso...",
      "..ojhhtssseso...",
      "..ojjttssssso...",
      "...oottsssso....",
      "....ooocccoo....",
    ],
  },
  // Design 1: long bob that reaches the shoulders.
  {
    front: [
      "....oooooooo....",
      "...ohhhhhhhho...",
      "..ohhhhhhihhho..",
      "..ohhhhhhhhhho..",
      "..ohhsssssshho..",
      "..ohsessssesho..",
      "..ohsessssesho..",
      "..ohssssssssho..",
      "..ohhtssssthho..",
      "..ohhoccccohho..",
    ],
    back: [
      "....oooooooo....",
      "...ohhhhhhhho...",
      "..ohhhhhhihhho..",
      "..ohhhhhhhhhho..",
      "..ohhhhhhhhhho..",
      "..ohhhhhhhhhho..",
      "..ohhhhhhhhhho..",
      "..ohhhhhhhhhho..",
      "..ohjhhhhhhjho..",
      "..ohjjhhhhjjho..",
    ],
    side: [
      "....ooooooo.....",
      "...ohhhhhhho....",
      "..ohhhhhihhho...",
      "..ohhhhhhhhso...",
      "..ohhhhhhssso...",
      "..ohhhhhsseso...",
      "..ohhhhhsseso...",
      "..ohhhhtsssso...",
      "..ohhhottssso...",
      "..ohhhooccoo....",
    ],
  },
  // Design 2: top bun.
  {
    front: [
      "......oooo......",
      "....oohhhhoo....",
      "...ohhhhhhhho...",
      "..ohhihhhhhhho..",
      "..ohhhhssshhho..",
      "..ohsessssesho..",
      "..otsessssesto..",
      "..otssssssssto..",
      "...otssssssto...",
      "...oooccccooo...",
    ],
    back: [
      "......oooo......",
      "....oohhhhoo....",
      "...ohhhhhhhho...",
      "..ohhhhhhihhho..",
      "..ohhhhhhhhhho..",
      "..ohhhhhhhhhho..",
      "..otjhhhhhhjto..",
      "..otsjjjjjjsto..",
      "...otssssssto...",
      "...oooccccooo...",
    ],
    side: [
      "...oooo.........",
      "..ohhhoooooo....",
      "..ohhhhhhhhho...",
      "..ohhhihhhsso...",
      "..ohhhhhsssso...",
      "..ohhhhssseso...",
      "..ojhhtssseso...",
      "..ojjttssssso...",
      "...oottsssso....",
      "....ooocccoo....",
    ],
  },
];

/** Rows 10-13: torso and arms, shared by every design. */
const TORSO: Record<View, readonly string[]> = {
  front: ["...odccccccdo...", "..oddccccccddo..", "..osdccccccdso..", "...oodccccdoo..."],
  back: ["...odccccccdo...", "..oddccccccddo..", "..osdccccccdso..", "...oodccccdoo..."],
  side: ["....odcccco.....", "....odcdcco.....", "....odcdcco.....", "....odcscco....."],
};

/**
 * Optional per-design rows painted over the torso (`.` keeps the torso pixel): the long bob
 * falls onto the shoulders.
 */
const TORSO_OVERLAY: Partial<Record<View, readonly string[]>>[] = [
  {},
  {
    front: ["..oh........ho.."],
    back: ["..ojhhhhhhhhjo.."],
    side: ["..ojjo.........."],
  },
  {},
];

/** Rows 14-19: legs. Walking changes only these rows. */
const LEGS: Record<"front" | "side", Record<ResidentFrameName, readonly string[]>> = {
  front: {
    idle: [
      "....oppppppo....",
      "....oppqqppo....",
      "....oppooppo....",
      "....oppooppo....",
      "....obboobbo....",
      "....oooooooo....",
    ],
    walk_a: [
      "....oppppppo....",
      "....oppqqppo....",
      "....oppooppo....",
      "....oppoobbo....",
      "....obbo.oo.....",
      "....oooo........",
    ],
    walk_b: [
      "....oppppppo....",
      "....oppqqppo....",
      "....oppooppo....",
      "....obbooppo....",
      ".....oo.obbo....",
      "........oooo....",
    ],
  },
  side: {
    idle: [
      ".....oppppo.....",
      ".....oppppo.....",
      ".....oppppo.....",
      ".....oppppo.....",
      ".....obbbbbo....",
      ".....ooooooo....",
    ],
    walk_a: [
      ".....oppppo.....",
      "....oppppppo....",
      "...oppo..oppo...",
      "...oppo..oppo...",
      "...obbo..obbbo..",
      "...oooo..ooooo..",
    ],
    walk_b: [
      ".....oppppo.....",
      ".....oppppo.....",
      ".....oqppo......",
      ".....oqppo......",
      ".....obbbbo.....",
      ".....oooooo.....",
    ],
  },
};

export const HAIR_DESIGN_COUNT = HEADS.length;

interface HairColour {
  h: string;
  i: string;
  j: string;
}
interface ClothColour {
  c: string;
  d: string;
}

// Hair colours cycle with period 5 and shirts with period 8, so the first eight residents all
// differ in shirt colour and the hair shape cycles with period 3.
const HAIR_COLOURS: readonly HairColour[] = [
  { h: "#7a4a2a", i: "#9c6a3c", j: "#5a341d" },
  { h: "#e39a3c", i: "#f6c266", j: "#bd7425" },
  { h: "#a2423a", i: "#c8665a", j: "#7d2e29" },
  { h: "#3c3440", i: "#5a5060", j: "#28222c" },
  { h: "#c9c2b0", i: "#e6e0d0", j: "#a39c8a" },
];

/** Shirt colours. The base colour is also the resident's tag colour in the interface. */
const SHIRT_COLOURS: readonly ClothColour[] = [
  { c: "#2fa39a", d: "#217a74" },
  { c: "#f0bd2c", d: "#c8961a" },
  { c: "#ec7286", d: "#c7536a" },
  { c: "#8f6fd6", d: "#6f52b0" },
  { c: "#4f8fe0", d: "#386fb8" },
  { c: "#7fbf4a", d: "#5f9a34" },
  { c: "#9aa3ad", d: "#757e88" },
  { c: "#f08a3c", d: "#c96a22" },
];

const TROUSER_COLOURS: readonly { p: string; q: string }[] = [
  { p: "#6e4f3a", q: "#553a29" },
  { p: "#5d6f95", q: "#465679" },
  { p: "#7b5a44", q: "#604433" },
];

const COMMON: Palette = {
  o: "#3a2a22",
  s: "#f6cfa4",
  t: "#dea77c",
  e: "#2b2130",
  b: "#3d2b22",
};

export interface ResidentLook {
  /** Supplementary non-colour identifier: A, B, C, ... */
  letter: string;
  /** Tag colour, equal to the shirt colour. */
  colour: string;
  hairDesign: number;
  palette: Palette;
}

/** Stable: depends only on the resident's index in the declared (ID-sorted) list. */
export function residentLook(index: number): ResidentLook {
  const i = Math.max(0, Math.trunc(index));
  const hair = HAIR_COLOURS[i % HAIR_COLOURS.length] as HairColour;
  const shirt = SHIRT_COLOURS[i % SHIRT_COLOURS.length] as ClothColour;
  const trousers = TROUSER_COLOURS[i % TROUSER_COLOURS.length] as { p: string; q: string };
  return {
    letter: String.fromCharCode(65 + (i % 26)),
    colour: shirt.c,
    hairDesign: i % HAIR_DESIGN_COUNT,
    palette: { ...COMMON, ...hair, ...shirt, ...trousers },
  };
}

function overlayRows(base: readonly string[], overlay: readonly string[] | undefined): string[] {
  return base.map((row, y) => {
    const over = overlay?.[y];
    if (over === undefined) return row;
    return [...row].map((ch, x) => (over[x] === "." || over[x] === undefined ? ch : over[x])).join("");
  });
}

function rowsFor(design: number, view: View, frame: ResidentFrameName): string[] {
  const head = (HEADS[design] as Record<View, readonly string[]>)[view];
  const torso = overlayRows(TORSO[view], (TORSO_OVERLAY[design] ?? {})[view]);
  const legs = LEGS[view === "side" ? "side" : "front"][frame];
  return [...head, ...torso, ...legs];
}

const cache = new Map<string, PixelSprite>();

export function residentSpriteKey(index: number, facing: Facing, frame: ResidentFrameName): string {
  return `resident/${index}/${facing}/${frame}`;
}

export function residentSprite(index: number, facing: Facing, frame: ResidentFrameName): PixelSprite {
  const key = residentSpriteKey(index, facing, frame);
  let sprite = cache.get(key);
  if (sprite === undefined) {
    const look = residentLook(index);
    const view: View = facing === "down" ? "front" : facing === "up" ? "back" : "side";
    sprite = spriteFromRows(rowsFor(look.hairDesign, view, frame), look.palette, key);
    if (facing === "left") sprite = mirror(sprite);
    cache.set(key, sprite);
  }
  return sprite;
}

export function corpseSpriteKey(index: number): string {
  return `corpse/${index}`;
}

/**
 * A corpse is the resident's own front view, lying on its side and greyed. The lying pose and
 * the crossed tag are the non-colour cues; the grey tone only supports them.
 */
export function corpseSprite(index: number): PixelSprite {
  const key = corpseSpriteKey(index);
  let sprite = cache.get(key);
  if (sprite === undefined) {
    sprite = desaturate(rotateClockwise(residentSprite(index, "down", "idle")), 0.7);
    cache.set(key, sprite);
  }
  return sprite;
}
