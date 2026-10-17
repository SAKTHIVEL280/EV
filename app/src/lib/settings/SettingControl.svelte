<!--
  One setting's control (F-410, F-415). The schema says which: a switch, a
  segmented choice, a slider, a model menu, a folder picker, a shortcut
  recorder, or a text field for free text. Every change goes to core, which
  validates it; nothing here needs a Save button.
-->
<script lang="ts">
  import { commands, type SettingItem, type SettingValue } from "../bindings";
  import { models } from "../models/store.svelte";
  import {
    anyModelInstalled,
    modelOptions,
    nearestIndex,
    recordShortcut,
    shortcutLabel,
    sliderText,
    sliderValues,
  } from "./controls";
  import { itemId, parseInput } from "./settings";

  interface Props {
    item: SettingItem;
    disabled: boolean;
    apply: (value: SettingValue) => void;
    fail: (message: string | null) => void;
    /** Show the model list (when no model is installed). */
    showModels: () => void;
  }

  const { item, disabled, apply, fail, showModels }: Props = $props();

  const labelId = $derived(`label-${itemId(item)}`);

  // --- slider: shows the value live while dragging, applies on release.
  const values = $derived(item.widget === "slider" ? sliderValues(item) : []);
  let dragIndex = $state<number | null>(null);
  const storedIndex = $derived(
    typeof item.value === "number" ? nearestIndex(values, item.value) : 0,
  );
  const shownIndex = $derived(dragIndex ?? storedIndex);
  const shownValue = $derived(values[shownIndex] ?? 0);

  function slide(event: Event): void {
    dragIndex = Number((event.currentTarget as HTMLInputElement).value);
  }

  function commitSlide(): void {
    if (dragIndex === null) return;
    const value = values[dragIndex];
    dragIndex = null;
    if (value !== undefined && value !== item.value) apply(value);
  }

  // --- shortcut recorder.
  let recording = $state(false);
  let recorder: HTMLButtonElement | undefined = $state();

  function startRecording(): void {
    fail(null);
    recording = true;
    recorder?.focus();
  }

  function onRecordKey(event: KeyboardEvent): void {
    if (!recording) return;
    event.preventDefault();
    event.stopPropagation();
    const result = recordShortcut(event);
    if (result.kind === "pending") return;
    recording = false;
    if (result.kind === "refused") fail(result.message);
    else if (result.kind === "shortcut" && result.spec !== item.value) apply(result.spec);
  }

  // --- folder picker.
  async function chooseFolder(): Promise<void> {
    fail(null);
    const start = typeof item.value === "string" && item.value ? item.value : null;
    const result = await commands.pickFolder(item.label, start);
    if (result.status === "error") fail(result.error.message);
    else if (result.data !== null && result.data !== item.value) apply(result.data);
  }

  // --- model menu.
  const options = $derived(
    item.widget === "model"
      ? modelOptions(models.state, item.role ?? "default", String(item.value))
      : [],
  );
  const selected = $derived(options.find((o) => o.value === item.value) ?? null);

  // --- free text and plain numbers.
  function commitInput(event: Event): void {
    const parsed = parseInput(item, (event.currentTarget as HTMLInputElement).value);
    if (!parsed.ok) {
      fail(parsed.message);
      return;
    }
    if (parsed.value !== item.value) apply(parsed.value);
  }
</script>

{#if item.kind === "boolean"}
  <button
    type="button"
    role="switch"
    class="switch"
    aria-checked={item.value === true}
    aria-labelledby={labelId}
    {disabled}
    onclick={() => {
      apply(item.value !== true);
    }}
  >
    <span class="knob"></span>
  </button>
{:else if item.kind === "choice"}
  <div class="segmented" role="radiogroup" aria-labelledby={labelId}>
    {#each item.options as option (option)}
      <button
        type="button"
        role="radio"
        aria-checked={item.value === option}
        {disabled}
        onclick={() => {
          apply(option);
        }}
      >
        {option}
      </button>
    {/each}
  </div>
{:else if item.widget === "slider" && values.length > 1}
  <div class="slider">
    <input
      type="range"
      min="0"
      max={values.length - 1}
      step="1"
      value={shownIndex}
      aria-labelledby={labelId}
      aria-valuetext={sliderText(item, shownValue)}
      {disabled}
      oninput={slide}
      onchange={commitSlide}
    />
    <span class="value">{sliderText(item, shownValue)}</span>
  </div>
{:else if item.widget === "model"}
  {#if anyModelInstalled(models.state) || item.value !== ""}
    <div class="model">
      <select
        aria-labelledby={labelId}
        {disabled}
        value={String(item.value)}
        onchange={(event) => {
          apply(event.currentTarget.value);
        }}
      >
        {#each options as option (option.value)}
          <option value={option.value}>{option.label}</option>
        {/each}
      </select>
      {#if selected?.detail}<span class="detail">{selected.detail}</span>{/if}
    </div>
  {:else}
    <div class="model">
      <span class="detail">No model installed</span>
      <button type="button" class="action" {disabled} onclick={showModels}>Download</button>
    </div>
  {/if}
{:else if item.widget === "folder"}
  <div class="folder">
    {#if item.value === ""}
      <span class="detail">{models.state?.models_dir ?? "EV's data folder"}</span>
    {:else}
      <span class="path" title={String(item.value)}>{String(item.value)}</span>
    {/if}
    <button type="button" class="action" {disabled} onclick={() => void chooseFolder()}>
      Choose folder
    </button>
  </div>
{:else if item.widget === "shortcut"}
  <div class="shortcut">
    <button
      bind:this={recorder}
      type="button"
      class="keys"
      class:recording
      aria-labelledby={labelId}
      aria-describedby={`${labelId}-hint`}
      {disabled}
      onclick={startRecording}
      onkeydown={onRecordKey}
      onblur={() => (recording = false)}
    >
      {recording ? "Press the keys" : shortcutLabel(String(item.value))}
    </button>
    <span class="detail" id={`${labelId}-hint`}>
      {recording ? "Esc cancels" : "Click, then press the new shortcut"}
    </span>
    {#if item.value !== "" && !recording}
      <button
        type="button"
        class="link"
        {disabled}
        onclick={() => {
          apply("");
        }}>Turn off</button
      >
    {/if}
  </div>
{:else}
  <span class="field" class:number={item.kind === "integer"}>
    <input
      type="text"
      inputmode={item.kind === "integer" ? "numeric" : "text"}
      value={String(item.value)}
      aria-labelledby={labelId}
      {disabled}
      onchange={commitInput}
    />
    {#if item.unit}<span class="unit">{item.unit}</span>{/if}
  </span>
{/if}

<style>
  .switch {
    width: 40px;
    height: 22px;
    padding: 2px;
    border: 0;
    border-radius: 11px;
    background: var(--ev-control-hover);
    cursor: pointer;
    display: flex;
  }

  .switch[aria-checked="true"] {
    background: var(--ev-switch-on);
    justify-content: flex-end;
  }

  .knob {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    background: var(--ev-switch-knob);
  }

  .segmented {
    display: flex;
    gap: 2px;
    padding: 2px;
    background: var(--ev-control);
    border-radius: var(--ev-radius-control);
  }

  .segmented button,
  .action,
  .link,
  .keys {
    font: inherit;
    color: var(--ev-fg-1);
    border: 0;
    cursor: pointer;
  }

  .segmented button {
    background: transparent;
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-1) var(--ev-space-3);
    text-transform: capitalize;
  }

  .segmented button[aria-checked="true"] {
    background: var(--ev-surface);
    font-weight: var(--ev-weight-medium);
  }

  .segmented button:hover,
  .action:hover,
  .keys:hover {
    background: var(--ev-control-hover);
  }

  .slider {
    display: flex;
    align-items: center;
    gap: var(--ev-space-3);
  }

  .slider input {
    width: var(--ev-slider-width);
    accent-color: var(--ev-switch-on);
  }

  .value {
    min-width: var(--ev-slider-value-width);
    text-align: right;
    font-variant-numeric: tabular-nums;
    color: var(--ev-fg-1);
  }

  .model,
  .folder,
  .shortcut {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--ev-space-1);
    max-width: var(--ev-control-column-width);
  }

  select {
    width: var(--ev-control-column-width);
    font: inherit;
    color: var(--ev-fg-1);
    background: var(--ev-control);
    border: 1px solid var(--ev-hairline);
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-2) var(--ev-space-3);
  }

  .detail {
    color: var(--ev-fg-2);
    font-size: var(--ev-text-11);
    text-align: right;
  }

  .path {
    font-family: var(--ev-font-mono);
    font-size: var(--ev-text-11);
    color: var(--ev-fg-2);
    max-width: var(--ev-control-column-width);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    direction: rtl;
    text-align: left;
  }

  .action,
  .keys {
    background: var(--ev-control);
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-2) var(--ev-space-4);
  }

  .keys {
    min-width: var(--ev-model-action-width);
    font-variant-numeric: tabular-nums;
    font-weight: var(--ev-weight-medium);
  }

  .keys.recording {
    outline: 2px solid var(--ev-theme-focus-ring);
    outline-offset: 2px;
    font-weight: var(--ev-weight-regular);
    color: var(--ev-fg-2);
  }

  .link {
    background: transparent;
    color: var(--ev-fg-2);
    text-decoration: underline;
    padding: 0;
  }

  .field {
    display: inline-flex;
    align-items: center;
    gap: var(--ev-space-2);
  }

  .unit {
    min-width: var(--ev-unit-width);
    font-size: var(--ev-text-13);
    color: var(--ev-fg-2);
  }

  input[type="text"] {
    width: var(--ev-control-column-width);
    box-sizing: border-box;
    font: inherit;
    color: var(--ev-fg-1);
    background: var(--ev-control);
    border: 1px solid var(--ev-hairline);
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-2) var(--ev-space-3);
    font-variant-numeric: tabular-nums;
  }

  .number input[type="text"] {
    width: var(--ev-number-input-width);
    text-align: right;
  }

  button:disabled,
  select:disabled,
  input:disabled {
    cursor: default;
    opacity: 0.5;
  }

  button:focus-visible,
  input:focus-visible,
  select:focus-visible {
    outline: 2px solid var(--ev-theme-focus-ring);
    outline-offset: 2px;
  }
</style>
