/**
 * Frame-time recorder for spike S1 (60 fps, 0 dropped frames during a morph).
 * A frame longer than DROPPED_MS counts as dropped (docs/PERFORMANCE.md §2).
 */
export const DROPPED_MS = 20;

export interface FrameSummary {
  frames: number;
  dropped: number;
  worstMs: number;
  p95Ms: number;
}

export class FrameRecorder {
  private deltas: number[] = [];

  add(deltaMs: number): void {
    this.deltas.push(deltaMs);
  }

  get count(): number {
    return this.deltas.length;
  }

  summary(): FrameSummary {
    const sorted = [...this.deltas].sort((a, b) => a - b);
    const p95Index = Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1);
    return {
      frames: sorted.length,
      dropped: sorted.filter((d) => d > DROPPED_MS).length,
      worstMs: sorted.at(-1) ?? 0,
      p95Ms: sorted.length === 0 ? 0 : (sorted[Math.max(0, p95Index)] ?? 0),
    };
  }

  reset(): void {
    this.deltas = [];
  }
}
