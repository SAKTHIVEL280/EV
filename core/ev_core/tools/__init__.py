"""Tool implementations (each implements ev_core.interfaces.tools.Tool)."""

from ev_core.interfaces.pc import PcControl
from ev_core.interfaces.tools import Tool
from ev_core.tools.clipboard import ClipboardHistory, ClipboardTool
from ev_core.tools.clock import CurrentTimeTool
from ev_core.tools.datemath import DateMathTool
from ev_core.tools.focus import FocusMode, FocusModeTool
from ev_core.tools.pc_tools import (
    AppsTool,
    FilesTool,
    ScreenshotTool,
    SystemTool,
    UiTool,
    WindowTool,
)
from ev_core.tools.timers import Timers, TimerTool


def build_tools(
    pc: PcControl, timers: Timers, clipboard: ClipboardHistory, focus: FocusMode
) -> list[Tool]:
    """Every tool the agent offers, in prompt order (the app and golden tests share it)."""
    return [
        CurrentTimeTool(),
        DateMathTool(),
        AppsTool(pc),
        WindowTool(pc),
        SystemTool(pc),
        ScreenshotTool(pc),
        ClipboardTool(pc, clipboard),
        FilesTool(pc),
        TimerTool(timers),
        FocusModeTool(focus),
        UiTool(pc),
    ]
