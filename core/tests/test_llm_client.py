import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
import pytest
from aiohttp import web

from ev_core.interfaces.llm import (
    ChatMessage,
    Finished,
    LlmError,
    LlmEvent,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolCallsReady,
    ToolSpec,
    Usage,
)
from ev_core.llm.client import LlamaServerClient, StreamParser, request_body, to_wire

KEY = "k" * 64

type Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def test_request_body() -> None:
    tool = ToolSpec("current_time", "Get the time.", {"type": "object", "properties": {}})
    body = request_body(
        [ChatMessage("system", "s"), ChatMessage("user", "u")], [tool], thinking=True, max_tokens=99
    )
    assert body["stream"] is True
    assert body["cache_prompt"] is True
    assert body["max_tokens"] == 99
    assert body["chat_template_kwargs"] == {"enable_thinking": True}
    assert body["tools"][0]["function"]["name"] == "current_time"
    assert "tools" not in request_body([], [], thinking=False, max_tokens=1)


def test_to_wire_tool_messages() -> None:
    call = ToolCall("c1", "current_time", "{}")
    assert to_wire(ChatMessage("assistant", "", tool_calls=(call,)))["tool_calls"] == [
        {"id": "c1", "type": "function", "function": {"name": "current_time", "arguments": "{}"}}
    ]
    assert to_wire(ChatMessage("tool", "r", tool_call_id="c1"))["tool_call_id"] == "c1"


def test_parser_text_reasoning_tools_usage() -> None:
    parser = StreamParser()
    events: list[LlmEvent] = []
    chunks: list[dict[str, Any]] = [
        {"choices": [{"delta": {"reasoning_content": "hm"}}]},
        {"choices": [{"delta": {"content": "Hi"}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": "current_", "arguments": '{"a"'},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"name": "time", "arguments": ": 1}"}}
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 4}},
    ]
    for chunk in chunks:
        events += parser.feed(chunk)
    events += parser.finish()
    assert events == [
        ReasoningDelta("hm"),
        TextDelta("Hi"),
        ToolCallsReady((ToolCall("c1", "current_time", '{"a": 1}'),)),
        Finished("tool_calls", Usage(10, 4)),
    ]


def test_parser_timings_fallback_and_default_id() -> None:
    parser = StreamParser()
    parser.feed({"choices": [{"delta": {"tool_calls": [{"index": 1, "function": {"name": "x"}}]}}]})
    parser.feed({"timings": {"prompt_n": 7, "predicted_n": 2}, "choices": []})
    assert parser.finish() == [
        ToolCallsReady((ToolCall("call_1", "x", ""),)),
        Finished("stop", Usage(7, 2)),
    ]


@asynccontextmanager
async def serve(handler: Handler) -> AsyncIterator[str]:
    app = web.Application()
    app.router.add_post("/v1/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


async def collect(handler: Handler) -> list[LlmEvent]:
    async with (
        serve(handler) as base,
        aiohttp.ClientSession(connector=aiohttp.TCPConnector(force_close=True)) as session,
    ):
        client = LlamaServerClient(session, base, KEY, "m.gguf")
        stream = client.stream([ChatMessage("user", "hi")], tools=[], thinking=False, max_tokens=5)
        return [event async for event in stream]


async def test_streams_sse_with_auth() -> None:
    seen: dict[str, object] = {}

    async def handler(request: web.Request) -> web.StreamResponse:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = await request.json()
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        for chunk in (
            {"choices": [{"delta": {"content": "A"}}]},
            {"choices": [{"delta": {"content": "B"}, "finish_reason": "stop"}]},
        ):
            await response.write(f"data: {json.dumps(chunk)}\n\n".encode())
        await response.write(b"data: [DONE]\n\n")
        return response

    events = await collect(handler)
    assert events == [TextDelta("A"), TextDelta("B"), Finished("stop", Usage())]
    assert seen["auth"] == f"Bearer {KEY}"
    assert isinstance(seen["body"], dict)
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]


async def test_http_error_becomes_llm_error() -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.Response(status=500, text="context overflow")

    with pytest.raises(LlmError) as caught:
        await collect(handler)
    assert caught.value.code == "model_error"
    assert "context overflow" in caught.value.detail


async def test_dropped_connection_becomes_llm_error() -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(b'data: {"choices": [{"delta": {"content": "A"}}]}\n\n')
        assert request.transport is not None
        request.transport.close()
        return response

    with pytest.raises(LlmError):
        await collect(handler)


async def test_bad_chunk_becomes_llm_error() -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(b"data: {not json\n\n")
        return response

    with pytest.raises(LlmError):
        await collect(handler)
