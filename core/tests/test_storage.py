import sqlite3
from datetime import date
from pathlib import Path

import pytest

from ev_core.storage import Database, DatabaseError, Migration, bundled_migrations


def test_bundled_migrations_are_numbered_in_order() -> None:
    migrations = bundled_migrations()
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))
    assert migrations[0].name == "001_timers_and_action_log.sql"


async def test_fresh_database_gets_every_migration(tmp_path: Path) -> None:
    db = Database(tmp_path / "ev.db")
    await db.open()
    version = await db.run(lambda c: c.execute("PRAGMA user_version").fetchone()[0])
    tables = await db.run(
        lambda c: {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    )
    mode = await db.run(lambda c: c.execute("PRAGMA journal_mode").fetchone()[0])
    assert version == db.version
    assert {"timers", "action_log"} <= tables
    assert mode == "wal"
    await db.close()


async def test_only_new_migrations_run_and_data_survives(tmp_path: Path) -> None:
    first = [Migration(1, "001_a.sql", "CREATE TABLE a (x INTEGER);")]
    db = Database(tmp_path / "ev.db", first)
    await db.open()
    await db.run(lambda c: c.execute("INSERT INTO a VALUES (7)"))
    await db.close()
    second = [*first, Migration(2, "002_b.sql", "ALTER TABLE a ADD COLUMN y TEXT;")]
    db = Database(tmp_path / "ev.db", second)
    await db.open()
    rows = await db.run(lambda c: c.execute("SELECT x, y FROM a").fetchall())
    assert [tuple(r) for r in rows] == [(7, None)]
    await db.close()


async def test_failed_migration_rolls_back_and_reports(tmp_path: Path) -> None:
    broken = [
        Migration(1, "001_a.sql", "CREATE TABLE a (x INTEGER);"),
        Migration(2, "002_bad.sql", "CREATE TABLE b (y INTEGER); CREATE TABLE a (x INTEGER);"),
    ]
    db = Database(tmp_path / "ev.db", broken)
    with pytest.raises(DatabaseError) as caught:
        await db.open()
    assert caught.value.user_message == "Couldn't update EV's database."
    conn = sqlite3.connect(tmp_path / "ev.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='b'").fetchone() is None
    conn.close()


async def test_newer_database_is_refused(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "ev.db")
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    with pytest.raises(DatabaseError) as caught:
        await Database(tmp_path / "ev.db").open()
    assert "newer version" in caught.value.user_message


async def test_daily_backup_keeps_three(tmp_path: Path) -> None:
    db = Database(tmp_path / "ev.db")
    await db.open()
    folder = tmp_path / "backups"
    for day in range(1, 6):
        await db.backup(folder, date(2026, 10, day))
    assert sorted(p.name for p in folder.iterdir()) == [
        "ev-2026-10-03.db",
        "ev-2026-10-04.db",
        "ev-2026-10-05.db",
    ]
    assert await db.backup(folder, date(2026, 10, 5)) is None  # already made today
    copy = sqlite3.connect(folder / "ev-2026-10-05.db")
    assert copy.execute("PRAGMA user_version").fetchone()[0] == db.version
    copy.close()
    await db.close()
