import { describe, expect, it } from "vitest";

import type { ModelInfo, ModelsState, SettingItem } from "../bindings";
import {
  KEY_NOT_ALLOWED_TEXT,
  NEEDS_MODIFIER_TEXT,
  anyModelInstalled,
  modelOptions,
  nearestIndex,
  recordShortcut,
  shortcutLabel,
  sliderText,
  sliderValues,
  type KeyPress,
} from "./controls";

function press(code: string, mods: Partial<KeyPress> = {}): KeyPress {
  return { code, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods };
}

function item(over: Partial<SettingItem>): SettingItem {
  return {
    section: "island",
    key: "arc_width",
    nav: "appearance",
    label: "Island width",
    description: "d",
    kind: "integer",
    default: 56,
    value: 56,
    options: [],
    minimum: 24,
    maximum: 30,
    unit: "px",
    widget: "slider",
    role: null,
    steps: [],
    labels: [],
    ...over,
  };
}

function model(over: Partial<ModelInfo>): ModelInfo {
  return {
    id: "qwen3.5-4b",
    name: "Qwen3.5 4B",
    summary: "Good answers.",
    role: "default",
    recommended: true,
    file: "Qwen3.5-4B-Q4_K_M.gguf",
    size_kb: 2_740_937,
    state: "installed",
    received_kb: 0,
    kb_per_second: 0,
    error: null,
    ...over,
  };
}

describe("shortcut recorder", () => {
  it.each([
    [press("Space", { ctrlKey: true }), "Ctrl+Space"],
    [press("Space", { ctrlKey: true, shiftKey: true }), "Ctrl+Shift+Space"],
    [press("KeyK", { ctrlKey: true, altKey: true }), "Ctrl+Alt+K"],
    [press("Digit1", { metaKey: true }), "Super+1"],
    [press("F12", { altKey: true }), "Alt+F12"],
  ])("records %o as %s", (p, spec) => {
    expect(recordShortcut(p)).toEqual({ kind: "shortcut", spec });
  });

  it("waits while only modifiers are held", () => {
    expect(recordShortcut(press("ControlLeft", { ctrlKey: true }))).toEqual({ kind: "pending" });
    expect(recordShortcut(press("ShiftRight", { shiftKey: true }))).toEqual({ kind: "pending" });
  });

  it("refuses a key without a modifier, and keys the config can't store", () => {
    expect(recordShortcut(press("KeyA"))).toEqual({
      kind: "refused",
      message: NEEDS_MODIFIER_TEXT,
    });
    expect(recordShortcut(press("Space"))).toEqual({
      kind: "refused",
      message: NEEDS_MODIFIER_TEXT,
    });
    expect(recordShortcut(press("F13", { ctrlKey: true }))).toEqual({
      kind: "refused",
      message: KEY_NOT_ALLOWED_TEXT,
    });
    expect(recordShortcut(press("Comma", { ctrlKey: true }))).toEqual({
      kind: "refused",
      message: KEY_NOT_ALLOWED_TEXT,
    });
    expect(
      recordShortcut(press("KeyA", { ctrlKey: true, altKey: true, shiftKey: true, metaKey: true })),
    ).toEqual({ kind: "refused", message: KEY_NOT_ALLOWED_TEXT });
  });

  it("cancels on Esc alone", () => {
    expect(recordShortcut(press("Escape"))).toEqual({ kind: "cancel" });
  });

  it("labels shortcuts the Windows way", () => {
    expect(shortcutLabel("ctrl+shift+space")).toBe("Ctrl + Shift + Space");
    expect(shortcutLabel("Super+k")).toBe("Win + K");
    expect(shortcutLabel("")).toBe("Off");
  });
});

describe("sliders", () => {
  it("uses declared steps, else every integer", () => {
    expect(sliderValues(item({ steps: [0, 5, 10] }))).toEqual([0, 5, 10]);
    expect(sliderValues(item({}))).toEqual([24, 25, 26, 27, 28, 29, 30]);
  });

  it("snaps to the nearest stop", () => {
    expect(nearestIndex([0, 5, 10, 15], 11)).toBe(2);
    expect(nearestIndex([0, 5, 10, 15], 100)).toBe(3);
    expect(nearestIndex([2048, 4096, 8192], 8192)).toBe(2);
  });

  it("reads values plainly", () => {
    expect(sliderText(item({ key: "idle_unload_minutes", unit: "min" }), 0)).toBe("Never");
    expect(sliderText(item({ key: "threads", unit: null }), 0)).toBe("Automatic");
    expect(sliderText(item({ key: "context", unit: "tokens" }), 8192)).toBe("8K tokens");
    expect(sliderText(item({}), 56)).toBe("56 px");
  });
});

describe("model menu", () => {
  const state: ModelsState = {
    models_dir: "/m",
    models: [
      model({}),
      model({
        id: "qwen3.5-2b",
        name: "Qwen3.5 2B",
        role: "small",
        file: "2B.gguf",
        size_kb: 1_280_835,
      }),
      model({
        id: "qwen3.5-9b",
        name: "Qwen3.5 9B",
        role: "large",
        file: "9B.gguf",
        state: "available",
      }),
    ],
    other_files: ["mine.gguf"],
    voice: [],
  };

  it("lists installed models for the role first, then the user's files and None", () => {
    expect(modelOptions(state, "small", "2B.gguf").map((o) => o.label)).toEqual([
      "Qwen3.5 2B",
      "Qwen3.5 4B",
      "mine.gguf",
      "None",
    ]);
    expect(modelOptions(state, "small", "")[0]?.detail).toBe("1.3 GB · Good answers.");
  });

  it("shows a missing configured file instead of hiding it", () => {
    const options = modelOptions(state, "large", "9B.gguf");
    expect(options[0]).toEqual({
      value: "9B.gguf",
      label: "Missing: 9B.gguf",
      detail: "This file isn't in the models folder.",
    });
  });

  it("knows when nothing is installed", () => {
    expect(anyModelInstalled(state)).toBe(true);
    expect(anyModelInstalled({ models_dir: "/m", models: [], other_files: [], voice: [] })).toBe(
      false,
    );
    expect(anyModelInstalled(null)).toBe(false);
  });
});
