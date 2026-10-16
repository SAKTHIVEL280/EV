<!--
  Island spike (Phase 0, S1). Shapes: idle pill, hover, panel. One black
  surface morphs through a squircle clip-path driven by springs; content
  cross-fades on top. Only clip-path and opacity animate (CLAUDE.md §6.2).
  Exact geometry and the full state set arrive in Phase 2.
-->
<script lang="ts">
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { onMount } from "svelte";

  import { commands, events, type CoreStatus, type HitRect } from "../bindings";
  import { FrameRecorder, type FrameSummary } from "./frames";
  import { Spring, type SpringConfig } from "./spring";
  import { squirclePath } from "./squircle";

  type Mode = "idle" | "hover" | "panel";
  interface Size {
    width: number;
    height: number;
  }
  interface MorphResult extends FrameSummary {
    label: string;
    settleMs: number;
    firstFrameMs: number;
  }

  const MORPH_TEST_CYCLES = 3;
  const PANEL_RADIUS = 28;

  let mode = $state<Mode>("idle");
  let status = $state<CoreStatus>({ state: "starting" });
  let pointerInside = $state(false);
  let testing = $state(false);
  let lastTest = $state<MorphResult[]>([]);

  let surface: HTMLDivElement | undefined = $state();

  const statusText = $derived.by(() => {
    switch (status.state) {
      case "starting":
        return "Starting";
      case "running":
        return "Ready";
      case "restarting":
        return `Reconnecting in ${String(Math.max(1, Math.round(status.delay_ms / 1000)))} s`;
      case "failed":
        return status.message;
    }
  });

  const coreVersion = $derived(status.state === "running" ? status.core_version : null);

  const testSummary = $derived.by(() => {
    if (lastTest.length === 0) return null;
    const frames = lastTest.reduce((n, r) => n + r.frames, 0);
    const dropped = lastTest.reduce((n, r) => n + r.dropped, 0);
    const worst = Math.max(...lastTest.map((r) => r.worstMs));
    const settle = Math.max(...lastTest.map((r) => r.settleMs));
    return `${String(lastTest.length)} morphs · ${String(frames)} frames · ${String(dropped)} dropped · worst ${worst.toFixed(1)} ms · settle ${String(Math.round(settle))} ms`;
  });

  // Tokens are the single source of geometry and motion values.
  function token(name: string): number {
    return Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  }

  function sizeFor(m: Mode): Size {
    return {
      width: token(`--ev-island-${m}-width`),
      height: token(`--ev-island-${m}-height`),
    };
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let widthSpring: Spring;
  let heightSpring: Spring;
  let raf = 0;
  let lastFrame = 0;
  let morphStart = 0;
  let inputAt = 0;
  let firstFrameAt = 0;
  let morphLabel = "";
  const recorder = new FrameRecorder();
  let settleWaiters: ((result: MorphResult) => void)[] = [];

  function geometry(width: number, height: number): { x: number; y: number; r: number } {
    return {
      x: (window.innerWidth - width) / 2,
      y: token("--ev-island-top"),
      r: Math.min(height / 2, PANEL_RADIUS),
    };
  }

  function draw(): void {
    if (!surface) return;
    const width = widthSpring.value;
    const height = heightSpring.value;
    const { x, y, r } = geometry(width, height);
    const path = squirclePath(x, y, width, height, r, token("--ev-squircle-exponent"));
    surface.style.clipPath = `path("${path}")`;
  }

  function hitRect(size: Size): HitRect {
    const slop = token("--ev-island-hit-slop");
    const { x, y } = geometry(size.width, size.height);
    return {
      x: Math.floor(x - slop),
      y: 0,
      width: Math.ceil(size.width + 2 * slop),
      height: Math.ceil(y + size.height + slop),
    };
  }

  function reportHitRect(size: Size): void {
    void commands.islandSetHitRect(hitRect(size));
  }

  function frame(now: number): void {
    if (firstFrameAt === 0) firstFrameAt = now;
    const dt = lastFrame === 0 ? 1000 / 60 : now - lastFrame;
    if (lastFrame !== 0) recorder.add(dt);
    lastFrame = now;
    const doneW = widthSpring.step(dt / 1000);
    const doneH = heightSpring.step(dt / 1000);
    draw();
    if (doneW && doneH) {
      raf = 0;
      settled(now);
    } else {
      raf = requestAnimationFrame(frame);
    }
  }

  function settled(now: number): void {
    const result: MorphResult = {
      ...recorder.summary(),
      label: morphLabel,
      settleMs: now - morphStart,
      firstFrameMs: Math.max(0, firstFrameAt - inputAt),
    };
    reportHitRect({ width: widthSpring.target, height: heightSpring.target });
    void commands.spikeReportFrames({
      label: result.label,
      frames: result.frames,
      dropped: result.dropped,
      worst_us: Math.round(result.worstMs * 1000),
      p95_us: Math.round(result.p95Ms * 1000),
      first_frame_us: Math.round(result.firstFrameMs * 1000),
      settle_ms: Math.round(result.settleMs),
      dpr_percent: Math.round(window.devicePixelRatio * 100),
    });
    const waiters = settleWaiters;
    settleWaiters = [];
    for (const resolve of waiters) resolve(result);
  }

  /** Morph to `next`, interrupting any morph in flight from its current value. */
  function morph(next: Mode, label: string): Promise<MorphResult> {
    const target = sizeFor(next);
    const current = { width: widthSpring.value, height: heightSpring.value };
    // While growing, the target area must already accept the cursor.
    reportHitRect({
      width: Math.max(current.width, target.width),
      height: Math.max(current.height, target.height),
    });
    morphLabel = label;
    inputAt = performance.now();
    morphStart = inputAt;
    firstFrameAt = 0;
    lastFrame = 0;
    recorder.reset();
    const done = new Promise<MorphResult>((resolve) => settleWaiters.push(resolve));
    if (reducedMotion.matches) {
      widthSpring.jump(target.width);
      heightSpring.jump(target.height);
      draw();
      settled(performance.now());
      return done;
    }
    widthSpring.target = target.width;
    heightSpring.target = target.height;
    if (raf === 0) raf = requestAnimationFrame(frame);
    return done;
  }

  function setMode(next: Mode): void {
    if (next === mode) return;
    const label = `${mode}->${next}`;
    mode = next;
    void morph(next, label);
  }

  function openPanel(): void {
    setMode("panel");
    void commands.islandSetPanelOpen(true);
  }

  function closePanel(): void {
    if (mode !== "panel") return;
    setMode(pointerInside ? "hover" : "idle");
    void commands.islandSetPanelOpen(false);
  }

  async function runMorphTest(): Promise<void> {
    testing = true;
    const results: MorphResult[] = [];
    for (let i = 0; i < MORPH_TEST_CYCLES; i += 1) {
      results.push(await morph("idle", "test panel->idle"));
      results.push(await morph("panel", "test idle->panel"));
    }
    lastTest = results;
    testing = false;
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") closePanel();
  }

  onMount(() => {
    const config: SpringConfig = {
      stiffness: token("--ev-spring-stiffness"),
      damping: token("--ev-spring-damping"),
      mass: token("--ev-spring-mass"),
    };
    const idle = sizeFor("idle");
    widthSpring = new Spring(idle.width, config);
    heightSpring = new Spring(idle.height, config);
    draw();
    reportHitRect(idle);
    // Spike S2: two frames later the first island frame has been painted.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => void commands.spikeIslandPainted());
    });

    const unlisteners = [
      events.coreStatusChanged.listen((event) => {
        status = event.payload;
      }),
      events.islandPointer.listen((event) => {
        pointerInside = event.payload.inside;
        if (pointerInside && mode === "idle") setMode("hover");
        if (!pointerInside && mode === "hover") setMode("idle");
      }),
      getCurrentWindow().onFocusChanged((event) => {
        if (!event.payload) closePanel();
      }),
    ];
    void commands.coreStatus().then((initial) => {
      status = initial;
    });

    return () => {
      cancelAnimationFrame(raf);
      for (const pending of unlisteners)
        void pending.then((unlisten) => {
          unlisten();
        });
    };
  });
</script>

<svelte:window onkeydown={onKeydown} />

<div class="island" data-mode={mode}>
  <div class="surface" bind:this={surface}></div>

  {#if mode === "hover"}
    <button class="hover" type="button" onclick={openPanel} aria-label="Open EV">
      <span class="status" aria-live="polite">{statusText}</span>
    </button>
  {:else if mode === "panel"}
    <div class="panel" class:testing role="dialog" aria-label="EV">
      <header>
        <span class="title">EV</span>
        {#if coreVersion}<span class="meta">core {coreVersion}</span>{/if}
      </header>
      <p class="status-line" aria-live="polite">{statusText}</p>
      <section class="spike" aria-label="Island spike">
        <button type="button" onclick={() => void runMorphTest()} disabled={testing}>
          {testing ? "Testing" : "Run morph test"}
        </button>
        {#if testSummary}<p class="result">{testSummary}</p>{/if}
      </section>
      <footer>
        <button type="button" onclick={closePanel}>Close</button>
        <button type="button" onclick={() => void commands.appQuit()}>Quit EV</button>
      </footer>
    </div>
  {/if}
</div>

<style>
  .island {
    position: fixed;
    inset: 0;
    font-family: var(--ev-font-sans);
    color: var(--ev-island-fg-1);
  }

  .surface {
    position: absolute;
    inset: 0;
    background: var(--ev-island-bg);
    will-change: clip-path;
  }

  .hover,
  .panel {
    position: absolute;
    left: 50%;
    top: var(--ev-island-top);
    transform: translateX(-50%);
    animation: fade-in var(--ev-fade-content) ease-out both;
  }

  .hover {
    width: var(--ev-island-hover-width);
    height: var(--ev-island-hover-height);
    display: grid;
    place-items: center;
    padding: 0 var(--ev-space-4);
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .status {
    font-size: var(--ev-text-13);
    font-weight: var(--ev-weight-medium);
    color: var(--ev-island-fg-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  .panel {
    width: var(--ev-island-panel-width);
    height: var(--ev-island-panel-height);
    box-sizing: border-box;
    padding: var(--ev-space-4) var(--ev-space-5);
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-2);
  }

  /* The morph test shrinks the surface under the panel; hide its content meanwhile. */
  .panel.testing {
    opacity: 0;
  }

  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }

  .title {
    font-size: var(--ev-text-15);
    font-weight: var(--ev-weight-semibold);
  }

  .meta,
  .result {
    font-size: var(--ev-text-13);
    color: var(--ev-island-fg-3);
    font-variant-numeric: tabular-nums;
  }

  .status-line {
    margin: 0;
    font-size: var(--ev-text-13);
    color: var(--ev-island-fg-2);
  }

  .spike {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--ev-space-1);
    padding-top: var(--ev-space-2);
    border-top: 1px solid var(--ev-island-hairline);
  }

  .result {
    margin: 0;
  }

  footer {
    margin-top: auto;
    display: flex;
    gap: var(--ev-space-2);
    justify-content: flex-end;
  }

  .spike button,
  footer button {
    font: inherit;
    font-size: var(--ev-text-13);
    font-weight: var(--ev-weight-medium);
    color: var(--ev-island-fg-1);
    background: var(--ev-island-control-bg);
    border: 0;
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-1) var(--ev-space-3);
    cursor: pointer;
  }

  .spike button:hover,
  footer button:hover {
    background: var(--ev-island-control-bg-hover);
  }

  button:focus-visible {
    outline: 2px solid var(--ev-focus-ring);
    outline-offset: 2px;
  }

  button:disabled {
    color: var(--ev-island-fg-3);
    cursor: default;
  }

  @keyframes fade-in {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .hover,
    .panel {
      animation-duration: var(--ev-fade-reduced);
    }
  }
</style>
