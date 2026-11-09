// Camera layout: pure display math. Floats here never feed back into data; entity positions
// are never changed, only the transform from tile coordinates to screen pixels.
import type { Camera } from "../replay/store.ts";

export interface Viewport {
  width: number;
  height: number;
}
export interface MapSize {
  width: number;
  height: number;
}
export interface Layout {
  /** Tile edge in screen pixels (display float). */
  tile: number;
  offsetX: number;
  offsetY: number;
}

/** Fit-to-view base tile size: min(panelWidth / map.width, panelHeight / map.height). */
export function baseTileSize(view: Viewport, map: MapSize): number {
  return Math.min(view.width / map.width, view.height / map.height);
}

function axisOffset(view: number, content: number, pan: number): number {
  if (content <= view) return (view - content) / 2;
  return Math.min(0, Math.max(view - content, pan));
}

/** Clamps camera bounds (never entity positions): content smaller than the view is centred. */
export function layoutFor(view: Viewport, map: MapSize, camera: Camera): Layout {
  const tile = baseTileSize(view, map) * camera.zoom;
  return {
    tile,
    offsetX: axisOffset(view.width, map.width * tile, camera.panX),
    offsetY: axisOffset(view.height, map.height * tile, camera.panY),
  };
}

export function panNeeded(view: Viewport, map: MapSize, zoom: number): boolean {
  const tile = baseTileSize(view, map) * zoom;
  return map.width * tile > view.width || map.height * tile > view.height;
}

/** Pan values that centre a tile in the view, before clamping. */
export function panToCentre(view: Viewport, tile: number, x: number, y: number): [number, number] {
  return [view.width / 2 - (x + 0.5) * tile, view.height / 2 - (y + 0.5) * tile];
}

/** Applies a drag delta and returns the clamped pan, so the camera never leaves the content. */
export function dragPan(
  view: Viewport,
  map: MapSize,
  camera: Camera,
  dx: number,
  dy: number,
): { panX: number; panY: number } {
  const current = layoutFor(view, map, camera);
  const next = layoutFor(view, map, {
    ...camera,
    panX: current.offsetX + dx,
    panY: current.offsetY + dy,
  });
  return { panX: next.offsetX, panY: next.offsetY };
}

export function tileToScreen(layout: Layout, x: number, y: number): { left: number; top: number } {
  return { left: layout.offsetX + x * layout.tile, top: layout.offsetY + y * layout.tile };
}

export function screenToTile(layout: Layout, px: number, py: number): { x: number; y: number } {
  return {
    x: Math.floor((px - layout.offsetX) / layout.tile),
    y: Math.floor((py - layout.offsetY) / layout.tile),
  };
}
