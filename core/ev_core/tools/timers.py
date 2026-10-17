"""Timers, reminders and alarms (docs/FEATURES.md F-108). Stored in `ev.db`, so
they survive restarts; ones that came due while EV was off fire once at the
next start, marked missed."""

import asyncio
import contextlib
import json
import logging
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Final

from ev_core import localtime
from ev_core.bus import Event
from ev_core.interfaces.events import TimerFired
from ev_core.interfaces.tools import Risk, Tool, ToolContext, ToolResult
from ev_core.storage import Database
from ev_core.tools.helpers import parse_when, say_duration

logger = logging.getLogger(__name__)

MAX_DELAY: Final = timedelta(days=366)


@dataclass(frozen=True, slots=True)
class Timer:
    id: int
    kind: str
    label: str
    due_at: datetime


def _row(row: sqlite3.Row) -> Timer:
    return Timer(row["id"], row["kind"], row["label"], datetime.fromisoformat(row["due_at"]))


class Timers:
    """The schedule: one task sleeps until the next due timer."""

    def __init__(
        self,
        db: Database,
        publish: Callable[[Event], None],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._db = db
        self._publish = publish
        self._now = now
        self._task: asyncio.Task[None] | None = None
        self._changed = asyncio.Event()

    async def start(self) -> None:
        missed = await self._take_due("missed")
        for timer in missed:
            self._publish(TimerFired(timer.id, timer.kind, timer.label, missed=True))
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def add(self, kind: str, label: str, due_at: datetime) -> Timer:
        when = due_at.astimezone(UTC)
        created = self._now().isoformat()

        def _insert(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                "INSERT INTO timers (kind, label, due_at, created_at) VALUES (?, ?, ?, ?)",
                (kind, label, when.isoformat(), created),
            )
            return int(cursor.lastrowid or 0)

        timer = Timer(await self._db.run(_insert), kind, label, when)
        self._changed.set()
        return timer

    async def pending(self) -> list[Timer]:
        rows = await self._db.run(
            lambda c: c.execute(
                "SELECT * FROM timers WHERE state = 'pending' ORDER BY due_at"
            ).fetchall()
        )
        return [_row(r) for r in rows]

    async def cancel(self, timer_id: int) -> Timer | None:
        def _cancel(conn: sqlite3.Connection) -> Timer | None:
            row = conn.execute(
                "SELECT * FROM timers WHERE id = ? AND state = 'pending'", (timer_id,)
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE timers SET state = 'cancelled' WHERE id = ?", (timer_id,))
            return _row(row)

        timer = await self._db.run(_cancel)
        self._changed.set()
        return timer

    async def restore(self, timer_id: int) -> None:
        await self._db.run(
            lambda c: c.execute(
                "UPDATE timers SET state = 'pending' WHERE id = ? AND state = 'cancelled'",
                (timer_id,),
            )
        )
        self._changed.set()

    async def _take_due(self, state: str) -> list[Timer]:
        now = self._now().isoformat()

        def _take(conn: sqlite3.Connection) -> list[Timer]:
            rows = conn.execute(
                "SELECT * FROM timers WHERE state = 'pending' AND due_at <= ? ORDER BY due_at",
                (now,),
            ).fetchall()
            conn.executemany(
                "UPDATE timers SET state = ? WHERE id = ?", [(state, r["id"]) for r in rows]
            )
            return [_row(r) for r in rows]

        return await self._db.run(_take)

    async def _loop(self) -> None:
        while True:
            for timer in await self._take_due("fired"):
                self._publish(TimerFired(timer.id, timer.kind, timer.label, missed=False))
            upcoming = await self.pending()
            self._changed.clear()
            delay = (upcoming[0].due_at - self._now()).total_seconds() if upcoming else 3600.0
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(max(0.05, min(delay, 3600.0))):
                    await self._changed.wait()


class TimerTool(Tool):
    name = "timer"
    description = (
        "Timers (minutes), reminders and alarms (text, at: e.g. 5 pm), list, cancel by id."
    )
    parameters: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["timer", "reminder", "alarm", "list", "cancel"]},
            "minutes": {"type": "number"},
            "at": {"type": "string"},
            "text": {"type": "string"},
            "id": {"type": "integer"},
        },
        "required": ["action"],
    }
    risk = Risk.SAFE

    def __init__(self, timers: Timers, now: Callable[[], datetime] = localtime.now) -> None:
        self._timers = timers
        self._now = now

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        action = args.get("action")
        now = self._now()
        try:
            if action == "timer":
                minutes = float(args.get("minutes", 0))
                if minutes <= 0:
                    return ToolResult(False, "error: how long?", "How long should the timer be?")
                seconds = minutes * 60
                timer = await self._timers.add(
                    "timer",
                    str(args.get("text", "")).strip() or "Timer",
                    now + timedelta(seconds=seconds),
                )
                text = f"Timer set for {say_duration(seconds)}."
                return self._made(timer, text)
            if action in ("reminder", "alarm"):
                when = parse_when(str(args.get("at", "")), now)
                if when - now > MAX_DELAY:
                    return ToolResult(False, "error: too far ahead", "That's too far ahead.")
                label = str(args.get("text", "")).strip() or (
                    "Alarm" if action == "alarm" else "Reminder"
                )
                timer = await self._timers.add(str(action), label, when)
                day = "today" if when.date() == now.date() else f"{when:%A}"
                hour = when.hour % 12 or 12
                at = f"{hour}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"
                text = (
                    f"I'll remind you {day} at {at}: {label}."
                    if action == "reminder"
                    else f"Alarm set for {day} at {at}."
                )
                return self._made(timer, text)
            if action == "list":
                items = [
                    {
                        "id": t.id,
                        "kind": t.kind,
                        "label": t.label,
                        "due": t.due_at.astimezone(now.tzinfo).isoformat(timespec="minutes"),
                    }
                    for t in await self._timers.pending()
                ]
                return ToolResult(True, json.dumps({"pending": items}))
            if action == "cancel":
                cancelled = await self._timers.cancel(int(args.get("id", -1)))
                if cancelled is None:
                    return ToolResult(False, "error: no such timer", "That timer isn't set.")
                return ToolResult(
                    True,
                    f"cancelled {cancelled.label}",
                    user_message=f"Cancelled: {cancelled.label}.",
                    summary=f"Cancelled {cancelled.kind}: {cancelled.label}",
                    undo={"restore": cancelled.id},
                )
        except ValueError:
            return ToolResult(
                False, "error: use a time like 17:00 or 5 pm", "When? Say a time like 5 pm."
            )
        return ToolResult(False, "error: unknown action")

    @staticmethod
    def _made(timer: Timer, text: str) -> ToolResult:
        return ToolResult(
            True,
            json.dumps({"id": timer.id, "due_utc": timer.due_at.isoformat(timespec="seconds")}),
            user_message=text,
            summary=text.rstrip("."),
            undo={"cancel": timer.id},
        )

    async def undo(self, data: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        if "cancel" in data:
            await self._timers.cancel(int(data["cancel"]))
        elif "restore" in data:
            await self._timers.restore(int(data["restore"]))
        return ToolResult(True, "undone")
