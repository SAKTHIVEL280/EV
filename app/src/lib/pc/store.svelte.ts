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
