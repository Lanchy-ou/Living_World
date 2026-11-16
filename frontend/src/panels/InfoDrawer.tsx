import type { ReactNode } from "react";
import { Icon } from "../controls/icons.tsx";
import { Legend } from "../render/Legend.tsx";
import type { ReplayStore } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";
import { DRAWER_TABS, DRAWER_TITLES } from "./drawerTabs.ts";
import type { DrawerTab } from "./drawerTabs.ts";
import { EventList } from "./EventList.tsx";
import { ResourcesPanel } from "./ResourcesPanel.tsx";

export type InfoDrawerTab = DrawerTab | "inspection";

interface Props {
  store: ReplayStore;
  tab: InfoDrawerTab;
  onTab: (tab: InfoDrawerTab) => void;
  onClose: () => void;
  inspection?: ReactNode;
}

/**
 * On-demand detail: the full event list with filters and raw JSON, the resource list and the
 * legend. It overlays the lower part of the map and does not resize it.
 */
export function InfoDrawer({ store, tab, onTab, onClose, inspection }: Props) {
  const { bundle } = useReplayState(store);
  if (bundle === null) return null;
  return (
    <section className="drawer" aria-label="Details">
      <header className="drawer-head">
        <div className="tabs" role="tablist" aria-label="Detail views">
          {DRAWER_TABS.map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={t === tab}
              className={`tab${t === tab ? " active" : ""}`}
              onClick={() => onTab(t)}
            >
              {DRAWER_TITLES[t]}
            </button>
          ))}
          {inspection !== undefined && (
            <button
              type="button" role="tab" aria-selected={tab === "inspection"}
              className={`tab${tab === "inspection" ? " active" : ""}`}
              onClick={() => onTab("inspection")}
            >
              Decision debug
            </button>
          )}
        </div>
        <button type="button" className="icon-button" aria-label="Close details" onClick={onClose}>
          <Icon name="close" />
        </button>
      </header>
      <div className="drawer-body" role="tabpanel">
        {tab === "events" && <EventList store={store} />}
        {tab === "resources" && <ResourcesPanel store={store} />}
        {tab === "legend" && <Legend bundle={bundle} />}
        {tab === "inspection" && inspection}
      </div>
    </section>
  );
}
