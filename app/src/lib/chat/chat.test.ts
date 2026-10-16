import { describe, expect, it } from "vitest";

import type { ChatUpdateKind } from "../bindings";
import { apply, begin, busy, empty, sendFailed, sent } from "./chat";

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
    expect(s.current?.reply).toBe("Hi there");
    expect(s.current?.status).toBe("streaming");
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
    expect(done.current).toMatchObject({ id: A, reply: "Hi there.", status: "done", totalMs: 900 });
    expect(busy(done)).toBe(false);
  });

  it("adopts the turn id from the first event even before send resolves", () => {
    const s = run({ kind: "started", turn_id: A, effort: "instant", model: null });
    expect(s.current?.id).toBe(A);
    expect(sent(s, A).current?.id).toBe(A);
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
    expect(late.current?.id).toBeNull();
    const next = apply(late, { kind: "started", turn_id: B, effort: "normal", model: null });
    expect(next.current).toMatchObject({ id: B, user: "second" });
  });

  it("shows the running tool and clears it when done", () => {
    let s = run({ kind: "tool", turn_id: A, name: "current_time", state: "running" });
    expect(s.current?.tool).toBe("current_time");
    s = apply(s, { kind: "tool", turn_id: A, name: "current_time", state: "done" });
    expect(s.current?.tool).toBeNull();
  });

  it("records failures from core and from sending", () => {
    const s = run({ kind: "failed", turn_id: A, code: "no_model", message: "No model installed." });
    expect(s.current).toMatchObject({ status: "failed", error: "No model installed." });
    const f = sendFailed(begin(empty, "x"), "EV's core isn't running yet.");
    expect(f.current?.status).toBe("failed");
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
    expect(s.current?.status).toBe("cancelled");
  });

  it("ignores updates without a current turn", () => {
    expect(apply(empty, { kind: "delta", turn_id: A, text: "x" })).toBe(empty);
  });
});
