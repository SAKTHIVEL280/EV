/**
 * Path data for the EV icon set (20 × 20, 1.5 px stroke). Every icon has a
 * reason to exist; add one only when a control needs it.
 */
export const PATHS = {
  /** Settings: two sliders. */
  settings: ["M4 7h12", "M4 13h12", "M7.5 5v4", "M12.5 11v4"],
  /** Quit EV: a power symbol. */
  power: ["M10 3.5v6", "M6.2 6.1a5.5 5.5 0 1 0 7.6 0"],
  /** Download a file. */
  download: ["M10 3.5v9", "M6.5 9.5 10 13l3.5-3.5", "M4.5 16.5h11"],
  /** Stop a running task. */
  stop: ["M6.5 6.5h7v7h-7z"],
} as const satisfies Record<string, readonly string[]>;

export type IconName = keyof typeof PATHS;
