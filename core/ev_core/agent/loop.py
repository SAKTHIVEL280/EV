"""One chat turn (CLAUDE.md §5.4): router, or model steps with tool calls,
streamed as bus events. Pure logic over interfaces; tested with fakes."""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from ev_core.agent import router
from ev_core.agent.effort import POLICIES
from ev_core.agent.history import History, budget_chars
from ev_core.agent.prompt import SYSTEM_PROMPT
from ev_core.agent.toolbox import Toolbox
from ev_core.bus import Event
from ev_core.config import EffortLevel
from ev_core.interfaces.events import ChatDelta, ChatDone, ChatFailed, ChatStarted, ChatToolChanged
from ev_core.interfaces.llm import (
    ChatMessage,
    Finished,
    LlmError,
    LlmProvider,
    TextDelta,
    ToolCall,
    ToolCallsReady,
)
from ev_core.interfaces.tools import Risk

ROUTER_FAILED_TEXT: Final = "Couldn't do that."
STEP_LIMIT_TEXT: Final = (
    "I stopped there: this request needs more steps than this effort level allows."
)


@dataclass(frozen=True, slots=True)
class TurnRequest:
    turn_id: str
    text: str
    effort: EffortLevel
    context_tokens: int
    received_at: float
    """time.monotonic() when the request arrived."""


def _ms(since: float) -> int:
    return round((time.monotonic() - since) * 1000)


async def run_turn(
    request: TurnRequest,
    provider: LlmProvider,
    toolbox: Toolbox,
    history: History,
    emit: Callable[[Event], None],
) -> None:
    rule = router.match(request.text)
    if rule is not None:
        await _run_router(request, rule, toolbox, history, emit)
        return

    policy = POLICIES[request.effort]
    try:
        backend = await provider.acquire(policy.role)
    except LlmError as exc:
        emit(ChatFailed(request.turn_id, exc.code, exc.user_message))
        return

    emit(ChatStarted(request.turn_id, request.effort, backend.model_name))
    user = ChatMessage("user", request.text)
    prior = history.window(budget_chars(request.context_tokens, policy.max_tokens))
    turn: list[ChatMessage] = [user]
    reply: list[str] = []
    first_token_ms: int | None = None
    prompt_tokens = generated_tokens = 0
    # A single step cannot follow up on a tool result, so Instant gets no tools.
    tools = toolbox.specs() if policy.max_steps > 1 else []

    try:
        for _ in range(policy.max_steps):
            step_text: list[str] = []
            calls: tuple[ToolCall, ...] = ()
            messages = [ChatMessage("system", SYSTEM_PROMPT), *prior, *turn]
            async for event in backend.stream(
                messages, tools=tools, thinking=policy.thinking, max_tokens=policy.max_tokens
            ):
                if isinstance(event, TextDelta):
                    if first_token_ms is None:
                        first_token_ms = _ms(request.received_at)
                    step_text.append(event.text)
                    reply.append(event.text)
                    emit(ChatDelta(request.turn_id, event.text))
                elif isinstance(event, ToolCallsReady):
                    calls = event.calls
                elif isinstance(event, Finished):
                    prompt_tokens += event.usage.prompt_tokens or 0
                    generated_tokens += event.usage.generated_tokens or 0
            turn.append(ChatMessage("assistant", "".join(step_text), tool_calls=calls))
            if not calls:
                break
            for call in calls:
                result = await toolbox.execute(request.turn_id, call, emit)
                turn.append(ChatMessage("tool", result.content, tool_call_id=call.id))
        else:
            note = ("\n\n" if reply else "") + STEP_LIMIT_TEXT
            reply.append(note)
            emit(ChatDelta(request.turn_id, note))
            turn.append(ChatMessage("assistant", note))
    except LlmError as exc:
        emit(ChatFailed(request.turn_id, exc.code, exc.user_message))
        return
    except asyncio.CancelledError:
        _done(
            request,
            backend.model_name,
            reply,
            first_token_ms,
            prompt_tokens,
            generated_tokens,
            emit,
            cancelled=True,
        )
        history.add_turn([user, ChatMessage("assistant", "".join(reply))])
        raise

    _done(
        request,
        backend.model_name,
        reply,
        first_token_ms,
        prompt_tokens,
        generated_tokens,
        emit,
        cancelled=False,
    )
    history.add_turn(turn)


def _done(
    request: TurnRequest,
    model: str,
    reply: list[str],
    first_token_ms: int | None,
    prompt_tokens: int,
    generated_tokens: int,
    emit: Callable[[Event], None],
    *,
    cancelled: bool,
) -> None:
    emit(
        ChatDone(
            turn_id=request.turn_id,
            text="".join(reply),
            effort=request.effort,
            model=model,
            total_ms=_ms(request.received_at),
            cancelled=cancelled,
            first_token_ms=first_token_ms,
            prompt_tokens=prompt_tokens or None,
            generated_tokens=generated_tokens or None,
        )
    )


async def _run_router(
    request: TurnRequest,
    rule: router.RuleMatch,
    toolbox: Toolbox,
    history: History,
    emit: Callable[[Event], None],
) -> None:
    tool_name = rule.rule.tool
    emit(ChatStarted(request.turn_id, EffortLevel.INSTANT, None))
    call = ToolCall(id="router", name=tool_name, arguments=json.dumps(dict(rule.rule.args)))
    tool = toolbox.get(tool_name)
    if tool is None or tool.risk is not Risk.SAFE:
        emit(ChatToolChanged(request.turn_id, tool_name, "failed"))
        text = ROUTER_FAILED_TEXT
    else:
        result = await toolbox.execute(request.turn_id, call, emit)
        text = rule.rule.reply(json.loads(result.content)) if result.ok else ROUTER_FAILED_TEXT
    emit(ChatDelta(request.turn_id, text))
    emit(
        ChatDone(
            turn_id=request.turn_id,
            text=text,
            effort=EffortLevel.INSTANT,
            model=None,
            total_ms=_ms(request.received_at),
            cancelled=False,
            first_token_ms=_ms(request.received_at),
        )
    )
    history.add_turn([ChatMessage("user", request.text), ChatMessage("assistant", text)])
