"""Settings over the wire: server + SettingsService + store (docs/FEATURES.md F-410)."""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.client import ClientConnection, connect

from ev_core import protocol
from ev_core.bus import EventBus
from ev_core.config import ConfigStore, ConfigWatcher
from ev_core.config.service import SettingsService
from ev_core.server import CoreServer
from tests.conftest import TOKEN

AUTH = {"Authorization": f"Bearer {TOKEN}"}
SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "protocol" / "ev-protocol.schema.json").read_text()
)


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.bus = EventBus()
        self.store = ConfigStore(tmp_path / "config.toml")
        self.watcher = ConfigWatcher(self.store, self.bus, self.store.load())
        self.service = SettingsService(self.store, self.watcher, self.bus)
        self.server = CoreServer(
            bus=self.bus,
            token=TOKEN,
            core_version="t",
            module_statuses=list,
            on_shutdown=lambda _r: None,
        )
        self.port = 0


@pytest.fixture
async def rig(tmp_path: Path) -> AsyncIterator[Rig]:
    r = Rig(tmp_path)
    r.port = await r.server.start()
    yield r
    await r.server.close()


async def session(rig: Rig) -> ClientConnection:
    ws = await connect(f"ws://127.0.0.1:{rig.port}/", additional_headers=AUTH, max_size=2**22)
    await ws.send(protocol.encode(protocol.hello("t")))
    assert json.loads(await ws.recv())["type"] == "hello.ack"
    return ws


async def recv_type(ws: ClientConnection, *kinds: str) -> dict[str, Any]:
    while True:
        message: dict[str, Any] = json.loads(await ws.recv())
        if message["type"] in kinds:
            return message


def value(state: dict[str, Any], dotted: str) -> object:
    section, key = dotted.split(".")
    return next(
        i["value"] for i in state["payload"]["items"] if (i["section"], i["key"]) == (section, key)
    )


async def test_get_set_reject_reset(rig: Rig) -> None:
    async with await session(rig) as ws:
        get = protocol.config_get()
        await ws.send(protocol.encode(get))
        state = await recv_type(ws, "config.state")
        assert state["reply_to"] == get.id
        assert value(state, "llm.context") == 8192
        assert state["payload"]["path"] == str(rig.store.path)

        change = protocol.config_set("llm", "context", 16384)
        await ws.send(protocol.encode(change))
        state = await recv_type(ws, "config.state", "config.rejected")
        assert state["type"] == "config.state"
        assert state["reply_to"] == change.id
        assert value(state, "llm.context") == 16384
        assert "context = 16384" in rig.store.path.read_text(encoding="utf-8")

        bad = protocol.config_set("llm", "context", 1)
        await ws.send(protocol.encode(bad))
        rejected = await recv_type(ws, "config.state", "config.rejected")
        assert rejected["type"] == "config.rejected"
        assert rejected["reply_to"] == bad.id
        assert rejected["payload"]["message"] == "That value isn't allowed. Use 2048 to 131072."
        assert "context = 16384" in rig.store.path.read_text(encoding="utf-8")

        reset = protocol.config_reset("llm", "context")
        await ws.send(protocol.encode(reset))
        state = await recv_type(ws, "config.state")
        assert value(state, "llm.context") == 8192


async def test_hand_edit_pushes_state(rig: Rig) -> None:
    async with await session(rig) as ws:
        text = rig.store.path.read_text(encoding="utf-8").replace(
            'default_effort = "normal"', 'default_effort = "max"'
        )
        rig.store.path.write_text(text + "\n", encoding="utf-8")
        await rig.watcher.check()
        state = await recv_type(ws, "config.state")
        assert state.get("reply_to") is None
        assert value(state, "agent.default_effort") == "max"


async def test_config_messages_satisfy_schema(rig: Rig) -> None:
    import jsonschema

    validator = jsonschema.Draft202012Validator(SCHEMA)
    async with await session(rig) as ws:
        await ws.send(protocol.encode(protocol.config_get()))
        validator.validate(await recv_type(ws, "config.state"))
        await ws.send(protocol.encode(protocol.config_set("agent", "default_effort", "nope")))
        validator.validate(await recv_type(ws, "config.rejected"))


async def test_change_from_core_reaches_the_app(rig: Rig) -> None:
    # A finished model download fills llm.model_default from inside core; the
    # app must get the new state (it has no request id to reply to).
    async with await session(rig) as ws:
        await rig.service.set_value("llm", "model_default", "Qwen3.5-4B-Q4_K_M.gguf")
        async with asyncio.timeout(5):
            state = await recv_type(ws, "config.state")
        assert "reply_to" not in state
        assert value(state, "llm.model_default") == "Qwen3.5-4B-Q4_K_M.gguf"
