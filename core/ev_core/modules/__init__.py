"""Plug-and-play module base class and registry (docs/ARCHITECTURE.md §4.1).

Modules never import each other. A module only receives a ``ModuleContext``:
the event bus and its own logger. A module that fails to start disables only
itself; its status says why.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Final

from ev_core.bus import EventBus
from ev_core.errors import EvError

logger = logging.getLogger(__name__)

START_TIMEOUT_S: Final = 10.0
DISABLED_DETAIL: Final = "Turned off in Settings."
FAILED_DETAIL: Final = "Couldn't start. Details are in the log."
TIMEOUT_DETAIL: Final = "Took too long to start."


class ModuleState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    DISABLED = "disabled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ModuleStatus:
    name: str
    state: ModuleState
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleContext:
    bus: EventBus
    logger: logging.Logger


class Module(ABC):
    """A feature module. Subclasses set ``name`` and implement start/stop."""

    name: ClassVar[str]

    @abstractmethod
    async def start(self, ctx: ModuleContext) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...


@dataclass(slots=True)
class _Entry:
    module: Module
    enabled: bool
    status: ModuleStatus


class ModuleRegistry:
    def __init__(self, bus: EventBus, start_timeout_s: float = START_TIMEOUT_S) -> None:
        self._bus = bus
        self._start_timeout_s = start_timeout_s
        self._entries: dict[str, _Entry] = {}

    def register(self, module: Module, *, enabled: bool) -> None:
        if module.name in self._entries:
            raise ValueError(f"module {module.name!r} is already registered")
        self._entries[module.name] = _Entry(
            module=module,
            enabled=enabled,
            status=ModuleStatus(module.name, ModuleState.STARTING),
        )

    async def start_all(self) -> None:
        """Start modules in registration order, isolating each failure."""
        for entry in self._entries.values():
            entry.status = await self._start(entry)

    async def stop_all(self) -> None:
        """Stop ready modules in reverse order. Errors are logged, never raised."""
        for entry in reversed(self._entries.values()):
            if entry.status.state is not ModuleState.READY:
                continue
            try:
                await entry.module.stop()
            except Exception:
                logger.exception(
                    "module stop failed", extra={"fields": {"module": entry.module.name}}
                )

    def statuses(self) -> list[ModuleStatus]:
        return [entry.status for entry in self._entries.values()]

    async def _start(self, entry: _Entry) -> ModuleStatus:
        name = entry.module.name
        if not entry.enabled:
            return ModuleStatus(name, ModuleState.DISABLED, DISABLED_DETAIL)
        ctx = ModuleContext(bus=self._bus, logger=logging.getLogger(f"ev_core.module.{name}"))
        try:
            await asyncio.wait_for(entry.module.start(ctx), self._start_timeout_s)
        except TimeoutError:
            logger.exception("module start timed out", extra={"fields": {"module": name}})
            return ModuleStatus(name, ModuleState.FAILED, TIMEOUT_DETAIL)
        except EvError as exc:
            logger.exception("module start failed", extra={"fields": {"module": name}})
            return ModuleStatus(name, ModuleState.FAILED, exc.user_message)
        except Exception:
            logger.exception("module start failed", extra={"fields": {"module": name}})
            return ModuleStatus(name, ModuleState.FAILED, FAILED_DETAIL)
        return ModuleStatus(name, ModuleState.READY)
