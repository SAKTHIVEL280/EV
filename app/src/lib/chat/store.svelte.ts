/**
 * The chat session (F-414). It lives as long as the island window, not the
 * panel, so closing the panel keeps the conversation and any reply still
 * streaming. Quitting EV ends the session.
 */
import { commands, events, type CoreStatus, type LlmStatus } from "../bindings";
import { apply, begin, empty, reset, restarted, sendFailed, sent, type ChatState } from "./chat";

export const NEW_CHAT_FAILED_TEXT = "Couldn't start a new chat. Try again.";

class ChatStore {
  state = $state<ChatState>(empty);
  llm = $state<LlmStatus>({ state: "unloaded", model: null, detail: null });
  private started = false;
  private coreWasRunning = false;

  /** Start listening (idempotent). */
  init(): void {
    if (this.started) return;
    this.started = true;
    void events.chatUpdate.listen((event) => {
      this.state = apply(this.state, event.payload);
    });
    void events.llmStatusChanged.listen((event) => {
      this.llm = event.payload;
    });
    void events.coreStatusChanged.listen((event) => {
      this.onCoreStatus(event.payload);
    });
    void commands.llmStatus().then((initial) => {
      this.llm = initial;
    });
    void commands.coreStatus().then((status) => {
      this.onCoreStatus(status);
    });
  }

  private onCoreStatus(status: CoreStatus): void {
    if (status.state === "running") {
      this.coreWasRunning = true;
    } else if (this.coreWasRunning) {
      // Core's history went with it.
      this.coreWasRunning = false;
      this.state = restarted(this.state);
    }
  }

  async send(text: string): Promise<void> {
    this.state = begin(this.state, text);
    const result = await commands.chatSend(text, null);
    this.state =
      result.status === "ok"
        ? sent(this.state, result.data)
        : sendFailed(this.state, result.error.message);
  }

  /** New chat. Returns an error message, or null. */
  async newChat(): Promise<string | null> {
    const result = await commands.chatReset();
    if (result.status === "error") return NEW_CHAT_FAILED_TEXT;
    this.state = reset(this.state);
    return null;
  }
}

export const chat = new ChatStore();
