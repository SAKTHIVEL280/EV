"""Tool interface (CLAUDE.md §5.3, §5.4, docs/FEATURES.md F-111, F-418)."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar


class Risk(StrEnum):
    SAFE = "safe"
    """Runs immediately."""
    CONFIRM = "confirm"
    """Needs an inline yes/no in the island, unless the user set the tool to Allow."""
    DANGEROUS = "dangerous"
    """Needs explicit confirmation every time; never automatic."""


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    content: str
    """What the model reads."""
    user_message: str | None = None
    """Short text for the user when the tool answers directly (router)."""
    summary: str | None = None
    """One line for the action log; set only when the action changed something."""
    undo: Mapping[str, Any] | None = None
    """Data the tool's `undo` needs to reverse this action; None when it can't."""


@dataclass(frozen=True, slots=True)
class ToolContext:
    logger: logging.Logger


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    """At most 25 words; part of the cached prompt prefix."""
    parameters: ClassVar[Mapping[str, Any]]
    """JSON Schema of the arguments."""
    risk: ClassVar[Risk]
    """The highest risk of any action; `risk_for` decides per call."""
    untrusted_output: ClassVar[bool] = False
    """Its results contain outside text (files, screen, clipboard, web): data, never
    instructions, and later confirm/dangerous steps in the turn always ask (CLAUDE.md §8)."""
    confirm_once: ClassVar[bool] = False
    """One yes covers this tool's later `confirm` steps in the same request (F-110)."""
    general: ClassVar[bool] = False
    """Offered for every request. Otherwise only for requests that look like PC actions
    (`agent.intent`), so general questions get a short prompt."""
    offered: ClassVar[bool] = True
    """Shown to the model at all; False for tools only the router calls."""

    def risk_for(self, args: Mapping[str, Any]) -> Risk:
        """The risk of this particular call. Default: the tool's risk."""
        return self.risk

    def question(self, args: Mapping[str, Any]) -> str:
        """What the island asks before a confirm/dangerous call, e.g. "Close Notepad?"."""
        return f"Allow EV to use {self.name}?"

    @abstractmethod
    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult: ...

    async def undo(self, data: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        """Reverse an action from its `ToolResult.undo` data."""
        return ToolResult(False, f"error: {self.name} can't undo")
