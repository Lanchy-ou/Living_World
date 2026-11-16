import { useRef } from "react";
import type { InspectionState } from "./loadState.ts";

export function InspectionImport({ onFiles }: { onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input} type="file" multiple hidden accept=".json,application/json"
        aria-label="Inspection files" tabIndex={-1}
        onChange={(event) => {
          const files = Array.from(event.currentTarget.files ?? []);
          event.currentTarget.value = "";
          if (files.length > 0) onFiles(files);
        }}
      />
      <button
        type="button" className="text-button"
        title="Select the index, trace, registration and all inspection shards for this replay"
        onClick={() => input.current?.click()}
      >
        Open inspection…
      </button>
    </>
  );
}

export function InspectionNotice({ state, onDismiss }: { state: InspectionState; onDismiss: () => void }) {
  if (state.status === "idle") return null;
  if (state.status === "error") return (
    <div className="p3-notice p3-notice-error" role="alert">
      <div><strong>Inspection import refused</strong><p>{state.message}</p></div>
      <button type="button" className="text-button" onClick={onDismiss}>Dismiss</button>
    </div>
  );
  if (state.status === "loading") return <p className="p3-notice" role="status">Verifying inspection files…</p>;
  return <span className="p3-visually-hidden" role="status">Inspection verified. Character and decision views are available.</span>;
}
