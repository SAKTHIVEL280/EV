import { describe, expect, it } from "vitest";

import type { ModelInfo, ModelsState } from "../bindings";
import {
  active,
  downloadStatus,
  formatSize,
  formatSpeed,
  needsModel,
  ordered,
  percent,
  timeLeft,
} from "./models";

function model(changes: Partial<ModelInfo> = {}): ModelInfo {
  return {
    id: "qwen3.5-4b",
    name: "Qwen3.5 4B",
    summary: "Recommended.",
    role: "default",
    recommended: true,
    file: "Qwen3.5-4B-Q4_K_M.gguf",
    size_kb: 2_740_937,
    state: "available",
    received_kb: 0,
    kb_per_second: 0,
    error: null,
    ...changes,
  };
}

function state(...models: ModelInfo[]): ModelsState {
  return { models_dir: "/models", models, other_files: [] };
}

describe("model helpers", () => {
  it("formats sizes like download pages", () => {
    expect(formatSize(2_740_937)).toBe("2.7 GB");
    expect(formatSize(850_400)).toBe("850 MB");
    expect(formatSize(512)).toBe("512 kB");
    expect(formatSpeed(5_242)).toBe("5 MB/s");
  });

  it("computes progress and time left", () => {
    const m = model({ state: "downloading", received_kb: 1_370_469, kb_per_second: 10_000 });
    expect(percent(m)).toBe(50);
    expect(timeLeft(m)).toBe("About 2 min left");
    expect(timeLeft({ ...m, kb_per_second: 0 })).toBeNull();
    expect(timeLeft({ ...m, kb_per_second: 100_000 })).toBe("Less than a minute left");
    expect(timeLeft({ ...m, received_kb: 0, kb_per_second: 500 })).toBe("About 1 h 31 min left");
  });

  it("knows when EV needs a model", () => {
    expect(needsModel(null)).toBe(false);
    expect(needsModel(state(model()))).toBe(true);
    expect(needsModel(state(model(), model({ id: "b", state: "installed" })))).toBe(false);
  });

  it("reports the active download for the island", () => {
    expect(downloadStatus(state(model()))).toBeNull();
    const m = model({ state: "downloading", received_kb: 685_235 });
    expect(active(state(m))).toBe(m);
    expect(downloadStatus(state(m))).toBe("Downloading 25%");
    expect(downloadStatus(state(model({ state: "verifying" })))).toBe("Checking the model");
  });

  it("lists the recommended model first, then by size", () => {
    const big = model({ id: "9b", recommended: false, size_kb: 5_680_522 });
    const small = model({ id: "2b", recommended: false, size_kb: 1_280_835 });
    const rec = model();
    expect(ordered(state(big, small, rec)).map((m) => m.id)).toEqual(["qwen3.5-4b", "2b", "9b"]);
  });
});
