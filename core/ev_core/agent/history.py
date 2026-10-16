"""Rolling conversation window (CLAUDE.md §5.7).

Recent turns are kept verbatim, newest first, until the character budget is
used; the current turn is always included. Summaries of older turns arrive
with memory (Phase 6). Characters stand in for tokens at a conservative
3 characters per token, so the window never overflows the context.
"""

from typing import Final

from ev_core.interfaces.llm import ChatMessage

CHARS_PER_TOKEN: Final = 3
PREFIX_TOKENS: Final = 1_000
"""Static prefix budget: system prompt + tool list (CLAUDE.md §5.4)."""
RESERVED_TOKENS: Final = 600
"""Memory snippets + "this" context (§5.4), plus template overhead."""
MAX_TURNS: Final = 50


def budget_chars(context_tokens: int, max_output_tokens: int) -> int:
    free = context_tokens - PREFIX_TOKENS - RESERVED_TOKENS - max_output_tokens
    return max(0, free) * CHARS_PER_TOKEN


def _size(messages: list[ChatMessage]) -> int:
    return sum(
        len(m.content) + sum(len(c.name) + len(c.arguments) for c in m.tool_calls) for m in messages
    )


class History:
    def __init__(self) -> None:
        self._turns: list[list[ChatMessage]] = []

    def add_turn(self, messages: list[ChatMessage]) -> None:
        self._turns.append(list(messages))
        del self._turns[:-MAX_TURNS]

    def window(self, budget: int) -> list[ChatMessage]:
        kept: list[list[ChatMessage]] = []
        used = 0
        for turn in reversed(self._turns):
            size = _size(turn)
            if used + size > budget:
                break
            kept.append(turn)
            used += size
        return [m for turn in reversed(kept) for m in turn]

    def clear(self) -> None:
        self._turns.clear()
