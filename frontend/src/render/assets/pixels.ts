// Pixel sprites as plain RGBA buffers. Everything here is pure data manipulation, so the art
// can be built and tested without a canvas. Sprites carry no rules and no world state.

export interface PixelSprite {
  width: number;
  height: number;
  /** RGBA bytes, row-major. Alpha is 0 or 255. */
  data: Uint8ClampedArray;
}

/** One character per pixel. `.` is always transparent; other characters map to `#rrggbb`. */
export type Palette = Readonly<Record<string, string>>;

export type Rgb = readonly [number, number, number];

export function hexToRgb(hex: string): Rgb {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (m === null) throw new Error(`bad colour ${hex}`);
  const n = Number.parseInt(m[1] as string, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function emptySprite(width: number, height: number): PixelSprite {
  return { width, height, data: new Uint8ClampedArray(width * height * 4) };
}

export function setPixel(s: PixelSprite, x: number, y: number, rgb: Rgb): void {
  if (x < 0 || y < 0 || x >= s.width || y >= s.height) return;
  const i = (y * s.width + x) * 4;
  s.data[i] = rgb[0];
  s.data[i + 1] = rgb[1];
  s.data[i + 2] = rgb[2];
  s.data[i + 3] = 255;
}

/** Builds a sprite from character rows. Throws on ragged rows or unknown characters. */
export function spriteFromRows(rows: readonly string[], palette: Palette, name = "sprite"): PixelSprite {
  const height = rows.length;
  const width = rows[0]?.length ?? 0;
  if (width === 0) throw new Error(`${name}: empty sprite`);
  const out = emptySprite(width, height);
  const cache = new Map<string, Rgb>();
  rows.forEach((row, y) => {
    if (row.length !== width) {
      throw new Error(`${name}: row ${y} is ${row.length} wide, expected ${width}`);
    }
    for (let x = 0; x < width; x++) {
      const ch = row[x] as string;
      if (ch === ".") continue;
      let rgb = cache.get(ch);
      if (rgb === undefined) {
        const hex = palette[ch];
        if (hex === undefined) throw new Error(`${name}: no colour for "${ch}" at ${x},${y}`);
        rgb = hexToRgb(hex);
        cache.set(ch, rgb);
      }
      setPixel(out, x, y, rgb);
    }
  });
  return out;
}

/** Copies opaque pixels of `src` onto `dst` at (x, y). Pixels outside `dst` are dropped. */
export function blit(dst: PixelSprite, src: PixelSprite, x: number, y: number): void {
  for (let sy = 0; sy < src.height; sy++) {
    const dy = y + sy;
    if (dy < 0 || dy >= dst.height) continue;
    for (let sx = 0; sx < src.width; sx++) {
      const dx = x + sx;
      if (dx < 0 || dx >= dst.width) continue;
      const si = (sy * src.width + sx) * 4;
      if (src.data[si + 3] === 0) continue;
      const di = (dy * dst.width + dx) * 4;
      dst.data[di] = src.data[si] as number;
      dst.data[di + 1] = src.data[si + 1] as number;
      dst.data[di + 2] = src.data[si + 2] as number;
      dst.data[di + 3] = 255;
    }
  }
}

/** Horizontal mirror, used for the left-facing view of a right-facing sprite. */
export function mirror(s: PixelSprite): PixelSprite {
  const out = emptySprite(s.width, s.height);
  for (let y = 0; y < s.height; y++) {
    for (let x = 0; x < s.width; x++) {
      const si = (y * s.width + x) * 4;
      const di = (y * s.width + (s.width - 1 - x)) * 4;
      out.data.set(s.data.subarray(si, si + 4), di);
    }
  }
  return out;
}

/** Quarter turn clockwise: the top of the source ends up on the right. */
export function rotateClockwise(s: PixelSprite): PixelSprite {
  const out = emptySprite(s.height, s.width);
  for (let y = 0; y < s.height; y++) {
    for (let x = 0; x < s.width; x++) {
      const si = (y * s.width + x) * 4;
      const dx = s.height - 1 - y;
      const dy = x;
      out.data.set(s.data.subarray(si, si + 4), (dy * out.width + dx) * 4);
    }
  }
  return out;
}

/** Recolours every opaque pixel. */
export function mapColours(s: PixelSprite, fn: (rgb: Rgb) => Rgb): PixelSprite {
  const out = emptySprite(s.width, s.height);
  for (let i = 0; i < s.data.length; i += 4) {
    if (s.data[i + 3] === 0) continue;
    const [r, g, b] = fn([s.data[i] as number, s.data[i + 1] as number, s.data[i + 2] as number]);
    out.data[i] = r;
    out.data[i + 1] = g;
    out.data[i + 2] = b;
    out.data[i + 3] = 255;
  }
  return out;
}

/** Pulls colours towards grey and a cool tone. Used for corpses, with a non-colour cue too. */
export function desaturate(s: PixelSprite, amount: number): PixelSprite {
  return mapColours(s, ([r, g, b]) => {
    const grey = 0.3 * r + 0.59 * g + 0.11 * b;
    const mix = (c: number, tint: number) => Math.round(c + (grey * tint - c) * amount);
    return [mix(r, 0.96), mix(g, 0.98), mix(b, 1.06)];
  });
}

/**
 * Deterministic integer hash to [0, 1). Display variation (tufts, tree shapes, wave marks) is
 * a pure function of tile or pixel coordinates; nothing here uses Math.random.
 */
export function hash01(x: number, y: number, seed = 0): number {
  let h = (Math.imul(x | 0, 0x27d4eb2d) ^ Math.imul(y | 0, 0x165667b1) ^ Math.imul(seed | 0, 0x9e3779b1)) | 0;
  h = Math.imul(h ^ (h >>> 15), 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}
