"""Settings service: answers the app's config requests (docs/FEATURES.md F-410).

Get, set and reset come in as bus events; every answer is a full
``ConfigStateChanged`` (or ``ConfigRejected``). A change on disk (hand edit,
hot reload) also publishes the state, so an open Settings window stays current.
"""

import asyncio
import logging

from ev_core.bus import EventBus
from ev_core.config.settings import describe
from ev_core.config.store import ConfigEditError, ConfigStore
from ev_core.config.watcher import ConfigChanged, ConfigWatcher
from ev_core.interfaces.events import (
    ConfigGetRequested,
    ConfigRejected,
    ConfigResetRequested,
    ConfigSetRequested,
    ConfigStateChanged,
)

logger = logging.getLogger(__name__)

SAVE_FAILED = "Couldn't save the setting. Details are in the log."


class SettingsService:
    def __init__(self, store: ConfigStore, watcher: ConfigWatcher, bus: EventBus) -> None:
        self._store = store
        self._watcher = watcher
        self._bus = bus
        self._last: ConfigStateChanged | None = None
        bus.subscribe(ConfigGetRequested, self._on_get)
        bus.subscribe(ConfigSetRequested, self._on_set)
        bus.subscribe(ConfigResetRequested, self._on_reset)
        bus.subscribe(ConfigChanged, self._on_changed)

    def state(self, reply_to: str | None = None) -> ConfigStateChanged:
        current = self._watcher.current
        return ConfigStateChanged(
            path=str(self._store.path),
            items=tuple(describe(current.config)),
            warnings=current.warnings,
            reply_to=reply_to,
        )

    async def _on_get(self, event: ConfigGetRequested) -> None:
        self._publish(self.state(event.request_id), force=True)

    async def _on_set(self, event: ConfigSetRequested) -> None:
        await self._edit(event.request_id, event.section, event.key, event.value)

    async def _on_reset(self, event: ConfigResetRequested) -> None:
        await self._edit(event.request_id, event.section, event.key, None)

    async def _edit(
        self, request_id: str, section: str, key: str, value: bool | int | str | None
    ) -> None:
        try:
            if value is None:
                await asyncio.to_thread(self._store.reset_value, section, key)
            else:
                await asyncio.to_thread(self._store.set_value, section, key, value)
        except ConfigEditError as exc:
            logger.info(
                "setting refused",
                extra={"fields": {"key": f"{section}.{key}", "detail": exc.detail}},
            )
            self._bus.publish(ConfigRejected(section, key, exc.user_message, request_id))
            return
        except OSError:
            logger.exception("setting not saved", extra={"fields": {"key": f"{section}.{key}"}})
            self._bus.publish(ConfigRejected(section, key, SAVE_FAILED, request_id))
            return
        # Apply now (modules get ConfigChanged) instead of waiting for the poll.
        await self._watcher.check()
        self._publish(self.state(request_id), force=True)

    async def _on_changed(self, _: ConfigChanged) -> None:
        self._publish(self.state(), force=False)

    def _publish(self, state: ConfigStateChanged, *, force: bool) -> None:
        unchanged = self._last is not None and (state.items, state.warnings) == (
            self._last.items,
            self._last.warnings,
        )
        self._last = state
        if force or not unchanged:
            self._bus.publish(state)
