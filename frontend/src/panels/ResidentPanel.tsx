import { residentStyle } from "../render/theme.ts";
import type { ReplayStore } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";
import { residentView } from "./residentView.ts";

const fmtDelta = (d: number | null): string => (d === null ? "" : d > 0 ? ` (+${d})` : ` (${d})`);

export function ResidentPanel({ store }: { store: ReplayStore }) {
  const { bundle, currentTick, selectedResidentId } = useReplayState(store);
  if (bundle === null) return null;
  const view = selectedResidentId === null ? null : residentView(bundle, currentTick, selectedResidentId);
  return (
    <section className="panel resident-panel" aria-label="Resident">
      <h2>Resident</h2>
      <label>
        Select{" "}
        <select
          aria-label="Select resident"
          value={selectedResidentId ?? ""}
          onChange={(e) => store.selectResident(e.target.value === "" ? null : e.target.value)}
        >
          {bundle.residents.map((r, i) => (
            <option key={r.id} value={r.id}>
              {residentStyle(i).letter} · {r.display_name} ({r.id})
            </option>
          ))}
        </select>
      </label>
      {view === null ? (
        <p>No resident selected.</p>
      ) : (
        <dl>
          <dt>Name</dt>
          <dd>
            {view.displayName} ({view.id}) — {view.alive ? "alive" : "dead"}
          </dd>
          <dt>Position</dt>
          <dd>
            ({view.position.x},{view.position.y})
            {view.moved !== null && (view.moved.dx !== 0 || view.moved.dy !== 0)
              ? ` moved (${view.moved.dx >= 0 ? "+" : ""}${view.moved.dx},${view.moved.dy >= 0 ? "+" : ""}${view.moved.dy})`
              : ""}
          </dd>
          {view.conditions.map((c) => (
            <div key={c.name} className="condition">
              <dt>{c.name}</dt>
              <dd>
                {c.value}
                {fmtDelta(c.delta)}
                <div
                  className="bar"
                  role="meter"
                  aria-label={c.name}
                  aria-valuemin={bundle.condition_bounds.min_value}
                  aria-valuemax={bundle.condition_bounds.max_value}
                  aria-valuenow={c.value}
                >
                  <div className="bar-fill" style={{ width: `${c.fraction * 100}%` }} />
                </div>
              </dd>
            </div>
          ))}
          <dt>Fruit</dt>
          <dd>
            {view.fruitCount}
            {fmtDelta(view.fruitDelta)}
          </dd>
          <dt>Canteen</dt>
          <dd>
            {view.canteenServings === null
              ? "not holding the canteen"
              : `${view.canteenServings} servings${fmtDelta(view.canteenDelta)}`}
          </dd>
          <dt>Current action</dt>
          <dd>
            {view.action === null
              ? "none"
              : `${view.action.actionType} (intent ${view.action.intentId}), started tick ${view.action.tickStarted}, remaining ${view.action.remainingTicks ?? "open"}`}
          </dd>
        </dl>
      )}
    </section>
  );
}
