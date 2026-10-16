"""End-to-end: run ``python -m ev_core`` as the Rust supervisor would."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.client import connect

from ev_core import protocol
from ev_core.app import EXIT_BAD_ENV, EXIT_OK
from tests.conftest import TOKEN

TIMEOUT_S = 15.0


async def _spawn(data_dir: Path, token: str = TOKEN) -> asyncio.subprocess.Process:
    env = {**os.environ, "EV_CORE_TOKEN": token, "EV_DATA_DIR": str(data_dir)}
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "ev_core",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _listening(proc: asyncio.subprocess.Process) -> dict[str, Any]:
    assert proc.stdout is not None
    line = await asyncio.wait_for(proc.stdout.readline(), TIMEOUT_S)
    result: dict[str, Any] = json.loads(line)
    return result


async def test_full_lifecycle_via_shutdown(tmp_path: Path) -> None:
    proc = await _spawn(tmp_path)
    ready = await _listening(proc)
    assert ready["event"] == "listening"
    assert ready["protocol"] == protocol.PROTOCOL_VERSION

    url = f"ws://127.0.0.1:{ready['port']}/"
    async with connect(url, additional_headers={"Authorization": f"Bearer {TOKEN}"}) as ws:
        await ws.send(protocol.encode(protocol.hello("0.1.0-beta.1")))
        ack = json.loads(await ws.recv())
        assert ack["type"] == "hello.ack"
        await ws.send(protocol.encode(protocol.shutdown(protocol.Reason.app_exit)))

    assert await asyncio.wait_for(proc.wait(), TIMEOUT_S) == EXIT_OK
    assert proc.stdout is not None
    assert await proc.stdout.read() == b"", "stdout must carry only the listening line"
    assert (tmp_path / "config.toml").is_file()
    log_lines = [
        json.loads(line) for line in (tmp_path / "logs" / "core.log").read_text().splitlines()
    ]
    assert {"core listening", "core stopped"} <= {entry["msg"] for entry in log_lines}
    assert TOKEN not in (tmp_path / "logs" / "core.log").read_text()


async def test_exits_when_stdin_closes(tmp_path: Path) -> None:
    proc = await _spawn(tmp_path)
    await _listening(proc)
    assert proc.stdin is not None
    proc.stdin.close()
    assert await asyncio.wait_for(proc.wait(), TIMEOUT_S) == EXIT_OK


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
async def test_exits_on_sigterm(tmp_path: Path) -> None:
    proc = await _spawn(tmp_path)
    await _listening(proc)
    proc.terminate()
    assert await asyncio.wait_for(proc.wait(), TIMEOUT_S) == EXIT_OK


@pytest.mark.parametrize("token", ["", "short", "AB" * 32, "zz" * 32])
async def test_bad_token_exits_with_code_2(tmp_path: Path, token: str) -> None:
    proc = await _spawn(tmp_path, token)
    _, stderr = await asyncio.wait_for(proc.communicate(), TIMEOUT_S)
    assert proc.returncode == EXIT_BAD_ENV
    assert json.loads(stderr)["code"] == "bad_env"
    assert not (tmp_path / "config.toml").exists()


async def test_hot_reload_changes_log_level(tmp_path: Path) -> None:
    proc = await _spawn(tmp_path)
    await _listening(proc)
    config = tmp_path / "config.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace('level = "info"', 'level = "debug"'),
        encoding="utf-8",
    )
    log = tmp_path / "logs" / "core.log"
    deadline = asyncio.get_running_loop().time() + TIMEOUT_S
    while "config reloaded" not in log.read_text(encoding="utf-8"):
        assert asyncio.get_running_loop().time() < deadline, "reload not observed"
        await asyncio.sleep(0.1)
    assert proc.stdin is not None
    proc.stdin.close()
    assert await asyncio.wait_for(proc.wait(), TIMEOUT_S) == EXIT_OK
