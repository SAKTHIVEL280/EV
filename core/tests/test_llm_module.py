"""llm module lifecycle against a fake llama-server (same flags and HTTP API)."""

import asyncio
import logging
import sys
import time
from pathlib import Path

import psutil
import pytest

import ev_core.llm as llm_module
from ev_core.bus import EventBus
from ev_core.config import ConfigChanged, EvConfig, LlmSection
from ev_core.errors import EvError
from ev_core.interfaces.events import LlmStatusChanged
from ev_core.interfaces.llm import LlmError, ModelRole, TextDelta
from ev_core.llm import LlmModule, auto_threads, resolve_model
from ev_core.modules import ModuleContext

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake server is a POSIX script")

FAKE_SERVER = f"""#!{sys.executable}
import argparse, json, sys
from aiohttp import web
p = argparse.ArgumentParser()
for flag in ("--model", "--alias", "--host", "--port", "--api-key", "--load-mode", "--ctx-size",
             "--threads", "--parallel", "--cache-type-k", "--cache-type-v", "--cache-ram"):
    p.add_argument(flag)
p.add_argument("--jinja", action="store_true")
p.add_argument("--no-webui", action="store_true")
a = p.parse_args()
if a.model.endswith("fail.gguf"):
    print("error: failed to load model", file=sys.stderr)
    sys.exit(3)

async def health(request):
    return web.Response(text="ok")

async def chat(request):
    if request.headers.get("Authorization") != "Bearer " + a.api_key:
        return web.Response(status=401)
    response = web.StreamResponse(headers={{"Content-Type": "text/event-stream"}})
    await response.prepare(request)
    chunk = {{"choices": [{{"delta": {{"content": a.alias}}, "finish_reason": "stop"}}]}}
    await response.write(("data: " + json.dumps(chunk) + "\\n\\ndata: [DONE]\\n\\n").encode())
    return response

app = web.Application()
app.router.add_get("/health", health)
app.router.add_post("/v1/chat/completions", chat)
web.run_app(app, host=a.host, port=int(a.port), print=None)
"""


@pytest.fixture
def runtime(tmp_path: Path) -> Path:
    folder = tmp_path / "llama"
    folder.mkdir()
    binary = folder / "llama-server"
    binary.write_text(FAKE_SERVER)
    binary.chmod(0o755)
    models = tmp_path / "models"
    models.mkdir()
    for name in ("a.gguf", "b.gguf", "fail.gguf"):
        (models / name).write_bytes(b"")
    return folder


class Statuses:
    def __init__(self, bus: EventBus) -> None:
        self.seen: list[tuple[str, str | None]] = []
        self.unloaded = asyncio.Event()
        bus.subscribe(LlmStatusChanged, self._add)

    async def _add(self, event: LlmStatusChanged) -> None:
        self.seen.append((event.state, event.model))
        if event.state == "unloaded" and event.model is not None:
            self.unloaded.set()


async def started(runtime: Path, settings: LlmSection) -> tuple[LlmModule, EventBus, Statuses]:
    bus = EventBus()
    statuses = Statuses(bus)
    module = LlmModule(settings, runtime.parent, runtime)
    await module.start(ModuleContext(bus=bus, logger=logging.getLogger("t")))
    return module, bus, statuses


async def reply(module: LlmModule, role: ModelRole = ModelRole.DEFAULT) -> str:
    backend = await module.acquire(role)
    events = [e async for e in backend.stream([], tools=[], thinking=False, max_tokens=8)]
    return "".join(e.text for e in events if isinstance(e, TextDelta))


def test_resolve_model_fallbacks(tmp_path: Path) -> None:
    (tmp_path / "s.gguf").write_bytes(b"")
    (tmp_path / "d.gguf").write_bytes(b"")
    settings = LlmSection(model_small="s.gguf", model_default="d.gguf", model_large="missing.gguf")
    assert resolve_model(settings, tmp_path, ModelRole.SMALL) == tmp_path / "s.gguf"
    assert resolve_model(settings, tmp_path, ModelRole.LARGE) == tmp_path / "d.gguf"
    only_small = LlmSection(model_small="s.gguf")
    assert resolve_model(only_small, tmp_path, ModelRole.LARGE) == tmp_path / "s.gguf"
    assert resolve_model(LlmSection(), tmp_path, ModelRole.DEFAULT) is None


def test_auto_threads_at_least_two() -> None:
    assert auto_threads() >= 2


async def test_missing_runtime_fails_start(tmp_path: Path) -> None:
    module = LlmModule(LlmSection(), tmp_path, tmp_path / "nowhere")
    with pytest.raises(EvError) as caught:
        await module.start(ModuleContext(bus=EventBus(), logger=logging.getLogger("t")))
    assert caught.value.user_message == llm_module.RUNTIME_MISSING_TEXT


async def test_acquire_without_start_explains_why(tmp_path: Path) -> None:
    with pytest.raises(LlmError) as off:
        await LlmModule(LlmSection(enabled=False), tmp_path, None).acquire(ModelRole.DEFAULT)
    assert off.value.code == "llm_disabled"
    with pytest.raises(LlmError) as missing:
        await LlmModule(LlmSection(), tmp_path, None).acquire(ModelRole.DEFAULT)
    assert missing.value.code == "llm_unavailable"


async def test_no_model_configured(runtime: Path) -> None:
    module, _, _ = await started(runtime, LlmSection(models_dir=str(runtime.parent / "models")))
    with pytest.raises(LlmError) as caught:
        await module.acquire(ModelRole.DEFAULT)
    assert caught.value.code == "no_model"
    await module.stop()


async def test_load_reuse_reload_and_crash_recovery(runtime: Path) -> None:
    models = str(runtime.parent / "models")
    settings = LlmSection(models_dir=models, model_default="a.gguf", threads=2)
    module, bus, statuses = await started(runtime, settings)
    assert await reply(module) == "a.gguf"
    first_pid = module._server.pid if module._server else None
    assert await reply(module) == "a.gguf"
    assert (module._server.pid if module._server else None) == first_pid

    # Config change: the next acquire reloads with the new model.
    new = EvConfig(llm=LlmSection(models_dir=models, model_default="b.gguf", threads=2))
    bus.publish(ConfigChanged(new, frozenset({"llm"}), ()))
    await bus.drain()
    assert await reply(module) == "b.gguf"

    # Crash: the next acquire starts a new server.
    assert module._server is not None
    assert module._server.pid is not None
    psutil.Process(module._server.pid).kill()
    await asyncio.sleep(0.2)
    assert await reply(module) == "b.gguf"

    await module.stop()
    await bus.drain()
    loads = [s for s in statuses.seen if s[0] in ("loading", "ready")]
    assert loads[:2] == [("loading", "a.gguf"), ("ready", "a.gguf")]
    assert ("ready", "b.gguf") in loads


async def test_load_failure_reports_failed(runtime: Path) -> None:
    settings = LlmSection(
        models_dir=str(runtime.parent / "models"), model_default="fail.gguf", threads=2
    )
    module, bus, statuses = await started(runtime, settings)
    await bus.drain()  # background warm-up attempt
    with pytest.raises(LlmError) as caught:
        await module.acquire(ModelRole.DEFAULT)
    assert caught.value.code == "model_load_failed"
    assert "failed to load model" in caught.value.detail
    await bus.drain()
    assert ("failed", "fail.gguf") in statuses.seen
    await module.stop()


async def test_idle_unload_waits_for_streams_to_finish(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm_module, "IDLE_CHECK_S", 0.05)
    settings = LlmSection(
        models_dir=str(runtime.parent / "models"),
        model_default="a.gguf",
        threads=2,
        idle_unload_minutes=1,
    )
    module, _bus, statuses = await started(runtime, settings)
    await reply(module)
    module._enter()
    module._last_used = time.monotonic() - 120
    await asyncio.sleep(0.3)
    assert module._server is not None
    assert module._server.running
    module._exit()
    module._last_used = time.monotonic() - 120
    await asyncio.wait_for(statuses.unloaded.wait(), 5)
    assert not module._server.running
    assert statuses.seen[-1] == ("unloaded", "a.gguf")
    await module.stop()
