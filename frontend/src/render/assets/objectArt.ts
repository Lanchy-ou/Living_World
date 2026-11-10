// Ground items, fruit on trees and action bubbles. Project-made art, written as character
// grids. Each sprite stands for a recorded fact; none of them implies a rule.
import type { Palette, PixelSprite } from "./pixels.ts";
import { blit, emptySprite, spriteFromRows } from "./pixels.ts";

const FRUIT_PALETTE: Palette = {
  o: "#6e1f1c",
  r: "#e2533a",
  R: "#ff9a70",
  d: "#b8382c",
  g: "#4f9a3a",
};

const APPLE = spriteFromRows(
  ["...g..", ".orro.", "orRrro", "orrrdo", "orrddo", ".oooo."],
  FRUIT_PALETTE,
  "apple",
);

/** One fruit hanging in a tree canopy. */
const TREE_FRUIT = spriteFromRows(["oro.", "rRro", "rrdo", "odo."], FRUIT_PALETTE, "tree_fruit");

function pile(count: 1 | 2 | 3): PixelSprite {
  const out = emptySprite(12, 10);
  if (count === 1) {
    blit(out, APPLE, 3, 3);
  } else if (count === 2) {
    blit(out, APPLE, 0, 3);
    blit(out, APPLE, 6, 4);
  } else {
    blit(out, APPLE, 3, 0);
    blit(out, APPLE, 0, 4);
    blit(out, APPLE, 6, 4);
  }
  return out;
}

const CANTEEN = spriteFromRows(
  [
    "...oo...",
    "..obbo..",
    "..oooo..",
    ".ommmmo.",
    "ommMmmmo",
    "omMmmmno",
    "ommmmmno",
    "ommmmnno",
    ".onnnno.",
    "..oooo..",
  ],
  { o: "#2f3f4a", b: "#8a5a34", m: "#7fa9c0", M: "#d2eaf4", n: "#557d94" },
  "canteen",
);

const BUBBLE_ROWS = [
  "..ooooooo..",
  ".owwwwwwwo.",
  "owwwwwwwwwo",
  "owwwwwwwwwo",
  "owwwwwwwwwo",
  "owwwwwwwwwo",
  "owwwwwwwwwo",
  ".owwwwwwwo.",
  "..ooowwoo..",
  "....owo....",
  ".....o.....",
];
const BUBBLE_PALETTE: Palette = { o: "#3a2a22", w: "#fffaf0" };

const ICON_PALETTE: Palette = {
  z: "#4a6fb5",
  a: "#3d9fd6",
  A: "#bfe8fb",
  r: "#e2533a",
  R: "#ff9a70",
  g: "#4f9a3a",
  x: "#d23a2e",
  k: "#3a2a22",
  y: "#c98a1c",
};

/** 5x5 icons shown inside a bubble. */
const ICONS = {
  sleep: ["zzzzz", "...z.", "..z..", ".z...", "zzzzz"],
  water: ["..a..", ".aaa.", "aAaaa", "aaaaa", ".aaa."],
  fruit: ["..g..", ".rrr.", "rRrrr", "rrrrr", ".rrr."],
  fail: [".xxx.", ".xxx.", "..x..", ".....", "..x.."],
  rest: [".....", ".....", "k.k.k", ".....", "....."],
  talk: ["kkkkk", ".....", "kkk..", ".....", "kkkk."],
  hand: ["..y..", ".yyy.", "y.y.y", "..y..", "..y.."],
} as const;

export type EmoteName = keyof typeof ICONS;
export const EMOTE_NAMES = Object.keys(ICONS) as EmoteName[];

function bubble(icon: EmoteName): PixelSprite {
  const out = spriteFromRows(BUBBLE_ROWS, BUBBLE_PALETTE, "bubble");
  blit(out, spriteFromRows(ICONS[icon], ICON_PALETTE, `icon/${icon}`), 3, 2);
  return out;
}

const cache = new Map<string, PixelSprite>();

function cached(key: string, make: () => PixelSprite): PixelSprite {
  let s = cache.get(key);
  if (s === undefined) {
    s = make();
    cache.set(key, s);
  }
  return s;
}

/** Ground fruit pile: one, two, or three-or-more fruit. The exact number is a text badge. */
export function groundFruitKey(quantity: number): string {
  return `item/fruit_${Math.min(3, Math.max(1, Math.trunc(quantity)))}`;
}

export const CANTEEN_KEY = "item/canteen";
export const TREE_FRUIT_KEY = "item/tree_fruit";
export const APPLE_KEY = "item/apple";

export function emoteKey(name: EmoteName): string {
  return `emote/${name}`;
}

export function objectSprite(key: string): PixelSprite | null {
  switch (key) {
    case "item/fruit_1":
      return cached(key, () => pile(1));
    case "item/fruit_2":
      return cached(key, () => pile(2));
    case "item/fruit_3":
      return cached(key, () => pile(3));
    case CANTEEN_KEY:
      return CANTEEN;
    case TREE_FRUIT_KEY:
      return TREE_FRUIT;
    case APPLE_KEY:
      return APPLE;
  }
  if (key.startsWith("emote/")) {
    const name = key.slice("emote/".length) as EmoteName;
    if (name in ICONS) return cached(key, () => bubble(name));
  }
  return null;
}
