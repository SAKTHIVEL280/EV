"""Runs tool calls: permissions and confirmation (F-418), timeouts, status
events, and the action log with undo (F-111)."""

import asyncio
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar, Final

from ev_core.agent.actions import ActionLog
from ev_core.agent.confirm import Confirmer
from ev_core.agent.permissions import Decision, TurnState, decide
from ev_core.bus import Event
from ev_core.config import Permission, PermissionsSection
from ev_core.interfaces.events import ActionRecorded, ChatToolChanged
from ev_core.interfaces.llm import ToolCall, ToolSpec
from ev_core.interfaces.tools import Risk, Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

TOOL_TIMEOUT_S: Final = 30.0
BLOCKED_RESULT: Final = (
    "blocked: this action needs the user's confirmation, and confirmations are not available "
    "here. Tell the user you can't do it."
)
SETTING_BLOCKED_RESULT: Final = (
    "blocked: the user turned this off in Settings > Permissions. Tell them it is off there."
)
DECLINED_RESULT: Final = (
    "declined: the user said no, or didn't answer. Don't try again; tell them it wasn't done."
)
NOTHING_TO_UNDO: Final = "There's nothing to undo."


class Toolbox:
    def __init__(
        self,
        tools: Sequence[Tool],
        *,
        permissions: Callable[[], PermissionsSection] | None = None,
        confirmer: Confirmer | None = None,
        actions: ActionLog | None = None,
    ) -> None:
        all_tools = [*tools, UndoLastTool(self)] if actions is not None else list(tools)
        names = [t.name for t in all_tools]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate tool names: {names}")
        self._tools = {t.name: t for t in all_tools}
        self._permissions = permissions
        self._confirmer = confirmer
        self._actions = actions

    def specs(self, *, pc: bool = True) -> list[ToolSpec]:
        """Tools for the model: the general ones, plus the PC tools when `pc`."""
        return [
            ToolSpec(t.name, t.description, t.parameters)
            for t in self._tools.values()
            if t.offered and (t.general or pc) and self._permission(t.name) is not Permission.BLOCK
        ]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def _permission(self, name: str) -> Permission:
        settings = self._permissions() if self._permissions is not None else None
        value = getattr(settings, name, None)
        return value if isinstance(value, Permission) else Permission.ALLOW

    @staticmethod
    def _context(tool: Tool) -> ToolContext:
        return ToolContext(logger=logging.getLogger(f"ev_core.tool.{tool.name}"))

    async def execute(
        self,
        turn_id: str,
        call: ToolCall,
        emit: Callable[[Event], None],
        turn: TurnState | None = None,
    ) -> ToolResult:
        turn = turn if turn is not None else TurnState()
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(False, f"error: unknown tool {call.name!r}")
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            return ToolResult(False, "error: arguments are not valid JSON")
        if not isinstance(args, dict):
            return ToolResult(False, "error: arguments must be a JSON object")

        risk = tool.risk_for(args)
        decision = decide(
            risk,
            self._permission(tool.name),
            untrusted=turn.untrusted,
            approved_before=tool.confirm_once and tool.name in turn.approved,
        )
        if decision is Decision.BLOCK:
            emit(ChatToolChanged(turn_id, tool.name, "blocked"))
            return ToolResult(False, SETTING_BLOCKED_RESULT)
        if decision is Decision.ASK:
            if self._confirmer is None:
                emit(ChatToolChanged(turn_id, tool.name, "blocked"))
                return ToolResult(False, BLOCKED_RESULT)
            emit(ChatToolChanged(turn_id, tool.name, "asking"))
            if not await self._confirmer.ask(turn_id, tool.name, tool.question(args), risk):
                emit(ChatToolChanged(turn_id, tool.name, "declined"))
                return ToolResult(False, DECLINED_RESULT)
            if tool.confirm_once and risk is Risk.CONFIRM:
                turn.approved.add(tool.name)

        emit(ChatToolChanged(turn_id, tool.name, "running"))
        result = await self._run(tool.run(args, self._context(tool)), tool.name)
        if result.ok and tool.untrusted_output:
            turn.untrusted = True
        if result.ok and result.summary and self._actions is not None:
            action_id = await self._actions.record(tool.name, result.summary, result.undo)
            emit(
                ActionRecorded(
                    turn_id, action_id, tool.name, result.summary, result.undo is not None
                )
            )
        emit(ChatToolChanged(turn_id, tool.name, "done" if result.ok else "failed"))
        return result

    async def _run(self, work: Any, name: str) -> ToolResult:
        try:
            result: ToolResult = await asyncio.wait_for(work, TOOL_TIMEOUT_S)
        except TimeoutError:
            logger.warning("tool timed out", extra={"fields": {"tool": name}})
            return ToolResult(False, "error: the tool took too long")
        except Exception:
            logger.exception("tool failed", extra={"fields": {"tool": name}})
            return ToolResult(False, "error: the tool failed")
        return result

    async def undo(self, action_id: int | None = None) -> ToolResult:
        """Undo one logged action (the latest undoable one when `action_id` is None)."""
        if self._actions is None:
            return ToolResult(False, "error: no action log", user_message=NOTHING_TO_UNDO)
        if action_id is None:
            action = await self._actions.last_undoable()
        else:
            action = next((a for a in await self._actions.recent() if a.id == action_id), None)
        if action is None or not action.undoable or action.undo is None:
            return ToolResult(False, "error: nothing to undo", user_message=NOTHING_TO_UNDO)
        tool = self._tools.get(action.tool)
        if tool is None:
            return ToolResult(False, "error: that tool is gone", user_message=NOTHING_TO_UNDO)
        result = await self._run(tool.undo(action.undo, self._context(tool)), tool.name)
        if result.ok:
            await self._actions.mark_undone(action.id)
            text = f"Undone: {action.summary}"
            return ToolResult(True, text, user_message=text)
        return result


class UndoLastTool(Tool):
    name = "undo_last"
    description = "Undo EV's last change."
    parameters: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {},
    }
    risk = Risk.SAFE

    def __init__(self, toolbox: Toolbox) -> None:
        self._toolbox = toolbox

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        return await self._toolbox.undo()
