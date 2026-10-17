/**
 * The model list, shared by the island and the Settings window (each window
 * has its own copy, kept current by ModelsChanged events from Rust).
 */
import { commands, events, type ModelsState } from "../bindings";

class ModelsStore {
  state = $state<ModelsState | null>(null);
  private started = false;

  /** Start listening (idempotent). Returns nothing; updates arrive as state. */
  init(): void {
    if (this.started) return;
    this.started = true;
    void events.modelsChanged.listen((event) => {
      this.state = event.payload;
    });
    void commands.modelsState().then((cached) => {
      if (cached && this.state === null) this.state = cached;
    });
    void commands.modelsRefresh();
  }

  async download(id: string): Promise<string | null> {
    const result = await commands.modelsDownload(id);
    return result.status === "ok" ? null : result.error.message;
  }

  async cancel(id: string): Promise<string | null> {
    const result = await commands.modelsCancel(id);
    return result.status === "ok" ? null : result.error.message;
  }
}

export const models = new ModelsStore();
