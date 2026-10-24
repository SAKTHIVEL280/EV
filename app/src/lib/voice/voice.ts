/**
 * Voice rules for the island (F-005, F-008). Pure, so they are testable.
 */

/** Holding the hotkey this long is push-to-talk (F-005). */
export const PUSH_TO_TALK_MS = 400;

export interface VoiceState {
  /** The microphone is open: the mic indicator shows. */
  mic: boolean;
  speaking: boolean;
  /** Words recognized so far (live captions). */
  heard: string;
  /** Mic level 0..1. */
  level: number;
  /** Why voice stopped or couldn't start. */
  message: string | null;
  code: string | null;
}

export const IDLE: VoiceState = {
  mic: false,
  speaking: false,
  heard: "",
  level: 0,
  message: null,
  code: null,
};

/** A key press that types something switches the panel to text (F-008). */
export function typesText(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey">,
): boolean {
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  return event.key.length === 1 || event.key === "Backspace";
}

/** The release of a press that opened listening: was it push-to-talk? */
export function isPushToTalk(heldMs: number, listening: boolean): boolean {
  return listening && heldMs >= PUSH_TO_TALK_MS;
}

/** The voice message gets a button to Settings → Voice. */
export function needsSettings(code: string | null): boolean {
  return code === "not_installed" || code === "off";
}

/** Bars for the level meter: five heights 0..1, the middle one tallest. */
export function bars(level: number): number[] {
  const shape = [0.45, 0.75, 1, 0.75, 0.45];
  const clamped = Math.max(0, Math.min(1, level));
  return shape.map((s) => Math.max(0.12, s * clamped));
}
