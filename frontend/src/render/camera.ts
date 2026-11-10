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

/** Closest zoom: one tile is at most this many screen pixels (6x the 16-pixel tile art). */
export const MAX_TILE_SCREEN_PX = 96;

/** Zoom factor of one step of the zoom buttons and of a double click. */
export const ZOOM_STEP = 1.5;

/** Fit-to-view base tile size: min(panelWidth / map.width, panelHeight / map.height). */
export function baseTileSize(view: Viewport, map: MapSize): number {
  return Math.min(view.width / map.width, view.height / map.height);
}

/** Largest zoom multiplier for this viewport. Never below 1, so the fit view always exists. */
export function maxZoom(view: Viewport, map: MapSize): number {
  return Math.max(1, MAX_TILE_SCREEN_PX / baseTileSize(view, map));
}

export function clampZoom(view: Viewport, map: MapSize, zoom: number): number {
  if (!Number.isFinite(zoom)) return 1;
  return Math.min(maxZoom(view, map), Math.max(1, zoom));
}

/**
 * Pan is the offset of the map centre from the viewport centre. It is clamped so the map
 * always covers the viewport centre: any tile can be brought to the middle of the view (also
 * past a floating panel), and the map can never be dragged out of sight.
 */
function axisOffset(view: number, content: number, pan: number): number {
  const p = Number.isFinite(pan) ? pan : 0;
  return view / 2 - content / 2 + Math.min(content / 2, Math.max(-content / 2, p));
}

/** Clamps camera bounds (never entity positions). Pan (0, 0) centres the map. */
export function layoutFor(view: Viewport, map: MapSize, camera: Camera): Layout {
  const tile = baseTileSize(view, map) * clampZoom(view, map, camera.zoom);
  return {
    tile,
    offsetX: axisOffset(view.width, map.width * tile, camera.panX),
    offsetY: axisOffset(view.height, map.height * tile, camera.panY),
  };
}

/** The pan a layout corresponds to (the inverse of `layoutFor` for an in-range layout). */
export function panOf(view: Viewport, map: MapSize, layout: Layout): { panX: number; panY: number } {
  return {
    panX: layout.offsetX - (view.width / 2 - (map.width * layout.tile) / 2),
    panY: layout.offsetY - (view.height / 2 - (map.height * layout.tile) / 2),
  };
}

export function panNeeded(view: Viewport, map: MapSize, zoom: number): boolean {
  const tile = baseTileSize(view, map) * clampZoom(view, map, zoom);
  return map.width * tile > view.width + 1e-9 || map.height * tile > view.height + 1e-9;
}

/** Pan values that centre a tile position in the view, before clamping. Fractions allowed. */
export function panToCentre(map: MapSize, tile: number, x: number, y: number): [number, number] {
  return [(map.width / 2 - (x + 0.5)) * tile, (map.height / 2 - (y + 0.5)) * tile];
}

/** Applies a drag delta and returns the clamped pan, so the camera never leaves the content. */
export function dragPan(
  view: Viewport,
  map: MapSize,
  camera: Camera,
  dx: number,
  dy: number,
): { panX: number; panY: number } {
  const current = panOf(view, map, layoutFor(view, map, camera));
  const next = layoutFor(view, map, { ...camera, panX: current.panX + dx, panY: current.panY + dy });
  return panOf(view, map, next);
}

/**
 * Zooms by `factor` while keeping the map point under screen position (px, py) in place, as
 * far as the clamps allow. Used by the wheel, pinch, double click and the zoom buttons.
 */
export function zoomAt(
  view: Viewport,
  map: MapSize,
  camera: Camera,
  factor: number,
  px: number,
  py: number,
): { zoom: number; panX: number; panY: number } {
  const before = layoutFor(view, map, camera);
  const zoom = clampZoom(view, map, clampZoom(view, map, camera.zoom) * factor);
  const tile = baseTileSize(view, map) * zoom;
  const worldX = (px - before.offsetX) / before.tile;
  const worldY = (py - before.offsetY) / before.tile;
  const wanted: Layout = { tile, offsetX: px - worldX * tile, offsetY: py - worldY * tile };
  const pan = panOf(view, map, wanted);
  const clamped = panOf(view, map, layoutFor(view, map, { ...camera, zoom, ...pan }));
  return { zoom, ...clamped };
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
