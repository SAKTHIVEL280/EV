"""Action log (docs/FEATURES.md F-111): every tool action that changed something,
with the data to undo it. Stored in `ev.db`, kept 30 days."""

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from ev_core.storage import Database

KEEP_DAYS: Final = 30


@dataclass(frozen=True, slots=True)
class Action:
    id: int
    at: datetime
    tool: str
    summary: str
    undo: Mapping[str, Any] | None
    undone: bool

    @property
    def undoable(self) -> bool:
        return self.undo is not None and not self.undone


def _row(row: sqlite3.Row) -> Action:
    undo = json.loads(row["undo"]) if row["undo"] else None
    return Action(
        id=row["id"],
        at=datetime.fromisoformat(row["at"]),
        tool=row["tool"],
        summary=row["summary"],
        undo=undo,
        undone=bool(row["undone"]),
    )


class ActionLog:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(
        self, tool: str, summary: str, undo: Mapping[str, Any] | None, at: datetime | None = None
    ) -> int:
        when = (at or datetime.now(UTC)).isoformat()
        data = json.dumps(dict(undo)) if undo is not None else None

        def _insert(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                "INSERT INTO action_log (at, tool, summary, undo) VALUES (?, ?, ?, ?)",
                (when, tool, summary, data),
            )
            return int(cursor.lastrowid or 0)

        return await self._db.run(_insert)

    async def last_undoable(self) -> Action | None:
        def _query(conn: sqlite3.Connection) -> Action | None:
            row = conn.execute(
                "SELECT * FROM action_log WHERE undo IS NOT NULL AND undone = 0 "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return _row(row) if row else None

        return await self._db.run(_query)

    async def mark_undone(self, action_id: int) -> None:
        await self._db.run(
            lambda c: c.execute("UPDATE action_log SET undone = 1 WHERE id = ?", (action_id,))
        )

    async def recent(self, limit: int = 50) -> list[Action]:
        def _query(conn: sqlite3.Connection) -> list[Action]:
            rows = conn.execute(
                "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [_row(r) for r in rows]

        return await self._db.run(_query)

    async def purge(self, now: datetime | None = None) -> int:
        cutoff = ((now or datetime.now(UTC)) - timedelta(days=KEEP_DAYS)).isoformat()

        def _delete(conn: sqlite3.Connection) -> int:
            return conn.execute("DELETE FROM action_log WHERE at < ?", (cutoff,)).rowcount

        return await self._db.run(_delete)
