import { residentSprite } from "../render/assets/residentArt.ts";
import { SpriteCanvas } from "../render/SpriteCanvas.tsx";
import { residentStyle } from "../render/theme.ts";
import { frameAt } from "../replay/store.ts";
import type { ReplayStore } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";

/**
 * One button per declared resident. Selecting here is the same as clicking the resident on
 * the map: it opens the detail panel and changes nothing else.
 */
export function Roster({ store }: { store: ReplayStore }) {
  const { bundle, currentTick, selectedResidentId } = useReplayState(store);
  if (bundle === null) return null;
  const frame = frameAt(bundle, currentTick);
  return (
    <nav className="roster" aria-label="Residents">
      {bundle.residents.map((r, i) => {
        const style = residentStyle(i);
        const alive = frame.residents.find((f) => f.id === r.id)?.alive ?? false;
        const selected = selectedResidentId === r.id;
        return (
          <button
            key={r.id}
            type="button"
            className={`roster-item${selected ? " selected" : ""}${alive ? "" : " dead"}`}
            aria-pressed={selected}
            title={`${r.display_name} (${r.id})${alive ? "" : " — dead"}`}
            onClick={() => store.selectResident(selected ? null : r.id)}
          >
            <span className="tag" style={{ borderColor: style.colour }}>
              {style.letter}
            </span>
            <span className="face">
              <SpriteCanvas sprite={residentSprite(i, "down", "idle")} scale={2} />
            </span>
            <span className="roster-name">{r.display_name}</span>
            {!alive && <span className="dead-mark">dead</span>}
          </button>
        );
      })}
    </nav>
  );
}
