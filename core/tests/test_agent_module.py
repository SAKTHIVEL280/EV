import asyncio
import logging
from collections.abc import AsyncIterator, Sequence

from ev_core.agent import EMPTY_TEXT, TOO_LONG_TEXT, AgentModule
from ev_core.bus import Event, EventBus
from ev_core.config import AgentSection, EffortLevel, LlmSection
from ev_core.interfaces.events import (
    ChatCancelRequested,
    ChatDone,
    ChatFailed,
    ChatRequested,
    ChatResetRequested,
    ChatStarted,
    LlmStatusChanged,
)
from ev_core.interfaces.llm import (
    ChatMessage,
    Finished,
    LlmEvent,
    ModelRole,
    TextDelta,
    ToolSpec,
)
from ev_core.llm.fake import FakeBackend, FakeProvider
from ev_core.modules import ModuleContext


class Recorder:
    def __init__(self, bus: EventBus) -> None:
        self.events: list[Event] = []
        self._changed = asyncio.Event()
        for kind in (ChatStarted, ChatDone, ChatFailed):
            bus.subscribe(kind, self._add)

    async def _add(self, event: Event) -> None:
        self.events.append(event)
        self._changed.set()

    async def wait_for(self, kind: type[Event], count: int = 1) -> None:
        async with asyncio.timeout(5):
            while sum(isinstance(e, kind) for e in self.events) < count:
                self._changed.clear()
                await self._changed.wait()


class Blocking(FakeBackend):
    """Streams one token, then waits forever (until cancelled)."""

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec],
        thinking: bool,
        max_tokens: int,
    ) -> AsyncIterator[LlmEvent]:
        yield TextDelta("…")
        await asyncio.Event().wait()


async def setup(
    backend: FakeBackend, default: EffortLevel = EffortLevel.NORMAL
) -> tuple[EventBus, Recorder, AgentModule, FakeProvider]:
    bus = EventBus()
    provider = FakeProvider(backend)
    agent = AgentModule(AgentSection(default_effort=default), LlmSection(), provider, tools=[])
    await agent.start(ModuleContext(bus=bus, logger=logging.getLogger("t")))
    return bus, Recorder(bus), agent, provider


def answer(text: str) -> list[LlmEvent | Exception]:
    return [TextDelta(text), Finished("stop")]


async def test_request_runs_turn_with_default_effort() -> None:
    bus, rec, agent, provider = await setup(FakeBackend([answer("hi")]), EffortLevel.DEEP)
    bus.publish(ChatRequested("t1", "hello", None))
    await rec.wait_for(ChatDone)
    assert provider.roles == [ModelRole.LARGE]
    await agent.stop()


async def test_prefix_beats_requested_effort() -> None:
    bus, rec, agent, provider = await setup(FakeBackend([answer("ok")]))
    bus.publish(ChatRequested("t1", "instant effort, summarize", EffortLevel.MAX))
    await rec.wait_for(ChatDone)
    assert provider.roles == [ModelRole.DEFAULT]
    started = rec.events[0]
    assert isinstance(started, ChatStarted)
    assert started.effort is EffortLevel.INSTANT
    await agent.stop()


async def test_new_request_cancels_running_turn_first() -> None:
    bus, rec, agent, _ = await setup(Blocking([]))
    bus.publish(ChatRequested("t1", "first", None))
    await rec.wait_for(ChatStarted)
    agent._provider = FakeProvider(FakeBackend([answer("second")]))
    bus.publish(ChatRequested("t2", "second", None))
    await rec.wait_for(ChatDone, 2)
    kinds = [(type(e).__name__, getattr(e, "turn_id", None)) for e in rec.events]
    assert kinds == [
        ("ChatStarted", "t1"),
        ("ChatDone", "t1"),
        ("ChatStarted", "t2"),
        ("ChatDone", "t2"),
    ]
    first_done = rec.events[1]
    assert isinstance(first_done, ChatDone)
    assert first_done.cancelled
    await agent.stop()


async def test_cancel_request() -> None:
    bus, rec, agent, _ = await setup(Blocking([]))
    bus.publish(ChatRequested("t1", "first", None))
    await rec.wait_for(ChatStarted)
    bus.publish(ChatCancelRequested("other"))
    await asyncio.sleep(0.01)
    assert not any(isinstance(e, ChatDone) for e in rec.events)
    bus.publish(ChatCancelRequested("t1"))
    await rec.wait_for(ChatDone)
    done = rec.events[-1]
    assert isinstance(done, ChatDone)
    assert done.cancelled
    await agent.stop()


async def test_reset_cancels_running_turn_and_forgets_history() -> None:
    backend = FakeBackend([answer("Hi Sam."), answer("I don't know.")])
    bus, rec, agent, _ = await setup(backend)
    bus.publish(ChatRequested("t1", "my name is Sam", None))
    await rec.wait_for(ChatDone)
    blocking = Blocking([])
    agent._provider = FakeProvider(blocking)
    bus.publish(ChatRequested("t2", "long", None))
    await rec.wait_for(ChatStarted, 2)
    bus.publish(ChatResetRequested())
    await rec.wait_for(ChatDone, 2)
    done = rec.events[-1]
    assert isinstance(done, ChatDone)
    assert done.cancelled
    agent._provider = FakeProvider(backend)
    bus.publish(ChatRequested("t3", "what is my name", None))
    await rec.wait_for(ChatDone, 3)
    contents = [m.content for m in backend.calls[-1].messages]
    assert not any("Sam" in c for c in contents)
    await agent.stop()


async def test_empty_and_too_long_inputs_fail() -> None:
    bus, rec, agent, provider = await setup(FakeBackend([]))
    bus.publish(ChatRequested("t1", "   ", None))
    bus.publish(ChatRequested("t2", "max effort,  ", None))
    bus.publish(ChatRequested("t3", "x" * 8001, None))
    await rec.wait_for(ChatFailed, 3)
    assert rec.events == [
        ChatFailed("t1", "empty_input", EMPTY_TEXT),
        ChatFailed("t2", "empty_input", EMPTY_TEXT),
        ChatFailed("t3", "too_long", TOO_LONG_TEXT),
    ]
    assert provider.roles == []
    await agent.stop()


async def test_ready_model_gets_prefix_warmed() -> None:
    backend = FakeBackend([[Finished("length")]])
    bus, _, agent, provider = await setup(backend)
    bus.publish(LlmStatusChanged("ready", "fake.gguf"))
    await bus.drain()
    assert provider.roles == [ModelRole.DEFAULT]
    call = backend.calls[0]
    assert (call.max_tokens, call.thinking) == (1, False)
    assert [m.role for m in call.messages] == ["system", "user"]
    await agent.stop()


async def test_warm_up_skips_other_models_and_states() -> None:
    backend = FakeBackend([])
    bus, _, agent, _ = await setup(backend)
    bus.publish(LlmStatusChanged("loading", "fake.gguf"))
    bus.publish(LlmStatusChanged("ready", "other.gguf"))
    await bus.drain()
    assert backend.calls == []
    await agent.stop()
