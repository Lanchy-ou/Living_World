import { useRef } from "react";

interface Props {
  onFile: (file: File) => void;
  onExample: () => void;
  fileName: string | null;
}

export function LoadControls({ onFile, onExample, fileName }: Props) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <section className="load" aria-label="Load replay">
      <input
        ref={input}
        type="file"
        accept=".json,application/json"
        aria-label="Replay file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
      <button type="button" onClick={onExample}>
        Load bundled example
      </button>
      <span className="hint">or drop a replay.json anywhere on this page</span>
      {fileName !== null && <span className="file-name">Loaded: {fileName}</span>}
    </section>
  );
}
