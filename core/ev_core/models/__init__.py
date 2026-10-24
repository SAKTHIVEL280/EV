"""The `models` module: offers the catalog's models and downloads them
(docs/FEATURES.md F-403).

State for every catalog model is published as ``ModelsStateChanged`` on
request, on every download step (throttled by the downloader) and when the
models folder changes. A finished download publishes ``ModelInstalled``; the
composition root then fills the model's empty config slot.
"""

import asyncio
import contextlib
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import aiohttp

from ev_core import __version__
from ev_core.bus import EventBus
from ev_core.config import ConfigChanged, LlmSection
from ev_core.interfaces.events import (
    ModelCancelRequested,
    ModelDownloadRequested,
    ModelInfo,
    ModelInstalled,
    ModelsGetRequested,
    ModelsStateChanged,
    VoicePackInfo,
)
from ev_core.models.catalog import Catalog, CatalogModel, VoicePack
from ev_core.models.downloader import WRITE_TEXT, DownloadError, Progress, download, part_path
from ev_core.modules import Module, ModuleContext

logger = logging.getLogger(__name__)

USER_AGENT: Final = f"EV/{__version__} (+https://github.com/SAKTHIVEL280/EV)"
CONNECT_TIMEOUT_S: Final = 15
READ_TIMEOUT_S: Final = 60

SessionFactory = Callable[[], aiohttp.ClientSession]


def _default_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT},
        timeout=aiohttp.ClientTimeout(
            total=None, sock_connect=CONNECT_TIMEOUT_S, sock_read=READ_TIMEOUT_S
        ),
        # Honour HTTPS_PROXY and similar, like the rest of the system.
        trust_env=True,
    )


@dataclass(frozen=True, slots=True)
class _Live:
    """A download in progress, or the last one's failure."""

    state: str
    received_bytes: int = 0
    bytes_per_second: int = 0
    error: str | None = None


def models_folder(settings: LlmSection, data_dir: Path) -> Path:
    configured = settings.models_dir.strip()
    return Path(configured) if configured else data_dir / "models"


def pack_folder(models: Path, pack: VoicePack) -> Path:
    """Where an installed voice pack lives (the voice module reads it from here)."""
    return models / "voice" / pack.folder


def pack_part_folder(models: Path, pack: VoicePack) -> Path:
    """Where a pack downloads; renamed to ``pack_folder`` once every file is verified."""
    return models / "voice" / f"{pack.folder}.part"


class ModelsModule(Module):
    name = "models"

    def __init__(
        self,
        settings: LlmSection,
        data_dir: Path,
        catalog: Catalog,
        session_factory: SessionFactory = _default_session,
    ) -> None:
        self._settings = settings
        self._data_dir = data_dir
        self._catalog = catalog
        self._session_factory = session_factory
        self._session: aiohttp.ClientSession | None = None
        self._bus: EventBus | None = None
        self._live: dict[str, _Live] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def folder(self) -> Path:
        return models_folder(self._settings, self._data_dir)

    async def start(self, ctx: ModuleContext) -> None:
        self._bus = ctx.bus
        ctx.bus.subscribe(ModelsGetRequested, self._on_get)
        ctx.bus.subscribe(ModelDownloadRequested, self._on_download)
        ctx.bus.subscribe(ModelCancelRequested, self._on_cancel)
        ctx.bus.subscribe(ConfigChanged, self._on_config)

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._session is not None:
            await self._session.close()
            self._session = None

    def state(self, reply_to: str | None = None) -> ModelsStateChanged:
        folder = self.folder
        return ModelsStateChanged(
            models_dir=str(folder),
            models=tuple(self._info(m, folder) for m in self._catalog.models),
            reply_to=reply_to,
            other_files=self._other_files(folder),
            voice=tuple(self._pack_info(p, folder) for p in self._catalog.voice),
        )

    def _other_files(self, folder: Path) -> tuple[str, ...]:
        """Model files the user put in the folder themselves (picker, F-415).
        Vision projectors (mmproj) are companions, not models."""
        known = {m.file for m in self._catalog.models}
        try:
            names = sorted(p.name for p in folder.glob("*.gguf") if p.is_file())
        except OSError:
            return ()
        return tuple(n for n in names if n not in known and not n.lower().startswith("mmproj"))

    def _info(self, model: CatalogModel, folder: Path) -> ModelInfo:
        live = self._live.get(model.id)
        if model.id in self._tasks and live is not None:
            state, received, speed, error = (
                live.state,
                live.received_bytes,
                live.bytes_per_second,
                None,
            )
        elif _installed(folder / model.file, model.size_bytes):
            state, received, speed, error = "installed", model.size_bytes, 0, None
        else:
            partial = _size(part_path(folder / model.file))
            failed = live is not None and live.state == "failed"
            state = "failed" if failed else ("partial" if partial else "available")
            received, speed = partial, 0
            error = live.error if failed and live is not None else None
        return ModelInfo(
            id=model.id,
            name=model.name,
            summary=model.summary,
            role=model.role.value,
            recommended=model.recommended,
            file=model.file,
            size_bytes=model.size_bytes,
            state=state,
            received_bytes=received,
            bytes_per_second=speed,
            error=error,
        )

    def _pack_info(self, pack: VoicePack, folder: Path) -> VoicePackInfo:
        live = self._live.get(pack.id)
        if pack.id in self._tasks and live is not None:
            state, received, speed, error = (
                live.state,
                live.received_bytes,
                live.bytes_per_second,
                None,
            )
        elif _pack_installed(folder, pack):
            state, received, speed, error = "installed", pack.size_bytes, 0, None
        else:
            partial = _pack_received(pack_part_folder(folder, pack), pack)
            failed = live is not None and live.state == "failed"
            state = "failed" if failed else ("partial" if partial else "available")
            received, speed = partial, 0
            error = live.error if failed and live is not None else None
        return VoicePackInfo(
            id=pack.id,
            name=pack.name,
            summary=pack.summary,
            kind=pack.kind,
            option=pack.option,
            size_bytes=pack.size_bytes,
            state=state,
            received_bytes=received,
            bytes_per_second=speed,
            error=error,
        )

    def _publish(self, reply_to: str | None = None) -> None:
        if self._bus is not None:
            self._bus.publish(self.state(reply_to))

    async def _on_get(self, event: ModelsGetRequested) -> None:
        self._publish(event.request_id)

    async def _on_download(self, event: ModelDownloadRequested) -> None:
        model = self._catalog.get(event.model_id)
        pack = self._catalog.pack(event.model_id)
        if pack is not None:
            if pack.id not in self._tasks and not _pack_installed(self.folder, pack):
                received = _pack_received(pack_part_folder(self.folder, pack), pack)
                self._live[pack.id] = _Live("downloading", received)
                self._tasks[pack.id] = asyncio.create_task(self._run_pack(pack))
            self._publish(event.request_id)
            return
        if model is None:
            logger.warning("unknown model requested", extra={"fields": {"model": event.model_id}})
        elif event.model_id not in self._tasks and not _installed(
            self.folder / model.file, model.size_bytes
        ):
            # Show what is already on disk while the partial file is re-hashed.
            partial = _size(part_path(self.folder / model.file))
            self._live[model.id] = _Live("downloading", partial)
            self._tasks[model.id] = asyncio.create_task(self._run(model))
        self._publish(event.request_id)

    async def _on_cancel(self, event: ModelCancelRequested) -> None:
        task = self._tasks.get(event.model_id)
        if task is not None:
            task.cancel()
        else:
            self._publish(event.request_id)

    async def _on_config(self, event: ConfigChanged) -> None:
        if "llm" not in event.sections:
            return
        before = self.folder
        self._settings = event.config.llm
        if self.folder != before:
            self._publish()

    async def _run(self, model: CatalogModel) -> None:
        def on_progress(progress: Progress) -> None:
            self._live[model.id] = _Live(
                progress.phase, progress.received_bytes, round(progress.bytes_per_second)
            )
            self._publish()

        try:
            if self._session is None:
                self._session = self._session_factory()
            path = await download(self._session, model, self.folder, on_progress)
        except asyncio.CancelledError:
            logger.info("download stopped", extra={"fields": {"model": model.id}})
            self._live.pop(model.id, None)
            raise
        except DownloadError as exc:
            logger.warning(
                "download failed",
                extra={"fields": {"model": model.id, "code": exc.code, "detail": exc.detail}},
            )
            self._live[model.id] = replace(_Live("failed"), error=exc.user_message)
        else:
            self._live.pop(model.id, None)
            if self._bus is not None:
                self._bus.publish(ModelInstalled(model.id, path.name, model.role.value))
        finally:
            self._tasks.pop(model.id, None)
            self._publish()

    async def _run_pack(self, pack: VoicePack) -> None:
        part = pack_part_folder(self.folder, pack)
        try:
            if self._session is None:
                self._session = self._session_factory()
            for file in pack.files:
                if _installed(part / file.path, file.size_bytes):
                    continue
                done = sum(
                    f.size_bytes for f in pack.files if _installed(part / f.path, f.size_bytes)
                )

                def on_progress(progress: Progress, done: int = done) -> None:
                    phase = "verifying" if progress.phase == "verifying" else "downloading"
                    self._live[pack.id] = _Live(
                        phase, done + progress.received_bytes, round(progress.bytes_per_second)
                    )
                    self._publish()

                await download(self._session, file, part, on_progress)
            final = pack_folder(self.folder, pack)
            await asyncio.to_thread(_replace_folder, part, final)
        except asyncio.CancelledError:
            logger.info("download stopped", extra={"fields": {"model": pack.id}})
            self._live.pop(pack.id, None)
            raise
        except DownloadError as exc:
            logger.warning(
                "download failed",
                extra={"fields": {"model": pack.id, "code": exc.code, "detail": exc.detail}},
            )
            self._live[pack.id] = replace(_Live("failed"), error=exc.user_message)
        except OSError as exc:
            logger.warning(
                "download failed", extra={"fields": {"model": pack.id, "detail": str(exc)}}
            )
            self._live[pack.id] = replace(_Live("failed"), error=WRITE_TEXT)
        else:
            self._live.pop(pack.id, None)
            logger.info("voice pack installed", extra={"fields": {"pack": pack.id}})
        finally:
            self._tasks.pop(pack.id, None)
            self._publish()


def _replace_folder(part: Path, final: Path) -> None:
    if final.exists():
        shutil.rmtree(final)
    part.rename(final)


def _pack_installed(models: Path, pack: VoicePack) -> bool:
    folder = pack_folder(models, pack)
    return all(_installed(folder / f.path, f.size_bytes) for f in pack.files)


def _pack_received(part: Path, pack: VoicePack) -> int:
    """Bytes already on disk in a pack's download folder (whole and partial files)."""
    total = 0
    for f in pack.files:
        path = part / f.path
        total += f.size_bytes if _installed(path, f.size_bytes) else _size(part_path(path))
    return total


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _installed(path: Path, size: int) -> bool:
    return _size(path) == size
