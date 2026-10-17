import { describe, expect, it } from "vitest";

import { dropletBounds, dropletPath, dropletPoints, fitted, type Drop } from "./droplet";

const idle: Drop = { cx: 210, width: 16, height: 13, radius: 8, neck: 5, exponent: 2 };
const panel: Drop = { cx: 210, width: 380, height: 264, radius: 26, neck: 12, exponent: 5 };

describe("droplet", () => {
  it("hangs from the top edge and reaches its full height", () => {
    for (const drop of [idle, panel]) {
      const ys = dropletPoints(drop).map(([, y]) => y);
      expect(Math.min(...ys)).toBeLessThan(0); // closes above the edge
      expect(Math.max(...ys)).toBeCloseTo(drop.height, 5);
    }
  });

  it("spans the body plus the neck on both sides", () => {
    const xs = dropletPoints(panel).map(([x]) => x);
    expect(Math.min(...xs)).toBeCloseTo(210 - 190 - 12, 5);
    expect(Math.max(...xs)).toBeCloseTo(210 + 190 + 12, 5);
  });

  it("has the same point count for every size, so frames interpolate", () => {
    expect(dropletPoints(idle).length).toBe(dropletPoints(panel).length);
    expect(dropletPoints({ ...idle, width: 0, height: 0 }).length).toBe(dropletPoints(idle).length);
  });

  it("clamps radii so spring overshoot or tiny sizes never break the outline", () => {
    const tiny = fitted({ ...idle, width: 4, height: 3, radius: 20, neck: 9 });
    expect(tiny.neck).toBeLessThanOrEqual(1.5);
    expect(tiny.radius).toBeLessThanOrEqual(2);
    expect(tiny.radius + tiny.neck).toBeLessThanOrEqual(tiny.height);
    expect(dropletPath({ ...idle, width: -5, height: -1 })).not.toMatch(/NaN/);
  });

  it("bounds cover the visible outline", () => {
    expect(dropletBounds(idle)).toEqual({ x: 197, y: 0, width: 26, height: 13 });
  });
});
