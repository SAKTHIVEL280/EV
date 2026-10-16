"""Tool interface (CLAUDE.md §5.3, §5.4). `undo` arrives with the action log (Phase 3)."""

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
    """Needs an inline yes/no in the island."""
    DANGEROUS = "dangerous"
    """Needs explicit confirmation every time; never automatic."""


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    content: str
    """What the model reads."""
    user_message: str | None = None
    """Short text for the user when the tool answers directly (router)."""


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

    @abstractmethod
    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult: ...
