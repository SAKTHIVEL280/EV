/**
 * Logic behind the Settings controls that replace typing (F-415): the
 * shortcut recorder, sliders with steps and the model menu. Pure, so the
 * rules are testable without a window.
 */
import type { ModelsState, SettingItem } from "../bindings";
import { formatSize } from "../models/models";

// --- Shortcut recorder ----------------------------------------------------

export interface KeyPress {
  /** KeyboardEvent.code: the physical key, so keyboard layouts don't matter. */
  code: string;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  metaKey: boolean;
}

export type Recorded =
  | { kind: "shortcut"; spec: string }
  /** Only modifiers so far: keep listening. */
  | { kind: "pending" }
  | { kind: "cancel" }
  | { kind: "refused"; message: string };

export const NEEDS_MODIFIER_TEXT = "Add Ctrl, Alt, Shift or Win.";
export const KEY_NOT_ALLOWED_TEXT = "That key can't be used in a shortcut.";

const MODIFIER_CODES = new Set([
  "ControlLeft",
  "ControlRight",
  "AltLeft",
  "AltRight",
  "ShiftLeft",
  "ShiftRight",
  "MetaLeft",
  "MetaRight",
  "OSLeft",
  "OSRight",
]);

/** The config name of a main key (hotkeys.open_panel format), or null. */
function keyName(code: string): string | null {
  if (code === "Space") return "Space";
  const letter = /^Key([A-Z])$/.exec(code);
  if (letter?.[1]) return letter[1];
  const digit = /^Digit([0-9])$/.exec(code);
  if (digit?.[1]) return digit[1];
  const fn = /^F([1-9]|1[0-2])$/.exec(code);
  if (fn?.[1]) return `F${fn[1]}`;
  return null;
}

/**
 * Turn one key press into a shortcut in config format ("Ctrl+Shift+Space").
 * Esc without modifiers cancels; a key without a modifier is refused, because
 * it would take that key away from every other app.
 */
export function recordShortcut(press: KeyPress): Recorded {
  if (MODIFIER_CODES.has(press.code)) return { kind: "pending" };
  const modifiers = [
    press.ctrlKey ? "Ctrl" : null,
    press.altKey ? "Alt" : null,
    press.shiftKey ? "Shift" : null,
    press.metaKey ? "Super" : null,
  ].filter((m): m is string => m !== null);
  if (press.code === "Escape" && modifiers.length === 0) return { kind: "cancel" };
  const key = keyName(press.code);
  if (key === null) return { kind: "refused", message: KEY_NOT_ALLOWED_TEXT };
  if (modifiers.length === 0) return { kind: "refused", message: NEEDS_MODIFIER_TEXT };
  if (modifiers.length > 3) return { kind: "refused", message: KEY_NOT_ALLOWED_TEXT };
  return { kind: "shortcut", spec: [...modifiers, key].join("+") };
}

/** How a stored shortcut reads on Windows ("Super" is the Windows key). */
export function shortcutLabel(spec: string): string {
  if (!spec) return "Off";
  return spec
    .split("+")
    .map((part) => {
      const lower = part.trim().toLowerCase();
      if (lower === "super") return "Win";
      if (lower === "ctrl" || lower === "alt" || lower === "shift" || lower === "space") {
        return lower.charAt(0).toUpperCase() + lower.slice(1);
      }
      return part.trim().toUpperCase();
    })
    .join(" + ");
}

// --- Sliders ----------------------------------------------------------------

/** The values a slider stops at: declared steps, else every integer in range. */
export function sliderValues(item: SettingItem): number[] {
  if (item.steps.length > 0) return item.steps;
  const low = item.minimum ?? 0;
  const high = item.maximum ?? low;
  return Array.from({ length: Math.max(0, high - low) + 1 }, (_, i) => low + i);
}

/** Index of the value closest to `value` (hand-edited values snap to a stop). */
export function nearestIndex(values: number[], value: number): number {
  let best = 0;
  values.forEach((v, i) => {
    const current = values[best] ?? v;
    if (Math.abs(v - value) < Math.abs(current - value)) best = i;
  });
  return best;
}

/** "0 min" reads better as "Never" for the idle timer; other zeros stay. */
export function sliderText(item: SettingItem, value: number): string {
  if (value === 0 && item.key === "idle_unload_minutes") return "Never";
  if (value === 0 && item.key === "threads") return "Automatic";
  if (item.unit === "tokens" && value >= 1024) return `${String(value / 1024)}K tokens`;
  return item.unit ? `${String(value)} ${item.unit}` : String(value);
}

// --- Model menu ---------------------------------------------------------------

export interface ModelOption {
  /** Config value: the model's file name; "" for none. */
  value: string;
  label: string;
  detail: string;
}

export const NONE_LABEL = "None";

/**
 * Menu entries for a model setting: installed catalog models (the ones meant
 * for this role first), other model files in the folder, None, and the
 * current value when its file is missing.
 */
export function modelOptions(
  state: ModelsState | null,
  role: string,
  current: string,
): ModelOption[] {
  const installed = (state?.models ?? [])
    .filter((m) => m.state === "installed")
    .sort((a, b) => Number(b.role === role) - Number(a.role === role) || a.size_kb - b.size_kb);
  const options: ModelOption[] = installed.map((m) => ({
    value: m.file,
    label: m.name,
    detail: `${formatSize(m.size_kb)} · ${m.summary}`,
  }));
  for (const file of state?.other_files ?? []) {
    options.push({ value: file, label: file, detail: "Your file" });
  }
  options.push({ value: "", label: NONE_LABEL, detail: "" });
  if (current && !options.some((o) => o.value === current)) {
    options.unshift({
      value: current,
      label: `Missing: ${current}`,
      detail: "This file isn't in the models folder.",
    });
  }
  return options;
}

/** Whether any model is installed at all (else the picker offers Download). */
export function anyModelInstalled(state: ModelsState | null): boolean {
  return (
    (state?.models ?? []).some((m) => m.state === "installed") ||
    (state?.other_files.length ?? 0) > 0
  );
}
