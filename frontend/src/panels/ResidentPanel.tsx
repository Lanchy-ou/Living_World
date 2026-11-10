import { Icon } from "../controls/icons.tsx";
import { APPLE_KEY, CANTEEN_KEY, objectSprite } from "../render/assets/objectArt.ts";
import type { PixelSprite } from "../render/assets/pixels.ts";
import { corpseSprite, residentSprite } from "../render/assets/residentArt.ts";
import { facingAt } from "../render/motion.ts";
import { SpriteCanvas } from "../render/SpriteCanvas.tsx";
import { residentStyle } from "../render/theme.ts";
import { eventsOfFrame, frameAt } from "../replay/store.ts";
import type { ReplayStore } from "../replay/store.ts";
import type { WorldEvent } from "../replay/types.ts";
import { useReplayState } from "../replay/useStore.ts";
import { activityOf, deathRecord } from "./activityView.ts";
import { eventInvolvesResident, failureCode, summarize } from "./eventView.ts";
import { residentView } from "./residentView.ts";
import type { ConditionName } from "./residentView.ts";

const fmtDelta = (d: number | null): string => (d === null || d === 0 ? "" : d > 0 ? `+${d}` : `${d}`);

/** Display names for the four recorded condition fields. */
const CONDITION_LABELS: Record<ConditionName, string> = {
  health: "Health",
  satiety: "Satiety",
  hydration: "Hydration",
  stamina: "Stamina",
};
const CONDITION_ORDER: ConditionName[] = ["health", "satiety", "hydration", "stamina"];

interface Props {
  store: ReplayStore;
  /** Opens the events view on one recorded event. */
  onShowEvent: (event: WorldEvent) => void;
}

/**
 * Detail panel for the selected resident: recorded action, the four recorded conditions,
 * inventory and this tick's events. It floats over the map, so opening it never resizes the
 * map or moves the camera.
 */
export function ResidentPanel({ store, onShowEvent }: Props) {
  const { bundle, currentTick, selectedResidentId, camera } = useReplayState(store);
  if (bundle === null || selectedResidentId === null) return null;
  const view = residentView(bundle, currentTick, selectedResidentId);
  if (view === null) return null;
  const index = bundle.residents.findIndex((r) => r.id === view.id);
  const style = residentStyle(index);
  const activity = activityOf(bundle, currentTick, view.id);
  const death = view.alive ? null : deathRecord(bundle, currentTick, view.id);
  const tickEvents = eventsOfFrame(bundle, frameAt(bundle, currentTick)).filter((e) =>
    eventInvolvesResident(e, view.id),
  );
  const conditions = CONDITION_ORDER.map((name) => view.conditions.find((c) => c.name === name)!);
  const portrait = view.alive
    ? residentSprite(index, facingAt(bundle, currentTick, view.id), "idle")
    : corpseSprite(index);

  return (
    <aside className="resident-panel" aria-label="Resident">
      <header className="resident-head">
        <div className={`portrait${view.alive ? "" : " dead"}`}>
          <SpriteCanvas sprite={portrait} scale={4} label={`${view.displayName}, ${view.alive ? "alive" : "dead"}`} />
        </div>
        <div className="resident-title">
          <h2>
            <span className="tag" style={{ borderColor: style.colour }}>
              {style.letter}
            </span>
            {view.displayName}
          </h2>
          <p className="quiet">
            {view.id} · {view.alive ? "alive" : "dead"} · tile ({view.position.x},{view.position.y})
            {view.moved !== null && (view.moved.dx !== 0 || view.moved.dy !== 0)
              ? ` · moved (${view.moved.dx >= 0 ? "+" : ""}${view.moved.dx},${view.moved.dy >= 0 ? "+" : ""}${view.moved.dy})`
              : ""}
          </p>
          <p className={`status status-${activity.kind}`} aria-label="Current action">
            {activity.label}
          </p>
        </div>
        <button type="button" className="icon-button" aria-label="Close resident panel" onClick={() => store.selectResident(null)}>
          <Icon name="close" />
        </button>
      </header>

      {death !== null && (
        <p className="death-note">
          Recorded death at tick {death.tick}: {death.cause}
        </p>
      )}

      <dl className="conditions">
        {conditions.map((c) => (
          <div key={c.name} className="condition">
            <dt>{CONDITION_LABELS[c.name]}</dt>
            <dd>
              <div
                className={`bar bar-${c.name}`}
                role="meter"
                aria-label={c.name}
                aria-valuemin={bundle.condition_bounds.min_value}
                aria-valuemax={bundle.condition_bounds.max_value}
                aria-valuenow={c.value}
              >
                <div className="bar-fill" style={{ width: `${c.fraction * 100}%` }} />
              </div>
              <span className="num value">{c.value}</span>
              <span className="num delta">{fmtDelta(c.delta)}</span>
            </dd>
          </div>
        ))}
      </dl>

      <div className="inventory" aria-label="Inventory">
        <span className="inventory-item" title="Recorded fruit count">
          <SpriteCanvas sprite={objectSprite(APPLE_KEY) as PixelSprite} scale={3} />
          Fruit <strong className="num">{view.fruitCount}</strong>
          <span className="num delta">{fmtDelta(view.fruitDelta)}</span>
        </span>
        <span className="inventory-item" title="Recorded canteen servings">
          <SpriteCanvas sprite={objectSprite(CANTEEN_KEY) as PixelSprite} scale={3} />
          {view.canteenServings === null ? (
            <span className="quiet">not holding the canteen</span>
          ) : (
            <>
              Canteen <strong className="num">{view.canteenServings}</strong> servings
              <span className="num delta">{fmtDelta(view.canteenDelta)}</span>
            </>
          )}
        </span>
      </div>

      <section className="action-detail" aria-label="Action detail">
        <h3>Recorded action</h3>
        {view.action === null ? (
          <p className="quiet">No active action in this frame.</p>
        ) : (
          <p>
            <code>{view.action.actionType}</code> · started tick {view.action.tickStarted} · remaining{" "}
            {view.action.remainingTicks ?? "open"} · intent <code>{view.action.intentId}</code>
          </p>
        )}
      </section>

      <section className="tick-events" aria-label="Events this tick">
        <h3>
          This tick <span className="quiet">({tickEvents.length})</span>
        </h3>
        {tickEvents.length === 0 ? (
          <p className="quiet">No recorded events involve this resident at tick {currentTick}.</p>
        ) : (
          <ul>
            {tickEvents.map((e) => (
              <li key={e.event_id}>
                <button
                  type="button"
                  className={`event-link${failureCode(e) !== null ? " failure" : ""}`}
                  onClick={() => onShowEvent(e)}
                  title="Open this event in the events view"
                >
                  <span className="event-type">{e.type}</span> {summarize(e)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="resident-foot">
        <label className="toggle">
          <input
            type="checkbox"
            checked={camera.follow}
            onChange={(e) => store.setCamera({ follow: e.target.checked })}
          />{" "}
          Follow on the map
        </label>
      </footer>
    </aside>
  );
}
