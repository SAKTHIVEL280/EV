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

  /** Send a message; returns its turn id, or null when it couldn't be sent.
   *  `shown` is what the conversation displays (a quick action's label). */
  async send(text: string, shown: string = text): Promise<string | null> {
    this.state = begin(this.state, shown);
    const result = await commands.chatSend(text, null);
    if (result.status === "ok") {
      this.state = sent(this.state, result.data);
      return result.data;
    }
    this.state = sendFailed(this.state, result.error.message);
    return null;
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
