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
  /** New chat: a speech bubble with a plus. */
  newChat: [
    "M4.5 5.75c0-.69.56-1.25 1.25-1.25h8.5c.69 0 1.25.56 1.25 1.25v6c0 .69-.56 1.25-1.25 1.25H9.5l-3 2.5V13h-.75c-.69 0-1.25-.56-1.25-1.25z",
    "M10 6.75v3.5",
    "M8.25 8.5h3.5",
  ],
  /** Stop a running task. */
  stop: ["M6.5 6.5h7v7h-7z"],
} as const satisfies Record<string, readonly string[]>;

export type IconName = keyof typeof PATHS;
