// Sprite lookup by key. Keys are the asset interface between the scene (which names what to
// draw) and the atlas (which turns sprites into canvases). See README.md in this directory.
import { objectSprite } from "./objectArt.ts";
import type { PixelSprite } from "./pixels.ts";
import type { Facing, ResidentFrameName } from "./residentArt.ts";
import { FACINGS, RESIDENT_FRAMES, corpseSprite, residentSprite } from "./residentArt.ts";

/**
 * Key grammar:
 *   resident/<index>/<down|up|left|right>/<idle|walk_a|walk_b>
 *   corpse/<index>
 *   item/<fruit_1|fruit_2|fruit_3|canteen|tree_fruit|apple>
 *   emote/<sleep|water|fruit|fail|rest|talk|hand>
 */
export function spriteByKey(key: string): PixelSprite | null {
  const parts = key.split("/");
  if (parts[0] === "resident" && parts.length === 4) {
    const index = Number(parts[1]);
    const facing = parts[2] as Facing;
    const frame = parts[3] as ResidentFrameName;
    if (!Number.isInteger(index) || index < 0) return null;
    if (!FACINGS.includes(facing) || !RESIDENT_FRAMES.includes(frame)) return null;
    return residentSprite(index, facing, frame);
  }
  if (parts[0] === "corpse" && parts.length === 2) {
    const index = Number(parts[1]);
    return Number.isInteger(index) && index >= 0 ? corpseSprite(index) : null;
  }
  return objectSprite(key);
}
