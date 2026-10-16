"""llama-server client: OpenAI-compatible streaming chat completions over SSE."""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, Final

import aiohttp

from ev_core.interfaces.llm import (
    ChatMessage,
    Finished,
    LlmBackend,
    LlmError,
    LlmEvent,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolCallsReady,
    ToolSpec,
    Usage,
)

STOPPED_TEXT: Final = "The model stopped responding. Try again."


def to_wire(message: ChatMessage) -> dict[str, Any]:
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        wire["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in message.tool_calls
        ]
    if message.tool_call_id is not None:
        wire["tool_call_id"] = message.tool_call_id
    return wire


def request_body(
    messages: Sequence[ChatMessage],
    tools: Sequence[ToolSpec],
    *,
    thinking: bool,
    max_tokens: int,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "messages": [to_wire(m) for m in messages],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": max_tokens,
        # Reuse the KV cache for the shared prefix (system prompt + tools + history).
        "cache_prompt": True,
        # Qwen chat templates switch thinking on and off with this flag.
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    if tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
    return body


class StreamParser:
    """Turns SSE `data:` payloads into LlmEvents; assembles streamed tool calls."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, Any]] = {}
        self._reason = "stop"
        self._usage = Usage()

    def feed(self, chunk: dict[str, Any]) -> list[LlmEvent]:
        events: list[LlmEvent] = []
        usage = chunk.get("usage")
        if isinstance(usage, dict):
            self._usage = Usage(usage.get("prompt_tokens"), usage.get("completion_tokens"))
        timings = chunk.get("timings")
        if isinstance(timings, dict) and self._usage.prompt_tokens is None:
            self._usage = Usage(timings.get("prompt_n"), timings.get("predicted_n"))
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if reasoning := delta.get("reasoning_content"):
                events.append(ReasoningDelta(reasoning))
            if content := delta.get("content"):
                events.append(TextDelta(content))
            for part in delta.get("tool_calls") or []:
                slot = self._calls.setdefault(
                    int(part.get("index", 0)), {"id": "", "name": "", "args": []}
                )
                if part.get("id"):
                    slot["id"] = part["id"]
                function = part.get("function") or {}
                if function.get("name"):
                    slot["name"] += function["name"]
                if function.get("arguments"):
                    slot["args"].append(function["arguments"])
            if choice.get("finish_reason"):
                self._reason = choice["finish_reason"]
        return events

    def finish(self) -> list[LlmEvent]:
        events: list[LlmEvent] = []
        if self._calls:
            calls = tuple(
                ToolCall(
                    id=slot["id"] or f"call_{index}",
                    name=slot["name"],
                    arguments="".join(slot["args"]),
                )
                for index, slot in sorted(self._calls.items())
            )
            events.append(ToolCallsReady(calls))
        events.append(Finished(self._reason, self._usage))
        return events


class LlamaServerClient(LlmBackend):
    def __init__(
        self, session: aiohttp.ClientSession, base_url: str, api_key: str, model: str
    ) -> None:
        self._session = session
        self._url = f"{base_url}/v1/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec],
        thinking: bool,
        max_tokens: int,
    ) -> AsyncIterator[LlmEvent]:
        body = request_body(messages, tools, thinking=thinking, max_tokens=max_tokens)
        parser = StreamParser()
        try:
            async with self._session.post(self._url, json=body, headers=self._headers) as response:
                if response.status != 200:
                    detail = (await response.text())[:500]
                    raise LlmError("model_error", STOPPED_TEXT, f"HTTP {response.status}: {detail}")
                async for raw in response.content:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    for event in parser.feed(json.loads(data)):
                        yield event
        except aiohttp.ClientError as exc:
            raise LlmError("model_error", STOPPED_TEXT, f"{type(exc).__name__}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LlmError("model_error", STOPPED_TEXT, f"bad stream chunk: {exc}") from exc
        for event in parser.finish():
            yield event
