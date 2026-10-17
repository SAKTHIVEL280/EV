"""The `llm` module: owns llama-server and provides models to the agent
(CLAUDE.md §5.5-5.6, docs/FEATURES.md F-003).

- Effort roles (small / default / large) map to configured model files with
  fallback to the nearest installed model.
- One model is loaded at a time; asking for another reloads llama-server.
- The default model warms in the background at start; after
  `llm.idle_unload_minutes` without use the model is unloaded (never while a
  reply is streaming).
- Every state change is published as `LlmStatusChanged`.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Final

import aiohttp
import psutil

from ev_core.bus import EventBus
from ev_core.config import ConfigChanged, LlmSection
from ev_core.errors import EvError
from ev_core.interfaces.events import LlmStatusChanged
from ev_core.interfaces.llm import (
    ChatMessage,
    LlmBackend,
    LlmError,
    LlmEvent,
    LlmProvider,
    ModelRole,
    ToolSpec,
)
from ev_core.llm.client import LlamaServerClient
from ev_core.llm.server import BINARY, LaunchConfig, LlamaServer, ServerStartError
from ev_core.modules import Module, ModuleContext
from ev_core.platform.children import ChildGuard

logger = logging.getLogger(__name__)

NO_MODEL_TEXT: Final = "No model installed. Add one in Settings."
LOAD_FAILED_TEXT: Final = "Couldn't load the model. Details are in the log."
RUNTIME_MISSING_TEXT: Final = "The model runtime is missing. Reinstall EV."
DISABLED_TEXT: Final = "The language model is turned off in Settings."
READY_TIMEOUT_S: Final = 180.0
IDLE_CHECK_S: Final = 30.0

FALLBACK: Final[dict[ModelRole, tuple[ModelRole, ...]]] = {
    ModelRole.SMALL: (ModelRole.SMALL, ModelRole.DEFAULT, ModelRole.LARGE),
    ModelRole.DEFAULT: (ModelRole.DEFAULT, ModelRole.SMALL, ModelRole.LARGE),
    ModelRole.LARGE: (ModelRole.LARGE, ModelRole.DEFAULT, ModelRole.SMALL),
}


def resolve_model(settings: LlmSection, models_dir: Path, role: ModelRole) -> Path | None:
    """The configured model file for `role`, or the nearest installed fallback."""
    configured = {
        ModelRole.SMALL: settings.model_small,
        ModelRole.DEFAULT: settings.model_default,
        ModelRole.LARGE: settings.model_large,
    }
    for candidate in FALLBACK[role]:
        name = configured[candidate].strip()
        if name and (models_dir / name).is_file():
            return models_dir / name
    return None


def auto_threads() -> int:
    """Physical cores minus 2, at least 2 (CLAUDE.md §5.6)."""
    physical = psutil.cpu_count(logical=False) or max(1, (psutil.cpu_count() or 2) // 2)
    return max(2, physical - 2)


class LlmModule(Module, LlmProvider):
    name = "llm"

    def __init__(self, settings: LlmSection, data_dir: Path, llama_dir: Path | None) -> None:
        self._settings = settings
        self._data_dir = data_dir
        self._llama_dir = llama_dir
        self._binary: Path | None = None
        self._guard: ChildGuard | None = None
        self._server: LlamaServer | None = None
        self._session: aiohttp.ClientSession | None = None
        self._bus: EventBus | None = None
        self._client: LlamaServerClient | None = None
        self._loaded: Path | None = None
        self._loaded_config: LaunchConfig | None = None
        self._lock = asyncio.Lock()
        self._busy = 0
        self._last_used = time.monotonic()
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def models_dir(self) -> Path:
        configured = self._settings.models_dir.strip()
        return Path(configured) if configured else self._data_dir / "models"

    async def start(self, ctx: ModuleContext) -> None:
        binary = self._llama_dir / BINARY if self._llama_dir else None
        if binary is None or not binary.is_file():
            raise EvError(RUNTIME_MISSING_TEXT, f"llama-server not found at {binary}")
        self._binary = binary
        self._bus = ctx.bus
        self._guard = ChildGuard()
        self._server = LlamaServer(self._guard)
        self._session = aiohttp.ClientSession(
            # llama-server closes the connection after a streamed reply; reusing it
            # fails with ServerDisconnectedError (found in Phase 1 testing). A fresh
            # loopback connection per request costs microseconds.
            connector=aiohttp.TCPConnector(force_close=True),
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=5),
            read_bufsize=2**20,
        )
        ctx.bus.subscribe(ConfigChanged, self._on_config)
        self._publish("unloaded", None)
        self._tasks.append(asyncio.create_task(self._idle_loop()))
        if resolve_model(self._settings, self.models_dir, ModelRole.DEFAULT) is not None:
            self._tasks.append(asyncio.create_task(self._warm()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        if self._server is not None:
            await self._server.stop()
        if self._session is not None:
            await self._session.close()
        if self._guard is not None:
            self._guard.close()

    async def acquire(self, role: ModelRole) -> LlmBackend:
        async with self._lock:
            server = self._server
            if server is None or self._session is None or self._binary is None:
                # The registry never started this module: turned off, or the runtime is missing.
                if not self._settings.enabled:
                    raise LlmError("llm_disabled", DISABLED_TEXT, "llm.enabled is false")
                raise LlmError("llm_unavailable", RUNTIME_MISSING_TEXT, "llm module not started")
            model = resolve_model(self._settings, self.models_dir, role)
            if model is None:
                raise LlmError("no_model", NO_MODEL_TEXT, f"no installed model for role {role}")
            config = LaunchConfig(
                binary=self._binary,
                model=model,
                threads=self._settings.threads or auto_threads(),
                context=self._settings.context,
            )
            if self._client is None or not server.running or self._loaded_config != config:
                await self._load(server, self._session, config)
            self._last_used = time.monotonic()
            assert self._client is not None  # noqa: S101 -- set by _load
            return _Tracked(self._client, self)

    async def _load(
        self, server: LlamaServer, session: aiohttp.ClientSession, config: LaunchConfig
    ) -> None:
        self._client = None
        self._publish("loading", config.model.name)
        started = time.monotonic()
        try:
            endpoint = await server.start(config, session, READY_TIMEOUT_S)
        except (ServerStartError, OSError) as exc:
            logger.exception("model load failed", extra={"fields": {"model": config.model.name}})
            self._loaded = self._loaded_config = None
            self._publish("failed", config.model.name, LOAD_FAILED_TEXT)
            raise LlmError("model_load_failed", LOAD_FAILED_TEXT, str(exc)) from exc
        self._client = LlamaServerClient(
            session, endpoint.base_url, endpoint.api_key, config.model.name
        )
        self._loaded, self._loaded_config = config.model, config
        logger.info(
            "model ready",
            extra={
                "fields": {
                    "model": config.model.name,
                    "load_ms": round((time.monotonic() - started) * 1000),
                    "threads": config.threads,
                    "context": config.context,
                    "pid": server.pid,
                }
            },
        )
        self._publish("ready", config.model.name)

    async def _unload(self) -> None:
        async with self._lock:
            if self._server is None or self._client is None:
                return
            model = self._loaded.name if self._loaded else None
            await self._server.stop()
            self._client = None
            self._loaded = self._loaded_config = None
            self._publish("unloaded", model)

    async def _warm(self) -> None:
        try:
            await self.acquire(ModelRole.DEFAULT)
        except LlmError as exc:
            logger.warning("background warm-up failed", extra={"fields": {"code": exc.code}})

    async def _idle_loop(self) -> None:
        while True:
            await asyncio.sleep(IDLE_CHECK_S)
            minutes = self._settings.idle_unload_minutes
            idle_s = time.monotonic() - self._last_used
            if (
                minutes > 0
                and self._busy == 0
                and self._client is not None
                and idle_s >= minutes * 60
            ):
                logger.info("unloading idle model", extra={"fields": {"idle_s": round(idle_s)}})
                await self._unload()

    async def _on_config(self, event: ConfigChanged) -> None:
        if "llm" in event.sections:
            # The next acquire() compares launch configs and reloads if needed.
            self._settings = event.config.llm
            # A model that just became available (e.g. downloaded) warms at once.
            if (
                self._server is not None
                and self._client is None
                and not self._lock.locked()
                and resolve_model(self._settings, self.models_dir, ModelRole.DEFAULT) is not None
            ):
                self._tasks.append(asyncio.create_task(self._warm()))

    def _publish(self, state: str, model: str | None, detail: str | None = None) -> None:
        if self._bus is not None:
            self._bus.publish(LlmStatusChanged(state, model, detail))

    def _enter(self) -> None:
        self._busy += 1

    def _exit(self) -> None:
        self._busy -= 1
        self._last_used = time.monotonic()


class _Tracked(LlmBackend):
    """Marks the module busy while a stream runs, so idle unload never interrupts it."""

    def __init__(self, inner: LlamaServerClient, owner: LlmModule) -> None:
        self._inner = inner
        self._owner = owner

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec],
        thinking: bool,
        max_tokens: int,
    ) -> AsyncIterator[LlmEvent]:
        self._owner._enter()
        try:
            async for event in self._inner.stream(
                messages, tools=tools, thinking=thinking, max_tokens=max_tokens
            ):
                yield event
        finally:
            self._owner._exit()
