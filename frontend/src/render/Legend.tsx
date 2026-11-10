import { useMemo } from "react";
import type { ReplayBundle } from "../replay/types.ts";
import type { EmoteName } from "./assets/objectArt.ts";
import { CANTEEN_KEY, emoteKey, groundFruitKey, objectSprite } from "./assets/objectArt.ts";
import type { PixelSprite } from "./assets/pixels.ts";
import { corpseSprite, residentSprite } from "./assets/residentArt.ts";
import { SpriteCanvas } from "./SpriteCanvas.tsx";
import { terrainSwatch } from "./terrainLayer.ts";
import { residentStyle } from "./theme.ts";

/** What each bubble stands for: the recorded action types or event types that show it. */
const EMOTE_MEANINGS: [EmoteName, string][] = [
  ["sleep", "sleep action active"],
  ["rest", "rest action active"],
  ["fruit", "gather or eat (active, or fruit gathered or consumed this tick)"],
  ["water", "drink or fill canteen (active, or recorded this tick)"],
  ["talk", "talk (active, or an utterance spoken this tick)"],
  ["hand", "give or pick up (active, or recorded this tick)"],
  ["fail", "an action of this resident failed this tick"],
];

/** Fixed legend: terrain from the bundle legend, art from the frontend theme. */
export function Legend({ bundle }: { bundle: ReplayBundle }) {
  const swatches = useMemo(
    () => bundle.map.terrain_legend.map((e) => ({ ...e, sprite: terrainSwatch(e.terrain) })),
    [bundle],
  );
  return (
    <aside className="legend" aria-label="Legend">
      <h3>Terrain</h3>
      <ul>
        {swatches.map((e) => (
          <li key={e.symbol}>
            <SpriteCanvas sprite={e.sprite} scale={2} />
            <span>
              {e.terrain.replace("_", " ")} <code>{e.symbol}</code>
            </span>
          </li>
        ))}
      </ul>
      <h3>Residents</h3>
      <ul>
        {bundle.residents.map((r, i) => (
          <li key={r.id}>
            <SpriteCanvas sprite={residentSprite(i, "down", "idle")} scale={2} />
            <span>
              <span className="tag" style={{ borderColor: residentStyle(i).colour }}>
                {residentStyle(i).letter}
              </span>{" "}
              {r.display_name} ({r.id})
            </span>
          </li>
        ))}
        <li>
          <SpriteCanvas sprite={corpseSprite(0)} scale={2} />
          <span>corpse: lying, greyed, with a grey letter tag marked ×</span>
        </li>
      </ul>
      <h3>Objects</h3>
      <ul>
        <li>
          <SpriteCanvas sprite={objectSprite(groundFruitKey(3)) as PixelSprite} scale={2} />
          <span>ground fruit, with its recorded quantity</span>
        </li>
        <li>
          <SpriteCanvas sprite={objectSprite(CANTEEN_KEY) as PixelSprite} scale={2} />
          <span>ground canteen, with its recorded servings</span>
        </li>
        <li>
          <span className="badge-sample">3</span>
          <span>fruit tree stock (the fruit drawn in the canopy show at most 8)</span>
        </li>
      </ul>
      <h3>Bubbles</h3>
      <ul>
        {EMOTE_MEANINGS.map(([name, meaning]) => (
          <li key={name}>
            <SpriteCanvas sprite={objectSprite(emoteKey(name)) as PixelSprite} scale={2} />
            <span>{meaning}</span>
          </li>
        ))}
      </ul>
      <p className="quiet">
        Night is a blue tint from the replay clock. Walking between tiles, the facing direction and the
        shimmer on water are display only; positions come from the recorded frames.
      </p>
    </aside>
  );
}
