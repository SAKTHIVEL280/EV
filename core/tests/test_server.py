import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidStatus

from ev_core import protocol
from ev_core.bus import EventBus
from ev_core.modules import ModuleState, ModuleStatus
from ev_core.server import CoreServer
from tests.conftest import TOKEN

AUTH = {"Authorization": f"Bearer {TOKEN}"}


class Harness:
    def __init__(self) -> None:
        self.shutdowns: list[protocol.Reason] = []
        self.bus = EventBus()
        self.server = CoreServer(
            bus=self.bus,
            token=TOKEN,
            core_version="0.1.0b1",
            module_statuses=lambda: [ModuleStatus("voice", ModuleState.DISABLED, "Off.")],
            on_shutdown=self.shutdowns.append,
        )
        self.port = 0

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/"


@pytest.fixture
async def harness() -> AsyncIterator[Harness]:
    h = Harness()
    h.port = await h.server.start()
    yield h
    await h.server.close()


async def _recv(ws: ClientConnection) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(await ws.recv())
    return result


async def _greet(ws: ClientConnection) -> dict[str, Any]:
    hello = protocol.hello("0.1.0-beta.1")
    await ws.send(protocol.encode(hello))
    ack = await _recv(ws)
    assert ack["reply_to"] == hello.id
    return ack


async def test_hello_ack_reports_versions_and_modules(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as ws:
        ack = await _greet(ws)
    assert ack["type"] == "hello.ack"
    assert ack["payload"] == {
        "core_version": "0.1.0b1",
        "protocol": protocol.PROTOCOL_VERSION,
        "modules": [{"name": "voice", "state": "disabled", "detail": "Off."}],
    }


async def test_ping_pong(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as ws:
        await _greet(ws)
        ping = protocol.ping()
        await ws.send(protocol.encode(ping))
        pong = await _recv(ws)
    assert pong["type"] == "pong"
    assert pong["reply_to"] == ping.id


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 401),
        ({"Authorization": "Bearer " + "0" * 64}, 401),
        ({"Authorization": TOKEN}, 401),
        ({**AUTH, "Origin": "https://evil.example"}, 403),
    ],
    ids=["missing", "wrong", "no-bearer", "origin"],
)
async def test_handshake_rejections(harness: Harness, headers: dict[str, str], status: int) -> None:
    with pytest.raises(InvalidStatus) as caught:
        async with connect(harness.url, additional_headers=headers):
            pass
    assert caught.value.response.status_code == status


async def test_second_client_rejected_while_first_connected(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as first:
        await _greet(first)
        with pytest.raises(InvalidStatus) as caught:
            async with connect(harness.url, additional_headers=AUTH):
                pass
        assert caught.value.response.status_code == 409
    # After the first disconnects, a new client is accepted.
    async with connect(harness.url, additional_headers=AUTH) as again:
        await _greet(again)


async def test_messages_before_hello_are_refused(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as ws:
        ping = protocol.ping()
        await ws.send(protocol.encode(ping))
        err = await _recv(ws)
        assert err["type"] == "error"
        assert err["payload"]["code"] == "handshake_required"
        assert err["reply_to"] == ping.id
        await _greet(ws)


async def test_bad_message_gets_error_and_session_continues(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as ws:
        await ws.send("not json")
        err = await _recv(ws)
        assert err["payload"]["code"] == "bad_message"
        assert "reply_to" not in err
        await _greet(ws)


async def test_duplicate_hello_and_wrong_direction_messages(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as ws:
        await _greet(ws)
        await ws.send(protocol.encode(protocol.hello("x")))
        assert (await _recv(ws))["payload"]["code"] == "unexpected_message"
        await ws.send(protocol.encode(protocol.pong(protocol.new_id())))
        assert (await _recv(ws))["payload"]["code"] == "unexpected_message"


async def test_envelope_version_mismatch_closes(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as ws:
        msg = json.loads(protocol.encode(protocol.hello("x")))
        msg["v"] = 2
        await ws.send(json.dumps(msg))
        err = await _recv(ws)
        assert err["payload"]["code"] == "protocol_mismatch"
        await ws.wait_closed()
    assert ws.close_code == 1002


async def test_hello_protocol_mismatch_closes(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as ws:
        msg = json.loads(protocol.encode(protocol.hello("x")))
        msg["payload"]["protocol"] = 2
        await ws.send(json.dumps(msg))
        err = await _recv(ws)
        assert err["payload"]["code"] == "protocol_mismatch"
        await ws.wait_closed()
    assert ws.close_code == 1002


async def test_shutdown_invokes_callback(harness: Harness) -> None:
    async with connect(harness.url, additional_headers=AUTH) as ws:
        await _greet(ws)
        await ws.send(protocol.encode(protocol.shutdown(protocol.Reason.app_exit)))
        await ws.wait_closed()
    assert harness.shutdowns == [protocol.Reason.app_exit]


async def test_binds_loopback_only(harness: Harness) -> None:
    assert harness.server._server is not None
    hosts = {sock.getsockname()[0] for sock in harness.server._server.sockets}
    assert hosts == {"127.0.0.1"}


async def test_chat_send_and_cancel_become_bus_events(harness: Harness) -> None:
    from ev_core.config import EffortLevel
    from ev_core.interfaces.events import ChatCancelRequested, ChatRequested

    seen: list[object] = []

    async def record(event: object) -> None:
        seen.append(event)

    harness.bus.subscribe(ChatRequested, record)
    harness.bus.subscribe(ChatCancelRequested, record)
    async with connect(harness.url, additional_headers=AUTH) as ws:
        await _greet(ws)
        send = protocol.chat_send("hi", protocol.Effort.deep)
        await ws.send(protocol.encode(send))
        await ws.send(protocol.encode(protocol.chat_cancel(send.id)))
        await ws.send(protocol.encode(protocol.ping()))
        await _recv(ws)  # pong: both earlier frames were handled
    await harness.bus.drain()
    assert seen == [ChatRequested(send.id, "hi", EffortLevel.DEEP), ChatCancelRequested(send.id)]


async def test_outbound_events_keep_order_and_status_is_replayed(harness: Harness) -> None:
    from ev_core.config import EffortLevel
    from ev_core.interfaces.events import ChatDelta, ChatDone, ChatStarted, LlmStatusChanged

    turn = protocol.new_id()
    harness.bus.publish(LlmStatusChanged("ready", "m.gguf"))
    harness.bus.publish(ChatDelta(turn, "dropped: no client yet"))
    await harness.bus.drain()
    async with connect(harness.url, additional_headers=AUTH) as ws:
        await _greet(ws)
        status = await _recv(ws)
        assert status["type"] == "llm.status"
        assert status["payload"] == {"state": "ready", "model": "m.gguf"}
        harness.bus.publish(ChatStarted(turn, EffortLevel.NORMAL, "m.gguf"))
        for i in range(50):
            harness.bus.publish(ChatDelta(turn, str(i)))
        harness.bus.publish(
            ChatDone(turn, "x", EffortLevel.NORMAL, "m.gguf", total_ms=5, cancelled=False)
        )
        received = [await _recv(ws) for _ in range(52)]
    assert received[0]["type"] == "chat.started"
    assert [m["payload"]["text"] for m in received[1:51]] == [str(i) for i in range(50)]
    assert received[51]["type"] == "chat.done"
    assert received[51]["payload"]["timings"] == {"total_ms": 5}
