"""Model catalog, downloader and module (docs/FEATURES.md F-403).

The downloader runs against a real local HTTP server that can honour or
ignore Range requests, drop the connection, serve damaged data or be slow.
"""

import asyncio
import hashlib
import json
import logging
import shutil
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web

from ev_core.app import fill_model_slot
from ev_core.bus import EventBus
from ev_core.config import LlmSection
from ev_core.interfaces.events import (
    ModelCancelRequested,
    ModelDownloadRequested,
    ModelInstalled,
    ModelsGetRequested,
    ModelsStateChanged,
)
from ev_core.interfaces.llm import ModelRole
from ev_core.models import ModelsModule
from ev_core.models.catalog import Catalog, CatalogModel, load_catalog
from ev_core.models.downloader import DownloadError, Progress, download, part_path
from ev_core.modules import ModuleContext

DATA = bytes(range(256)) * 4096  # 1 MiB, not all one byte value
SHA = hashlib.sha256(DATA).hexdigest()


@dataclass
class Server:
    """Serves DATA at /model.gguf with switchable behaviour."""

    honour_range: bool = True
    drop_after: int | None = None
    """Close the connection after this many body bytes (first request only)."""
    body: bytes = DATA
    chunk_delay_s: float = 0.0
    status: int = 200
    ranges: list[str | None] = field(default_factory=list)
    base_url: str = ""

    async def handle(self, request: web.Request) -> web.StreamResponse:
        header = request.headers.get("Range")
        self.ranges.append(header)
        if self.status != 200:
            return web.Response(status=self.status)
        start = 0
        if header and self.honour_range:
            start = int(header.removeprefix("bytes=").removesuffix("-"))
        body = self.body[start:]
        response = web.StreamResponse(status=206 if start else 200)
        response.content_length = len(body)
        await response.prepare(request)
        sent = 0
        step = 64 * 1024
        for offset in range(0, len(body), step):
            if self.drop_after is not None and sent >= self.drop_after:
                self.drop_after = None
                assert request.transport is not None
                request.transport.close()
                return response
            await response.write(body[offset : offset + step])
            sent += step
            if self.chunk_delay_s:
                await asyncio.sleep(self.chunk_delay_s)
        await response.write_eof()
        return response


@pytest_asyncio.fixture
async def server() -> AsyncIterator[Server]:
    state = Server()
    app = web.Application()
    app.router.add_get("/model.gguf", state.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    state.base_url = f"http://127.0.0.1:{port}"
    yield state
    await runner.cleanup()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


def model(server: Server, **changes: Any) -> CatalogModel:
    # model_construct skips the huggingface.co rule, so tests can use the local server.
    values: dict[str, Any] = {
        "id": "test-1b",
        "name": "Test 1B",
        "summary": "Test model.",
        "role": ModelRole.DEFAULT,
        "recommended": True,
        "file": "Test-1B.gguf",
        "url": f"{server.base_url}/model.gguf",
        "size_bytes": len(DATA),
        "sha256": SHA,
        "license": "Apache-2.0",
    }
    values.update(changes)
    return CatalogModel.model_construct(**values)


def collect() -> tuple[list[Progress], Callable[[Progress], None]]:
    seen: list[Progress] = []
    return seen, seen.append


# --- downloader -------------------------------------------------------------


async def test_full_download_is_verified_and_renamed(
    server: Server, session: aiohttp.ClientSession, tmp_path: Path
) -> None:
    seen, on_progress = collect()
    path = await download(session, model(server), tmp_path, on_progress)
    assert path == tmp_path / "Test-1B.gguf"
    assert path.read_bytes() == DATA
    assert not part_path(path).exists()
    assert server.ranges == [None]
    assert seen[0].phase == "downloading"
    assert seen[-1] == Progress("verifying", len(DATA), len(DATA), 0.0)


async def test_resumes_from_a_partial_file(
    server: Server, session: aiohttp.ClientSession, tmp_path: Path
) -> None:
    part_path(tmp_path / "Test-1B.gguf").write_bytes(DATA[:300_000])
    path = await download(session, model(server), tmp_path, lambda _: None)
    assert path.read_bytes() == DATA
    assert server.ranges == ["bytes=300000-"]


async def test_server_ignoring_range_restarts_from_zero(
    server: Server, session: aiohttp.ClientSession, tmp_path: Path
) -> None:
    server.honour_range = False
    part_path(tmp_path / "Test-1B.gguf").write_bytes(DATA[:300_000])
    path = await download(session, model(server), tmp_path, lambda _: None)
    assert path.read_bytes() == DATA


async def test_dropped_connection_is_retried_and_resumed(
    server: Server, session: aiohttp.ClientSession, tmp_path: Path
) -> None:
    # Whether the retry resumes or restarts depends on how much arrived before
    # the drop (a partial 1 MiB read is discarded); either way the file is right.
    server.drop_after = 256 * 1024
    path = await download(session, model(server), tmp_path, lambda _: None, retry_delays=(0.0,))
    assert path.read_bytes() == DATA
    assert len(server.ranges) == 2


async def test_retries_run_out(
    server: Server, session: aiohttp.ClientSession, tmp_path: Path
) -> None:
    server.status = 503
    with pytest.raises(DownloadError) as caught:
        await download(session, model(server), tmp_path, lambda _: None, retry_delays=(0.0,))
    assert caught.value.code == "network"
    assert len(server.ranges) == 2


async def test_client_error_is_not_retried(
    server: Server, session: aiohttp.ClientSession, tmp_path: Path
) -> None:
    server.status = 404
    with pytest.raises(DownloadError) as caught:
        await download(session, model(server), tmp_path, lambda _: None, retry_delays=(0.0,))
    assert caught.value.code == "network"
    assert caught.value.user_message.startswith("Couldn't reach Hugging Face")
    assert len(server.ranges) == 1


async def test_damaged_file_is_deleted(
    server: Server, session: aiohttp.ClientSession, tmp_path: Path
) -> None:
    server.body = DATA[:-1] + b"\x00"
    with pytest.raises(DownloadError) as caught:
        await download(session, model(server), tmp_path, lambda _: None)
    assert caught.value.code == "damaged"
    assert caught.value.user_message == "The download was damaged. Try again."
    assert not part_path(tmp_path / "Test-1B.gguf").exists()
    assert not (tmp_path / "Test-1B.gguf").exists()


async def test_not_enough_disk_space(
    server: Server,
    session: aiohttp.ClientSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @dataclass
    class Usage:
        free: int

    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(free=1000))
    with pytest.raises(DownloadError) as caught:
        await download(session, model(server), tmp_path, lambda _: None)
    assert caught.value.code == "disk_full"
    assert caught.value.user_message == "Not enough free space. EV needs 0.3 GB more."
    assert server.ranges == []


async def test_cancel_keeps_the_partial_file(
    server: Server, session: aiohttp.ClientSession, tmp_path: Path
) -> None:
    server.chunk_delay_s = 0.05
    task = asyncio.create_task(download(session, model(server), tmp_path, lambda _: None))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    partial = part_path(tmp_path / "Test-1B.gguf").stat().st_size
    assert 0 < partial < len(DATA)


# --- catalog -----------------------------------------------------------------


def test_bundled_catalog_is_valid() -> None:
    catalog = load_catalog()
    assert {m.role for m in catalog.models} == set(ModelRole)
    recommended = [m for m in catalog.models if m.recommended]
    assert [m.id for m in recommended] == ["qwen3.5-4b"]
    for m in catalog.models:
        assert m.url.startswith("https://huggingface.co/unsloth/")
        assert m.url.endswith("/" + m.file)


def _catalog_text(**changes: Any) -> str:
    entry = load_catalog().models[0].model_dump(mode="json") | changes
    return json.dumps({"manifest_version": 1, "models": [entry]})


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "https://example.com/x/resolve/abc/Q.gguf"},
        {"url": "http://huggingface.co/x/resolve/abc/Q.gguf"},
        {"url": "https://huggingface.co/x/resolve/main/Q.gguf"},
        {"sha256": "ABC"},
        {"file": "../evil.gguf"},
        {"file": "model.exe"},
        {"recommended": False},
    ],
)
def test_catalog_rejects_unsafe_entries(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="validation error"):
        load_catalog(_catalog_text(**changes))


# --- module ------------------------------------------------------------------


def catalog_for(server: Server) -> Catalog:
    return Catalog.model_construct(manifest_version=1, models=(model(server),))


class Recorder:
    def __init__(self, bus: EventBus) -> None:
        self.states: list[ModelsStateChanged] = []
        self.installed: list[ModelInstalled] = []
        self._changed = asyncio.Event()
        bus.subscribe(ModelsStateChanged, self._on_state)
        bus.subscribe(ModelInstalled, self._on_installed)

    async def _on_state(self, event: ModelsStateChanged) -> None:
        self.states.append(event)
        self._changed.set()

    async def _on_installed(self, event: ModelInstalled) -> None:
        self.installed.append(event)
        self._changed.set()

    @property
    def last(self) -> str | None:
        return self.states[-1].models[0].state if self.states else None

    async def wait_for(self, predicate: Callable[[], bool]) -> None:
        async with asyncio.timeout(5):
            while not predicate():
                self._changed.clear()
                await self._changed.wait()


async def started(server: Server, tmp_path: Path, bus: EventBus) -> tuple[ModelsModule, Recorder]:
    recorder = Recorder(bus)
    module = ModelsModule(LlmSection(), tmp_path, catalog_for(server))
    await module.start(ModuleContext(bus=bus, logger=logging.getLogger("models")))
    return module, recorder


async def test_module_downloads_and_reports_installed(server: Server, tmp_path: Path) -> None:
    bus = EventBus()
    module, rec = await started(server, tmp_path, bus)
    bus.publish(ModelsGetRequested("r1"))
    await bus.drain()
    first = rec.states[-1]
    assert first.reply_to == "r1"
    assert first.models_dir == str(tmp_path / "models")
    assert first.models[0].state == "available"

    bus.publish(ModelDownloadRequested("r2", "test-1b"))
    await rec.wait_for(lambda: bool(rec.installed))
    await bus.drain()
    assert rec.installed == [ModelInstalled("test-1b", "Test-1B.gguf", "default")]
    assert rec.last == "installed"
    seen = {m.state for s in rec.states for m in s.models}
    assert {"downloading", "verifying", "installed"} <= seen
    await module.stop()


async def test_module_cancel_leaves_a_resumable_partial(server: Server, tmp_path: Path) -> None:
    server.chunk_delay_s = 0.05
    bus = EventBus()
    module, rec = await started(server, tmp_path, bus)
    bus.publish(ModelDownloadRequested("r1", "test-1b"))
    await rec.wait_for(lambda: any(m.received_bytes > 0 for s in rec.states for m in s.models))
    bus.publish(ModelCancelRequested("r2", "test-1b"))
    await rec.wait_for(lambda: rec.last == "partial")
    assert not rec.installed
    await module.stop()


async def test_module_reports_failure_with_the_user_message(server: Server, tmp_path: Path) -> None:
    server.body = b"x" * len(DATA)
    bus = EventBus()
    module, rec = await started(server, tmp_path, bus)
    bus.publish(ModelDownloadRequested("r1", "test-1b"))
    await rec.wait_for(lambda: rec.last == "failed")
    assert rec.states[-1].models[0].error == "The download was damaged. Try again."
    await module.stop()


async def test_module_ignores_unknown_and_installed_models(server: Server, tmp_path: Path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "Test-1B.gguf").write_bytes(DATA)
    bus = EventBus()
    module, rec = await started(server, tmp_path, bus)
    bus.publish(ModelDownloadRequested("r1", "nope"))
    bus.publish(ModelDownloadRequested("r2", "test-1b"))
    await bus.drain()
    assert server.ranges == []
    assert not rec.installed
    assert rec.last == "installed"
    await module.stop()


# --- config slot ---------------------------------------------------------------


class FakeSettings:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool | int | str]] = []

    async def set_value(self, section: str, key: str, value: bool | int | str) -> None:
        self.calls.append((section, key, value))


async def test_installed_model_fills_only_an_empty_slot() -> None:
    settings = FakeSettings()
    event = ModelInstalled("qwen3.5-4b", "Qwen3.5-4B-Q4_K_M.gguf", "default")
    await fill_model_slot(event, LlmSection(), settings)  # type: ignore[arg-type]
    assert settings.calls == [("llm", "model_default", "Qwen3.5-4B-Q4_K_M.gguf")]

    settings = FakeSettings()
    chosen = LlmSection(model_default="Mine.gguf")
    await fill_model_slot(event, chosen, settings)  # type: ignore[arg-type]
    assert settings.calls == []
