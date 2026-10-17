"""Composition root: config -> logging -> bus -> registry -> server.

Startup contract with the Rust supervisor (docs/ARCHITECTURE.md §2):
- ``EV_CORE_TOKEN``: 64 lowercase hex chars, required.
- ``EV_DATA_DIR``: optional data directory override.
- ``EV_LLAMA_DIR``: folder containing llama-server (bundled runtime).
- Exactly one line on stdout once listening:
  ``{"event": "listening", "port": <int>, "protocol": <int>}``.
- Exit when the app sends ``shutdown``, on SIGTERM/SIGINT, or when stdin
  reaches EOF (the parent died or closed the pipe).

Exit codes: 0 clean stop, 1 startup failure, 2 bad environment.
"""

import asyncio
import contextlib
import json
import logging
import re
import signal
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TextIO

from ev_core import __version__, protocol
from ev_core.agent import AgentModule
from ev_core.bus import EventBus
from ev_core.config import ConfigChanged, ConfigStore, ConfigWatcher, LlmSection
from ev_core.config.service import SettingsService
from ev_core.errors import EvError
from ev_core.interfaces.events import ModelInstalled
from ev_core.llm import LlmModule
from ev_core.log import set_level, setup_logging
from ev_core.models import ModelsModule
from ev_core.models.catalog import load_catalog
from ev_core.modules import ModuleRegistry
from ev_core.paths import data_dir
from ev_core.server import CoreServer
from ev_core.tools.clock import CurrentTimeTool

logger = logging.getLogger(__name__)

LLAMA_DIR_ENV: Final = "EV_LLAMA_DIR"
TOKEN_ENV: Final = "EV_CORE_TOKEN"  # noqa: S105 -- variable name, not a secret
_TOKEN_RE: Final = re.compile(r"^[0-9a-f]{64}$")

EXIT_OK: Final = 0
EXIT_STARTUP_FAILED: Final = 1
EXIT_BAD_ENV: Final = 2


async def run(env: Mapping[str, str], stdout: TextIO, stdin: TextIO | None) -> int:
    token = env.get(TOKEN_ENV, "")
    if not _TOKEN_RE.match(token):
        _stderr_line("bad_env", f"{TOKEN_ENV} must be 64 lowercase hex characters")
        return EXIT_BAD_ENV

    try:
        root = data_dir(env)
        root.mkdir(parents=True, exist_ok=True)
        store = ConfigStore(root / "config.toml")
        loaded = store.load()
        setup_logging(root / "logs", loaded.config.logging.level.value)
    except (EvError, OSError) as exc:
        _stderr_line("startup_failed", str(exc))
        return EXIT_STARTUP_FAILED

    logger.info("core starting", extra={"fields": {"version": __version__}})
    for warning in loaded.warnings:
        logger.warning(
            "config warning", extra={"fields": {"key": warning.key, "detail": warning.message}}
        )

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    bus = EventBus()
    registry = ModuleRegistry(bus)
    config = loaded.config
    llama_dir = env.get(LLAMA_DIR_ENV)
    llm = LlmModule(config.llm, root, Path(llama_dir) if llama_dir else None)
    registry.register(llm, enabled=config.llm.enabled)
    registry.register(
        AgentModule(config.agent, config.llm, provider=llm, tools=[CurrentTimeTool()]),
        enabled=True,
    )
    registry.register(ModelsModule(config.llm, root, load_catalog()), enabled=True)

    async def on_config_changed(event: ConfigChanged) -> None:
        if "logging" in event.sections:
            set_level(event.config.logging.level.value)

    bus.subscribe(ConfigChanged, on_config_changed)
    watcher = ConfigWatcher(store, bus, loaded)
    settings = SettingsService(store, watcher, bus)

    async def on_model_installed(event: ModelInstalled) -> None:
        await fill_model_slot(event, watcher.current.config.llm, settings)

    bus.subscribe(ModelInstalled, on_model_installed)

    server = CoreServer(
        bus=bus,
        token=token,
        core_version=__version__,
        module_statuses=registry.statuses,
        on_shutdown=lambda _reason: stop.set(),
    )
    try:
        await registry.start_all()
        port = await server.start()
    except (EvError, OSError):
        logger.exception("core failed to start")
        await registry.stop_all()
        return EXIT_STARTUP_FAILED

    _install_stop_triggers(loop, stop, stdin)
    watcher_task = asyncio.create_task(watcher.run())

    stdout.write(
        json.dumps({"event": "listening", "port": port, "protocol": protocol.PROTOCOL_VERSION})
        + "\n"
    )
    stdout.flush()
    logger.info("core listening", extra={"fields": {"port": port}})

    await stop.wait()

    logger.info("core stopping")
    watcher_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher_task
    await server.close()
    await registry.stop_all()
    await bus.drain()
    logger.info("core stopped")
    return EXIT_OK


async def fill_model_slot(
    event: ModelInstalled, llm: LlmSection, settings: SettingsService
) -> None:
    """Put a newly installed model in its config slot, only when that slot is empty:
    a downloaded model never replaces the user's choice (docs/FEATURES.md F-403)."""
    key = f"model_{event.role}"
    current = getattr(llm, key, None)
    if isinstance(current, str) and not current.strip():
        await settings.set_value("llm", key, event.file)


def _install_stop_triggers(
    loop: asyncio.AbstractEventLoop, stop: asyncio.Event, stdin: TextIO | None
) -> None:
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
    if stdin is None:
        logger.warning("no stdin; parent-exit detection disabled")
        return

    def wait_for_eof() -> None:
        # Blocking read on a daemon thread; returns only at EOF.
        while stdin.read(4096):
            pass
        logger.info("stdin closed")
        loop.call_soon_threadsafe(stop.set)

    threading.Thread(target=wait_for_eof, name="stdin-eof", daemon=True).start()


def _stderr_line(code: str, detail: str) -> None:
    sys.stderr.write(json.dumps({"level": "error", "code": code, "msg": detail}) + "\n")
    sys.stderr.flush()
