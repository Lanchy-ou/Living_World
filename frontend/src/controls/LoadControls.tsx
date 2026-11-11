import { useRef } from "react";
import { Icon } from "./icons.tsx";

interface Props {
  onFile: (file: File) => void;
  onExample: () => void;
  fileName: string | null;
}

export function LoadControls({ onFile, onExample, fileName }: Props) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <section className="load" aria-label="Load replay">
      {fileName !== null && (
        <span className="file-name" title={fileName}>
          {fileName}
        </span>
      )}
      <input
        ref={input}
        hidden
        type="file"
        accept=".json,application/json"
        aria-label="Replay file"
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
      <button type="button" className="text-button" onClick={() => input.current?.click()}>
        <Icon name="folder" /> Open replay…
      </button>
      <button type="button" className="text-button" onClick={onExample} title="Load the bundled hand-made example">
        Example
      </button>
    </section>
  );
}
