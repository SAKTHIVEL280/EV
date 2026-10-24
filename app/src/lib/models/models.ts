/**
 * Model list helpers (docs/FEATURES.md F-403). Pure, so formatting and the
 * "does EV have a model yet" rule are testable.
 */
import type { ModelInfo, ModelsState, VoicePackInfo } from "../bindings";

/** What a download row needs: a model or a voice pack (F-010). */
export type Download = ModelInfo | VoicePackInfo;

/** 1 kB = 1000 bytes, as on download pages. */
export function formatSize(kb: number): string {
  if (kb >= 1_000_000) return `${(kb / 1_000_000).toFixed(1)} GB`;
  if (kb >= 1_000) return `${String(Math.round(kb / 1_000))} MB`;
  return `${String(Math.max(0, Math.round(kb)))} kB`;
}

export function formatSpeed(kbPerSecond: number): string {
  return `${formatSize(kbPerSecond)}/s`;
}

export function percent(model: Download): number {
  if (model.size_kb <= 0) return 0;
  return Math.min(100, Math.floor((model.received_kb / model.size_kb) * 100));
}

/** "About 3 min left", or null while the speed is not known yet. */
export function timeLeft(model: Download): string | null {
  if (model.kb_per_second <= 0) return null;
  const seconds = (model.size_kb - model.received_kb) / model.kb_per_second;
  if (seconds < 60) return "Less than a minute left";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `About ${String(minutes)} min left`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `About ${String(hours)} h ${String(rest)} min left`;
}

export function installed(state: ModelsState | null): ModelInfo[] {
  return state?.models.filter((m) => m.state === "installed") ?? [];
}

/** Known to have no model at all (unknown state counts as "not yet known"). */
export function needsModel(state: ModelsState | null): boolean {
  return state !== null && installed(state).length === 0;
}

/** The download in progress, if any (one at a time is the common case). */
export function active(state: ModelsState | null): Download | null {
  const all: Download[] = [...(state?.models ?? []), ...(state?.voice ?? [])];
  return all.find((m) => m.state === "downloading" || m.state === "verifying") ?? null;
}

/** Short status for the island's hover capsule while a model downloads. */
export function downloadStatus(state: ModelsState | null): string | null {
  const model = active(state);
  if (!model) return null;
  return model.state === "verifying"
    ? "Checking the model"
    : `Downloading ${String(percent(model))}%`;
}

/** Recommended first, then by size. */
export function ordered(state: ModelsState | null): ModelInfo[] {
  return [...(state?.models ?? [])].sort(
    (a, b) => Number(b.recommended) - Number(a.recommended) || a.size_kb - b.size_kb,
  );
}
