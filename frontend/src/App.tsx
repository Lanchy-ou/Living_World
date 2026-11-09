import { useState } from "react";
import type { DragEvent } from "react";
import { CameraControls } from "./controls/CameraControls.tsx";
import { LoadControls } from "./controls/LoadControls.tsx";
import { PlaybackBar } from "./controls/PlaybackBar.tsx";
import { ErrorDetails } from "./debug/ErrorDetails.tsx";
import { EventList } from "./panels/EventList.tsx";
import { ResidentPanel } from "./panels/ResidentPanel.tsx";
import { ResourcesPanel } from "./panels/ResourcesPanel.tsx";
import { Legend } from "./render/Legend.tsx";
import { MapCanvas } from "./render/MapCanvas.tsx";
import { EXAMPLE_NAME, loadExample, loadFromFile } from "./replay/loader.ts";
import { ReplayStore } from "./replay/store.ts";
import type { LoadResult, ReplayError } from "./replay/types.ts";
import { useReplayState } from "./replay/useStore.ts";
import "./App.css";

// One store per page. The viewer is read-only: it displays recorded frames and sends no commands.
const store = new ReplayStore();

export default function App() {
  const { bundle, fileName } = useReplayState(store);
  const [error, setError] = useState<{ error: ReplayError; fileName: string | null } | null>(null);

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

  return (
    <main onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
      <header>
        <h1>Living Island — replay viewer</h1>
        <LoadControls
          onFile={(f) => void onFile(f)}
          onExample={() => accept(loadExample(), EXAMPLE_NAME)}
          fileName={fileName}
        />
      </header>
      {error !== null && <ErrorDetails error={error.error} fileName={error.fileName} />}
      {bundle === null ? (
        <p className="hint">Load a replay file to begin. Nothing is sent anywhere: files stay in this browser.</p>
      ) : (
        <>
          <PlaybackBar store={store} />
          <CameraControls store={store} />
          <div className="layout">
            <div className="map-column">
              <MapCanvas store={store} />
              <Legend bundle={bundle} />
            </div>
            <div className="side-column">
              <ResidentPanel store={store} />
              <ResourcesPanel store={store} />
            </div>
          </div>
          <EventList store={store} />
        </>
      )}
    </main>
  );
}
