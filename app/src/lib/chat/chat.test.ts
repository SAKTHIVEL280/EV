import { describe, expect, it } from "vitest";

import type { ChatUpdateKind } from "../bindings";
import {
  MAX_TURNS,
  RESTARTED_TEXT,
  apply,
  begin,
  busy,
  empty,
  latest,
  reset,
  restarted,
  sendFailed,
  sent,
} from "./chat";

const A = "11111111-1111-4111-8111-111111111111";
const B = "22222222-2222-4222-8222-222222222222";

function run(...updates: ChatUpdateKind[]) {
  return updates.reduce(apply, begin(empty, "hello"));
}

describe("chat state", () => {
  it("streams a reply to done", () => {
    const s = run(
      { kind: "started", turn_id: A, effort: "normal", model: "m.gguf" },
      { kind: "delta", turn_id: A, text: "Hi" },
      { kind: "delta", turn_id: A, text: " there" },
    );
    expect(latest(s)?.reply).toBe("Hi there");
    expect(latest(s)?.status).toBe("streaming");
    expect(busy(s)).toBe(true);
    const done = apply(s, {
      kind: "done",
      turn_id: A,
      text: "Hi there.",
      effort: "normal",
      model: "m.gguf",
      first_token_ms: 400,
      total_ms: 900,
      cancelled: false,
    });
    expect(latest(done)).toMatchObject({ id: A, reply: "Hi there.", status: "done", totalMs: 900 });
    expect(busy(done)).toBe(false);
  });

  it("adopts the turn id from the first event even before send resolves", () => {
    const s = run({ kind: "started", turn_id: A, effort: "instant", model: null });
    expect(latest(s)?.id).toBe(A);
    expect(latest(sent(s, A))?.id).toBe(A);
  });

  it("ignores events of other turns once the id is known", () => {
    const s = sent(begin(empty, "hi"), A);
    expect(apply(s, { kind: "delta", turn_id: B, text: "x" })).toBe(s);
  });

  it("drops late events of a replaced turn", () => {
    let s = sent(begin(empty, "first"), A);
    s = apply(s, { kind: "delta", turn_id: A, text: "partial" });
    s = begin(s, "second");
    const late = apply(s, {
      kind: "done",
      turn_id: A,
      text: "partial",
      effort: "normal",
      model: null,
      first_token_ms: null,
      total_ms: 5,
      cancelled: true,
    });
    expect(late).toBe(s);
    expect(latest(late)?.id).toBeNull();
    // The replaced reply stays in the session as far as it got.
    expect(late.entries[0]).toMatchObject({ id: A, reply: "partial", status: "cancelled" });
    const next = apply(late, { kind: "started", turn_id: B, effort: "normal", model: null });
    expect(latest(next)).toMatchObject({ id: B, user: "second" });
  });

  it("shows the running tool and clears it when done", () => {
    let s = run({ kind: "tool", turn_id: A, name: "current_time", state: "running" });
    expect(latest(s)?.tool).toBe("current_time");
    s = apply(s, { kind: "tool", turn_id: A, name: "current_time", state: "done" });
    expect(latest(s)?.tool).toBeNull();
  });

  it("records failures from core and from sending", () => {
    const s = run({ kind: "failed", turn_id: A, code: "no_model", message: "No model installed." });
    expect(latest(s)).toMatchObject({ status: "failed", error: "No model installed." });
    const f = sendFailed(begin(empty, "x"), "EV's core isn't running yet.");
    expect(latest(f)?.status).toBe("failed");
    expect(busy(f)).toBe(false);
  });

  it("marks cancelled turns", () => {
    const s = run({
      kind: "done",
      turn_id: A,
      text: "par",
      effort: "max",
      model: null,
      first_token_ms: null,
      total_ms: 10,
      cancelled: true,
    });
    expect(latest(s)?.status).toBe("cancelled");
  });

  it("ignores updates without a current turn", () => {
    expect(apply(empty, { kind: "delta", turn_id: A, text: "x" })).toBe(empty);
  });

  it("keeps every exchange of the session in order", () => {
    let s = sent(begin(empty, "one"), A);
    s = apply(s, {
      kind: "done",
      turn_id: A,
      text: "1",
      effort: "normal",
      model: null,
      first_token_ms: 1,
      total_ms: 2,
      cancelled: false,
    });
    s = sent(begin(s, "two"), B);
    s = apply(s, { kind: "delta", turn_id: B, text: "2" });
    expect(s.entries.map((e) => (e.type === "turn" ? [e.user, e.reply] : e.text))).toEqual([
      ["one", "1"],
      ["two", "2"],
    ]);
  });

  it("new chat empties the session and drops the old turn's late events", () => {
    let s = sent(begin(empty, "one"), A);
    s = reset(apply(s, { kind: "delta", turn_id: A, text: "par" }));
    expect(s.entries).toEqual([]);
    s = begin(s, "fresh");
    expect(apply(s, { kind: "delta", turn_id: A, text: "late" })).toBe(s);
  });

  it("keeps only the newest exchanges", () => {
    let s = empty;
    for (let i = 0; i < MAX_TURNS + 5; i += 1) s = begin(s, `m${String(i)}`);
    expect(s.entries.length).toBe(MAX_TURNS);
    expect(s.entries[0]).toMatchObject({ user: "m5" });
  });

  it("notes a core restart once, and only after a conversation", () => {
    expect(restarted(empty)).toBe(empty);
    let s = sent(begin(empty, "hi"), A);
    s = restarted(apply(s, { kind: "delta", turn_id: A, text: "par" }));
    expect(s.entries.at(-1)).toEqual({ type: "notice", text: RESTARTED_TEXT });
    expect(latest(s)?.status).toBe("cancelled");
    expect(restarted(s)).toBe(s);
    expect(busy(s)).toBe(false);
  });
});

describe("tool states", () => {
  it("keeps the tool while EV waits for the user's answer", () => {
    let s = run({ kind: "tool", turn_id: A, name: "files", state: "asking" });
    expect(latest(s)?.tool).toBe("files");
    s = apply(s, { kind: "tool", turn_id: A, name: "files", state: "declined" });
    expect(latest(s)?.tool).toBeNull();
  });
});
