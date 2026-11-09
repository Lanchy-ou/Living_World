// Pure Canvas drawing from the current frame only. No hidden state, no randomness, no network.
// `computeSprites` is the geometry (testable without a canvas); `drawFrame` paints it.
import { isNight } from "../replay/clock.ts";
import type { DisplayFrame, ReplayBundle } from "../replay/types.ts";
import type { Layout } from "./camera.ts";
import { tileToScreen } from "./camera.ts";
import {
  CANTEEN_COLOUR,
  CORPSE_COLOUR,
  FRUIT_COLOUR,
  NIGHT_OVERLAY,
  TERRAIN_COLOURS,
  residentStyle,
} from "./theme.ts";

export type Ctx2D = Pick<
  CanvasRenderingContext2D,
  | "fillStyle"
  | "strokeStyle"
  | "lineWidth"
  | "font"
  | "textAlign"
  | "textBaseline"
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
>;

export type SpriteKind = "resident" | "ground_fruit" | "ground_canteen" | "corpse";

export interface Sprite {
  kind: SpriteKind;
  /** Resident ID, corpse ID, or a descriptive key for ground objects. */
  id: string;
  /** Recorded tile coordinates; never altered by offsets, zoom or pan. */
  tileX: number;
  tileY: number;
  /** Screen centre in pixels (display only). */
  cx: number;
  cy: number;
  /** Half-size in pixels. */
  radius: number;
  label: string;
  colour: string;
}

interface Item {
  kind: SpriteKind;
  id: string;
  x: number;
  y: number;
  label: string;
  colour: string;
}

function residentIndex(bundle: ReplayBundle, id: string): number {
  return bundle.residents.findIndex((r) => r.id === id);
}

function itemsOf(bundle: ReplayBundle, frame: DisplayFrame): Item[] {
  const items: Item[] = [];
  for (const c of frame.corpses) {
    const style = residentStyle(residentIndex(bundle, c.resident_id));
    items.push({ kind: "corpse", id: c.id, x: c.position.x, y: c.position.y, label: style.letter, colour: CORPSE_COLOUR });
  }
  for (const g of frame.ground_fruit) {
    items.push({
      kind: "ground_fruit",
      id: `fruit@${g.position.x},${g.position.y}`,
      x: g.position.x,
      y: g.position.y,
      label: String(g.quantity),
      colour: FRUIT_COLOUR,
    });
  }
  if (frame.ground_canteen !== null) {
    const c = frame.ground_canteen;
    items.push({
      kind: "ground_canteen",
      id: "canteen",
      x: c.position.x,
      y: c.position.y,
      label: String(c.servings),
      colour: CANTEEN_COLOUR,
    });
  }
  for (const r of frame.residents) {
    if (!r.alive) continue; // the corpse stands for a dead resident
    const style = residentStyle(residentIndex(bundle, r.id));
    items.push({ kind: "resident", id: r.id, x: r.position.x, y: r.position.y, label: style.letter, colour: style.colour });
  }
  return items;
}

/** Items on one tile share it in a small grid; their recorded coordinates are untouched. */
export function computeSprites(bundle: ReplayBundle, frame: DisplayFrame, layout: Layout): Sprite[] {
  const byTile = new Map<string, Item[]>();
  for (const item of itemsOf(bundle, frame)) {
    const key = `${item.x},${item.y}`;
    const list = byTile.get(key);
    if (list) list.push(item);
    else byTile.set(key, [item]);
  }
  const sprites: Sprite[] = [];
  for (const list of byTile.values()) {
    const grid = Math.ceil(Math.sqrt(list.length));
    const cell = layout.tile / grid;
    list.forEach((item, i) => {
      const { left, top } = tileToScreen(layout, item.x, item.y);
      const col = i % grid;
      const row = Math.floor(i / grid);
      sprites.push({
        kind: item.kind,
        id: item.id,
        tileX: item.x,
        tileY: item.y,
        cx: left + (col + 0.5) * cell,
        cy: top + (row + 0.5) * cell,
        radius: cell * 0.4,
        label: item.label,
        colour: item.colour,
      });
    });
  }
  return sprites;
}

export interface DrawOptions {
  selectedResidentId: string | null;
}

function terrainOf(bundle: ReplayBundle): Map<string, keyof typeof TERRAIN_COLOURS> {
  return new Map(bundle.map.terrain_legend.map((e) => [e.symbol, e.terrain]));
}

export function drawFrame(
  ctx: Ctx2D,
  bundle: ReplayBundle,
  frame: DisplayFrame,
  layout: Layout,
  view: { width: number; height: number },
  options: DrawOptions,
): void {
  ctx.clearRect(0, 0, view.width, view.height);
  const terrain = terrainOf(bundle);
  const tile = layout.tile;
  bundle.map.rows.forEach((row, y) => {
    [...row].forEach((symbol, x) => {
      const t = terrain.get(symbol);
      const { left, top } = tileToScreen(layout, x, y);
      ctx.fillStyle = t === undefined ? "#ff00ff" : TERRAIN_COLOURS[t];
      ctx.fillRect(left, top, tile + 0.5, tile + 0.5);
    });
  });
  ctx.font = `bold ${Math.max(8, tile * 0.38)}px sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const t of frame.fruit_trees) {
    const { left, top } = tileToScreen(layout, t.position.x, t.position.y);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(String(t.stock), left + tile / 2, top + tile * 0.2);
  }
  for (const s of computeSprites(bundle, frame, layout)) {
    ctx.fillStyle = s.colour;
    if (s.kind === "ground_canteen") {
      ctx.fillRect(s.cx - s.radius, s.cy - s.radius, s.radius * 2, s.radius * 2);
    } else if (s.kind === "corpse") {
      ctx.strokeStyle = s.colour;
      ctx.lineWidth = Math.max(2, s.radius * 0.35);
      ctx.beginPath();
      ctx.moveTo(s.cx - s.radius, s.cy - s.radius);
      ctx.lineTo(s.cx + s.radius, s.cy + s.radius);
      ctx.moveTo(s.cx + s.radius, s.cy - s.radius);
      ctx.lineTo(s.cx - s.radius, s.cy + s.radius);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(s.cx, s.cy, s.radius, 0, Math.PI * 2);
      ctx.fill();
    }
    if (s.kind === "resident" && s.id === options.selectedResidentId) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(s.cx, s.cy, s.radius + 2, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.fillStyle = s.kind === "ground_canteen" ? "#000000" : "#ffffff";
    ctx.font = `bold ${Math.max(7, s.radius * 1.1)}px sans-serif`;
    ctx.fillText(s.label, s.cx, s.cy);
  }
  if (isNight(frame.tick, bundle.clock)) {
    ctx.fillStyle = NIGHT_OVERLAY;
    ctx.fillRect(layout.offsetX, layout.offsetY, bundle.map.width * tile, bundle.map.height * tile);
  }
}
