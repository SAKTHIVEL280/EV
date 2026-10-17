<!--
  Model choices with download progress (docs/FEATURES.md F-403). Used in the
  island panel (first run, white on black) and in Settings (theme colors).
-->
<script lang="ts">
  import Icon from "../icons/Icon.svelte";
  import { formatSize, formatSpeed, ordered, percent, timeLeft } from "./models";
  import { models } from "./store.svelte";

  interface Props {
    variant: "island" | "settings";
  }

  const { variant }: Props = $props();

  let errors = $state<Record<string, string>>({});
  const list = $derived(ordered(models.state));

  async function act(id: string, action: "download" | "cancel"): Promise<void> {
    const error = await (action === "download" ? models.download(id) : models.cancel(id));
    errors = { ...errors, [id]: error ?? "" };
  }
</script>

<ul class="models {variant}">
  {#each list as model (model.id)}
    {@const busy = model.state === "downloading" || model.state === "verifying"}
    <li>
      <div class="row">
        <div class="text">
          <p class="name">
            {model.name}
            {#if model.recommended}<span class="tag">Recommended</span>{/if}
          </p>
          <p class="summary">{model.summary}</p>
        </div>
        <span class="size">{formatSize(model.size_kb)}</span>
        {#if model.state === "installed"}
          <span class="done">Installed</span>
        {:else if busy}
          <button
            class="action"
            type="button"
            onclick={() => void act(model.id, "cancel")}
            disabled={model.state === "verifying"}
            aria-label={`Stop downloading ${model.name}`}
          >
            <Icon name="stop" size={16} />
            <span>Stop</span>
          </button>
        {:else}
          <button
            class="action"
            type="button"
            onclick={() => void act(model.id, "download")}
            aria-label={`Download ${model.name}`}
          >
            <Icon name="download" size={16} />
            <span
              >{model.state === "partial"
                ? "Resume"
                : model.state === "failed"
                  ? "Try again"
                  : "Download"}</span
            >
          </button>
        {/if}
      </div>
      {#if busy || model.state === "partial"}
        <div
          class="track"
          role="progressbar"
          aria-label={`${model.name} download`}
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={percent(model)}
        >
          <div class="fill" style:transform={`scaleX(${String(percent(model) / 100)})`}></div>
        </div>
        <p class="meta" aria-live="polite">
          {#if model.state === "verifying"}
            Checking the file
          {:else if model.state === "partial"}
            {percent(model)}% downloaded. Resume to continue.
          {:else}
            {percent(model)}%{model.kb_per_second > 0
              ? ` · ${formatSpeed(model.kb_per_second)}`
              : ""}{timeLeft(model) ? ` · ${timeLeft(model) ?? ""}` : ""}
          {/if}
        </p>
      {/if}
      {#if model.state === "failed" && model.error}
        <p class="meta error" role="alert">{model.error}</p>
      {:else if errors[model.id]}
        <p class="meta error" role="alert">{errors[model.id]}</p>
      {/if}
    </li>
  {/each}
</ul>

<style>
  .models {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  .island {
    --fg-1: var(--ev-island-fg-1);
    --fg-2: var(--ev-island-fg-2);
    --line: var(--ev-island-hairline);
    --control: var(--ev-island-control-bg);
    --control-hover: var(--ev-island-control-bg-hover);
    --fill: var(--ev-accent);
    --track: var(--ev-progress-track);
    --ring: var(--ev-focus-ring);
  }

  .settings {
    --fg-1: var(--ev-fg-1);
    --fg-2: var(--ev-fg-2);
    --line: var(--ev-hairline);
    --control: var(--ev-control);
    --control-hover: var(--ev-control-hover);
    --fill: var(--ev-fg-1);
    --track: var(--ev-control);
    --ring: var(--ev-theme-focus-ring);
  }

  li {
    padding: var(--ev-space-2) 0;
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-1);
  }

  li + li {
    border-top: 1px solid var(--line);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--ev-space-3);
  }

  .text {
    flex: 1;
    min-width: 0;
  }

  p {
    margin: 0;
  }

  .name {
    font-size: var(--ev-text-13);
    font-weight: var(--ev-weight-semibold);
    color: var(--fg-1);
    display: flex;
    align-items: baseline;
    gap: var(--ev-space-2);
  }

  .tag,
  .summary,
  .size,
  .done,
  .meta {
    font-size: var(--ev-text-11);
    color: var(--fg-2);
    font-variant-numeric: tabular-nums;
  }

  .tag {
    font-weight: var(--ev-weight-medium);
  }

  .summary {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .size {
    white-space: nowrap;
  }

  .done {
    min-width: var(--ev-model-action-width);
    text-align: center;
  }

  .action {
    min-width: var(--ev-model-action-width);
    height: var(--ev-control-height);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--ev-space-1);
    padding: 0 var(--ev-space-3);
    font: inherit;
    font-size: var(--ev-text-11);
    font-weight: var(--ev-weight-medium);
    color: var(--fg-1);
    background: var(--control);
    border: 0;
    border-radius: var(--ev-radius-control);
    cursor: pointer;
  }

  .action:hover:not(:disabled) {
    background: var(--control-hover);
  }

  .action:disabled {
    color: var(--fg-2);
    cursor: default;
  }

  .action:focus-visible {
    outline: 2px solid var(--ring);
    outline-offset: 2px;
  }

  .track {
    height: var(--ev-progress-height);
    background: var(--track);
    border-radius: var(--ev-progress-height);
    overflow: hidden;
  }

  .fill {
    height: 100%;
    background: var(--fill);
    transform-origin: left center;
    transition: transform var(--ev-fade-content) linear;
  }
</style>
