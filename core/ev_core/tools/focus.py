"""Focus mode (docs/FEATURES.md F-109): EV stays quiet for a while. Windows has
no supported API to switch its own Do Not Disturb, so EV says so."""

import asyncio
import contextlib
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from ev_core.bus import Event
from ev_core.interfaces.events import FocusModeChanged
from ev_core.interfaces.tools import Risk, Tool, ToolContext, ToolResult
from ev_core.tools.helpers import say_duration

WINDOWS_NOTE = "Windows' own Do Not Disturb isn't changed; say if you want its settings opened."


class FocusMode:
    def __init__(self, publish: Callable[[Event], None]) -> None:
        self._publish = publish
        self.on = False
        self._timer: asyncio.Task[None] | None = None

    def set(self, on: bool, minutes: int | None = None) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self.on = on
        self._publish(FocusModeChanged(on, minutes if on else None))
        if on and minutes:
            self._timer = asyncio.create_task(self._end_after(minutes * 60))

    async def _end_after(self, seconds: float) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(seconds)
            self._timer = None
            self.on = False
            self._publish(FocusModeChanged(False, None))


class FocusModeTool(Tool):
    name = "focus_mode"
    description = "EV focus mode on (optional minutes) or off."
    parameters: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {
            "on": {"type": "boolean"},
            "minutes": {"type": "integer"},
        },
        "required": ["on"],
    }
    risk = Risk.SAFE

    def __init__(self, focus: FocusMode) -> None:
        self._focus = focus

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        on = bool(args.get("on"))
        minutes = args.get("minutes") if isinstance(args.get("minutes"), int) else None
        was = self._focus.on
        self._focus.set(on, minutes)
        if on:
            span = f" for {say_duration(minutes * 60)}" if minutes else ""
            text = f"Focus mode on{span}. {WINDOWS_NOTE}"
        else:
            text = "Focus mode off."
        return ToolResult(
            True,
            text,
            user_message=text,
            summary=f"Focus mode {'on' if on else 'off'}",
            undo={"on": was},
        )

    async def undo(self, data: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        self._focus.set(bool(data["on"]))
        return ToolResult(True, "restored")
