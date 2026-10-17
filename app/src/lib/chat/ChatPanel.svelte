<!--
  Typed chat (docs/FEATURES.md F-001, F-414): the whole session and one
  input. The session lives in the chat store, so closing the panel keeps it.
  Replies stream in; a new message replaces a reply that is still streaming.
  Until a model is installed, the panel offers the models instead (F-403).
-->
<script lang="ts">
  import { onMount, tick } from "svelte";

  import ModelList from "../models/ModelList.svelte";
  import { needsModel } from "../models/models";
  import { models } from "../models/store.svelte";
  import { busy, latest, type Turn } from "./chat";
  import { chat } from "./store.svelte";
  import { pc } from "../pc/store.svelte";

  const TOOL_TEXT: Record<string, string> = {
    current_time: "Checking the time",
    date_math: "Counting the days",
    apps: "Working with your apps",
    window: "Moving the window",
    system: "Changing the setting",
    screenshot: "Taking a screenshot",
    clipboard: "Reading the clipboard",
    files: "Looking through your files",
    timer: "Setting it up",
    focus_mode: "Updating focus mode",
    ui: "Working in the app",
    undo_last: "Undoing",
  };
  /** Within this distance of the bottom, new text keeps the view pinned there. */
  const PIN_SLACK_PX = 24;

  let draft = $state("");
  let input: HTMLInputElement | undefined = $state();
  let list: HTMLDivElement | undefined = $state();
  let pinned = true;

  const setup = $derived(needsModel(models.state));
  const entries = $derived(chat.state.entries);
  const newest = $derived(latest(chat.state));

  export function focus(): void {
    input?.focus();
  }

  const modelText = $derived.by(() => {
    switch (chat.llm.state) {
      case "loading":
        return "Waking up";
      case "failed":
        return chat.llm.detail ?? "Couldn't load the model.";
      default:
        return "";
    }
  });

  function waiting(turn: Turn): string | null {
    if (turn.reply || turn.status === "failed") return null;
    if (turn.tool) {
      return pc.question?.turnId === turn.id
        ? "Waiting for your answer"
        : (TOOL_TEXT[turn.tool] ?? "Working");
    }
    return turn === newest && busy(chat.state) ? "Thinking" : null;
  }

  function onScroll(): void {
    if (!list) return;
    pinned = list.scrollHeight - list.scrollTop - list.clientHeight <= PIN_SLACK_PX;
  }

  function toBottom(): void {
    if (list) list.scrollTop = list.scrollHeight;
  }

  /** Changes whenever a message arrives or the newest reply grows. */
  const growth = $derived(`${String(entries.length)}:${String(newest?.reply.length ?? 0)}`);

  // Keep the newest text in view while pinned.
  $effect(() => {
    if (growth && pinned) void tick().then(toBottom);
  });

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    draft = "";
    pinned = true;
    await chat.send(text);
  }

  onMount(() => {
    models.init();
    chat.init();
    // Opening the panel shows the newest message.
    void tick().then(toBottom);
  });
</script>

{#if setup}
  <div class="setup">
    <p class="lead">Choose a model to start.</p>
    <p class="hint">It runs on this PC. Nothing you type leaves it.</p>
    <ModelList variant="island" />
  </div>
{:else}
  <div class="chat">
    {#if modelText}<p class="model" aria-live="polite">{modelText}</p>{/if}

    <div class="session" bind:this={list} onscroll={onScroll} aria-live="polite">
      {#each entries as entry, i (i)}
        {#if entry.type === "notice"}
          <p class="notice">{entry.text}</p>
        {:else}
          <div class="turn">
            <p class="user">{entry.user}</p>
            {#if entry.status === "failed"}
              <p class="reply muted">{entry.error}</p>
            {:else if waiting(entry)}
              <p class="reply muted">{waiting(entry)}</p>
            {:else}
              <p class="reply">{entry.reply}</p>
            {/if}
            {#if entry.status === "cancelled"}<p class="meta">Stopped</p>{/if}
            {#if pc.undoFor(entry.id)}
              {@const action = pc.undoFor(entry.id)}
              {#if action?.undone}
                <p class="meta">{action.undone}</p>
              {:else if action}
                <button
                  class="undo"
                  type="button"
                  onclick={() => void pc.undo(action.actionId)}
                  title={action.summary}>Undo</button
                >
              {/if}
            {/if}
            {#if entry === newest && entry.status === "done" && entry.totalMs !== null}
              <p class="meta">
                {entry.firstTokenMs !== null
                  ? `first word ${String(entry.firstTokenMs)} ms · `
                  : ""}total {String(entry.totalMs)} ms
              </p>
            {/if}
          </div>
        {/if}
      {:else}
        <p class="hint">Ask anything. Press Enter to send.</p>
      {/each}
    </div>

    {#if pc.question}
      <div class="ask" role="alertdialog" aria-live="assertive">
        <p>{pc.question.text}</p>
        <div class="ask-actions">
          <button type="button" onclick={() => void pc.answer(false)}>No</button>
          <button
            type="button"
            class="primary"
            class:danger={pc.question.dangerous}
            onclick={() => void pc.answer(true)}>Yes</button
          >
        </div>
      </div>
    {/if}
    {#each pc.notices as notice (notice.id)}
      <div class="ask" role="status">
        <p>{notice.text}</p>
        <div class="ask-actions">
          <button
            type="button"
            onclick={() => {
              pc.dismiss(notice.id);
            }}>Dismiss</button
          >
        </div>
      </div>
    {/each}

    <form onsubmit={submit}>
      <input
        bind:this={input}
        bind:value={draft}
        type="text"
        maxlength="8000"
        placeholder="Ask EV"
        aria-label="Message"
        autocomplete="off"
        spellcheck="true"
      />
    </form>
  </div>
{/if}

<style>
  /* Scroll areas reach into the panel's side padding, so the scrollbar line
     sits beside the text instead of taking width from it. */
  .setup,
  .session {
    margin-right: calc(-1 * var(--ev-space-3));
    padding-right: var(--ev-space-3);
  }

  .setup {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-1);
  }

  .lead {
    font-size: var(--ev-text-15);
    font-weight: var(--ev-weight-semibold);
    color: var(--ev-island-fg-1);
  }

  .hint {
    font-size: var(--ev-text-13);
    color: var(--ev-island-fg-2);
  }

  .setup .hint {
    margin-bottom: var(--ev-space-1);
  }

  .chat {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-2);
  }

  p {
    margin: 0;
  }

  /* Text uses fg-1 / fg-2 only: fg-3 (40%) is below WCAG AA on black. */
  .model,
  .meta,
  .notice {
    font-size: var(--ev-text-11);
    color: var(--ev-island-fg-2);
    font-variant-numeric: tabular-nums;
  }

  .session {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-3);
    user-select: text;
  }

  .turn {
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-1);
  }

  .user {
    font-size: var(--ev-text-13);
    color: var(--ev-island-fg-2);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .reply {
    font-size: var(--ev-text-13);
    line-height: 1.45;
    color: var(--ev-island-fg-1);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .muted {
    color: var(--ev-island-fg-2);
  }

  .undo {
    align-self: flex-start;
    font: inherit;
    font-size: var(--ev-text-11);
    color: var(--ev-island-fg-2);
    background: transparent;
    border: 0;
    padding: 0;
    text-decoration: underline;
    cursor: pointer;
  }

  .undo:hover {
    color: var(--ev-island-fg-1);
  }

  .ask {
    display: flex;
    align-items: center;
    gap: var(--ev-space-3);
    padding: var(--ev-space-2) var(--ev-space-2) var(--ev-space-2) var(--ev-space-3);
    background: var(--ev-island-control-bg);
    border-radius: var(--ev-radius-control);
  }

  .ask p {
    flex: 1;
    font-size: var(--ev-text-13);
    color: var(--ev-island-fg-1);
  }

  .ask-actions {
    display: flex;
    gap: var(--ev-space-1);
  }

  .ask button {
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

  .ask button.primary {
    color: var(--ev-island-bg);
    background: var(--ev-island-fg-1);
  }

  /* Dangerous steps: the yes button reads differently, not by colour alone. */
  .ask button.danger {
    text-decoration: underline;
  }

  .undo:focus-visible,
  .ask button:focus-visible {
    outline: 2px solid var(--ev-focus-ring);
    outline-offset: 2px;
  }

  input {
    width: 100%;
    box-sizing: border-box;
    font: inherit;
    font-size: var(--ev-text-13);
    color: var(--ev-island-fg-1);
    background: var(--ev-island-control-bg);
    border: 0;
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-2) var(--ev-space-3);
  }

  input::placeholder {
    color: var(--ev-island-fg-2);
  }

  input:focus-visible {
    outline: 2px solid var(--ev-focus-ring);
    outline-offset: 0;
  }
</style>
