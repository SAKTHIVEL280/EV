"""The `pc` module: background parts of the PC tools (docs/FEATURES.md Phase 3):
the timer schedule, the clipboard watcher, the action log's 30-day cleanup and
the daily database backup."""

import contextlib
import logging
from pathlib import Path

from ev_core.agent.actions import ActionLog
from ev_core.config import ConfigChanged
from ev_core.modules import Module, ModuleContext
from ev_core.storage import Database
from ev_core.tools.clipboard import ClipboardHistory
from ev_core.tools.timers import Timers

logger = logging.getLogger(__name__)


class PcModule(Module):
    name = "pc"

    def __init__(
        self,
        db: Database,
        backups: Path,
        actions: ActionLog,
        timers: Timers,
        clipboard: ClipboardHistory,
    ) -> None:
        self._db = db
        self._backups = backups
        self._actions = actions
        self._timers = timers
        self._clipboard = clipboard

    async def start(self, ctx: ModuleContext) -> None:
        ctx.bus.subscribe(ConfigChanged, self._on_config)
        await self._timers.start()
        self._clipboard.start()
        purged = await self._actions.purge()
        made = await self._db.backup(self._backups)
        logger.info(
            "pc tools ready",
            extra={"fields": {"purged_actions": purged, "backup": made.name if made else None}},
        )

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            await self._clipboard.stop()
        await self._timers.stop()

    async def _on_config(self, event: ConfigChanged) -> None:
        if "clipboard" in event.sections:
            self._clipboard.set_enabled(event.config.clipboard.history)
