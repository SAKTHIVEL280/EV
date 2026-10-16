"""Config hot reload by polling (docs/ARCHITECTURE.md §4.3).

Polling one ``stat`` per second costs nothing measurable and needs no
file-watcher dependency. A reload that changes nothing publishes nothing.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Final

from ev_core.bus import Event, EventBus
from ev_core.config.schema import EvConfig
from ev_core.config.store import ConfigStore, ConfigWarning, LoadedConfig

logger = logging.getLogger(__name__)

POLL_INTERVAL_S: Final = 1.0


@dataclass(frozen=True, slots=True)
class ConfigChanged(Event):
    config: EvConfig
    sections: frozenset[str]
    warnings: tuple[ConfigWarning, ...]


class ConfigWatcher:
    def __init__(
        self,
        store: ConfigStore,
        bus: EventBus,
        current: LoadedConfig,
        interval_s: float = POLL_INTERVAL_S,
    ) -> None:
        self._store = store
        self._bus = bus
        self._interval_s = interval_s
        self.current = current
        self._last_stat = self._stat()

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            await self.check()

    async def check(self) -> None:
        """Reload once if the file changed since the last check."""
        stat = self._stat()
        if stat == self._last_stat:
            return
        loaded = await asyncio.to_thread(self._store.load)
        # load() may rewrite the file (defaults, migration); don't reload our own write.
        self._last_stat = self._stat()
        previous = self.current
        self.current = loaded
        changed = frozenset(
            name
            for name in EvConfig.model_fields
            if getattr(previous.config, name) != getattr(loaded.config, name)
        )
        if changed or loaded.warnings != previous.warnings:
            logger.info("config reloaded", extra={"fields": {"sections": sorted(changed)}})
            self._bus.publish(ConfigChanged(loaded.config, changed, loaded.warnings))

    def _stat(self) -> tuple[int, int] | None:
        try:
            st = self._store.path.stat()
        except FileNotFoundError:
            return None
        return (st.st_mtime_ns, st.st_size)
