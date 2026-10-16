import asyncio
import time
from collections.abc import AsyncIterator, Sequence

import pytest

from ev_core.agent.history import History
from ev_core.agent.loop import STEP_LIMIT_TEXT, TurnRequest, run_turn
from ev_core.agent.prompt import SYSTEM_PROMPT
from ev_core.agent.toolbox import Toolbox
from ev_core.bus import Event
from ev_core.config import EffortLevel
from ev_core.interfaces.events import ChatDelta, ChatDone, ChatFailed, ChatStarted, ChatToolChanged
from ev_core.interfaces.llm import (
    ChatMessage,
    Finished,
    LlmError,
    LlmEvent,
    ModelRole,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolCallsReady,
    ToolSpec,
    Usage,
)
from ev_core.llm.fake import FakeBackend, FakeProvider
from ev_core.tools.clock import CurrentTimeTool

TURN = "36c14c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d"


def request(text: str, effort: EffortLevel = EffortLevel.NORMAL) -> TurnRequest:
    return TurnRequest(TURN, text, effort, context_tokens=8192, received_at=time.monotonic())


def answer(*parts: str, prompt: int = 100, generated: int = 5) -> list[LlmEvent | Exception]:
    return [*(TextDelta(p) for p in parts), Finished("stop", Usage(prompt, generated))]


def tool_step(name: str = "current_time") -> list[LlmEvent | Exception]:
    return [ToolCallsReady((ToolCall("c1", name, "{}"),)), Finished("tool_calls", Usage(50, 3))]


async def play(
    req: TurnRequest, scripts: list[list[LlmEvent | Exception]], history: History | None = None
) -> tuple[list[Event], FakeBackend, FakeProvider]:
    backend = FakeBackend(scripts)
    provider = FakeProvider(backend)
    events: list[Event] = []
    await run_turn(req, provider, Toolbox([CurrentTimeTool()]), history or History(), events.append)
    return events, backend, provider


async def test_streams_reply_and_records_usage() -> None:
    events, backend, provider = await play(request("hello"), [answer("Hi", " there.")])
    assert events[0] == ChatStarted(TURN, EffortLevel.NORMAL, "fake.gguf")
    assert events[1:3] == [ChatDelta(TURN, "Hi"), ChatDelta(TURN, " there.")]
    done = events[3]
    assert isinstance(done, ChatDone)
    assert (done.text, done.cancelled, done.prompt_tokens, done.generated_tokens) == (
        "Hi there.",
        False,
        100,
        5,
    )
    assert done.first_token_ms is not None
    assert done.total_ms >= done.first_token_ms
    assert provider.roles == [ModelRole.DEFAULT]
    call = backend.calls[0]
    assert call.messages[0].role == "system"
    assert call.messages[0].content == SYSTEM_PROMPT
    assert call.messages[-1].content == "hello"
    assert not call.thinking
    assert [t.name for t in call.tools] == ["current_time"]


async def test_tool_step_then_answer() -> None:
    events, backend, _ = await play(request("time in words?"), [tool_step(), answer("It's late.")])
    assert ChatToolChanged(TURN, "current_time", "running") in events
    assert ChatToolChanged(TURN, "current_time", "done") in events
    second = backend.calls[1].messages
    assert second[-2].role == "assistant"
    assert second[-2].tool_calls[0].name == "current_time"
    assert second[-1].role == "tool"
    assert second[-1].tool_call_id == "c1"
    assert "time_text" in second[-1].content
    done = events[-1]
    assert isinstance(done, ChatDone)
    assert done.text == "It's late."
    assert (done.prompt_tokens, done.generated_tokens) == (150, 8)


async def test_step_limit_stops_tool_loops() -> None:
    events, backend, _ = await play(request("loop"), [tool_step() for _ in range(5)])
    assert len(backend.calls) == 5
    done = events[-1]
    assert isinstance(done, ChatDone)
    assert done.text == STEP_LIMIT_TEXT


async def test_instant_gets_no_tools_and_small_model() -> None:
    _, backend, provider = await play(
        request("summarize this", EffortLevel.INSTANT), [answer("ok")]
    )
    assert backend.calls[0].tools == []
    assert backend.calls[0].max_tokens == 512
    assert provider.roles == [ModelRole.SMALL]


@pytest.mark.parametrize("effort", [EffortLevel.DEEP, EffortLevel.MAX])
async def test_deep_and_max_think_with_large_model(effort: EffortLevel) -> None:
    script: list[LlmEvent | Exception] = [ReasoningDelta("hmm"), *answer("done")]
    events, backend, provider = await play(request("plan", effort), [script])
    assert backend.calls[0].thinking
    assert provider.roles == [ModelRole.LARGE]
    # Reasoning is never part of the reply.
    assert [e.text for e in events if isinstance(e, ChatDelta)] == ["done"]


async def test_no_model_fails_cleanly() -> None:
    events: list[Event] = []
    await run_turn(request("hi"), FakeProvider(None), Toolbox([]), History(), events.append)
    assert events == [ChatFailed(TURN, "no_model", "No model installed. Add one in Settings.")]


async def test_model_error_mid_stream() -> None:
    err = LlmError("model_error", "The model stopped responding. Try again.")
    events, _, _ = await play(request("hi"), [[TextDelta("Par"), err]])
    assert events[-1] == ChatFailed(TURN, "model_error", "The model stopped responding. Try again.")


async def test_cancel_emits_cancelled_done_and_keeps_partial_history() -> None:
    gate = asyncio.Event()

    class Slow(FakeBackend):
        async def stream(
            self,
            messages: Sequence[ChatMessage],
            *,
            tools: Sequence[ToolSpec],
            thinking: bool,
            max_tokens: int,
        ) -> AsyncIterator[LlmEvent]:
            yield TextDelta("Partial")
            await gate.wait()

    events: list[Event] = []
    first_delta = asyncio.Event()

    def emit(event: Event) -> None:
        events.append(event)
        if isinstance(event, ChatDelta):
            first_delta.set()

    history = History()
    task = asyncio.create_task(
        run_turn(request("long"), FakeProvider(Slow([])), Toolbox([]), history, emit)
    )
    await asyncio.wait_for(first_delta.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    done = events[-1]
    assert isinstance(done, ChatDone)
    assert (done.text, done.cancelled) == ("Partial", True)
    assert [m.content for m in history.window(10_000)] == ["long", "Partial"]


async def test_router_answers_without_model() -> None:
    events, backend, provider = await play(request("What time is it?", EffortLevel.MAX), [])
    assert provider.roles == []
    assert backend.calls == []
    assert events[0] == ChatStarted(TURN, EffortLevel.INSTANT, None)
    assert events[1:3] == [
        ChatToolChanged(TURN, "current_time", "running"),
        ChatToolChanged(TURN, "current_time", "done"),
    ]
    delta = events[3]
    assert isinstance(delta, ChatDelta)
    assert delta.text.startswith("It's ")
    assert delta.text.endswith(("AM.", "PM."))
    done = events[4]
    assert isinstance(done, ChatDone)
    assert done.model is None
    assert done.effort is EffortLevel.INSTANT
    assert done.total_ms < 300


async def test_history_carries_into_next_turn() -> None:
    history = History()
    await play(request("my name is Sam"), [answer("Hi Sam.")], history)
    _, backend, _ = await play(request("what is my name"), [answer("Sam.")], history)
    contents = [m.content for m in backend.calls[0].messages]
    assert contents[1:] == ["my name is Sam", "Hi Sam.", "what is my name"]
