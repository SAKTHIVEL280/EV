/**
 * Voice state for the island (F-005, F-006, F-008): whether the mic is open,
 * whether EV is speaking, the live words and level, and why voice stopped.
 * When core reports the final words, they go out as a spoken chat message.
 */
import { commands, events, type VoiceSource, type VoiceStopReason } from "../bindings";
import { chat } from "../chat/store.svelte";
import { IDLE, isPushToTalk, type VoiceState } from "./voice";

class VoiceStore {
  state = $state<VoiceState>({ ...IDLE });
  /** Mic level 0..1, kept apart: it changes 15 times a second (only the meter reads it). */
  level = $state(0);
  private started = false;

  get listening(): boolean {
    return this.state.mic;
  }

  init(): void {
    if (this.started) return;
    this.started = true;
    void events.voiceUpdate.listen((event) => {
      const update = event.payload;
      switch (update.kind) {
        case "state":
          this.state = {
            ...this.state,
            mic: update.mic,
            speaking: update.speaking,
            heard: update.mic ? this.state.heard : "",
            message: update.message,
            code: update.code,
          };
          if (!update.mic) this.level = 0;
          break;
        case "level":
          // A float can arrive as null (NaN on the Rust side).
          this.level = update.level ?? 0;
          break;
        case "heard":
          if (update.is_final) {
            this.state = { ...this.state, heard: "" };
            void chat.send(update.text, update.text, true);
          } else {
            this.state = { ...this.state, heard: update.text, message: null, code: null };
          }
          break;
      }
    });
    void events.hotkeyReleased.listen((event) => {
      if (isPushToTalk(event.payload.held_ms, this.state.mic)) void this.stop("send");
    });
  }

  async start(source: VoiceSource): Promise<void> {
    this.state = { ...this.state, message: null, code: null };
    const result = await commands.voiceStart(source);
    if (result.status === "error") this.state = { ...this.state, message: result.error.message };
  }

  async stop(reason: VoiceStopReason): Promise<void> {
    await commands.voiceStop(reason);
  }

  dismiss(): void {
    this.state = { ...this.state, message: null, code: null };
  }
}

export const voice = new VoiceStore();
