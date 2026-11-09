import { ZOOMS } from "../replay/store.ts";
import type { ReplayStore, Zoom } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";

export function CameraControls({ store }: { store: ReplayStore }) {
  const { bundle, camera } = useReplayState(store);
  if (bundle === null) return null;
  return (
    <section className="camera" aria-label="Camera">
      <span>Zoom</span>
      {ZOOMS.map((z) => (
        <button
          key={z}
          type="button"
          aria-pressed={camera.zoom === z}
          onClick={() => store.setCamera({ zoom: z as Zoom, panX: 0, panY: 0 })}
        >
          ×{z}
        </button>
      ))}
      <button type="button" onClick={() => store.setCamera({ zoom: 1, panX: 0, panY: 0 })}>
        Fit to view
      </button>
      <label>
        <input
          type="checkbox"
          checked={camera.follow}
          onChange={(e) => store.setCamera({ follow: e.target.checked })}
        />{" "}
        Follow selected resident
      </label>
    </section>
  );
}
