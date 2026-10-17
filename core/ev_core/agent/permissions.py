"""Whether a tool call runs, asks first or is blocked (CLAUDE.md §5.4, §8; F-418).

Pure, so every combination is tested:
- Block (the user's setting) stops any call of that tool.
- `safe` calls run.
- `dangerous` calls always ask.
- `confirm` calls ask, unless the user set the tool to Allow or already said yes
  to this tool earlier in the same request (tools with `confirm_once`), but never
  silently after untrusted content was read in this turn.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from ev_core.config import Permission
from ev_core.interfaces.tools import Risk


class Decision(StrEnum):
    RUN = "run"
    ASK = "ask"
    BLOCK = "block"


@dataclass
class TurnState:
    """What one request has seen so far."""

    untrusted: bool = False
    """Outside text (files, screen, clipboard, web) was read in this turn."""
    approved: set[str] = field(default_factory=set)
    """Tools the user said yes to in this turn (for `confirm_once` tools)."""
    waited_ms: int = 0
    """Time spent waiting for the user's answers; left out of the reply timings."""


def decide(
    risk: Risk, permission: Permission, *, untrusted: bool, approved_before: bool
) -> Decision:
    if permission is Permission.BLOCK:
        return Decision.BLOCK
    if risk is Risk.SAFE:
        return Decision.RUN
    if risk is Risk.DANGEROUS or untrusted:
        return Decision.ASK
    if permission is Permission.ALLOW or approved_before:
        return Decision.RUN
    return Decision.ASK
