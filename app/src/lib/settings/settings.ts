/**
 * Settings window logic (docs/FEATURES.md F-410): sections, grouping and
 * input parsing. Core validates every change; parsing here only gives
 * immediate feedback with the same wording.
 */
import type { SettingItem, SettingsState, SettingValue } from "../bindings";
import { shortcutLabel, sliderText } from "./controls";

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
  /** One line under the title: what this page is for. */
  summary: string;
  /** Shown when the section has no settings yet: which feature brings them. */
  empty?: string;
}

const GENERAL: Section = { id: "general", label: "General", summary: "How EV answers." };

/** CLAUDE.md §6.5, in order. */
export const SECTIONS: readonly Section[] = [
  GENERAL,
  {
    id: "voice",
    label: "Voice",
    summary: "Listening, speaking and the wake word.",
    empty: "Voice settings arrive with voice input and speech.",
  },
  {
    id: "models",
    label: "Models & Performance",
    summary: "Which models EV uses and how much of this PC they may use.",
  },
  {
    id: "personality",
    label: "Personality",
    summary: "How EV sounds.",
    empty: "Personality presets arrive with the companion features.",
  },
  {
    id: "appearance",
    label: "Appearance",
    summary: "The island at the top of the screen.",
  },
  { id: "hotkeys", label: "Hotkeys", summary: "Keyboard shortcuts that work in any app." },
  {
    id: "permissions",
    label: "Permissions",
    summary: "What EV may do on this PC without asking.",
    empty: "Per-tool permissions arrive with PC control.",
  },
  {
    id: "memory",
    label: "Memory & History",
    summary: "What EV keeps, and for how long.",
    empty: "History and memory settings arrive with memory.",
  },
  {
    id: "routines",
    label: "Routines",
    summary: "Several actions under one command.",
    empty: "Routines arrive with the companion features.",
  },
  {
    id: "web",
    label: "Web & Privacy",
    summary: "When EV may go online, and what it shares.",
    empty: "Web search settings arrive with web search.",
  },
  { id: "advanced", label: "Advanced", summary: "The config file behind every setting." },
  { id: "diagnostics", label: "Diagnostics", summary: "What is running, and anything wrong." },
  { id: "about", label: "About", summary: "Versions and licenses." },
];

export function sectionById(id: SectionId): Section {
  return SECTIONS.find((s) => s.id === id) ?? GENERAL;
}

export function itemsFor(state: SettingsState | null, section: SectionId): SettingItem[] {
  return state ? state.items.filter((item) => item.nav === section) : [];
}

/** Headings for groups of settings, by config section. */
const GROUP_TITLES: Record<string, string> = {
  agent: "Answers",
  llm: "Model",
  island: "Island",
  hotkeys: "Shortcuts",
  logging: "Logs",
};

export interface Group {
  title: string;
  items: SettingItem[];
}

/** A page's settings grouped by config section, in schema order. */
export function groupsFor(items: SettingItem[]): Group[] {
  const groups: Group[] = [];
  for (const item of items) {
    const title = GROUP_TITLES[item.section] ?? item.section;
    const last = groups[groups.length - 1];
    if (last && last.title === title) last.items.push(item);
    else groups.push({ title, items: [item] });
  }
  return groups;
}

export function itemId(item: { section: string; key: string }): string {
  return `${item.section}.${item.key}`;
}

export function isDefault(item: SettingItem): boolean {
  return item.value === item.default;
}

/** A choice's display name: the schema's label, or the value with a capital first letter. */
export function choiceLabel(item: SettingItem, option: string): string {
  const label = item.labels[item.options.indexOf(option)];
  return label ?? option.charAt(0).toUpperCase() + option.slice(1);
}

export function displayValue(item: SettingItem, value: SettingValue): string {
  if (item.kind === "boolean") return value === true ? "On" : "Off";
  if (item.widget === "model" && value === "") return "None";
  if (item.widget === "folder" && value === "") return "EV's data folder";
  if (item.widget === "shortcut" && typeof value === "string") return shortcutLabel(value);
  if (item.widget === "slider" && typeof value === "number") return sliderText(item, value);
  if (item.kind === "text" && value === "") return "Empty";
  if (item.kind === "choice" && typeof value === "string") return choiceLabel(item, value);
  if (item.kind === "integer" && item.unit) return `${String(value)} ${item.unit}`;
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
