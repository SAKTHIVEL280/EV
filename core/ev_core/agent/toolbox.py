"""Runs tool calls with risk policy, validation, timeouts and status events."""

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from typing import Final

from ev_core.bus import Event
from ev_core.interfaces.events import ChatToolChanged
from ev_core.interfaces.llm import ToolCall, ToolSpec
from ev_core.interfaces.tools import Risk, Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

TOOL_TIMEOUT_S: Final = 30.0
BLOCKED_RESULT: Final = (
    "blocked: this action needs the user's confirmation, and confirmations are not available "
    "in this version. Tell the user you can't do it yet."
)


class Toolbox:
    def __init__(self, tools: Sequence[Tool]) -> None:
        names = [t.name for t in tools]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate tool names: {names}")
        self._tools = {t.name: t for t in tools}

    def specs(self) -> list[ToolSpec]:
        return [ToolSpec(t.name, t.description, t.parameters) for t in self._tools.values()]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def execute(
        self, turn_id: str, call: ToolCall, emit: Callable[[Event], None]
    ) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(False, f"error: unknown tool {call.name!r}")
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            return ToolResult(False, "error: arguments are not valid JSON")
        if not isinstance(args, dict):
            return ToolResult(False, "error: arguments must be a JSON object")
        if tool.risk is not Risk.SAFE:
            # Confirmations arrive with the island confirm state (Phase 3).
            emit(ChatToolChanged(turn_id, tool.name, "blocked"))
            return ToolResult(False, BLOCKED_RESULT)
        emit(ChatToolChanged(turn_id, tool.name, "running"))
        ctx = ToolContext(logger=logging.getLogger(f"ev_core.tool.{tool.name}"))
        try:
            result = await asyncio.wait_for(tool.run(args, ctx), TOOL_TIMEOUT_S)
        except TimeoutError:
            logger.warning("tool timed out", extra={"fields": {"tool": tool.name}})
            result = ToolResult(False, "error: the tool took too long")
        except Exception:
            logger.exception("tool failed", extra={"fields": {"tool": tool.name}})
            result = ToolResult(False, "error: the tool failed")
        emit(ChatToolChanged(turn_id, tool.name, "done" if result.ok else "failed"))
        return result
