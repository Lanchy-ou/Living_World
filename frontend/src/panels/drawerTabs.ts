// The on-demand detail views. Display state only.
export const DRAWER_TABS = ["events", "resources", "legend"] as const;
export type DrawerTab = (typeof DRAWER_TABS)[number];

export const DRAWER_TITLES: Record<DrawerTab, string> = {
  events: "Events",
  resources: "Resources",
  legend: "Legend",
};
