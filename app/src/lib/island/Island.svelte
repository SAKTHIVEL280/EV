<!--
  The island (CLAUDE.md §6.1, docs/DESIGN.md §3): a drop of black liquid
  hanging from the top edge of the screen. One outline morphs between the
  idle drop, the hover capsule and the panel, driven by springs; content
  cross-fades on top.

  The idle drop never takes clicks. Rust reveals it (IslandPointer) when the
  pointer stays near it; the UI reports its current shape and whether that
  shape takes clicks after every change (island/pointer.rs).
-->
<script lang="ts">
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { onMount } from "svelte";

  import { commands, events, type CoreStatus, type HitRect } from "../bindings";
  import ChatPanel from "../chat/ChatPanel.svelte";
  import Icon from "../icons/Icon.svelte";
  import { downloadStatus } from "../models/models";
  import { models } from "../models/store.svelte";
  import { dropletBounds, dropletPath, type Drop } from "./droplet";
  import { FrameRecorder } from "./frames";
  import { Spring, type SpringConfig } from "./spring";

  type Mode = "idle" | "hover" | "panel";
  interface Shape {
    width: number;
    height: number;
    radius: number;
    neck: number;
    exponent: number;
  }

  let mode = $state<Mode>("idle");
  let status = $state<CoreStatus>({ state: "starting" });
  let pointerInside = $state(false);
  let path = $state("");

  let chatPanel: { focus: () => void } | undefined = $state();

  const statusText = $derived.by(() => {
    switch (status.state) {
      case "starting":
        return "Starting";
      case "running":
        return downloadStatus(models.state) ?? "Ready";
      case "restarting":
        return `Reconnecting in ${String(Math.max(1, Math.round(status.delay_ms / 1000)))} s`;
      case "failed":
        return status.message;
    }
  });

  // Tokens are the single source of geometry and motion values.
  function token(name: string): number {
    return Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  }

  function shapeFor(m: Mode): Shape {
    return {
      width: token(`--ev-island-${m}-width`),
      height: token(`--ev-island-${m}-height`),
      radius: token(`--ev-island-${m}-radius`),
      neck: token(`--ev-island-${m}-neck`),
      exponent: token(`--ev-island-${m}-exponent`),
    };
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let springs: Record<keyof Shape, Spring>;
  let raf = 0;
  let lastFrame = 0;
  let morphStart = 0;
  let firstFrameAt = 0;
  let morphLabel = "";
  const recorder = new FrameRecorder();

  function current(): Shape {
    return {
      width: springs.width.value,
      height: springs.height.value,
      radius: springs.radius.value,
      neck: springs.neck.value,
      exponent: springs.exponent.value,
    };
  }

  function drop(shape: Shape): Drop {
    return { cx: window.innerWidth / 2, ...shape };
  }

  function draw(): void {
    path = dropletPath(drop(current()));
  }

  /** Tell Rust where the shape is and whether it takes clicks. */
  function report(shape: Shape, clickable: boolean): void {
    const rect: HitRect = dropletBounds(drop(shape));
    void commands.islandSetHitRect(rect, clickable);
  }

  function frame(now: number): void {
    if (firstFrameAt === 0) firstFrameAt = now;
    const dt = lastFrame === 0 ? 1000 / 60 : now - lastFrame;
    if (lastFrame !== 0) recorder.add(dt);
    lastFrame = now;
    let done = true;
    for (const spring of Object.values(springs)) done = spring.step(dt / 1000) && done;
    draw();
    if (done) {
      raf = 0;
      settled(now);
    } else {
      raf = requestAnimationFrame(frame);
    }
  }

  function settled(now: number): void {
    if (mode !== "idle") report(shapeFor(mode), true);
    const summary = recorder.summary();
    // Frame times of every morph go to app.log (budget checks, spike S1).
    void commands.spikeReportFrames({
      label: morphLabel,
      frames: summary.frames,
      dropped: summary.dropped,
      worst_us: Math.round(summary.worstMs * 1000),
      p95_us: Math.round(summary.p95Ms * 1000),
      first_frame_us: Math.round(Math.max(0, firstFrameAt - morphStart) * 1000),
      settle_ms: Math.round(now - morphStart),
      dpr_percent: Math.round(window.devicePixelRatio * 100),
    });
  }

  /** Morph to `next`, interrupting any morph in flight from its current value. */
  function morph(next: Mode, label: string): void {
    const target = shapeFor(next);
    if (next === "idle") {
      // Click-through at once, not when the drop has finished shrinking.
      report(target, false);
    } else {
      // While growing, the area the shape is growing into already takes clicks.
      const now = current();
      report(
        {
          width: Math.max(now.width, target.width),
          height: Math.max(now.height, target.height),
          radius: target.radius,
          neck: Math.max(now.neck, target.neck),
          exponent: target.exponent,
        },
        true,
      );
    }
    morphLabel = label;
    morphStart = performance.now();
    firstFrameAt = 0;
    lastFrame = 0;
    recorder.reset();
    for (const key of Object.keys(springs) as (keyof Shape)[]) {
      if (reducedMotion.matches) springs[key].jump(target[key]);
      else springs[key].target = target[key];
    }
    if (reducedMotion.matches) {
      draw();
      settled(performance.now());
    } else if (raf === 0) {
      raf = requestAnimationFrame(frame);
    }
  }

  function setMode(next: Mode): void {
    if (next === mode) return;
    const label = `${mode}->${next}`;
    mode = next;
    morph(next, label);
  }

  function openPanel(): void {
    setMode("panel");
    void commands.islandSetPanelOpen(true).then(() => chatPanel?.focus());
  }

  function closePanel(): void {
    if (mode !== "panel") return;
    setMode(pointerInside ? "hover" : "idle");
    void commands.islandSetPanelOpen(false);
  }

  function openSettings(): void {
    closePanel();
    void commands.settingsOpen();
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") closePanel();
  }

  onMount(() => {
    const width: SpringConfig = {
      stiffness: token("--ev-spring-width-stiffness"),
      damping: token("--ev-spring-width-damping"),
      mass: token("--ev-spring-mass"),
    };
    const height: SpringConfig = {
      stiffness: token("--ev-spring-height-stiffness"),
      damping: token("--ev-spring-height-damping"),
      mass: token("--ev-spring-mass"),
    };
    const idle = shapeFor("idle");
    springs = {
      width: new Spring(idle.width, width),
      height: new Spring(idle.height, height),
      radius: new Spring(idle.radius, height),
      neck: new Spring(idle.neck, height),
      exponent: new Spring(idle.exponent, height),
    };
    draw();
    report(idle, false);
    models.init();
    // Spike S2: two frames later the first island frame has been painted.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => void commands.spikeIslandPainted());
    });

    // Smoke test (CI): once core runs, open Settings exactly like the button does.
    let smokeTest = false;
    let smokeStarted = false;
    function smokeOnStatus(next: CoreStatus): void {
      if (!smokeTest || smokeStarted || next.state !== "running") return;
      smokeStarted = true;
      void commands.smokeTestStep("core-running");
      void commands.settingsOpen();
    }

    const unlisteners = [
      events.coreStatusChanged.listen((event) => {
        status = event.payload;
        smokeOnStatus(event.payload);
      }),
      events.islandPointer.listen((event) => {
        pointerInside = event.payload.inside;
        if (pointerInside && mode === "idle") setMode("hover");
        if (!pointerInside && mode === "hover") setMode("idle");
      }),
      // Hotkey and tray (F-004, F-412): open with focus, or close if open.
      events.islandToggleRequested.listen(() => {
        if (mode === "panel") closePanel();
        else openPanel();
      }),
      getCurrentWindow().onFocusChanged((event) => {
        if (!event.payload) closePanel();
      }),
    ];
    void commands.smokeTestMode().then(async (enabled) => {
      smokeTest = enabled;
      status = await commands.coreStatus();
      smokeOnStatus(status);
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
  <svg class="surface" aria-hidden="true">
    <path d={path} />
  </svg>

  {#if mode === "hover"}
    <button class="hover" type="button" onclick={openPanel} aria-label="Open EV">
      <span class="status" aria-live="polite">{statusText}</span>
    </button>
  {:else if mode === "panel"}
    <div class="panel" role="dialog" aria-label="EV">
      <header>
        <span class="title">EV</span>
        <span class="meta" aria-live="polite">{statusText}</span>
        <div class="actions">
          <button
            class="icon-button"
            type="button"
            onclick={openSettings}
            aria-label="Settings"
            title="Settings"
          >
            <Icon name="settings" size={18} />
          </button>
          <button
            class="icon-button"
            type="button"
            onclick={() => void commands.appQuit()}
            aria-label="Quit EV"
            title="Quit EV"
          >
            <Icon name="power" size={18} />
          </button>
        </div>
      </header>
      <ChatPanel bind:this={chatPanel} />
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
    width: 100%;
    height: 100%;
    overflow: visible;
  }

  .surface path {
    fill: var(--ev-island-bg);
    stroke: var(--ev-island-rim);
    stroke-width: var(--ev-island-rim-width);
  }

  .hover,
  .panel {
    position: absolute;
    left: 50%;
    top: 0;
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
    padding: var(--ev-space-3) var(--ev-space-5) var(--ev-space-5);
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-3);
  }

  header {
    display: flex;
    align-items: center;
    gap: var(--ev-space-2);
    min-height: var(--ev-control-height);
  }

  .title {
    font-size: var(--ev-text-15);
    font-weight: var(--ev-weight-semibold);
  }

  /* Text uses fg-1 / fg-2 only: fg-3 (40%) is 3.7:1 on black, below WCAG AA. */
  .meta {
    font-size: var(--ev-text-13);
    color: var(--ev-island-fg-2);
    font-variant-numeric: tabular-nums;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .actions {
    margin-left: auto;
    display: flex;
    gap: var(--ev-space-1);
  }

  .icon-button {
    width: var(--ev-control-height);
    height: var(--ev-control-height);
    display: grid;
    place-items: center;
    padding: 0;
    color: var(--ev-island-fg-2);
    background: transparent;
    border: 0;
    border-radius: var(--ev-radius-control);
    cursor: pointer;
  }

  .icon-button:hover {
    color: var(--ev-island-fg-1);
    background: var(--ev-island-control-bg);
  }

  button:focus-visible {
    outline: 2px solid var(--ev-focus-ring);
    outline-offset: 2px;
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
