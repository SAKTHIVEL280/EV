/**
 * Chat session state (docs/FEATURES.md F-001, F-414): every exchange since the
 * last New chat, built from ChatUpdate events. Pure functions so the ordering
 * rules are testable.
 *
 * Race handled here: chat_send resolves with the turn id, but events may arrive
 * before that. The latest turn adopts the first unseen turn id, except ids of
 * turns the user already replaced (their late "cancelled" events are ignored).
 */
import type { ChatUpdateKind, Effort } from "../bindings";

export type TurnStatus = "pending" | "streaming" | "done" | "cancelled" | "failed";

export interface Turn {
  type: "turn";
  id: string | null;
  user: string;
  reply: string;
  status: TurnStatus;
  effort: Effort | null;
  tool: string | null;
  error: string | null;
  firstTokenMs: number | null;
  totalMs: number | null;
}

/** A line from EV itself between exchanges, such as "EV restarted." */
export interface Notice {
  type: "notice";
  text: string;
}

export type Entry = Turn | Notice;

export interface ChatState {
  entries: Entry[];
  /** Turn ids that were replaced; their events are dropped. */
  replaced: string[];
}

export const empty: ChatState = { entries: [], replaced: [] };

/** The panel keeps this many exchanges (core's history window is separate). */
export const MAX_TURNS = 50;
export const RESTARTED_TEXT = "EV restarted. Earlier messages aren't remembered.";
const MAX_REPLACED = 20;

function isTurn(entry: Entry): entry is Turn {
  return entry.type === "turn";
}

/** The newest exchange, or null when the session is empty. */
export function latest(state: ChatState): Turn | null {
  for (let i = state.entries.length - 1; i >= 0; i -= 1) {
    const entry = state.entries[i];
    if (entry && isTurn(entry)) return entry;
  }
  return null;
}

function replaceLatest(state: ChatState, turn: Turn): ChatState {
  const index = state.entries.lastIndexOf(latest(state) ?? turn);
  if (index < 0) return state;
  const entries = state.entries.slice();
  entries[index] = turn;
  return { ...state, entries };
}

function capped(entries: Entry[]): Entry[] {
  let turns = entries.filter(isTurn).length;
  let start = 0;
  while (turns > MAX_TURNS && start < entries.length) {
    const entry = entries[start];
    if (entry && isTurn(entry)) turns -= 1;
    start += 1;
  }
  return start === 0 ? entries : entries.slice(start);
}

export function begin(state: ChatState, text: string): ChatState {
  const previous = latest(state);
  let entries = state.entries;
  let replaced = state.replaced;
  if (previous) {
    // A new message cancels a reply that is still streaming; it stays in the
    // list as far as it got.
    if (previous.status === "pending" || previous.status === "streaming") {
      entries = replaceLatest(state, { ...previous, status: "cancelled", tool: null }).entries;
    }
    if (previous.id) replaced = [...replaced, previous.id].slice(-MAX_REPLACED);
  }
  const turn: Turn = {
    type: "turn",
    id: null,
    user: text,
    reply: "",
    status: "pending",
    effort: null,
    tool: null,
    error: null,
    firstTokenMs: null,
    totalMs: null,
  };
  return { entries: capped([...entries, turn]), replaced };
}

export function sent(state: ChatState, turnId: string): ChatState {
  const turn = latest(state);
  if (!turn || turn.id !== null) return state;
  return replaceLatest(state, { ...turn, id: turnId });
}

export function sendFailed(state: ChatState, message: string): ChatState {
  const turn = latest(state);
  if (!turn) return state;
  return replaceLatest(state, { ...turn, status: "failed", error: message });
}

export function apply(state: ChatState, update: ChatUpdateKind): ChatState {
  const current = latest(state);
  if (!current || state.replaced.includes(update.turn_id)) return state;
  if (current.id !== null && current.id !== update.turn_id) return state;
  const turn: Turn = { ...current, id: update.turn_id };
  switch (update.kind) {
    case "started":
      turn.effort = update.effort;
      break;
    case "delta":
      turn.reply += update.text;
      turn.status = "streaming";
      break;
    case "tool":
      turn.tool = update.state === "running" ? update.name : null;
      break;
    case "done":
      turn.reply = update.text;
      turn.status = update.cancelled ? "cancelled" : "done";
      turn.tool = null;
      turn.firstTokenMs = update.first_token_ms;
      turn.totalMs = update.total_ms;
      break;
    case "failed":
      turn.status = "failed";
      turn.error = update.message;
      turn.tool = null;
      break;
  }
  return replaceLatest(state, turn);
}

/** New chat: an empty session; late events of the old turn are dropped. */
export function reset(state: ChatState): ChatState {
  const id = latest(state)?.id;
  return {
    entries: [],
    replaced: id ? [...state.replaced, id].slice(-MAX_REPLACED) : state.replaced,
  };
}

/**
 * Core restarted, so its history is gone. Say so once, and only when there is
 * a conversation it would have remembered. A reply still streaming ends.
 */
export function restarted(state: ChatState): ChatState {
  const last = state.entries[state.entries.length - 1];
  if (!last || (last.type === "notice" && last.text === RESTARTED_TEXT)) return state;
  const turn = latest(state);
  let next = state;
  if (turn && (turn.status === "pending" || turn.status === "streaming")) {
    next = replaceLatest(state, { ...turn, status: "cancelled", tool: null });
  }
  return { ...next, entries: [...next.entries, { type: "notice", text: RESTARTED_TEXT }] };
}

export function busy(state: ChatState): boolean {
  const status = latest(state)?.status;
  return status === "pending" || status === "streaming";
}
