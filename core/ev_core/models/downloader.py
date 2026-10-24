"""Resumable, verified model download (docs/FEATURES.md F-403).

- Data goes to ``<file>.part`` next to the final file; a later call resumes
  from it with an HTTP Range request (the existing bytes are hashed first).
- A dropped connection is retried, resuming each time; a server that ignores
  the Range request restarts the file from zero.
- The finished file must match the catalog's size and SHA-256, then it is
  renamed into place atomically. A damaged file is deleted.
- Disk writes and hashing run in a worker thread, never on the event loop.
- Cancelling the task keeps the partial file for a later resume.
"""

import asyncio
import contextlib
import hashlib
import logging
import os
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final, Literal, Protocol

import aiohttp

from ev_core.errors import EvError


class Downloadable(Protocol):
    """A pinned file: a catalog model or one file of a voice pack."""

    @property
    def id(self) -> str: ...
    @property
    def file(self) -> str: ...
    @property
    def url(self) -> str: ...
    @property
    def size_bytes(self) -> int: ...
    @property
    def sha256(self) -> str: ...


logger = logging.getLogger(__name__)

CHUNK_BYTES: Final = 1 << 20
PROGRESS_INTERVAL_S: Final = 0.25
DISK_MARGIN_BYTES: Final = 256 * 1024 * 1024
RETRY_DELAYS_S: Final = (1.0, 2.0, 5.0)
SPEED_SMOOTHING: Final = 0.3

DISK_FULL_TEXT: Final = "Not enough free space. EV needs {gb} GB more."
NETWORK_TEXT: Final = "Couldn't reach Hugging Face. Check the connection and try again."
DAMAGED_TEXT: Final = "The download was damaged. Try again."
WRITE_TEXT: Final = "Couldn't save the model. Check the models folder in Settings."

Phase = Literal["downloading", "verifying"]


class DownloadError(EvError):
    def __init__(self, code: str, user_message: str, detail: str) -> None:
        super().__init__(user_message, detail)
        self.code = code


@dataclass(slots=True)
class _Partial:
    """What is on disk in the .part file: its byte count and running hash.
    Updated with every chunk written, so a dropped connection can never leave
    the count, the hash and the file out of step (found by a test)."""

    digest: "hashlib._Hash"
    received: int

    def reset(self) -> None:
        self.digest = hashlib.sha256()
        self.received = 0


@dataclass(frozen=True, slots=True)
class Progress:
    phase: Phase
    received_bytes: int
    total_bytes: int
    bytes_per_second: float


def part_path(final: Path) -> Path:
    return final.with_name(final.name + ".part")


def _hash_file(path: Path) -> tuple["hashlib._Hash", int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return digest, size


def _open(path: Path, *, append: bool) -> BinaryIO:
    return path.open("ab") if append else path.open("wb")


def _write(f: BinaryIO, partial: _Partial, chunk: bytes) -> None:
    f.write(chunk)
    partial.digest.update(chunk)
    partial.received += len(chunk)


def _finish(f: BinaryIO) -> None:
    f.flush()
    os.fsync(f.fileno())
    f.close()


class _Reporter:
    """Throttled progress with a smoothed speed."""

    def __init__(self, total: int, on_progress: Callable[[Progress], None]) -> None:
        self._total = total
        self._on_progress = on_progress
        self._last_time = time.monotonic()
        self._last_bytes = 0
        self._speed = 0.0

    def start(self, received: int) -> None:
        self._last_time = time.monotonic()
        self._last_bytes = received
        self._on_progress(Progress("downloading", received, self._total, self._speed))

    def update(self, received: int) -> None:
        now = time.monotonic()
        elapsed = now - self._last_time
        if elapsed < PROGRESS_INTERVAL_S and received < self._total:
            return
        instant = (received - self._last_bytes) / elapsed if elapsed > 0 else 0.0
        self._speed = (
            instant
            if self._speed == 0
            else SPEED_SMOOTHING * instant + (1 - SPEED_SMOOTHING) * self._speed
        )
        self._last_time, self._last_bytes = now, received
        self._on_progress(Progress("downloading", received, self._total, self._speed))

    def verifying(self) -> None:
        self._on_progress(Progress("verifying", self._total, self._total, 0.0))


async def download(
    session: aiohttp.ClientSession,
    model: Downloadable,
    folder: Path,
    on_progress: Callable[[Progress], None],
    *,
    retry_delays: Sequence[float] = RETRY_DELAYS_S,
) -> Path:
    """Download ``model`` into ``folder`` and return the verified file's path."""
    final = folder / model.file
    part = part_path(final)
    try:
        await asyncio.to_thread(final.parent.mkdir, parents=True, exist_ok=True)
        partial = _Partial(hashlib.sha256(), 0)
        if part.exists():
            partial.digest, partial.received = await asyncio.to_thread(_hash_file, part)
        if partial.received > model.size_bytes:
            await asyncio.to_thread(part.unlink)
            partial.reset()
        free = (await asyncio.to_thread(shutil.disk_usage, folder)).free
    except OSError as exc:
        raise DownloadError("write_failed", WRITE_TEXT, str(exc)) from exc

    needed = model.size_bytes - partial.received + DISK_MARGIN_BYTES
    if free < needed:
        gb = max(0.1, (needed - free) / 1e9)
        raise DownloadError(
            "disk_full", DISK_FULL_TEXT.format(gb=f"{gb:.1f}"), f"free {free}, need {needed}"
        )

    reporter = _Reporter(model.size_bytes, on_progress)
    attempts = len(retry_delays) + 1
    for attempt in range(attempts):
        try:
            await _fetch(session, model, part, partial, reporter)
        except aiohttp.ClientResponseError as exc:
            # A 4xx will not fix itself; only server errors are retried.
            if exc.status < 500 or attempt == attempts - 1:
                raise DownloadError("network", NETWORK_TEXT, f"HTTP {exc.status}") from exc
        except (aiohttp.ClientError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise DownloadError("network", NETWORK_TEXT, repr(exc)) from exc
        except OSError as exc:
            raise DownloadError("write_failed", WRITE_TEXT, str(exc)) from exc
        if partial.received >= model.size_bytes:
            break
        if attempt == attempts - 1:
            raise DownloadError("network", NETWORK_TEXT, f"stopped at {partial.received} bytes")
        delay = retry_delays[attempt]
        logger.info(
            "download interrupted; retrying",
            extra={"fields": {"model": model.id, "received": partial.received, "delay_s": delay}},
        )
        await asyncio.sleep(delay)

    reporter.verifying()
    sha256 = partial.digest.hexdigest()
    if partial.received != model.size_bytes or sha256 != model.sha256:
        with contextlib.suppress(OSError):
            await asyncio.to_thread(part.unlink)
        raise DownloadError("damaged", DAMAGED_TEXT, f"size {partial.received}, sha256 {sha256}")
    try:
        await asyncio.to_thread(os.replace, part, final)
    except OSError as exc:
        raise DownloadError("write_failed", WRITE_TEXT, str(exc)) from exc
    logger.info("model downloaded", extra={"fields": {"model": model.id, "file": model.file}})
    return final


async def _fetch(
    session: aiohttp.ClientSession,
    model: Downloadable,
    part: Path,
    partial: _Partial,
    reporter: _Reporter,
) -> None:
    """One request: append to ``part`` until the server stops sending."""
    headers = {"Range": f"bytes={partial.received}-"} if partial.received else {}
    async with session.get(model.url, headers=headers) as response:
        response.raise_for_status()
        if partial.received and response.status != 206:
            # The server ignored the Range request: start over.
            logger.info("server ignored resume; restarting", extra={"fields": {"model": model.id}})
            partial.reset()
        f = await asyncio.to_thread(_open, part, append=partial.received > 0)
        try:
            reporter.start(partial.received)
            async for chunk in response.content.iter_chunked(CHUNK_BYTES):
                await asyncio.to_thread(_write, f, partial, chunk)
                reporter.update(partial.received)
        finally:
            await asyncio.to_thread(_finish, f)
