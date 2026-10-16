import asyncio
from collections.abc import Mapping
from typing import Any, ClassVar

import pytest

from ev_core.agent import toolbox as toolbox_module
from ev_core.agent.toolbox import BLOCKED_RESULT, Toolbox
from ev_core.bus import Event
from ev_core.interfaces.events import ChatToolChanged
from ev_core.interfaces.llm import ToolCall
from ev_core.interfaces.tools import Risk, Tool, ToolContext, ToolResult


class EchoTool(Tool):
    name = "echo"
    description = "Echo the text argument."
    parameters: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
    }
    risk = Risk.SAFE

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(True, str(args.get("text", "")))


class DeleteTool(EchoTool):
    name = "delete_file"
    risk = Risk.DANGEROUS


class BrokenTool(EchoTool):
    name = "broken"

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        raise RuntimeError("boom")


class SlowTool(EchoTool):
    name = "slow"

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        await asyncio.sleep(10)
        return ToolResult(True, "late")


def make() -> tuple[Toolbox, list[Event]]:
    events: list[Event] = []
    return Toolbox([EchoTool(), DeleteTool(), BrokenTool(), SlowTool()]), events


async def test_success_emits_running_then_done() -> None:
    box, events = make()
    result = await box.execute("t", ToolCall("1", "echo", '{"text": "hi"}'), events.append)
    assert result == ToolResult(True, "hi")
    assert events == [ChatToolChanged("t", "echo", "running"), ChatToolChanged("t", "echo", "done")]


@pytest.mark.parametrize(
    ("call", "content"),
    [
        (ToolCall("1", "nope", "{}"), "error: unknown tool 'nope'"),
        (ToolCall("1", "echo", "{not json"), "error: arguments are not valid JSON"),
        (ToolCall("1", "echo", "[1, 2]"), "error: arguments must be a JSON object"),
    ],
)
async def test_rejected_calls(call: ToolCall, content: str) -> None:
    box, events = make()
    result = await box.execute("t", call, events.append)
    assert result == ToolResult(False, content)
    assert events == []


async def test_empty_arguments_mean_empty_object() -> None:
    box, events = make()
    assert (await box.execute("t", ToolCall("1", "echo", ""), events.append)).ok


async def test_non_safe_tools_are_blocked() -> None:
    box, events = make()
    result = await box.execute("t", ToolCall("1", "delete_file", "{}"), events.append)
    assert result == ToolResult(False, BLOCKED_RESULT)
    assert events == [ChatToolChanged("t", "delete_file", "blocked")]


async def test_tool_exception_is_contained() -> None:
    box, events = make()
    result = await box.execute("t", ToolCall("1", "broken", "{}"), events.append)
    assert not result.ok
    assert events[-1] == ChatToolChanged("t", "broken", "failed")


async def test_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toolbox_module, "TOOL_TIMEOUT_S", 0.05)
    box, events = make()
    result = await box.execute("t", ToolCall("1", "slow", "{}"), events.append)
    assert result == ToolResult(False, "error: the tool took too long")
    assert events[-1] == ChatToolChanged("t", "slow", "failed")


def test_duplicate_names_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        Toolbox([EchoTool(), EchoTool()])


def test_specs() -> None:
    box, _ = make()
    assert [s.name for s in box.specs()] == ["echo", "delete_file", "broken", "slow"]
