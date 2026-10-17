<!--
  Appearance (F-413): the resting island as it will look, drawn on a slice of
  the screen's top edge, with three size presets. The sliders below it change
  width and depth one at a time.
-->
<script lang="ts">
  import type { SettingItem, SettingValue } from "../bindings";
  import { outlinePath } from "../island/outline";

  interface Props {
    width: SettingItem;
    depth: SettingItem;
    disabled: boolean;
    apply: (item: SettingItem, value: SettingValue) => void;
  }

  const { width, depth, disabled, apply }: Props = $props();

  /** The arc is small; the preview draws it twice as large and says so. */
  const ZOOM = 2;

  const PRESETS = [
    { label: "Small", width: 36, depth: 5 },
    { label: "Default", width: 56, depth: 7 },
    { label: "Large", width: 88, depth: 10 },
  ] as const;

  const w = $derived(typeof width.value === "number" ? width.value : 56);
  const d = $derived(typeof depth.value === "number" ? depth.value : 7);
  const path = $derived(
    outlinePath({ cx: 0, width: w, height: d, radius: d, neck: 0, exponent: 2, arc: 1 }),
  );

  function choose(preset: (typeof PRESETS)[number]): void {
    if (preset.width !== w) apply(width, preset.width);
    if (preset.depth !== d) apply(depth, preset.depth);
  }
</script>

<div class="preview">
  <div class="screen" aria-hidden="true">
    <svg
      width={(w + 2) * ZOOM}
      height={(d + 2) * ZOOM}
      viewBox={`${String(-w / 2 - 1)} -1 ${String(w + 2)} ${String(d + 2)}`}
    >
      <path d={path} />
    </svg>
  </div>
  <p class="caption">Shown at twice its size: {w} × {d} px on screen.</p>
  <div class="presets" role="radiogroup" aria-label="Island size">
    {#each PRESETS as preset (preset.label)}
      <button
        type="button"
        role="radio"
        aria-checked={preset.width === w && preset.depth === d}
        {disabled}
        onclick={() => {
          choose(preset);
        }}
      >
        {preset.label}
      </button>
    {/each}
  </div>
</div>

<style>
  .preview {
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-3);
    padding: var(--ev-space-4) 0;
    border-bottom: 1px solid var(--ev-hairline);
  }

  .screen {
    height: var(--ev-preview-height);
    background: var(--ev-control);
    border-radius: var(--ev-radius-control);
    overflow: hidden;
    display: flex;
    justify-content: center;
  }

  svg {
    display: block;
    overflow: visible;
  }

  path {
    fill: var(--ev-island-bg);
    stroke: var(--ev-island-rim);
    stroke-width: calc(var(--ev-island-rim-width) / 2);
  }

  .caption {
    margin: 0;
    color: var(--ev-fg-2);
    font-size: var(--ev-text-11);
    font-variant-numeric: tabular-nums;
  }

  .presets {
    display: flex;
    gap: 2px;
    padding: 2px;
    background: var(--ev-control);
    border-radius: var(--ev-radius-control);
    align-self: flex-start;
  }

  button {
    font: inherit;
    color: var(--ev-fg-1);
    background: transparent;
    border: 0;
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-1) var(--ev-space-3);
    cursor: pointer;
  }

  button[aria-checked="true"] {
    background: var(--ev-surface);
    font-weight: var(--ev-weight-medium);
  }

  button:hover {
    background: var(--ev-control-hover);
  }

  button:disabled {
    cursor: default;
    opacity: 0.5;
  }

  button:focus-visible {
    outline: 2px solid var(--ev-theme-focus-ring);
    outline-offset: 2px;
  }
</style>
