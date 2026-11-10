// Explicit display theme. The bundle carries terrain names only; colours and art live in the
// frontend and carry no rules. Colour is never the only cue: residents also get a letter.
import { residentLook } from "./assets/residentArt.ts";
import { FLAT_COLOURS } from "./terrainLayer.ts";

/** One flat colour per terrain, used for the fallback drawing and anywhere a swatch is enough. */
export const TERRAIN_COLOURS = FLAT_COLOURS;

export interface ResidentStyle {
  colour: string;
  letter: string;
}

/** Stable: depends only on the resident's index in the declared (ID-sorted) list. */
export function residentStyle(index: number): ResidentStyle {
  const look = residentLook(index);
  return { colour: look.colour, letter: look.letter };
}

/** Night is a flat tint over the map. It follows the frozen daylight interval exactly. */
export const NIGHT_OVERLAY = "rgba(18, 24, 78, 0.36)";
/** Backdrop outside the map rectangle: open sea, so the island sits in the viewport. */
export const BACKDROP_COLOUR = "#1c8fa6";
export const MAP_EDGE_COLOUR = "rgba(255, 255, 255, 0.18)";
export const FRUIT_COLOUR = "#e2533a";
export const CANTEEN_COLOUR = "#7fa9c0";
export const CORPSE_COLOUR = "#6f6a72";
export const INK = "#3a2a22";
export const PAPER = "#fffaf0";

export const LABEL_FONT = '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif';
