import { useMemo } from "react";
import type { ReplayStore } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";
import { RawEvent } from "../debug/RawEvent.tsx";
import { failureCode, filterEvents, summarize } from "./eventView.ts";

const WINDOW = 150;

export function EventList({ store }: { store: ReplayStore }) {
  const { bundle, currentTick, filters, selectedEventId } = useReplayState(store);
  const events = useMemo(
    () => (bundle === null ? [] : filterEvents(bundle, filters)),
    [bundle, filters],
  );
  if (bundle === null) return null;

  // Long runs have tens of thousands of events: render a window around the current tick.
  let first = events.findIndex((e) => e.tick >= currentTick);
  if (first < 0) first = events.length;
  const start = Math.max(0, first - 10);
  const shown = events.slice(start, start + WINDOW);
  const selected = bundle.events.find((e) => e.event_id === selectedEventId) ?? null;

  return (
    <section className="events" aria-label="Events">
      <h2>
        Events ({events.length}
        {events.length === bundle.events.length ? "" : ` of ${bundle.events.length}`})
      </h2>
      <div className="filters">
        <label>
          Resident{" "}
          <select
            aria-label="Filter by resident"
            value={filters.residentId ?? ""}
            onChange={(e) => store.setFilters({ residentId: e.target.value === "" ? null : e.target.value })}
          >
            <option value="">All residents</option>
            {bundle.residents.map((r) => (
              <option key={r.id} value={r.id}>
                {r.display_name} ({r.id})
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={filters.failuresOnly}
            onChange={(e) => store.setFilters({ failuresOnly: e.target.checked })}
          />{" "}
          Failures and interruptions only
        </label>
      </div>
      <div className="events-body">
        {events.length === 0 ? (
          <p>No events match.</p>
        ) : (
          <div>
            <table>
              <thead>
                <tr>
                  <th>Tick</th>
                  <th>Seq</th>
                  <th>Type</th>
                  <th>Actor → target</th>
                  <th>Summary</th>
                  <th>Code</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((e) => {
                  const code = failureCode(e);
                  return (
                    <tr
                      key={e.event_id}
                      className={[
                        e.tick === currentTick ? "current" : "",
                        e.event_id === selectedEventId ? "selected" : "",
                        code !== null ? "failure" : "",
                      ].join(" ")}
                      onClick={() => store.selectEvent(e)}
                    >
                      <td>{e.tick}</td>
                      <td>{e.seq_in_tick}</td>
                      <td>{e.type}</td>
                      <td>
                        {e.actor_id ?? "—"} → {e.target_id ?? "—"}
                      </td>
                      <td>{summarize(e)}</td>
                      <td>{code ?? ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {events.length > shown.length && (
              <p className="hint">
                Showing {shown.length} of {events.length} events around tick {currentTick}; seek or filter
                to see others.
              </p>
            )}
          </div>
        )}
        {selected !== null ? (
          <RawEvent event={selected} />
        ) : (
          <p className="hint">Select an event to jump to its tick and see its raw JSON.</p>
        )}
      </div>
    </section>
  );
}
