import { Icon } from "../controls/icons.tsx";
import { APPLE_KEY, CANTEEN_KEY, objectSprite } from "../render/assets/objectArt.ts";
import type { PixelSprite } from "../render/assets/pixels.ts";
import { SpriteCanvas } from "../render/SpriteCanvas.tsx";
import { residentStyle } from "../render/theme.ts";
import type { ReplayStore } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";
import { hudView } from "./hudView.ts";

/** Concise island-wide status: day and time, living residents and recorded resource totals. */
export function Hud({ store }: { store: ReplayStore }) {
  const { bundle, currentTick } = useReplayState(store);
  if (bundle === null) return null;
  const view = hudView(bundle, currentTick);
  const letterOf = (id: string) => residentStyle(bundle.residents.findIndex((r) => r.id === id)).letter;
  return (
    <section className="hud" aria-label="Island status">
      <span className="chip clock" aria-label="Clock" title={`Tick ${view.tick}`}>
        <Icon name={view.night ? "moon" : "sun"} />
        <strong>Day {view.day}</strong>
        <span className="num">{view.time}</span>
        <span className="quiet">{view.night ? "night" : "day"}</span>
      </span>
      <span className="chip" aria-label="Living residents">
        Alive{" "}
        <strong className="num">
          {view.alive}/{view.residents}
        </strong>
      </span>
      <span className="chip" title="Sum of the recorded stock of all fruit trees">
        <SpriteCanvas sprite={objectSprite(APPLE_KEY) as PixelSprite} scale={2} />
        <strong className="num">{view.treeFruit}</strong> on {view.trees} trees
      </span>
      {view.groundFruit > 0 && (
        <span className="chip" title="Sum of the recorded ground fruit piles">
          <SpriteCanvas sprite={objectSprite(APPLE_KEY) as PixelSprite} scale={2} />
          <strong className="num">{view.groundFruit}</strong> on the ground
        </span>
      )}
      {view.canteens.map((c) => (
        <span className="chip" key={c.holderId ?? "ground"} title="Canteen location and recorded servings">
          <SpriteCanvas sprite={objectSprite(CANTEEN_KEY) as PixelSprite} scale={2} />
          {c.holderId === null ? "on the ground" : `with ${letterOf(c.holderId)}`} ·{" "}
          <strong className="num">{c.servings}</strong>
        </span>
      ))}
    </section>
  );
}
