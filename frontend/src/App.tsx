import { useEffect, useState } from "react";
import type { DragEvent } from "react";
import { LoadControls } from "./controls/LoadControls.tsx";
import { PlaybackBar } from "./controls/PlaybackBar.tsx";
import { ErrorDetails } from "./debug/ErrorDetails.tsx";
import { eventInvolvesResident, isFailureEvent } from "./panels/eventView.ts";
import { Hud } from "./panels/Hud.tsx";
import { DRAWER_TABS, DRAWER_TITLES } from "./panels/drawerTabs.ts";
import type { DrawerTab } from "./panels/drawerTabs.ts";
import { InfoDrawer } from "./panels/InfoDrawer.tsx";
import { ResidentPanel } from "./panels/ResidentPanel.tsx";
import { Roster } from "./panels/Roster.tsx";
import { residentSprite } from "./render/assets/residentArt.ts";
import { MapCanvas } from "./render/MapCanvas.tsx";
import { SpriteCanvas } from "./render/SpriteCanvas.tsx";
import { EXAMPLE_NAME, loadExample, loadFromFile } from "./replay/loader.ts";
import { ReplayStore } from "./replay/store.ts";
import type { LoadResult, ReplayError, WorldEvent } from "./replay/types.ts";
import { useReplayState } from "./replay/useStore.ts";
import "./App.css";

// One store per page. The viewer is read-only: it displays recorded frames and sends no commands.
const store = new ReplayStore();

export default function App() {
  const { bundle, fileName } = useReplayState(store);
  const [error, setError] = useState<{ error: ReplayError; fileName: string | null } | null>(null);
  // Which on-demand detail view is open, if any. Display state only.
  const [drawer, setDrawer] = useState<DrawerTab | null>(null);

  function accept(result: LoadResult, name: string) {
    if (result.ok) {
      setError(null);
      store.load(result.bundle, name);
    } else {
      // A refused file never replaces a successfully loaded replay and is never repaired.
      setError({ error: result.error, fileName: name });
    }
  }

  async function onFile(file: File) {
    accept(await loadFromFile(file), file.name);
  }

  function onDrop(e: DragEvent<HTMLElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) void onFile(file);
  }

  function showEvent(event: WorldEvent) {
    // If the current filters would hide the event, clear them; then select it (which seeks to
    // its tick). Filters that already show the event are left as the user set them.
    const { filters } = store.getState();
    const hidden =
      (filters.residentId !== null && !eventInvolvesResident(event, filters.residentId)) ||
      (filters.failuresOnly && !isFailureEvent(event));
    if (hidden) store.setFilters({ residentId: null, failuresOnly: false });
    store.selectEvent(event);
    setDrawer("events");
  }

  useEffect(() => {
    // Space plays or pauses and Escape closes the open panel, unless a control has the focus.
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName ?? "";
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "BUTTON") return;
      const state = store.getState();
      if (state.bundle === null) return;
      if (e.key === " ") {
        e.preventDefault();
        if (state.playing) store.pause();
        else store.play();
      } else if (e.key === "Escape") {
        if (state.selectedResidentId !== null) store.selectResident(null);
        else setDrawer(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const load = (
    <LoadControls
      onFile={(f) => void onFile(f)}
      onExample={() => accept(loadExample(), EXAMPLE_NAME)}
      fileName={fileName}
    />
  );

  return (
    <main className="app" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
      <header className="topbar">
        <h1 className="brand">
          <span className="brand-mark" aria-hidden="true" />
          Living Island
        </h1>
        <Hud store={store} />
        <div className="topbar-actions">
          {bundle !== null && (
            <div className="detail-toggles" role="group" aria-label="Detail views">
              {DRAWER_TABS.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`text-button${drawer === t ? " active" : ""}`}
                  aria-pressed={drawer === t}
                  onClick={() => setDrawer(drawer === t ? null : t)}
                >
                  {DRAWER_TITLES[t]}
                </button>
              ))}
            </div>
          )}
          {load}
        </div>
      </header>

      <div className={`stage${drawer !== null ? " has-drawer" : ""}`}>
        {bundle === null ? (
          <section className="welcome" aria-label="Welcome">
            <div className="welcome-card">
              <div className="welcome-faces" aria-hidden="true">
                {[0, 1, 2].map((i) => (
                  <SpriteCanvas key={i} sprite={residentSprite(i, "down", "idle")} scale={4} />
                ))}
              </div>
              <h2>Watch a recorded island</h2>
              <p>
                Open a <code>replay.json</code> exported by the simulation, or drop it anywhere on this page.
              </p>
              <p className="hint">Load a replay file to begin. Nothing is sent anywhere: files stay in this browser.</p>
            </div>
          </section>
        ) : (
          <>
            <MapCanvas store={store} />
            <Roster store={store} />
            <ResidentPanel store={store} onShowEvent={showEvent} />
            {drawer !== null && (
              <InfoDrawer store={store} tab={drawer} onTab={setDrawer} onClose={() => setDrawer(null)} />
            )}
          </>
        )}
        {error !== null && (
          <div className="error-layer">
            <ErrorDetails error={error.error} fileName={error.fileName} onDismiss={() => setError(null)} />
          </div>
        )}
      </div>

      {bundle !== null && (
        <footer className="bottombar">
          <PlaybackBar store={store} />
        </footer>
      )}
    </main>
  );
}
