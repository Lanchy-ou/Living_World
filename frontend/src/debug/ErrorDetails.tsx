import type { ReplayError } from "../replay/types.ts";

const TITLES: Record<ReplayError["kind"], string> = {
  broken_json: "Broken JSON",
  unknown_version: "Unknown replay version",
  schema: "Schema validation failed",
  event_payload: "Event payload does not match its type",
  cross_field: "Cross-field validation failed",
};

export function ErrorDetails({ error, fileName }: { error: ReplayError; fileName: string | null }) {
  return (
    <section className="error" role="alert" aria-label="Validation error">
      <h2>File refused: {TITLES[error.kind]}</h2>
      {fileName !== null && <p>File: {fileName}</p>}
      <p>{error.message}</p>
      {error.rule !== undefined && <p>Rule: {error.rule}</p>}
      {error.details.length > 0 && (
        <ul>
          {error.details.map((d, i) => (
            <li key={i}>
              <code>{d}</code>
            </li>
          ))}
        </ul>
      )}
      <p className="hint">The viewer never repairs or modifies a file. Fix the file and load it again.</p>
    </section>
  );
}
