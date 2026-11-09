import type { WorldEvent } from "../replay/types.ts";

/** Raw event JSON exactly as recorded; the viewer adds no interpretation. */
export function RawEvent({ event }: { event: WorldEvent }) {
  return (
    <details open className="raw-event">
      <summary>Raw event {event.event_id}</summary>
      <pre>{JSON.stringify(event, null, 2)}</pre>
    </details>
  );
}
