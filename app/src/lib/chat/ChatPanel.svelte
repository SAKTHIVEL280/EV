<!--
  Typed chat (docs/FEATURES.md F-001): one input and the current exchange.
  Replies stream in; a new message replaces a reply that is still streaming.
-->
<script lang="ts">
  import { onMount } from "svelte";

  import { commands, events, type LlmStatus } from "../bindings";
  import { apply, begin, busy, empty, sendFailed, sent, type ChatState } from "./chat";

  const TOOL_TEXT: Record<string, string> = { current_time: "Checking the time" };

  let chat = $state<ChatState>(empty);
  let llm = $state<LlmStatus>({ state: "unloaded", model: null, detail: null });
  let draft = $state("");
  let input: HTMLInputElement | undefined = $state();

  export function focus(): void {
    input?.focus();
  }

  const modelText = $derived.by(() => {
    switch (llm.state) {
      case "loading":
        return "Waking up";
      case "ready":
        return "Ready";
      case "failed":
        return llm.detail ?? "Couldn't load the model.";
      default:
        return "";
    }
  });

  const turn = $derived(chat.current);

  const placeholder = $derived.by(() => {
    if (!turn) return null;
    if (turn.reply || turn.status === "failed") return null;
    if (turn.tool) return TOOL_TEXT[turn.tool] ?? "Working";
    return busy(chat) ? "Thinking" : null;
  });

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    chat = begin(chat, text);
    draft = "";
    const result = await commands.chatSend(text, null);
    chat =
      result.status === "ok" ? sent(chat, result.data) : sendFailed(chat, result.error.message);
  }

  onMount(() => {
    const unlisteners = [
      events.chatUpdate.listen((event) => {
        chat = apply(chat, event.payload);
      }),
      events.llmStatusChanged.listen((event) => {
        llm = event.payload;
      }),
    ];
    void commands.llmStatus().then((initial) => {
      llm = initial;
    });
    return () => {
      for (const pending of unlisteners)
        void pending.then((unlisten) => {
          unlisten();
        });
    };
  });
</script>

<div class="chat">
  {#if modelText}<p class="model" aria-live="polite">{modelText}</p>{/if}

  <div class="exchange" aria-live="polite">
    {#if turn}
      <p class="user">{turn.user}</p>
      {#if turn.status === "failed"}
        <p class="reply error">{turn.error}</p>
      {:else if placeholder}
        <p class="reply waiting">{placeholder}</p>
      {:else}
        <p class="reply">{turn.reply}</p>
      {/if}
      {#if turn.status === "cancelled"}<p class="meta">Stopped</p>{/if}
      {#if turn.status === "done" && turn.totalMs !== null}
        <p class="meta">
          {turn.firstTokenMs !== null ? `first word ${String(turn.firstTokenMs)} ms · ` : ""}total {String(
            turn.totalMs,
          )} ms
        </p>
      {/if}
    {:else}
      <p class="hint">Type a question and press Enter.</p>
    {/if}
  </div>

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

<style>
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

  .model,
  .meta,
  .hint,
  .user {
    font-size: var(--ev-text-11);
    color: var(--ev-island-fg-3);
    font-variant-numeric: tabular-nums;
  }

  .user {
    font-size: var(--ev-text-13);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .exchange {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-1);
    user-select: text;
  }

  .reply {
    font-size: var(--ev-text-13);
    line-height: 1.45;
    color: var(--ev-island-fg-1);
    white-space: pre-wrap;
  }

  .waiting,
  .error {
    color: var(--ev-island-fg-2);
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
    color: var(--ev-island-fg-3);
  }

  input:focus-visible {
    outline: 2px solid var(--ev-focus-ring);
    outline-offset: 0;
  }
</style>
