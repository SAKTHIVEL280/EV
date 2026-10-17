import { describe, expect, it } from "vitest";

import type { SettingItem, SettingsState } from "../bindings";
import { SECTIONS, displayValue, groupsFor, isDefault, itemsFor, parseInput } from "./settings";

function item(overrides: Partial<SettingItem>): SettingItem {
  return {
    section: "llm",
    key: "context",
    nav: "models",
    label: "Context window",
    description: "Context window in tokens.",
    kind: "integer",
    default: 8192,
    value: 8192,
    options: [],
    minimum: 2048,
    maximum: 131072,
    unit: null,
    widget: null,
    role: null,
    steps: [],
    ...overrides,
  };
}

describe("settings", () => {
  it("has the 13 sections of CLAUDE.md §6.5 in order", () => {
    expect(SECTIONS.map((s) => s.label)).toEqual([
      "General",
      "Voice",
      "Models & Performance",
      "Personality",
      "Appearance",
      "Hotkeys",
      "Permissions",
      "Memory & History",
      "Routines",
      "Web & Privacy",
      "Advanced",
      "Diagnostics",
      "About",
    ]);
    for (const section of SECTIONS) {
      if (section.empty) expect(section.empty).not.toMatch(/[!]|soon/i);
      expect(section.summary).toMatch(/^[A-Z].*\.$/);
      expect(section.summary).not.toMatch(/!/);
    }
  });

  it("groups items by section", () => {
    const state: SettingsState = {
      path: "/c",
      items: [item({}), item({ key: "default_effort", nav: "general" })],
      warnings: [],
    };
    expect(itemsFor(state, "models").map((i) => i.key)).toEqual(["context"]);
    expect(itemsFor(state, "general").map((i) => i.key)).toEqual(["default_effort"]);
    expect(itemsFor(null, "general")).toEqual([]);
  });

  it("groups a page's settings under headings, in order", () => {
    const groups = groupsFor([
      item({ section: "llm", key: "a" }),
      item({ section: "llm", key: "b" }),
      item({ section: "island", key: "c" }),
    ]);
    expect(groups.map((g) => [g.title, g.items.map((i) => i.key)])).toEqual([
      ["Model", ["a", "b"]],
      ["Island", ["c"]],
    ]);
  });

  it("knows defaults and formats values", () => {
    expect(isDefault(item({}))).toBe(true);
    expect(isDefault(item({ value: 4096 }))).toBe(false);
    const flag = item({ kind: "boolean", default: true, value: false });
    expect(displayValue(flag, true)).toBe("On");
    expect(displayValue(flag, false)).toBe("Off");
    expect(displayValue(item({ kind: "text" }), "")).toBe("Empty");
    expect(displayValue(item({ unit: "px" }), 6)).toBe("6 px");
    expect(displayValue(item({ unit: null }), 6)).toBe("6");
    expect(displayValue(item({ kind: "choice" }), "normal")).toBe("Normal");
  });

  it("parses integers within bounds", () => {
    const it8 = item({});
    expect(parseInput(it8, " 16384 ")).toEqual({ ok: true, value: 16384 });
    expect(parseInput(it8, "99")).toEqual({
      ok: false,
      message: "That value isn't allowed. Use 2048 to 131072.",
    });
    expect(parseInput(it8, "12.5")).toMatchObject({ ok: false });
    expect(parseInput(it8, "abc")).toMatchObject({ ok: false });
    const unbounded = item({ minimum: null, maximum: null });
    expect(parseInput(unbounded, "x")).toEqual({
      ok: false,
      message: "That value isn't allowed. Use a whole number.",
    });
  });

  it("trims text", () => {
    expect(parseInput(item({ kind: "text" }), "  model.gguf ")).toEqual({
      ok: true,
      value: "model.gguf",
    });
  });
});
