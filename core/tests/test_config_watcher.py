import os
from pathlib import Path

from ev_core.bus import EventBus
from ev_core.config import ConfigChanged, ConfigStore, ConfigWatcher, LogLevel


def _touch_write(path: Path, text: str) -> None:
    before = path.stat().st_mtime_ns if path.exists() else 0
    path.write_text(text, encoding="utf-8")
    # Guarantee a visible mtime change on coarse-resolution filesystems.
    os.utime(path, ns=(before + 1_000_000_000, before + 1_000_000_000))


async def test_change_publishes_changed_sections(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.toml")
    bus = EventBus()
    events: list[ConfigChanged] = []

    async def on_change(event: ConfigChanged) -> None:
        events.append(event)

    bus.subscribe(ConfigChanged, on_change)
    watcher = ConfigWatcher(store, bus, store.load())

    await watcher.check()
    await bus.drain()
    assert events == []

    _touch_write(store.path, 'config_version = 1\n[logging]\nlevel = "debug"\n')
    await watcher.check()
    await bus.drain()

    assert len(events) == 1
    assert events[0].sections == frozenset({"logging"})
    assert events[0].config.logging.level is LogLevel.DEBUG
    assert watcher.current.config.logging.level is LogLevel.DEBUG


async def test_rewrite_with_same_values_publishes_nothing(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.toml")
    bus = EventBus()
    events: list[ConfigChanged] = []

    async def on_change(event: ConfigChanged) -> None:
        events.append(event)

    bus.subscribe(ConfigChanged, on_change)
    watcher = ConfigWatcher(store, bus, store.load())
    _touch_write(store.path, store.path.read_text(encoding="utf-8") + "\n# comment only\n")
    await watcher.check()
    await bus.drain()
    assert events == []


async def test_new_warning_is_published(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.toml")
    bus = EventBus()
    events: list[ConfigChanged] = []

    async def on_change(event: ConfigChanged) -> None:
        events.append(event)

    bus.subscribe(ConfigChanged, on_change)
    watcher = ConfigWatcher(store, bus, store.load())
    _touch_write(store.path, 'config_version = 1\n[logging]\nlevel = "loud"\n')
    await watcher.check()
    await bus.drain()
    assert len(events) == 1
    assert events[0].sections == frozenset()
    assert [w.key for w in events[0].warnings] == ["logging.level"]
