/**
 * Damped spring integrated with fixed 1 ms sub-steps (stable and frame-rate
 * independent). Changing the target keeps the current value and velocity, so
 * every animation can be reversed mid-flight without snapping.
 */
export interface SpringConfig {
  stiffness: number;
  damping: number;
  mass: number;
}

const SUBSTEP_S = 0.001;
/** Longest frame gap integrated at once; longer gaps (tab hidden, debugger) are clamped. */
const MAX_DT_S = 0.064;
/** At rest when slower than this (px/s) and closer than REST_DISTANCE (px); the final snap is invisible. */
const REST_VELOCITY = 10;
const REST_DISTANCE = 0.5;

export class Spring {
  value: number;
  velocity = 0;
  target: number;

  constructor(
    initial: number,
    private readonly config: SpringConfig,
  ) {
    this.value = initial;
    this.target = initial;
  }

  get settled(): boolean {
    return (
      Math.abs(this.velocity) < REST_VELOCITY && Math.abs(this.value - this.target) < REST_DISTANCE
    );
  }

  /** Move instantly (reduced motion, first layout). */
  jump(value: number): void {
    this.value = value;
    this.target = value;
    this.velocity = 0;
  }

  /** Advance by `dtSeconds`; returns true once at rest on the target. */
  step(dtSeconds: number): boolean {
    const { stiffness, damping, mass } = this.config;
    let remaining = Math.min(Math.max(dtSeconds, 0), MAX_DT_S);
    while (remaining > 0) {
      const h = Math.min(SUBSTEP_S, remaining);
      const force = -stiffness * (this.value - this.target) - damping * this.velocity;
      this.velocity += (force / mass) * h;
      this.value += this.velocity * h;
      remaining -= h;
    }
    if (this.settled) {
      this.value = this.target;
      this.velocity = 0;
      return true;
    }
    return false;
  }
}
