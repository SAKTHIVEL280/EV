import { describe, expect, it } from "vitest";

import { fitted, outlineBounds, outlinePath, outlinePoints, type Outline } from "./outline";

const arc: Outline = { cx: 210, width: 56, height: 7, radius: 999, neck: 0, exponent: 2, arc: 1 };
const panel: Outline = {
  cx: 210,
  width: 380,
  height: 264,
  radius: 26,
  neck: 12,
  exponent: 5,
  arc: 0,
};

describe("outline", () => {
  it("hangs from the top edge and reaches its full height", () => {
    for (const shape of [arc, panel]) {
      const ys = outlinePoints(shape).map(([, y]) => y);
      expect(Math.min(...ys)).toBeLessThan(0); // closes above the edge
      expect(Math.max(...ys)).toBeCloseTo(shape.height, 5);
    }
  });

  it("draws the arc as a circle segment from edge to edge", () => {
    const inner = outlinePoints(arc).slice(1, -1);
    const first = inner[0] ?? [0, 0];
    const last = inner[inner.length - 1] ?? [0, 0];
    expect(first[0]).toBeCloseTo(210 - 28, 5);
    expect(first[1]).toBeCloseTo(0, 5);
    expect(last[0]).toBeCloseTo(210 + 28, 5);
    expect(last[1]).toBeCloseTo(0, 5);
    // Every point lies on one circle: center (210, depth - r).
    const r = (28 * 28 + 7 * 7) / (2 * 7);
    for (const [x, y] of inner) expect(Math.hypot(x - 210, y - (7 - r))).toBeCloseTo(r, 4);
  });

  it("caps the arc's depth at a half circle", () => {
    const deep = outlinePoints({ ...arc, width: 20, height: 40 }).map(([, y]) => y);
    expect(Math.max(...deep)).toBeCloseTo(10, 5);
  });

  it("spans the body plus the neck on both sides", () => {
    const xs = outlinePoints(panel).map(([x]) => x);
    expect(Math.min(...xs)).toBeCloseTo(210 - 190 - 12, 5);
    expect(Math.max(...xs)).toBeCloseTo(210 + 190 + 12, 5);
  });

  it("has the same point count for every shape and blend, so frames interpolate", () => {
    const count = outlinePoints(panel).length;
    for (const a of [0, 0.3, 1]) expect(outlinePoints({ ...panel, arc: a }).length).toBe(count);
    expect(outlinePoints({ ...arc, width: 0, height: 0 }).length).toBe(count);
  });

  it("blends half way between the arc and the body", () => {
    const body = outlinePoints({ ...arc, arc: 0 });
    const segment = outlinePoints(arc);
    const mid = outlinePoints({ ...arc, arc: 0.5 });
    mid.forEach(([x, y], i) => {
      const [bx, by] = body[i] ?? [0, 0];
      const [sx, sy] = segment[i] ?? [0, 0];
      expect(x).toBeCloseTo((bx + sx) / 2, 5);
      expect(y).toBeCloseTo((by + sy) / 2, 5);
    });
  });

  it("clamps values so spring overshoot or tiny sizes never break the outline", () => {
    const tiny = fitted({ ...panel, width: 4, height: 3, radius: 20, neck: 9, arc: 1.2 });
    expect(tiny.neck).toBeLessThanOrEqual(1.5);
    expect(tiny.radius).toBeLessThanOrEqual(2);
    expect(tiny.radius + tiny.neck).toBeLessThanOrEqual(tiny.height);
    expect(tiny.arc).toBe(1);
    expect(outlinePath({ ...arc, width: -5, height: -1 })).not.toMatch(/NaN/);
    expect(outlinePath({ ...panel, arc: -1 })).not.toMatch(/NaN/);
  });

  it("bounds cover the visible outline", () => {
    expect(outlineBounds(arc)).toEqual({ x: 182, y: 0, width: 56, height: 7 });
    expect(outlineBounds(panel)).toEqual({ x: 8, y: 0, width: 404, height: 264 });
  });
});
