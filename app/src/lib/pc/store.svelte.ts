/**
 * PC-tool state for the island (F-108, F-109, F-111, F-418): the question
 * waiting for a yes or no, actions that can be undone, timers that came due
 * and focus mode. Updates arrive as PcUpdate events from Rust.
 */
import { commands, events, type PcUpdateKind } from "../bindings";

export interface Question {
  requestId: string;
  turnId: string;
  text: string;
  dangerous: boolean;
}

export interface Action {
  actionId: number;
  turnId: string;
  summary: string;
  undoable: boolean;
  /** Set once undone, with core's message ("Undone: Volume 30%"). */
  undone: string | null;
}

/** What the hotkey captured from the app the user was in (F-201). */
export interface Context {
  text: string;
  app: string;
  title: string;
}

/** Quick actions on the captured selection (F-202): label and request text. */
export const QUICK_ACTIONS = [
  { label: "Explain", text: "Explain this briefly." },
  { label: "Fix", text: "Fix the spelling and grammar of this. Reply with only the fixed text." },
  { label: "Shorten", text: "Shorten this. Reply with only the shorter text." },
  { label: "Reply", text: "Write a short, friendly reply to this. Reply with only the reply." },
  { label: "Translate", text: "Translate this to English. Reply with only the translation." },
] as const;

export interface Notice {
  id: number;
  text: string;
}

/** A timer notice closes by itself after this long (F-108). */
export const NOTICE_MS = 60_000;

export function timerText(kind: string, label: string, missed: boolean): string {
  const what =
    kind === "timer"
      ? label === "Timer"
        ? "Time's up."
        : `Time's up: ${label}`
      : kind === "alarm"
        ? label === "Alarm"
          ? "Alarm."
          : `Alarm: ${label}`
        : `Reminder: ${label}`;
  return missed ? `Missed while EV was off. ${what}` : what;
}

class PcStore {
  question = $state<Question | null>(null);
  actions = $state<Action[]>([]);
  notices = $state<Notice[]>([]);
  focus = $state(false);
  context = $state<Context | null>(null);
  /** The turn a quick action started; its reply gets Copy and Replace. */
  contextTurn = $state<string | null>(null);
  replaced = $state<string | null>(null);
  private started = false;

  init(): void {
    if (this.started) return;
    this.started = true;
    void events.pcUpdate.listen((event) => {
      this.apply(event.payload);
    });
  }

  apply(update: PcUpdateKind): void {
    switch (update.kind) {
      case "confirm":
        this.question = {
          requestId: update.request_id,
          turnId: update.turn_id,
          text: update.question,
          dangerous: update.risk === "dangerous",
        };
        break;
      case "confirm_closed":
        if (this.question?.requestId === update.request_id) this.question = null;
        break;
      case "action":
        this.actions = [
          ...this.actions.slice(-19),
          {
            actionId: update.action_id,
            turnId: update.turn_id,
            summary: update.summary,
            undoable: update.undoable,
            undone: null,
          },
        ];
        break;
      case "undone":
        this.actions = this.actions.map((a) =>
          a.actionId === update.action_id || (update.action_id === 0 && !a.undone && a.undoable)
            ? { ...a, undone: update.message }
            : a,
        );
        break;
      case "timer": {
        const notice = {
          id: update.timer_id,
          text: timerText(update.timer_kind, update.label, update.missed),
        };
        this.notices = [...this.notices.filter((n) => n.id !== notice.id), notice];
        setTimeout(() => {
          this.dismiss(notice.id);
        }, NOTICE_MS);
        break;
      }
      case "focus":
        this.focus = update.on;
        break;
      case "context":
        this.context = update.text
          ? { text: update.text, app: update.app, title: update.title }
          : null;
        break;
      case "replaced":
        this.replaced = update.message;
        break;
    }
  }

  async answer(allowed: boolean): Promise<void> {
    const question = this.question;
    if (!question) return;
    this.question = null;
    await commands.toolAnswer(question.requestId, allowed);
  }

  async undo(actionId: number): Promise<void> {
    await commands.actionUndo(actionId);
  }

  /** Read the selection as the panel opens (only then; never in the background). */
  async capture(): Promise<void> {
    this.replaced = null;
    await commands.contextCapture();
  }

  async clearContext(): Promise<void> {
    this.context = null;
    await commands.contextClear();
  }

  /** The selection went with a request (core uses it once). */
  used(turnId: string | null): void {
    this.context = null;
    this.contextTurn = turnId;
  }

  async replace(text: string): Promise<void> {
    this.replaced = null;
    await commands.contextReplace(text);
  }

  dismiss(id: number): void {
    this.notices = this.notices.filter((n) => n.id !== id);
  }

  /** The newest undoable action of a turn, for the Undo button under its reply. */
  undoFor(turnId: string | null): Action | null {
    if (!turnId) return null;
    for (let i = this.actions.length - 1; i >= 0; i -= 1) {
      const action = this.actions[i];
      if (action && action.turnId === turnId && action.undoable) return action;
    }
    return null;
  }
}

export const pc = new PcStore();
