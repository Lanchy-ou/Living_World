// Scene layout: what to draw for one recorded frame and where, as plain data. Pure and
// testable without a canvas. `drawFrame` paints a scene; `MapCanvas` hit-tests it.
//
// Recorded tile coordinates are never altered. Each sprite keeps its recorded tile
// (`tileX`, `tileY`) and an anchor (`cx`, `cy`) that lies inside that tile when at rest; the
// drawn rectangle may be larger than the tile or fanned out so sprites stay readable.
import { activityOf } from "../panels/activityView.ts";
import { isNight } from "../replay/clock.ts";
import type { DisplayFrame, ReplayBundle } from "../replay/types.ts";
import { CANTEEN_KEY, TREE_FRUIT_KEY, emoteKey, groundFruitKey } from "./assets/objectArt.ts";
import {
  RESIDENT_HEIGHT,
  RESIDENT_WIDTH,
  corpseSpriteKey,
  residentLook,
  residentSpriteKey,
} from "./assets/residentArt.ts";
import type { ResidentFrameName } from "./assets/residentArt.ts";
import { FRUIT_SLOTS } from "./assets/terrainArt.ts";
import type { Layout } from "./camera.ts";
import { facingAt, pathInto, poseAt } from "./motion.ts";
import { FRUIT_TREE_OFFSET, TILE_PX, terrainTilePx } from "./terrainLayer.ts";
import { CANTEEN_COLOUR, CORPSE_COLOUR, FRUIT_COLOUR } from "./theme.ts";

/**
 * Draw order, bottom to top. Ground items sit above corpses, so what a dead resident dropped
 * stays visible. Labels and selection sit above the night tint to stay readable.
 */
export const SCENE_LAYERS = [
  "terrain",
  "tree_fruit",
  "corpse",
  "ground_item",
  "resident",
  "night",
  "emote",
  "label",
  "selection",
] as const;
export type SceneLayer = (typeof SCENE_LAYERS)[number];

/**
 * Smallest sprite scale in screen pixels per art pixel. At island scale a tile is smaller
 * than this allows, so residents and ground items are drawn larger than their tile, anchored
 * on it, to stay visible.
 */
export const MIN_ENTITY_SCALE = 2;

export type SpriteKind = "resident" | "ground_fruit" | "ground_canteen" | "corpse";

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Sprite {
  kind: SpriteKind;
  /** Resident ID, corpse ID, or a descriptive key for ground objects. */
  id: string;
  /** Recorded tile coordinates; never altered by offsets, zoom, pan or interpolation. */
  tileX: number;
  tileY: number;
  /** Anchor on screen (display only). Inside the recorded tile when at rest. */
  cx: number;
  cy: number;
  /** Drawn rectangle in screen pixels. */
  rect: Rect;
  /** Sprite key (see assets/index.ts). */
  image: string;
  /** Letter for residents and corpses; quantity for ground objects. */
  label: string;
  colour: string;
  /** The resident this sprite stands for (residents and corpses), else null. */
  residentId: string | null;
}

export interface TreeFruit {
  treeId: string;
  tileX: number;
  tileY: number;
  rect: Rect;
  image: string;
}

export type LabelKind = "tree_stock" | "quantity" | "tag" | "corpse_tag";

export interface Label {
  kind: LabelKind;
  id: string;
  text: string;
  /** Centre of the label on screen. */
  x: number;
  y: number;
  colour: string;
  selected: boolean;
  /** Drawn fainter: an empty tree. */
  dim: boolean;
}

export interface Emote {
  residentId: string;
  image: string;
  rect: Rect;
}

export interface Scene {
  treeFruit: TreeFruit[];
  sprites: Sprite[];
  emotes: Emote[];
  labels: Label[];
  night: boolean;
  selection: { rect: Rect; tile: Rect } | null;
}

export interface SceneOptions {
  /** 0..1 through the display beat of this tick; 1 (default) draws the recorded positions. */
  progress?: number;
  selectedResidentId?: string | null;
}

function residentIndex(bundle: ReplayBundle, id: string): number {
  return bundle.residents.findIndex((r) => r.id === id);
}

export function entityScale(layout: Layout): number {
  return Math.max(layout.tile / TILE_PX, MIN_ENTITY_SCALE);
}

function groupByTile<T>(items: T[], tileOf: (item: T) => { x: number; y: number }): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const { x, y } = tileOf(item);
    const key = `${x},${y}`;
    const list = groups.get(key);
    if (list) list.push(item);
    else groups.set(key, [item]);
  }
  return groups;
}

/**
 * Sprites for ground items, corpses and living residents; `drawFrame` paints them by layer.
 * Items on one tile get distinct anchors inside it; their recorded coordinates are untouched.
 */
export function computeSprites(
  bundle: ReplayBundle,
  frame: DisplayFrame,
  layout: Layout,
  options: SceneOptions = {},
): Sprite[] {
  const tile = layout.tile;
  const s = entityScale(layout);
  const centre = (x: number, y: number) => ({
    x: layout.offsetX + (x + 0.5) * tile,
    y: layout.offsetY + (y + 0.5) * tile,
  });
  const sprites: Sprite[] = [];

  for (const g of frame.ground_fruit) {
    const c = centre(g.position.x, g.position.y);
    const w = 12 * s;
    const h = 10 * s;
    const drawCx = c.x - Math.max(0.22 * tile, 0.4 * w);
    const cy = c.y + 0.25 * tile;
    sprites.push({
      kind: "ground_fruit",
      id: `fruit@${g.position.x},${g.position.y}`,
      tileX: g.position.x,
      tileY: g.position.y,
      cx: c.x - 0.22 * tile,
      cy,
      rect: { x: drawCx - w / 2, y: cy - h * 0.75, w, h },
      image: groundFruitKey(g.quantity),
      label: String(g.quantity),
      colour: FRUIT_COLOUR,
      residentId: null,
    });
  }
  if (frame.ground_canteen !== null) {
    const g = frame.ground_canteen;
    const c = centre(g.position.x, g.position.y);
    const w = 8 * s;
    const h = 10 * s;
    const drawCx = c.x + Math.max(0.22 * tile, 0.55 * w);
    const cy = c.y + 0.25 * tile;
    sprites.push({
      kind: "ground_canteen",
      id: "canteen",
      tileX: g.position.x,
      tileY: g.position.y,
      cx: c.x + 0.22 * tile,
      cy,
      rect: { x: drawCx - w / 2, y: cy - h * 0.75, w, h },
      image: CANTEEN_KEY,
      label: String(g.servings),
      colour: CANTEEN_COLOUR,
      residentId: null,
    });
  }

  for (const group of groupByTile(frame.corpses, (c) => c.position).values()) {
    group.forEach((corpse, k) => {
      const index = residentIndex(bundle, corpse.resident_id);
      const c = centre(corpse.position.x, corpse.position.y);
      const w = RESIDENT_HEIGHT * s;
      const h = RESIDENT_WIDTH * s;
      const fan = k - (group.length - 1) / 2;
      const inTile = (0.4 / Math.max(1, group.length - 1)) * tile;
      const cx = c.x + fan * inTile;
      const cy = c.y + 0.12 * tile;
      const drawCx = c.x + fan * Math.max(inTile, 0.7 * w);
      sprites.push({
        kind: "corpse",
        id: corpse.id,
        tileX: corpse.position.x,
        tileY: corpse.position.y,
        cx,
        cy,
        rect: { x: drawCx - w / 2, y: cy - h * 0.6, w, h },
        image: corpseSpriteKey(Math.max(0, index)),
        label: residentLook(index).letter,
        colour: CORPSE_COLOUR,
        residentId: corpse.resident_id,
      });
    });
  }

  // The corpse stands for a dead resident, so only living residents are drawn as residents.
  const living = frame.residents.filter((r) => r.alive);
  const residents: Sprite[] = [];
  for (const group of groupByTile(living, (r) => r.position).values()) {
    group.forEach((r, k) => {
      const index = residentIndex(bundle, r.id);
      // At rest the frame passed in is the only source of the position. The pose (which reads
      // the previous frame and this tick's move events) is used only while sliding.
      const progress = options.progress ?? 1;
      const sliding = progress < 1 ? poseAt(bundle, frame.tick, r.id, progress) : null;
      const at =
        sliding !== null && sliding.moving
          ? sliding
          : { x: r.position.x, y: r.position.y, facing: facingAt(bundle, frame.tick, r.id), moving: false };
      const c = centre(at.x, at.y);
      const w = RESIDENT_WIDTH * s;
      const h = RESIDENT_HEIGHT * s;
      const fan = k - (group.length - 1) / 2;
      const inTile = (0.56 / Math.max(1, group.length - 1)) * tile;
      const cy = c.y + 0.3 * tile;
      const drawCx = c.x + fan * Math.max(inTile, 0.62 * w);
      let frameName: ResidentFrameName = "idle";
      if (at.moving) {
        const steps = pathInto(bundle, frame.tick, r.id).length - 1;
        const along = Math.min(1, Math.max(0, progress)) * steps;
        frameName = Math.floor(along * 2) % 2 === 0 ? "walk_a" : "walk_b";
      }
      residents.push({
        kind: "resident",
        id: r.id,
        tileX: r.position.x,
        tileY: r.position.y,
        cx: c.x + fan * inTile,
        cy,
        rect: { x: drawCx - w / 2, y: cy - h + s, w, h },
        image: residentSpriteKey(Math.max(0, index), at.facing, frameName),
        label: residentLook(index).letter,
        colour: residentLook(index).colour,
        residentId: r.id,
      });
    });
  }
  // Lower on screen draws later, so a resident in front overlaps one behind.
  residents.sort((a, b) => a.cy - b.cy || a.id.localeCompare(b.id));
  sprites.push(...residents);
  return sprites;
}

function treeFruitOf(frame: DisplayFrame, layout: Layout): TreeFruit[] {
  const ts = layout.tile / TILE_PX;
  const out: TreeFruit[] = [];
  for (const t of frame.fruit_trees) {
    const left = layout.offsetX + t.position.x * layout.tile;
    const top = layout.offsetY + t.position.y * layout.tile;
    const shown = Math.min(Math.max(0, t.stock), FRUIT_SLOTS.length);
    for (let k = 0; k < shown; k++) {
      const [sx, sy] = FRUIT_SLOTS[k] as readonly [number, number];
      out.push({
        treeId: t.id,
        tileX: t.position.x,
        tileY: t.position.y,
        rect: {
          x: left + (FRUIT_TREE_OFFSET.x + sx) * ts,
          y: top + (FRUIT_TREE_OFFSET.y + sy) * ts,
          w: 4 * ts,
          h: 4 * ts,
        },
        image: TREE_FRUIT_KEY,
      });
    }
  }
  return out;
}

/** The whole scene for one frame. Reads only the bundle, the frame and the view. */
export function buildScene(
  bundle: ReplayBundle,
  frame: DisplayFrame,
  layout: Layout,
  options: SceneOptions = {},
): Scene {
  const selectedId = options.selectedResidentId ?? null;
  const fullDetail = terrainTilePx(bundle.map) === TILE_PX;
  const ts = layout.tile / TILE_PX;
  const sprites = computeSprites(bundle, frame, layout, options);
  const labels: Label[] = [];

  for (const t of frame.fruit_trees) {
    const left = layout.offsetX + t.position.x * layout.tile;
    const top = layout.offsetY + t.position.y * layout.tile;
    labels.push({
      kind: "tree_stock",
      id: t.id,
      text: String(t.stock),
      x: fullDetail ? left + (TILE_PX / 2 + 9) * ts : left + layout.tile / 2,
      y: fullDetail ? top + (FRUIT_TREE_OFFSET.y + 4) * ts : top + layout.tile / 2,
      colour: FRUIT_COLOUR,
      selected: false,
      dim: t.stock === 0,
    });
  }

  const emotes: Emote[] = [];
  const es = Math.max(ts * 0.75, MIN_ENTITY_SCALE);
  let selection: Scene["selection"] = null;
  for (const sp of sprites) {
    if (sp.kind === "ground_fruit" || sp.kind === "ground_canteen") {
      labels.push({
        kind: "quantity",
        id: sp.id,
        text: sp.label,
        x: sp.rect.x + sp.rect.w,
        y: sp.rect.y,
        colour: sp.colour,
        selected: false,
        dim: false,
      });
      continue;
    }
    const selected = sp.residentId !== null && sp.residentId === selectedId;
    labels.push({
      kind: sp.kind === "corpse" ? "corpse_tag" : "tag",
      id: sp.id,
      // A corpse tag carries a cross mark after the letter: a cue that does not rely on colour.
      text: sp.kind === "corpse" ? `${sp.label}×` : sp.label,
      x: sp.rect.x + sp.rect.w / 2,
      y: sp.rect.y - 9,
      colour: sp.colour,
      selected,
      dim: false,
    });
    if (selected) {
      selection = {
        rect: sp.rect,
        tile: {
          x: layout.offsetX + sp.tileX * layout.tile,
          y: layout.offsetY + sp.tileY * layout.tile,
          w: layout.tile,
          h: layout.tile,
        },
      };
    }
    if (sp.kind === "resident" && sp.residentId !== null) {
      const emote = activityOf(bundle, frame.tick, sp.residentId).emote;
      if (emote !== null) {
        emotes.push({
          residentId: sp.residentId,
          image: emoteKey(emote),
          rect: { x: sp.rect.x + sp.rect.w * 0.62, y: sp.rect.y - 11 * es * 0.72, w: 11 * es, h: 11 * es },
        });
      }
    }
  }

  return {
    treeFruit: fullDetail ? treeFruitOf(frame, layout) : [],
    sprites,
    emotes,
    labels,
    night: isNight(frame.tick, bundle.clock),
    selection,
  };
}

const TAG_HALF_WIDTH = 10;
const TAG_HALF_HEIGHT = 9;

/**
 * The resident under a screen point, topmost first: a resident sprite, a corpse, or one of
 * their letter tags. Returns the resident ID, or null. Pure hit testing on the drawn scene.
 */
export function residentAt(scene: Scene, px: number, py: number): string | null {
  const inRect = (r: Rect, pad: number) =>
    px >= r.x - pad && px <= r.x + r.w + pad && py >= r.y - pad && py <= r.y + r.h + pad;
  for (let i = scene.sprites.length - 1; i >= 0; i--) {
    const sp = scene.sprites[i] as Sprite;
    if (sp.residentId === null) continue;
    const tagX = sp.rect.x + sp.rect.w / 2;
    const tagY = sp.rect.y - 9;
    const onTag = Math.abs(px - tagX) <= TAG_HALF_WIDTH && Math.abs(py - tagY) <= TAG_HALF_HEIGHT;
    if (inRect(sp.rect, 2) || onTag) return sp.residentId;
  }
  return null;
}
