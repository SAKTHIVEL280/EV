"""Date math, clipboard, timers and focus mode (F-417, F-106, F-108, F-109)."""

import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ev_core.bus import Event
from ev_core.interfaces.events import FocusModeChanged, TimerFired
from ev_core.interfaces.tools import ToolContext
from ev_core.platform.fake_pc import FakePcControl
from ev_core.storage import Database
from ev_core.tools.clipboard import ClipboardHistory, ClipboardTool, sensitive
from ev_core.tools.datemath import DateMathTool
from ev_core.tools.focus import FocusMode, FocusModeTool
from ev_core.tools.timers import Timers, TimerTool

CTX = ToolContext(logger=logging.getLogger("test"))
IST = timezone(timedelta(hours=5, minutes=30))

# --- date math


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"operation": "days_between", "date": "today", "other": "2026-12-25"}, {"days": 69}),
        ({"operation": "days_between", "date": "2026-12-25", "other": "today"}, {"days": -69}),
        ({"operation": "days_between", "date": "2028-02-28", "other": "2028-03-01"}, {"days": 2}),
        (
            {"operation": "add", "date": "today", "days": 100},
            {"date": "2027-01-25", "weekday": "Monday"},
        ),
        ({"operation": "weekday", "date": "2026-12-25"}, {"weekday": "Friday"}),
    ],
)
async def test_date_math(args: dict[str, object], expected: dict[str, object]) -> None:
    tool = DateMathTool(today=lambda: date(2026, 10, 17))
    result = await tool.run(args, CTX)
    assert result.ok
    data = json.loads(result.content)
    assert {k: data[k] for k in expected} == expected


async def test_date_math_bad_input() -> None:
    result = await DateMathTool(today=lambda: date(2026, 10, 17)).run(
        {"operation": "weekday", "date": "next christmas"}, CTX
    )
    assert result.content == "error: dates must look like 2026-12-25"


# --- clipboard


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("4111 1111 1111 1111", True),
        ("  482913 ", True),
        ("sk-abcdefghijklmnop1234", True),
        ("password: hunter2", True),
        ("-----BEGIN RSA PRIVATE KEY-----", True),
        ("Meeting moved to 3 pm", False),
        ("Call me at 2026", False),
    ],
)
def test_sensitive_text(text: str, secret: bool) -> None:
    assert sensitive(text) is secret


async def test_clipboard_read_write_history_and_undo(tmp_path: Path) -> None:
    pc = FakePcControl(tmp_path)
    history = ClipboardHistory(pc)
    tool = ClipboardTool(pc, history)
    assert (await tool.run({"action": "read"}, CTX)).user_message == "Nothing is copied."
    await pc.set_clipboard_text("teh first")
    history.note(await pc.clipboard_text())
    history.note("482913")  # a one-time code: never kept
    read = await tool.run({"action": "read"}, CTX)
    assert json.loads(read.content) == {"copied_text": "teh first"}
    written = await tool.run({"action": "write", "text": "the first"}, CTX)
    assert written.user_message == "Copied. Paste it where you want it."
    assert json.loads((await tool.run({"action": "history"}, CTX)).content) == {
        "recent": ["the first", "teh first"]
    }
    assert written.undo is not None
    await tool.undo(written.undo, CTX)
    assert await pc.clipboard_text() == "teh first"
    history.set_enabled(False)
    assert history.items() == []
    off = await tool.run({"action": "history"}, CTX)
    assert off.content == "error: clipboard history is off in Settings"


# --- timers


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


async def timers_with(tmp_path: Path, clock: Clock) -> tuple[Timers, list[Event], Database]:
    db = Database(tmp_path / "ev.db")
    await db.open()
    fired: list[Event] = []
    return Timers(db, fired.append, now=clock), fired, db


async def test_timer_fires(tmp_path: Path) -> None:
    clock = Clock()
    timers, fired, _ = await timers_with(tmp_path, clock)
    await timers.start()
    tool = TimerTool(timers, now=lambda: clock.now.astimezone(IST))
    result = await tool.run({"action": "timer", "minutes": 10}, CTX)
    assert result.user_message == "Timer set for 10 minutes."
    await asyncio.sleep(0.1)
    assert fired == []
    clock.now += timedelta(minutes=10)
    timers._changed.set()  # the test clock jumped; wake the scheduler
    await asyncio.sleep(0.2)
    assert fired == [TimerFired(1, "timer", "Timer", missed=False)]
    await timers.stop()


async def test_reminders_list_cancel_and_undo(tmp_path: Path) -> None:
    clock = Clock()
    timers, _, _ = await timers_with(tmp_path, clock)
    tool = TimerTool(timers, now=lambda: clock.now.astimezone(IST))  # 15:30 IST
    made = await tool.run({"action": "reminder", "at": "5 pm", "text": "call mom"}, CTX)
    assert made.user_message == "I'll remind you today at 5:00 PM: call mom."
    alarm = await tool.run({"action": "alarm", "at": "tomorrow 6:30"}, CTX)
    assert alarm.user_message == "Alarm set for Sunday at 6:30 AM."
    listed = json.loads((await tool.run({"action": "list"}, CTX)).content)["pending"]
    assert [(t["kind"], t["label"], t["due"]) for t in listed] == [
        ("reminder", "call mom", "2026-10-17T17:00+05:30"),
        ("alarm", "Alarm", "2026-10-18T06:30+05:30"),
    ]
    cancelled = await tool.run({"action": "cancel", "id": 1}, CTX)
    assert cancelled.user_message == "Cancelled: call mom."
    assert cancelled.undo is not None
    await tool.undo(cancelled.undo, CTX)
    assert len(await timers.pending()) == 2
    bad = await tool.run({"action": "reminder", "at": "whenever"}, CTX)
    assert bad.user_message == "When? Say a time like 5 pm."


async def test_missed_while_off_fire_once_at_start(tmp_path: Path) -> None:
    clock = Clock()
    timers, _, db = await timers_with(tmp_path, clock)
    await timers.add("reminder", "standup", clock.now + timedelta(minutes=5))
    await db.close()
    clock.now += timedelta(hours=2)  # EV was off
    later, fired_later, _ = await timers_with(tmp_path, clock)
    await later.start()
    assert fired_later == [TimerFired(1, "reminder", "standup", missed=True)]
    assert await later.pending() == []
    await later.stop()


# --- focus mode


async def test_focus_mode_turns_off_by_itself() -> None:
    events: list[Event] = []
    focus = FocusMode(events.append)
    tool = FocusModeTool(focus)
    result = await tool.run({"on": True, "minutes": 25}, CTX)
    assert result.user_message is not None
    assert result.user_message.startswith("Focus mode on for 25 minutes.")
    assert events == [FocusModeChanged(True, 25)]
    if focus._timer is not None:
        focus._timer.cancel()
    off = await tool.run({"on": False}, CTX)
    assert off.user_message == "Focus mode off."
    assert events[-1] == FocusModeChanged(False, None)
