// Explicit display theme. The bundle carries terrain names only; colours live here and carry
// no rules. Colour is never the only cue: residents also get a letter.
import type { ReplayBundle } from "../replay/types.ts";

type Terrain = ReplayBundle["map"]["terrain_legend"][number]["terrain"];

export const TERRAIN_COLOURS: Record<Terrain, string> = {
  sea: "#2f6fa8",
  beach: "#e6d79a",
  grass: "#8fc272",
  woods: "#3f7d43",
  rock: "#7b7b7b",
  spring: "#4fc3e8",
  cave: "#4a3b32",
  fruit_tree: "#2f6a3a",
  damp_moss: "#5f7f52",
};

export const RESIDENT_COLOURS = [
  "#d6402b",
  "#1f6feb",
  "#e0a100",
  "#8a3ffc",
  "#0f9d7a",
  "#d9488a",
  "#555555",
  "#ff7a00",
] as const;

export interface ResidentStyle {
  colour: string;
  letter: string;
}

/** Stable: depends only on the resident's index in the declared (ID-sorted) list. */
export function residentStyle(index: number): ResidentStyle {
  return {
    colour: RESIDENT_COLOURS[index % RESIDENT_COLOURS.length] as string,
    letter: String.fromCharCode(65 + (index % 26)),
  };
}

export const NIGHT_OVERLAY = "rgba(10, 15, 50, 0.38)";
export const FRUIT_COLOUR = "#d94b3a";
export const CANTEEN_COLOUR = "#f2c14e";
export const CORPSE_COLOUR = "#222222";

/** Fixed legend entries shown beside the map. */
export const LEGEND_OBJECTS: { label: string; colour: string }[] = [
  { label: "Ground fruit", colour: FRUIT_COLOUR },
  { label: "Ground canteen", colour: CANTEEN_COLOUR },
  { label: "Corpse", colour: CORPSE_COLOUR },
];
