import type { ReplayBundle } from "../replay/types.ts";
import { LEGEND_OBJECTS, TERRAIN_COLOURS, residentStyle } from "./theme.ts";

/** Fixed legend: terrain from the bundle legend, colours from the explicit theme. */
export function Legend({ bundle }: { bundle: ReplayBundle }) {
  return (
    <aside className="legend" aria-label="Legend">
      <ul>
        {bundle.map.terrain_legend.map((e) => (
          <li key={e.symbol}>
            <span className="swatch" style={{ background: TERRAIN_COLOURS[e.terrain] }} />
            {e.terrain.replace("_", " ")}
          </li>
        ))}
        {LEGEND_OBJECTS.map((o) => (
          <li key={o.label}>
            <span className="swatch" style={{ background: o.colour }} />
            {o.label}
          </li>
        ))}
        {bundle.residents.map((r, i) => (
          <li key={r.id}>
            <span className="swatch" style={{ background: residentStyle(i).colour }} />
            {residentStyle(i).letter} {r.display_name}
          </li>
        ))}
      </ul>
    </aside>
  );
}
