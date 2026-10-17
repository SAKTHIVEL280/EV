"""llama-server process: start on a free loopback port with a fresh API key,
wait until healthy, stop (docs/ARCHITECTURE.md §1, CLAUDE.md §3)."""

import asyncio
import contextlib
import logging
import secrets
import socket
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import aiohttp

from ev_core.platform.children import ChildGuard

logger = logging.getLogger(__name__)

HOST: Final = "127.0.0.1"
BINARY: Final = "llama-server.exe" if sys.platform == "win32" else "llama-server"
STOP_GRACE_S: Final = 5.0
HEALTH_POLL_S: Final = 0.25
STDERR_TAIL: Final = 40


@dataclass(frozen=True, slots=True)
class LaunchConfig:
    binary: Path
    model: Path
    threads: int
    context: int


@dataclass(frozen=True, slots=True)
class Endpoint:
    base_url: str
    api_key: str


PROMPT_CACHE_MIB: Final = 512


class ServerStartError(Exception):
    """llama-server exited or never became healthy; ``tail`` is its last stderr lines."""

    def __init__(self, reason: str, tail: str) -> None:
        super().__init__(f"{reason}\n{tail}")
        self.reason = reason
        self.tail = tail


def arguments(config: LaunchConfig, port: int, api_key: str) -> list[str]:
    return [
        str(config.binary),
        "--model", str(config.model),
        "--alias", config.model.name,
        "--host", HOST,
        "--port", str(port),
        "--api-key", api_key,
        # Load without mmap: avoids a second copy of the weights (CLAUDE.md §3).
        "--load-mode", "none",
        "--ctx-size", str(config.context),
        "--threads", str(config.threads),
        # One conversation at a time: the whole context belongs to it.
        "--parallel", "1",
        # q8 KV cache (CLAUDE.md §5.7); flash attention defaults to auto.
        "--cache-type-k", "q8_0",
        "--cache-type-v", "q8_0",
        "--jinja",
        "--no-webui",
        # Saved prompts for other requests (the general and PC variants, agent.intent).
        # Measured: both fit in ~230 MB and switching reads ~16 new tokens instead of
        # the whole prompt (15 s for the PC one). The default cap is 8192 MiB.
        "--cache-ram", str(PROMPT_CACHE_MIB),
    ]  # fmt: skip


def free_port() -> int:
    """A currently free loopback port (the server binds it right after)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


class LlamaServer:
    def __init__(self, guard: ChildGuard) -> None:
        self._guard = guard
        self._process: asyncio.subprocess.Process | None = None
        self._stderr: deque[str] = deque(maxlen=STDERR_TAIL)
        self._drain: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self.running and self._process else None

    async def start(
        self, config: LaunchConfig, session: aiohttp.ClientSession, ready_timeout_s: float
    ) -> Endpoint:
        await self.stop()
        api_key = secrets.token_hex(32)
        port = free_port()
        self._stderr.clear()
        process = await asyncio.create_subprocess_exec(
            *self._guard.command(arguments(config, port, api_key)),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            **self._guard.spawn_kwargs(),
        )
        self._process = process
        self._guard.adopt(process.pid)
        self._drain = asyncio.create_task(self._drain_stderr(process))
        logger.info(
            "llama-server started",
            extra={"fields": {"pid": process.pid, "model": config.model.name}},
        )
        endpoint = Endpoint(f"http://{HOST}:{port}", api_key)
        try:
            await asyncio.wait_for(self._wait_healthy(process, session, endpoint), ready_timeout_s)
        except TimeoutError as exc:
            await self.stop()
            raise ServerStartError("not healthy in time", self.tail()) from exc
        except ServerStartError:
            await self.stop()
            raise
        return endpoint

    async def stop(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), STOP_GRACE_S)
            except TimeoutError:
                process.kill()
                await process.wait()
            logger.info("llama-server stopped", extra={"fields": {"pid": process.pid}})
        if self._drain is not None:
            self._drain.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drain
            self._drain = None

    def tail(self) -> str:
        return "\n".join(self._stderr)

    async def _wait_healthy(
        self,
        process: asyncio.subprocess.Process,
        session: aiohttp.ClientSession,
        endpoint: Endpoint,
    ) -> None:
        url = f"{endpoint.base_url}/health"
        while True:
            if process.returncode is not None:
                raise ServerStartError(f"exited with code {process.returncode}", self.tail())
            with contextlib.suppress(aiohttp.ClientError):
                async with session.get(url) as response:
                    if response.status == 200:
                        return
            await asyncio.sleep(HEALTH_POLL_S)

    async def _drain_stderr(self, process: asyncio.subprocess.Process) -> None:
        # llama-server logs a lot to stderr; it must be read or the pipe fills and it blocks.
        assert process.stderr is not None  # noqa: S101 -- created with stderr=PIPE
        while line := await process.stderr.readline():
            text = line.decode("utf-8", errors="replace").rstrip()
            self._stderr.append(text)
            logger.debug("llama-server", extra={"fields": {"line": text}})
