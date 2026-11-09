import { frameAt } from "../replay/store.ts";
import type { ReplayStore } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";
import { resourcesView } from "./resourcesView.ts";

export function ResourcesPanel({ store }: { store: ReplayStore }) {
  const { bundle, currentTick } = useReplayState(store);
  if (bundle === null) return null;
  const view = resourcesView(frameAt(bundle, currentTick));
  return (
    <section className="panel resources-panel" aria-label="Resources">
      <h2>Resources at tick {currentTick}</h2>
      <h3>Fruit trees</h3>
      {view.empty.trees ? (
        <p>No fruit trees.</p>
      ) : (
        <ul>
          {view.trees.map((t) => (
            <li key={t.id}>
              {t.id} at ({t.x},{t.y}): stock {t.stock}
            </li>
          ))}
        </ul>
      )}
      <h3>Ground fruit</h3>
      {view.empty.piles ? (
        <p>None on the ground.</p>
      ) : (
        <ul>
          {view.piles.map((p) => (
            <li key={`${p.x},${p.y}`}>
              ({p.x},{p.y}): {p.quantity}
            </li>
          ))}
        </ul>
      )}
      <h3>Ground canteen</h3>
      <p>
        {view.canteen === null
          ? "Not on the ground."
          : `At (${view.canteen.x},${view.canteen.y}): ${view.canteen.servings} servings`}
      </p>
      <h3>Corpses</h3>
      {view.empty.corpses ? (
        <p>None.</p>
      ) : (
        <ul>
          {view.corpses.map((c) => (
            <li key={c.id}>
              {c.id} ({c.residentId}) at ({c.x},{c.y})
            </li>
          ))}
        </ul>
      )}
      <h3>Objects by tile</h3>
      <ul className="tiles">
        {view.tiles.map((t) => (
          <li key={`${t.x},${t.y}`}>
            ({t.x},{t.y}): {t.objects.join("; ")}
          </li>
        ))}
      </ul>
    </section>
  );
}
