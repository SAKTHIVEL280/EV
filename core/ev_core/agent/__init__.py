"""The `agent` module: turns chat requests into replies (CLAUDE.md §5.4).

Listens for `ChatRequested` / `ChatCancelRequested` on the bus and publishes
the turn's events. One turn runs at a time; a new request cancels the running
one first, so its `ChatDone(cancelled=True)` always precedes the new turn.

When a model becomes ready, the agent pre-reads the static prompt prefix
(system prompt + tool list) with a one-token request. llama-server keeps it in
its KV cache, so the first real request skips ~400 tokens of prompt reading
(measured: first token 3.5 s cold vs 0.27 s cached, Qwen3.5-4B on CPU).
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Sequence
from typing import Final

from ev_core.agent.effort import POLICIES, parse_prefix
from ev_core.agent.history import History
from ev_core.agent.loop import TurnRequest, run_turn
from ev_core.agent.prompt import SYSTEM_PROMPT
from ev_core.agent.toolbox import Toolbox
from ev_core.bus import EventBus
from ev_core.config import AgentSection, ConfigChanged, LlmSection
from ev_core.interfaces.events import (
    ChatCancelRequested,
    ChatFailed,
    ChatRequested,
    ChatResetRequested,
    LlmStatusChanged,
)
from ev_core.interfaces.llm import ChatMessage, LlmError, LlmProvider
from ev_core.interfaces.tools import Tool
from ev_core.modules import Module, ModuleContext

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS: Final = 8_000
EMPTY_TEXT: Final = "Type a message first."
TOO_LONG_TEXT: Final = "That message is too long."


class AgentModule(Module):
    name = "agent"

    def __init__(
        self,
        settings: AgentSection,
        llm_settings: LlmSection,
        provider: LlmProvider,
        tools: Sequence[Tool],
    ) -> None:
        self._settings = settings
        self._llm_settings = llm_settings
        self._provider = provider
        self._toolbox = Toolbox(tools)
        self._history = History()
        self._bus: EventBus | None = None
        self._task: asyncio.Task[None] | None = None
        self._turn_id: str | None = None
        self._switch = asyncio.Lock()

    async def start(self, ctx: ModuleContext) -> None:
        self._bus = ctx.bus
        ctx.bus.subscribe(ChatRequested, self._on_request)
        ctx.bus.subscribe(ChatCancelRequested, self._on_cancel)
        ctx.bus.subscribe(ChatResetRequested, self._on_reset)
        ctx.bus.subscribe(ConfigChanged, self._on_config)
        ctx.bus.subscribe(LlmStatusChanged, self._on_llm_status)

    async def stop(self) -> None:
        await self._cancel_running()

    async def _on_llm_status(self, event: LlmStatusChanged) -> None:
        if event.state != "ready" or self._task is not None:
            return
        policy = POLICIES[self._settings.default_effort]
        try:
            backend = await self._provider.acquire(policy.role)
            if backend.model_name != event.model:
                return
            messages = [ChatMessage("system", SYSTEM_PROMPT), ChatMessage("user", "")]
            tools = self._toolbox.specs() if policy.max_steps > 1 else []
            async for _ in backend.stream(messages, tools=tools, thinking=False, max_tokens=1):
                pass
        except LlmError as exc:
            logger.info("prompt prefix warm-up skipped", extra={"fields": {"code": exc.code}})
            return
        logger.info("prompt prefix cached", extra={"fields": {"model": event.model}})

    async def _on_request(self, event: ChatRequested) -> None:
        received_at = time.monotonic()
        bus = self._bus
        if bus is None:
            return
        async with self._switch:
            await self._cancel_running()
            prefix_effort, text = parse_prefix(event.text)
            text = text.strip()
            if not text:
                bus.publish(ChatFailed(event.turn_id, "empty_input", EMPTY_TEXT))
                return
            if len(text) > MAX_INPUT_CHARS:
                bus.publish(ChatFailed(event.turn_id, "too_long", TOO_LONG_TEXT))
                return
            request = TurnRequest(
                turn_id=event.turn_id,
                text=text,
                effort=prefix_effort or event.effort or self._settings.default_effort,
                context_tokens=self._llm_settings.context,
                received_at=received_at,
            )
            self._turn_id = event.turn_id
            self._task = asyncio.create_task(
                run_turn(request, self._provider, self._toolbox, self._history, bus.publish)
            )
            self._task.add_done_callback(self._finished)

    async def _on_cancel(self, event: ChatCancelRequested) -> None:
        if event.turn_id == self._turn_id:
            async with self._switch:
                await self._cancel_running()

    async def _on_reset(self, _: ChatResetRequested) -> None:
        # New chat (F-414): the running turn stops first, so its cancelled
        # ChatDone and history entry land before the history is cleared.
        async with self._switch:
            await self._cancel_running()
            self._history.clear()
        logger.info("chat reset")

    async def _cancel_running(self) -> None:
        task, self._task = self._task, None
        self._turn_id = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _finished(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("turn crashed", exc_info=exc)

    async def _on_config(self, event: ConfigChanged) -> None:
        if "agent" in event.sections:
            self._settings = event.config.agent
        if "llm" in event.sections:
            self._llm_settings = event.config.llm
