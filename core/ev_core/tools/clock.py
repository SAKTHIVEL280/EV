"""`current_time`: the model has no clock of its own."""

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, ClassVar

from ev_core.interfaces.tools import Risk, Tool, ToolContext, ToolResult


def _now() -> datetime:
    return datetime.now().astimezone()


class CurrentTimeTool(Tool):
    name = "current_time"
    description = "Get the current local date, time, weekday and time zone."
    parameters: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    risk = Risk.SAFE

    def __init__(self, now: Callable[[], datetime] = _now) -> None:
        self._now = now

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        now = self._now()
        hour = now.hour % 12 or 12
        data = {
            "iso": now.isoformat(timespec="seconds"),
            "time_text": f"{hour}:{now.minute:02d} {'AM' if now.hour < 12 else 'PM'}",
            "date_text": f"{now:%A}, {now:%B} {now.day}, {now.year}",
            "weekday": f"{now:%A}",
            "timezone": now.tzname() or "",
        }
        return ToolResult(ok=True, content=json.dumps(data))
