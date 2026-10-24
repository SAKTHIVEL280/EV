"""The `pc` module: background parts of the PC tools (docs/FEATURES.md Phase 3):
the timer schedule, the clipboard watcher, the action log's 30-day cleanup and
the daily database backup."""

import contextlib
import logging
from pathlib import Path

from ev_core.agent.actions import ActionLog
from ev_core.bus import EventBus
from ev_core.config import ConfigChanged
from ev_core.interfaces.events import (
    ContextCaptured,
    ContextCaptureRequested,
    ContextReplaced,
    ContextReplaceRequested,
)
from ev_core.interfaces.pc import PcControl, PcError
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
        pc: PcControl,
    ) -> None:
        self._db = db
        self._backups = backups
        self._actions = actions
        self._timers = timers
        self._clipboard = clipboard
        self._pc = pc
        self._bus: EventBus | None = None

    async def start(self, ctx: ModuleContext) -> None:
        self._bus = ctx.bus
        ctx.bus.subscribe(ConfigChanged, self._on_config)
        ctx.bus.subscribe(ContextCaptureRequested, self._on_capture)
        ctx.bus.subscribe(ContextReplaceRequested, self._on_replace)
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

    async def _on_capture(self, _: ContextCaptureRequested) -> None:
        # "This" (F-201): only on the hotkey, never in the background; not stored.
        try:
            selection = await self._pc.selection()
        except PcError as exc:
            logger.info("selection unreadable", extra={"fields": {"detail": exc.detail}})
            selection = None
        if self._bus is not None:
            self._bus.publish(
                ContextCaptured(selection.text, selection.app, selection.title)
                if selection
                else ContextCaptured(None)
            )

    async def _on_replace(self, event: ContextReplaceRequested) -> None:
        # Quick action Replace (F-202): type it back; else copy it for the user.
        try:
            replaced = await self._pc.replace_selection(event.text)
            if not replaced:
                await self._pc.set_clipboard_text(event.text)
        except PcError as exc:
            if self._bus is not None:
                self._bus.publish(ContextReplaced(False, exc.user_message))
            return
        message = "Replaced." if replaced else "Copied. Paste it to replace."
        if self._bus is not None:
            self._bus.publish(ContextReplaced(replaced, message))
