import { describe, expect, it } from "vitest";

import { Spring } from "./spring";

const DEFAULT = { stiffness: 400, damping: 32, mass: 1 };

function run(spring: Spring, seconds: number, fps = 60): number {
  let frames = 0;
  for (let t = 0; t < seconds; t += 1 / fps) {
    frames += 1;
    if (spring.step(1 / fps)) break;
  }
  return frames;
}

describe("Spring", () => {
  it("settles exactly on the target", () => {
    const spring = new Spring(0, DEFAULT);
    spring.target = 100;
    run(spring, 2);
    expect(spring.value).toBe(100);
    expect(spring.velocity).toBe(0);
    expect(spring.settled).toBe(true);
  });

  it("default spring settles the largest morph (240 px) in about 417 ms", () => {
    // Known Phase 0 finding (docs/decisions.md): the contract default misses the
    // 350 ms "animation complete" budget for the idle -> panel morph; tuned in Phase 2.
    const spring = new Spring(0, DEFAULT);
    spring.target = 240;
    const ms = (run(spring, 2) / 60) * 1000;
    expect(ms).toBeGreaterThan(350);
    expect(ms).toBeLessThan(450);
  });

  it("a stiffer candidate meets the 350 ms budget", () => {
    const spring = new Spring(0, { stiffness: 500, damping: 40, mass: 1 });
    spring.target = 240;
    expect((run(spring, 2) / 60) * 1000).toBeLessThanOrEqual(350);
  });

  it("is frame-rate independent", () => {
    const a = new Spring(0, DEFAULT);
    const b = new Spring(0, DEFAULT);
    a.target = b.target = 50;
    for (let i = 0; i < 6; i += 1) a.step(1 / 60);
    for (let i = 0; i < 12; i += 1) b.step(1 / 120);
    // 1 ms sub-steps split 16.7 ms and 8.3 ms frames differently: <0.01% apart.
    expect(Math.abs(a.value - b.value) / a.value).toBeLessThan(1e-4);
  });

  it("reverses mid-flight from the current value without snapping", () => {
    const spring = new Spring(0, DEFAULT);
    spring.target = 100;
    for (let i = 0; i < 5; i += 1) spring.step(1 / 60);
    const before = spring.value;
    const velocity = spring.velocity;
    spring.target = 0;
    expect(spring.value).toBe(before);
    expect(spring.velocity).toBe(velocity);
    spring.step(1 / 60);
    expect(Math.abs(spring.value - before)).toBeLessThan(10);
  });

  it("clamps huge frame gaps", () => {
    const spring = new Spring(0, DEFAULT);
    spring.target = 100;
    spring.step(10);
    expect(Number.isFinite(spring.value)).toBe(true);
    expect(spring.value).toBeLessThan(100);
  });

  it("jump moves instantly", () => {
    const spring = new Spring(0, DEFAULT);
    spring.jump(42);
    expect(spring.value).toBe(42);
    expect(spring.settled).toBe(true);
  });
});
