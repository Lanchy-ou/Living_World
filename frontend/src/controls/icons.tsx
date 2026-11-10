// Small inline icons for controls. Each button also has a text label or an aria-label.
const PATHS = {
  play: "M5 3.5v13l11-6.5z",
  pause: "M5 3h4v14H5zM11 3h4v14h-4z",
  stepBack: "M15 3.5v13L6.5 10zM4 3h2.2v14H4z",
  stepForward: "M5 3.5v13l8.5-6.5zM13.8 3H16v14h-2.2z",
  first: "M16 3.5v13L8.5 10zM9 3.5v13L1.5 10z",
  last: "M4 3.5v13l7.5-6.5zM11 3.5v13l7.5-6.5z",
  plus: "M9 4h2v5h5v2h-5v5H9v-5H4V9h5z",
  minus: "M4 9h12v2H4z",
  fit: "M3 3h5v2H5v3H3zM12 3h5v5h-2V5h-3zM3 12h2v3h3v2H3zM15 12h2v5h-5v-2h3z",
  close:
    "M5.3 4 10 8.7 14.7 4 16 5.3 11.3 10 16 14.7 14.7 16 10 11.3 5.3 16 4 14.7 8.7 10 4 5.3z",
  sun: "M10 6a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM9 1h2v3H9zM9 16h2v3H9zM1 9h3v2H1zM16 9h3v2h-3zM3.2 4.6l1.4-1.4 2.1 2.1-1.4 1.4zM13.3 14.7l1.4-1.4 2.1 2.1-1.4 1.4zM3.2 15.4l2.1-2.1 1.4 1.4-2.1 2.1zM13.3 5.3l2.1-2.1 1.4 1.4-2.1 2.1z",
  moon: "M12.5 2.5a7.5 7.5 0 1 0 5 13 6.5 6.5 0 0 1-5-13z",
  locate:
    "M9 1h2v2.6A6.5 6.5 0 0 1 16.4 9H19v2h-2.6a6.5 6.5 0 0 1-5.4 5.4V19H9v-2.6A6.5 6.5 0 0 1 3.6 11H1V9h2.6A6.5 6.5 0 0 1 9 3.6zm1 4.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zm0 2.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4z",
  folder: "M2 4h6l2 2h8v10H2z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} fill="currentColor" fillRule="evenodd" />
    </svg>
  );
}
