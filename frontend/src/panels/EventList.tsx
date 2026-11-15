import { useMemo, useState } from "react";
import type { ReplayStore } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";
import { RawEvent } from "../debug/RawEvent.tsx";
import { failureCode, filterEvents, summarize } from "./eventView.ts";

import { eventPage } from "./eventPagination.ts";

export function EventList({ store }: { store: ReplayStore }) {
  const { bundle, currentTick, filters, selectedEventId } = useReplayState(store);
  const events = useMemo(
    () => (bundle === null ? [] : filterEvents(bundle, filters)),
    [bundle, filters],
  );
  const [pageOverride, setPageOverride] = useState<{
    events: typeof events;
    tick: number;
    index: number;
  } | null>(null);

  // Tick changes and new filter results re-anchor to the current tick.
  // Discard the override so a later seek back cannot revive an old page.
  const pageMatches = pageOverride?.events === events && pageOverride.tick === currentTick;
  if (pageOverride !== null && !pageMatches) setPageOverride(null);
  if (bundle === null) return null;

  const { rows: shown, pageIndex, pageCount, start } = eventPage(
    events,
    currentTick,
    pageMatches ? pageOverride.index : undefined,
  );
  const goToPage = (index: number) => setPageOverride({ events, tick: currentTick, index });

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
            {pageCount > 1 && (
              <nav aria-label="Event pages">
                <button type="button" disabled={pageIndex === 0} onClick={() => goToPage(pageIndex - 1)}>
                  Previous
                </button>{" "}
                <span aria-live="polite">
                  Events {start + 1}–{start + shown.length} of {events.length}
                </span>{" "}
                <button
                  type="button"
                  disabled={pageIndex === pageCount - 1}
                  onClick={() => goToPage(pageIndex + 1)}
                >
                  Next
                </button>
              </nav>
            )}
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
