import { describe, expect, it } from "vitest";

import { FrameRecorder } from "./frames";

describe("FrameRecorder", () => {
  it("summarises an empty run", () => {
    expect(new FrameRecorder().summary()).toEqual({ frames: 0, dropped: 0, worstMs: 0, p95Ms: 0 });
  });

  it("counts frames over 20 ms as dropped", () => {
    const rec = new FrameRecorder();
    for (const d of [16.7, 16.6, 16.8, 20, 20.1, 33.4]) rec.add(d);
    const s = rec.summary();
    expect(s.frames).toBe(6);
    expect(s.dropped).toBe(2);
    expect(s.worstMs).toBe(33.4);
  });

  it("computes p95", () => {
    const rec = new FrameRecorder();
    for (let i = 1; i <= 100; i += 1) rec.add(i);
    expect(rec.summary().p95Ms).toBe(95);
  });

  it("resets", () => {
    const rec = new FrameRecorder();
    rec.add(16);
    rec.reset();
    expect(rec.count).toBe(0);
  });
});
