import { useEffect, useRef } from "react";
import type { PixelSprite } from "./assets/pixels.ts";

interface Props {
  sprite: PixelSprite;
  /** CSS pixels per art pixel. */
  scale: number;
  className?: string;
  /** Accessible name; omit for decoration. */
  label?: string;
}

/** Shows one pixel sprite, enlarged without smoothing. Used for portraits, chips and the legend. */
export function SpriteCanvas({ sprite, scale, className, label }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = ref.current;
    const ctx = el?.getContext("2d") ?? null;
    if (el === null || ctx === null) return;
    el.width = sprite.width;
    el.height = sprite.height;
    const image = ctx.createImageData(sprite.width, sprite.height);
    image.data.set(sprite.data);
    ctx.putImageData(image, 0, 0);
  }, [sprite]);
  return (
    <canvas
      ref={ref}
      className={`sprite ${className ?? ""}`}
      style={{ width: sprite.width * scale, height: sprite.height * scale }}
      role={label === undefined ? "presentation" : "img"}
      aria-label={label}
      aria-hidden={label === undefined ? true : undefined}
    />
  );
}
