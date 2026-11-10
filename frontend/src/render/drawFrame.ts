// Pure Canvas painting of one scene. No hidden state, no randomness, no network: the output
// depends only on the arguments. `buildScene` decides what goes where; this file paints it in
// the fixed layer order of `SCENE_LAYERS`.
import type { DisplayFrame, ReplayBundle } from "../replay/types.ts";
import type { Layout } from "./camera.ts";
import { buildScene, computeSprites } from "./scene.ts";
import type { Label, Rect, Scene, SceneLayer } from "./scene.ts";
import { terrainGrid } from "./terrainLayer.ts";
import {
  BACKDROP_COLOUR,
  CORPSE_COLOUR,
  FRUIT_COLOUR,
  INK,
  LABEL_FONT,
  MAP_EDGE_COLOUR,
  NIGHT_OVERLAY,
  PAPER,
  TERRAIN_COLOURS,
} from "./theme.ts";

export { computeSprites };
export type { Sprite, SpriteKind } from "./scene.ts";

export type Ctx2D = Pick<
  CanvasRenderingContext2D,
  | "fillStyle"
  | "strokeStyle"
  | "lineWidth"
  | "font"
  | "textAlign"
  | "textBaseline"
  | "globalAlpha"
  | "imageSmoothingEnabled"
  | "fillRect"
  | "strokeRect"
  | "beginPath"
  | "arc"
  | "fill"
  | "stroke"
  | "moveTo"
  | "lineTo"
  | "fillText"
  | "clearRect"
  | "drawImage"
>;

/** Sprite images by key. Missing images fall back to simple shapes, so drawing never fails. */
export interface SpriteImages {
  get(key: string): CanvasImageSource | null;
}

/** The cached static terrain layer for the bundle's map. */
export interface TerrainImage {
  image: CanvasImageSource;
  /** Source pixels per tile in `image`. */
  tilePx: number;
}

export interface DrawOptions {
  selectedResidentId: string | null;
  /** 0..1 through the display beat of this tick; 1 (default) draws recorded positions. */
  progress?: number;
  images?: SpriteImages;
  terrain?: TerrainImage | null;
  /** Device pixels per CSS pixel, used only to choose image smoothing. */
  pixelRatio?: number;
  /** Called as each layer starts. For tests of the layer order; has no effect on drawing. */
  onLayer?: (layer: SceneLayer) => void;
}

const snap = (v: number): number => Math.round(v);

function drawTerrain(
  ctx: Ctx2D,
  bundle: ReplayBundle,
  layout: Layout,
  view: { width: number; height: number },
  options: DrawOptions,
): void {
  const { width, height } = bundle.map;
  const tile = layout.tile;
  ctx.fillStyle = BACKDROP_COLOUR;
  ctx.fillRect(0, 0, view.width, view.height);
  const terrain = options.terrain ?? null;
  if (terrain !== null) {
    // Pixel art stays crisp when enlarged; it is smoothed only when shrunk below 1:1.
    ctx.imageSmoothingEnabled = tile * (options.pixelRatio ?? 1) < terrain.tilePx;
    ctx.drawImage(terrain.image, layout.offsetX, layout.offsetY, width * tile, height * tile);
  } else {
    // No image yet (or no canvas support in tests): flat tiles from the same legend.
    const grid = terrainGrid(bundle.map);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const t = grid[y * width + x] ?? null;
        ctx.fillStyle = t === null ? "#ff00ff" : TERRAIN_COLOURS[t];
        ctx.fillRect(layout.offsetX + x * tile, layout.offsetY + y * tile, tile + 0.5, tile + 0.5);
      }
    }
  }
  // The edge of the recorded map: everything outside it is backdrop, not world.
  ctx.strokeStyle = MAP_EDGE_COLOUR;
  ctx.lineWidth = 1;
  ctx.strokeRect(snap(layout.offsetX) + 0.5, snap(layout.offsetY) + 0.5, snap(width * tile), snap(height * tile));
}

function drawImageOrShape(ctx: Ctx2D, images: SpriteImages | undefined, key: string, r: Rect, fallback: string): void {
  const image = images?.get(key) ?? null;
  if (image !== null) {
    ctx.drawImage(image, snap(r.x), snap(r.y), snap(r.w), snap(r.h));
    return;
  }
  ctx.fillStyle = fallback;
  ctx.beginPath();
  ctx.arc(r.x + r.w / 2, r.y + r.h / 2, Math.min(r.w, r.h) / 2, 0, Math.PI * 2);
  ctx.fill();
}

/** A pill with stepped corners, in keeping with the pixel art. */
function pill(ctx: Ctx2D, x: number, y: number, w: number, h: number): void {
  ctx.fillRect(x + 1, y, w - 2, h);
  ctx.fillRect(x, y + 1, w, h - 2);
}

function drawLabel(ctx: Ctx2D, label: Label): void {
  const small = label.kind === "tree_stock" || label.kind === "quantity";
  const fontPx = small ? 10 : 11;
  const h = small ? 13 : 15;
  const w = Math.max(h, label.text.length * (fontPx * 0.62) + 8);
  const x = snap(label.x - w / 2);
  const y = snap(label.y - h / 2);
  ctx.font = `700 ${fontPx}px ${LABEL_FONT}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  if (small) {
    ctx.globalAlpha = label.dim ? 0.6 : 1;
    ctx.fillStyle = INK;
    pill(ctx, x, y, w, h);
    ctx.fillStyle = PAPER;
    ctx.fillText(label.text, x + w / 2, y + h / 2 + 0.5);
    ctx.globalAlpha = 1;
    return;
  }
  // Resident and corpse tags: a border in the resident's colour around the letter. A selected
  // tag is filled. A corpse tag is grey and its text ends in a cross mark (set by the scene),
  // so it never depends on colour alone.
  const corpse = label.kind === "corpse_tag";
  ctx.fillStyle = corpse ? CORPSE_COLOUR : label.selected ? INK : label.colour;
  pill(ctx, x - 2, y - 2, w + 4, h + 4);
  ctx.fillStyle = label.selected && !corpse ? label.colour : PAPER;
  pill(ctx, x, y, w, h);
  ctx.fillStyle = corpse ? CORPSE_COLOUR : INK;
  ctx.fillText(label.text, x + w / 2, y + h / 2 + 0.5);
}

function corners(ctx: Ctx2D, r: Rect, arm: number): void {
  const x0 = r.x;
  const y0 = r.y;
  const x1 = r.x + r.w;
  const y1 = r.y + r.h;
  ctx.beginPath();
  ctx.moveTo(x0, y0 + arm);
  ctx.lineTo(x0, y0);
  ctx.lineTo(x0 + arm, y0);
  ctx.moveTo(x1 - arm, y0);
  ctx.lineTo(x1, y0);
  ctx.lineTo(x1, y0 + arm);
  ctx.moveTo(x1, y1 - arm);
  ctx.lineTo(x1, y1);
  ctx.lineTo(x1 - arm, y1);
  ctx.moveTo(x0 + arm, y1);
  ctx.lineTo(x0, y1);
  ctx.lineTo(x0, y1 - arm);
  ctx.stroke();
}

function drawSelection(ctx: Ctx2D, selection: NonNullable<Scene["selection"]>): void {
  // The recorded tile is outlined when it is large enough to see, so the sprite (which may be
  // drawn larger than its tile) is never mistaken for the position itself.
  if (selection.tile.w >= 20) {
    ctx.strokeStyle = "rgba(255, 250, 240, 0.75)";
    ctx.lineWidth = 1;
    ctx.strokeRect(snap(selection.tile.x) + 0.5, snap(selection.tile.y) + 0.5, snap(selection.tile.w), snap(selection.tile.h));
  }
  const pad = 4;
  const r = {
    x: snap(selection.rect.x) - pad,
    y: snap(selection.rect.y) - pad,
    w: snap(selection.rect.w) + pad * 2,
    h: snap(selection.rect.h) + pad * 2,
  };
  const arm = Math.max(5, Math.min(r.w, r.h) * 0.28);
  ctx.strokeStyle = INK;
  ctx.lineWidth = 4;
  corners(ctx, r, arm);
  ctx.strokeStyle = PAPER;
  ctx.lineWidth = 2;
  corners(ctx, r, arm);
}

export function drawFrame(
  ctx: Ctx2D,
  bundle: ReplayBundle,
  frame: DisplayFrame,
  layout: Layout,
  view: { width: number; height: number },
  options: DrawOptions,
): void {
  const layer = (name: SceneLayer) => options.onLayer?.(name);
  const scene = buildScene(bundle, frame, layout, {
    progress: options.progress ?? 1,
    selectedResidentId: options.selectedResidentId,
  });
  ctx.clearRect(0, 0, view.width, view.height);

  layer("terrain");
  drawTerrain(ctx, bundle, layout, view, options);

  // Everything above the terrain is sprite art drawn at whole or enlarged sizes: keep it crisp.
  ctx.imageSmoothingEnabled = false;

  layer("tree_fruit");
  for (const f of scene.treeFruit) drawImageOrShape(ctx, options.images, f.image, f.rect, FRUIT_COLOUR);

  layer("corpse");
  for (const s of scene.sprites) {
    if (s.kind === "corpse") drawImageOrShape(ctx, options.images, s.image, s.rect, s.colour);
  }

  layer("ground_item");
  for (const s of scene.sprites) {
    if (s.kind === "ground_fruit" || s.kind === "ground_canteen") {
      drawImageOrShape(ctx, options.images, s.image, s.rect, s.colour);
    }
  }

  layer("resident");
  for (const s of scene.sprites) {
    if (s.kind === "resident") drawImageOrShape(ctx, options.images, s.image, s.rect, s.colour);
  }

  layer("night");
  if (scene.night) {
    ctx.fillStyle = NIGHT_OVERLAY;
    ctx.fillRect(0, 0, view.width, view.height);
  }

  layer("emote");
  for (const e of scene.emotes) drawImageOrShape(ctx, options.images, e.image, e.rect, PAPER);

  layer("label");
  for (const l of scene.labels) drawLabel(ctx, l);

  layer("selection");
  if (scene.selection !== null) drawSelection(ctx, scene.selection);
}
