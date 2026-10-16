/**
 * Settings window logic (docs/FEATURES.md F-410): sections, grouping and
 * input parsing. Core validates every change; parsing here only gives
 * immediate feedback with the same wording.
 */
import type { SettingItem, SettingsState, SettingValue } from "../bindings";

export type SectionId =
  | "general"
  | "voice"
  | "models"
  | "personality"
  | "appearance"
  | "hotkeys"
  | "permissions"
  | "memory"
  | "routines"
  | "web"
  | "advanced"
  | "diagnostics"
  | "about";

export interface Section {
  id: SectionId;
  label: string;
  /** Shown when the section has no settings yet: which feature brings them. */
  empty?: string;
}

const GENERAL: Section = { id: "general", label: "General" };

/** CLAUDE.md §6.5, in order. */
export const SECTIONS: readonly Section[] = [
  GENERAL,
  { id: "voice", label: "Voice", empty: "Voice settings arrive with voice input and speech." },
  { id: "models", label: "Models & Performance" },
  {
    id: "personality",
    label: "Personality",
    empty: "Personality presets arrive with the companion features.",
  },
  {
    id: "appearance",
    label: "Appearance",
    empty: "Theme, accent color and island size arrive with the island design pass.",
  },
  { id: "hotkeys", label: "Hotkeys", empty: "Hotkeys arrive with the global shortcut." },
  {
    id: "permissions",
    label: "Permissions",
    empty: "Per-tool permissions arrive with PC control.",
  },
  {
    id: "memory",
    label: "Memory & History",
    empty: "History and memory settings arrive with memory.",
  },
  { id: "routines", label: "Routines", empty: "Routines arrive with the companion features." },
  { id: "web", label: "Web & Privacy", empty: "Web search settings arrive with web search." },
  { id: "advanced", label: "Advanced" },
  { id: "diagnostics", label: "Diagnostics" },
  { id: "about", label: "About" },
];

export function sectionById(id: SectionId): Section {
  return SECTIONS.find((s) => s.id === id) ?? GENERAL;
}

export function itemsFor(state: SettingsState | null, section: SectionId): SettingItem[] {
  return state ? state.items.filter((item) => item.nav === section) : [];
}

export function itemId(item: { section: string; key: string }): string {
  return `${item.section}.${item.key}`;
}

export function isDefault(item: SettingItem): boolean {
  return item.value === item.default;
}

export function displayValue(item: SettingItem, value: SettingValue): string {
  if (item.kind === "boolean") return value === true ? "On" : "Off";
  if (item.kind === "text" && value === "") return "Empty";
  return String(value);
}

export type Parsed = { ok: true; value: SettingValue } | { ok: false; message: string };

export function parseInput(item: SettingItem, raw: string): Parsed {
  if (item.kind === "text") return { ok: true, value: raw.trim() };
  if (item.kind === "integer") {
    const text = raw.trim();
    const range =
      item.minimum !== null && item.maximum !== null
        ? `Use ${String(item.minimum)} to ${String(item.maximum)}.`
        : "Use a whole number.";
    if (!/^-?\d+$/.test(text)) return { ok: false, message: `That value isn't allowed. ${range}` };
    const value = Number(text);
    if (
      (item.minimum !== null && value < item.minimum) ||
      (item.maximum !== null && value > item.maximum)
    ) {
      return { ok: false, message: `That value isn't allowed. ${range}` };
    }
    return { ok: true, value };
  }
  return { ok: false, message: "That value isn't allowed." };
}
