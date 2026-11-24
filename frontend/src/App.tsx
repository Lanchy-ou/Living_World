import { lazy, Suspense, useEffect, useState } from "react";
import type { DragEvent } from "react";
import { LoadControls } from "./controls/LoadControls.tsx";
import { PlaybackBar } from "./controls/PlaybackBar.tsx";
import { ErrorDetails } from "./debug/ErrorDetails.tsx";
import { eventInvolvesResident, isFailureEvent } from "./panels/eventView.ts";
import { Hud } from "./panels/Hud.tsx";
import { DRAWER_TABS, DRAWER_TITLES } from "./panels/drawerTabs.ts";
import { InfoDrawer } from "./panels/InfoDrawer.tsx";
import type { InfoDrawerTab } from "./panels/InfoDrawer.tsx";
import { ResidentPanel } from "./panels/ResidentPanel.tsx";
import { Roster } from "./panels/Roster.tsx";
import { residentSprite } from "./render/assets/residentArt.ts";
import { MapCanvas } from "./render/MapCanvas.tsx";
import { SpriteCanvas } from "./render/SpriteCanvas.tsx";
import { EXAMPLE_NAME, getValidator, loadExample } from "./replay/loader.ts";
import { ReplayStore } from "./replay/store.ts";
import type { ReplayError, WorldEvent } from "./replay/types.ts";
import { useReplayState } from "./replay/useStore.ts";
import { CharacterInspection } from "./p3/CharacterInspection.tsx";
import { InspectionImport, InspectionNotice } from "./p3/InspectionImport.tsx";
import type { ReplayFileSource } from "./p3/inspection.ts";
import { createInspectionImport, createReplayWithSource } from "./p3/loadState.ts";
import type { InspectionState } from "./p3/loadState.ts";
import { inspectionRouter } from "./features/v2-inspection/import.ts";
import type { ImportState } from "./features/v2-inspection/import.ts";
import "./App.css";

// One store per page. The viewer is read-only: it displays recorded frames and sends no commands.
const store = new ReplayStore();
const V2Inspection = lazy(() => import("./features/v2-inspection/Viewer.tsx"));
const DecisionInspection = lazy(async () => {
  const { DecisionInspection } = await import("./p3/DecisionInspection.tsx");
  return { default: DecisionInspection };
});

export default function App() {
  const { bundle, fileName, currentTick, selectedResidentId } = useReplayState(store);
  const [error, setError] = useState<{ error: ReplayError; fileName: string | null } | null>(null);
  // Which on-demand detail view is open, if any. Display state only.
  const [drawer, setDrawer] = useState<InfoDrawerTab | null>(null);
  const [replaySource, setReplaySource] = useState<ReplayFileSource | null>(null);
  const [inspectionState, setInspectionState] = useState<InspectionState>({ status: "idle" });
  const [v2, setV2] = useState<ImportState>({ status: "idle" });
  const [inspectionImport] = useState(() => inspectionRouter(createInspectionImport(
    async (files, replay, signal) => (await import("./p3/schemas.ts")).loadInspection(files, replay, signal),
    setInspectionState,
  ), async (files, replay, index) => (await import("./features/v2-inspection/schema.ts")).load(files, replay, index), setV2));
  const inspection = inspectionState.status === "ready" ? inspectionState.value : null;

  const [replayLoad] = useState(() =>
    createReplayWithSource(
      (text) => getValidator().validateText(text),
      (nextBundle, name, bytes) => {
        setError(null);
        inspectionImport.reset();
        setDrawer((open) => open === "inspection" ? null : open);
        store.load(nextBundle, name);
        const acceptedBundle = store.getState().bundle;
        setReplaySource(acceptedBundle !== null && bytes !== null ? { bundle: acceptedBundle, bytes } : null);
      },
      (loadError, name) => setError({ error: loadError, fileName: name }),
    ),
  );

  function onFile(file: File) {
    void replayLoad.file(file);
  }

  function onInspectionFiles(files: File[]) {
    if (replaySource === null || replaySource.bundle !== bundle) return;
    setDrawer((open) => open === "inspection" ? null : open);
    void inspectionImport.select(files, replaySource);
  }

  function onDrop(e: DragEvent<HTMLElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
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

  function showDecision(id: string) {
    const ref = inspection?.decisionRefsById.get(id);
    if (ref === undefined) return;
    store.pause();
    store.selectResident(ref.actor_id);
    store.seek(ref.tick);
    setDrawer("inspection");
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
      onFile={onFile}
      onExample={() => void replayLoad.example(EXAMPLE_NAME, loadExample)}
      fileName={fileName}
    />
  );
  const navigation = inspection === null ? null : { inspection, onDecision: showDecision, onShowEvent: showEvent };
  const inspectionTab = v2.status === "ready" ? (
    <Suspense fallback={<p role="status">Opening inspection…</p>}>
      <V2Inspection inspection={v2.value} seek={(actor, tick) => {
        store.pause();
        store.selectResident(actor);
        store.seek(tick);
      }} />
    </Suspense>
  ) : bundle === null || navigation === null ? undefined : (
    <Suspense fallback={<p role="status">Opening decision debug…</p>}>
      <DecisionInspection
        {...navigation} actor={selectedResidentId} tick={currentTick}
        residents={bundle.residents} onActor={(id) => store.selectResident(id)}
      />
    </Suspense>
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
          {load}
          {replaySource !== null && <InspectionImport onFiles={onInspectionFiles} />}
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
            <ResidentPanel
              store={store} onShowEvent={showEvent}
              renderInspection={navigation === null ? undefined : ({ id, tick, alive }) => (
                <CharacterInspection {...navigation} actor={id} tick={tick} alive={alive} />
              )}
            />
            {drawer !== null && (
              <InfoDrawer
                store={store} tab={drawer} onTab={setDrawer}
                onClose={() => setDrawer(null)} inspection={inspectionTab}
              />
            )}
          </>
        )}
        <InspectionNotice state={inspectionState} onDismiss={inspectionImport.reset} />
        {v2.status === "error" && <InspectionNotice state={v2} onDismiss={inspectionImport.reset} />}
        {v2.status === "loading" && <p role="status">Opening inspection…</p>}
        {error !== null && (
          <div className="error-layer">
            <ErrorDetails error={error.error} fileName={error.fileName} onDismiss={() => setError(null)} />
          </div>
        )}
      </div>

      {bundle !== null && (
        <footer className="bottombar">
          <PlaybackBar store={store} />
          {/* The detail views open from the bottom, so their buttons sit at the bottom right. */}
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
            {(navigation !== null || v2.status === "ready") && (
              <button
                type="button" className={`text-button${drawer === "inspection" ? " active" : ""}`}
                aria-pressed={drawer === "inspection"}
                onClick={() => setDrawer(drawer === "inspection" ? null : "inspection")}
              >
                Decision debug
              </button>
            )}
          </div>
        </footer>
      )}
    </main>
  );
}
