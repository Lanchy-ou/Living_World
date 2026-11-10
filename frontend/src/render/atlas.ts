// Browser-side image cache: turns pixel sprites and the terrain layer into canvases once, so
// each animation frame only issues drawImage calls. Display cache only; holds no world state.
import { spriteByKey } from "./assets/index.ts";
import type { PixelSprite } from "./assets/pixels.ts";
import type { SpriteImages, TerrainImage } from "./drawFrame.ts";
import type { MapLike } from "./terrainLayer.ts";
import { buildTerrainLayer, terrainTilePx } from "./terrainLayer.ts";

export function spriteToCanvas(sprite: PixelSprite): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = sprite.width;
  canvas.height = sprite.height;
  const ctx = canvas.getContext("2d");
  if (ctx !== null) {
    const image = ctx.createImageData(sprite.width, sprite.height);
    image.data.set(sprite.data);
    ctx.putImageData(image, 0, 0);
  }
  return canvas;
}

const spriteCanvases = new Map<string, HTMLCanvasElement | null>();

/** Sprite canvases by key, built on first use. An unknown key gives null. */
export const spriteImages: SpriteImages = {
  get(key: string): CanvasImageSource | null {
    let canvas = spriteCanvases.get(key);
    if (canvas === undefined) {
      const sprite = spriteByKey(key);
      canvas = sprite === null ? null : spriteToCanvas(sprite);
      spriteCanvases.set(key, canvas);
    }
    return canvas;
  },
};

/** The two ambient frames of the terrain layer for one map. */
export interface TerrainFrames {
  frames: [TerrainImage, TerrainImage];
}

export function buildTerrainFrames(map: MapLike): TerrainFrames {
  const tilePx = terrainTilePx(map);
  const first = { image: spriteToCanvas(buildTerrainLayer(map, 0)), tilePx };
  // The flat fallback has no shimmer, so both frames are the same image.
  const second = tilePx === 16 ? { image: spriteToCanvas(buildTerrainLayer(map, 1)), tilePx } : first;
  return { frames: [first, second] };
}
