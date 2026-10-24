import { describe, expect, it } from "vitest";

import { PUSH_TO_TALK_MS, bars, isPushToTalk, needsSettings, typesText } from "./voice";

const key = (k: string, mods: Partial<KeyboardEvent> = {}) => ({
  key: k,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...mods,
});

describe("voice rules", () => {
  it("typing a character switches to text; shortcuts and navigation don't", () => {
    expect(typesText(key("a"))).toBe(true);
    expect(typesText(key(" "))).toBe(true);
    expect(typesText(key("Backspace"))).toBe(true);
    expect(typesText(key("Enter"))).toBe(false);
    expect(typesText(key("ArrowUp"))).toBe(false);
    expect(typesText(key("Escape"))).toBe(false);
    expect(typesText(key("v", { ctrlKey: true }))).toBe(false);
  });

  it("a long hold while listening is push-to-talk", () => {
    expect(isPushToTalk(PUSH_TO_TALK_MS, true)).toBe(true);
    expect(isPushToTalk(PUSH_TO_TALK_MS - 1, true)).toBe(false);
    expect(isPushToTalk(2000, false)).toBe(false);
  });

  it("offers Settings when voice is missing or off", () => {
    expect(needsSettings("not_installed")).toBe(true);
    expect(needsSettings("off")).toBe(true);
    expect(needsSettings("no_mic")).toBe(false);
    expect(needsSettings(null)).toBe(false);
  });

  it("level bars stay visible and follow the level", () => {
    expect(bars(0)).toEqual([0.12, 0.12, 0.12, 0.12, 0.12]);
    const loud = bars(1);
    expect(loud[2]).toBe(1);
    expect(loud[0]).toBeLessThan(loud[2] ?? 0);
    expect(bars(5)).toEqual(loud);
  });
});
