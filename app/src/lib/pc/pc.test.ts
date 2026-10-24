import { describe, expect, it, vi } from "vitest";

vi.mock("../bindings", () => ({
  commands: {
    toolAnswer: vi.fn(),
    actionUndo: vi.fn(),
    contextCapture: vi.fn(),
    contextClear: vi.fn(),
    contextReplace: vi.fn(),
  },
  events: { pcUpdate: { listen: vi.fn() } },
}));

const { pc, timerText } = await import("./store.svelte");

const TURN = "36c14c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d";

describe("pc store", () => {
  it("shows a question until it is closed", () => {
    pc.apply({
      kind: "confirm",
      turn_id: TURN,
      request_id: "q1",
      tool: "files",
      question: "Delete a.pdf? It goes to the Recycle Bin.",
      risk: "dangerous",
    });
    expect(pc.question).toMatchObject({ requestId: "q1", dangerous: true });
    pc.apply({ kind: "confirm_closed", request_id: "other", allowed: false });
    expect(pc.question).not.toBeNull();
    pc.apply({ kind: "confirm_closed", request_id: "q1", allowed: false });
    expect(pc.question).toBeNull();
  });

  it("offers Undo for a turn's last undoable action and marks it undone", () => {
    pc.apply({
      kind: "action",
      turn_id: TURN,
      action_id: 4,
      tool: "system",
      summary: "Volume 30%",
      undoable: true,
    });
    pc.apply({
      kind: "action",
      turn_id: TURN,
      action_id: 5,
      tool: "files",
      summary: "Deleted a.pdf",
      undoable: false,
    });
    expect(pc.undoFor(TURN)?.actionId).toBe(4);
    pc.apply({ kind: "undone", action_id: 4, ok: true, message: "Undone: Volume 30%" });
    expect(pc.undoFor(TURN)?.undone).toBe("Undone: Volume 30%");
    expect(pc.undoFor(null)).toBeNull();
  });

  it("words timer notices plainly", () => {
    expect(timerText("timer", "Timer", false)).toBe("Time's up.");
    expect(timerText("timer", "tea", false)).toBe("Time's up: tea");
    expect(timerText("reminder", "call mom", false)).toBe("Reminder: call mom");
    expect(timerText("alarm", "Alarm", true)).toBe("Missed while EV was off. Alarm.");
  });

  it("tracks focus mode and notices", () => {
    pc.apply({ kind: "focus", on: true, minutes: 25 });
    expect(pc.focus).toBe(true);
    pc.apply({
      kind: "timer",
      timer_id: 9,
      timer_kind: "reminder",
      label: "standup",
      missed: false,
    });
    expect(pc.notices.map((n) => n.text)).toEqual(["Reminder: standup"]);
    pc.dismiss(9);
    expect(pc.notices).toEqual([]);
  });
});

describe("selection", () => {
  it("shows the captured selection until it is used or removed", () => {
    pc.apply({ kind: "context", text: "teh fox", app: "notepad", title: "notes.txt" });
    expect(pc.context).toEqual({ text: "teh fox", app: "notepad", title: "notes.txt" });
    pc.used("turn-1");
    expect(pc.context).toBeNull();
    expect(pc.contextTurn).toBe("turn-1");
    pc.apply({ kind: "context", text: null, app: "", title: "" });
    expect(pc.context).toBeNull();
    pc.apply({ kind: "replaced", ok: false, message: "Copied. Paste it to replace." });
    expect(pc.replaced).toBe("Copied. Paste it to replace.");
  });
});
