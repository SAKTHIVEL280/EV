/**
 * Chat panel state (docs/FEATURES.md F-001): the current exchange, built from
 * ChatUpdate events. Pure functions so the ordering rules are testable.
 *
 * Race handled here: chat_send resolves with the turn id, but events may arrive
 * before that. The current turn adopts the first unseen turn id, except ids of
 * turns the user already replaced (their late "cancelled" events are ignored).
 */
import type { ChatUpdateKind, Effort } from "../bindings";

export type TurnStatus = "pending" | "streaming" | "done" | "cancelled" | "failed";

export interface Turn {
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

export interface ChatState {
  current: Turn | null;
  /** Turn ids that were replaced; their events are dropped. */
  replaced: string[];
}

export const empty: ChatState = { current: null, replaced: [] };

const MAX_REPLACED = 20;

export function begin(state: ChatState, text: string): ChatState {
  const previous = state.current?.id;
  return {
    current: {
      id: null,
      user: text,
      reply: "",
      status: "pending",
      effort: null,
      tool: null,
      error: null,
      firstTokenMs: null,
      totalMs: null,
    },
    replaced: previous ? [...state.replaced, previous].slice(-MAX_REPLACED) : state.replaced,
  };
}

export function sent(state: ChatState, turnId: string): ChatState {
  if (!state.current || state.current.id !== null) return state;
  return { ...state, current: { ...state.current, id: turnId } };
}

export function sendFailed(state: ChatState, message: string): ChatState {
  if (!state.current) return state;
  return { ...state, current: { ...state.current, status: "failed", error: message } };
}

export function apply(state: ChatState, update: ChatUpdateKind): ChatState {
  const current = state.current;
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
  return { ...state, current: turn };
}

export function busy(state: ChatState): boolean {
  const status = state.current?.status;
  return status === "pending" || status === "streaming";
}
