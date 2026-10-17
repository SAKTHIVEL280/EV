"""`date_math` (docs/FEATURES.md F-417): small models get date arithmetic wrong
("days until Christmas"), so EV computes it."""

import json
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from typing import Any, ClassVar

from ev_core import localtime
from ev_core.interfaces.tools import Risk, Tool, ToolContext, ToolResult
from ev_core.tools.helpers import parse_day


class DateMathTool(Tool):
    name = "date_math"
    description = (
        "Date arithmetic: days between dates, a date plus days, a weekday. "
        "Dates: YYYY-MM-DD or today."
    )
    parameters: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["days_between", "add", "weekday"]},
            "date": {"type": "string"},
            "other": {"type": "string"},
            "days": {"type": "integer"},
        },
        "required": ["operation"],
    }
    risk = Risk.SAFE
    general = True

    def __init__(self, today: Callable[[], date] = lambda: localtime.now().date()) -> None:
        self._today = today

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        today = self._today()
        try:
            first = parse_day(str(args.get("date", "today")), today)
            match args.get("operation"):
                case "days_between":
                    second = parse_day(str(args.get("other", "today")), today)
                    data: dict[str, Any] = {
                        "from": first.isoformat(),
                        "to": second.isoformat(),
                        "days": (second - first).days,
                    }
                case "add":
                    result = first + timedelta(days=int(args.get("days", 0)))
                    data = {"date": result.isoformat(), "weekday": f"{result:%A}"}
                case "weekday":
                    data = {"date": first.isoformat(), "weekday": f"{first:%A}"}
                case _:
                    return ToolResult(False, "error: unknown operation")
        except (ValueError, OverflowError):
            return ToolResult(False, "error: dates must look like 2026-12-25")
        return ToolResult(True, json.dumps(data))
