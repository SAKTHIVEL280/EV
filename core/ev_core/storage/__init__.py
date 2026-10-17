"""Local database `ev.db` (CLAUDE.md §5.7, §10.2): SQLite in WAL mode with
numbered, forward-only migrations and a daily backup (keep 3).

Migrations are the files in `migrations/` named `NNN_description.sql`, applied
in order inside one transaction each; `PRAGMA user_version` records the last
one. A database newer than this build is refused rather than touched.

All access goes through `Database.run`, which serializes calls on one
connection in a worker thread so the event loop never blocks.
"""

import asyncio
import logging
import re
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Final

from ev_core.errors import EvError

logger = logging.getLogger(__name__)

BACKUPS_KEPT: Final = 3
_MIGRATION_NAME: Final = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


class DatabaseError(EvError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


def bundled_migrations() -> list[Migration]:
    found: list[Migration] = []
    for entry in resources.files("ev_core.storage.migrations").iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match:
            found.append(Migration(int(match[1]), entry.name, entry.read_text(encoding="utf-8")))
    found.sort(key=lambda m: m.version)
    versions = [m.version for m in found]
    if versions != list(range(1, len(found) + 1)):
        raise DatabaseError("EV's database files are damaged.", f"migration numbers {versions}")
    return found


class Database:
    def __init__(self, path: Path, migrations: list[Migration] | None = None) -> None:
        self.path = path
        self._migrations = migrations if migrations is not None else bundled_migrations()
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    @property
    def version(self) -> int:
        return self._migrations[-1].version if self._migrations else 0

    async def open(self) -> None:
        await asyncio.to_thread(self._open)

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current > self.version:
            conn.close()
            raise DatabaseError(
                "EV's database is from a newer version of EV.",
                f"user_version {current} > supported {self.version}",
            )
        for migration in self._migrations:
            if migration.version <= current:
                continue
            try:
                conn.execute("BEGIN IMMEDIATE")
                for statement in _statements(migration.sql):
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {migration.version}")
                conn.execute("COMMIT")
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                conn.close()
                raise DatabaseError(
                    "Couldn't update EV's database.", f"{migration.name}: {exc}"
                ) from exc
            logger.info("database migrated", extra={"fields": {"to": migration.name}})
        self._conn = conn

    async def close(self) -> None:
        def _close() -> None:
            with self._lock:
                if self._conn is not None:
                    self._conn.close()
                    self._conn = None

        await asyncio.to_thread(_close)

    async def run[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run `work` with the connection on a worker thread, one call at a time."""

        def _call() -> T:
            with self._lock:
                if self._conn is None:
                    raise DatabaseError("EV's database isn't open.", "run before open")
                return work(self._conn)

        return await asyncio.to_thread(_call)

    async def backup(self, folder: Path, today: date | None = None) -> Path | None:
        """Today's backup in `folder` (made if missing); older ones beyond 3 are deleted."""
        day = (today or date.today()).isoformat()
        target = folder / f"ev-{day}.db"

        def _backup() -> Path | None:
            folder.mkdir(parents=True, exist_ok=True)
            made = None
            if not target.exists():
                with self._lock:
                    if self._conn is None:
                        return None
                    dest = sqlite3.connect(target)
                    try:
                        self._conn.backup(dest)
                    finally:
                        dest.close()
                made = target
            backups = sorted(folder.glob("ev-????-??-??.db"))
            for old in backups[:-BACKUPS_KEPT]:
                old.unlink(missing_ok=True)
            return made

        return await asyncio.to_thread(_backup)


def _statements(sql: str) -> list[str]:
    """Split a migration into statements (no semicolons inside literals in our files)."""
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
