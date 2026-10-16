import { describe, expect, it } from "vitest";

import { squirclePath } from "./squircle";

function points(path: string): [number, number][] {
  return [...path.matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g)].map((m) => [Number(m[1]), Number(m[2])]);
}

describe("squirclePath", () => {
  it("stays inside its bounding box and touches every edge", () => {
    const pts = points(squirclePath(10, 20, 300, 100, 30, 5));
    const xs = pts.map(([x]) => x);
    const ys = pts.map(([, y]) => y);
    expect(Math.min(...xs)).toBeCloseTo(10, 1);
    expect(Math.max(...xs)).toBeCloseTo(310, 1);
    expect(Math.min(...ys)).toBeCloseTo(20, 1);
    expect(Math.max(...ys)).toBeCloseTo(120, 1);
  });

  it("has a constant point count for interpolation", () => {
    const a = points(squirclePath(0, 0, 120, 10, 5, 5)).length;
    const b = points(squirclePath(0, 0, 360, 200, 28, 5)).length;
    expect(a).toBe(b);
  });

  it("clamps the radius to half the shortest side", () => {
    const pts = points(squirclePath(0, 0, 100, 10, 50, 5));
    for (const [x, y] of pts) {
      expect(x).toBeGreaterThanOrEqual(-0.01);
      expect(x).toBeLessThanOrEqual(100.01);
      expect(y).toBeGreaterThanOrEqual(-0.01);
      expect(y).toBeLessThanOrEqual(10.01);
    }
  });

  it("is closed", () => {
    expect(squirclePath(0, 0, 10, 10, 2, 5).endsWith("Z")).toBe(true);
  });
});
