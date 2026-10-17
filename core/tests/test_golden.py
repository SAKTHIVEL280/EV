"""Golden tests against a real model (CLAUDE.md §10.4): fixed prompts -> expected behavior.

Skipped unless a real runtime and model are given:
    EV_GOLDEN_LLAMA_DIR=../vendor/llama.cpp/ubuntu-x64 \\
    EV_GOLDEN_MODEL=~/.local/share/EV/models/Qwen3.5-4B-Q4_K_M.gguf \\
    uv run pytest tests/test_golden.py -v
"""

import logging
import os
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from ev_core import localtime
from ev_core.agent.history import History
from ev_core.agent.loop import TurnRequest, run_turn
from ev_core.agent.toolbox import Toolbox
from ev_core.bus import Event, EventBus
from ev_core.config import EffortLevel, LlmSection
from ev_core.interfaces.events import ChatDone, ChatFailed, ChatStarted, ChatToolChanged
from ev_core.llm import LlmModule
from ev_core.modules import ModuleContext
from ev_core.tools.clock import CurrentTimeTool


def _path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else None


LLAMA_DIR = _path("EV_GOLDEN_LLAMA_DIR")
MODEL = _path("EV_GOLDEN_MODEL")

pytestmark = [
    pytest.mark.skipif(
        LLAMA_DIR is None or MODEL is None, reason="needs a real model (see docstring)"
    ),
    # One model load shared by every golden test.
    pytest.mark.asyncio(loop_scope="module"),
]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def provider(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[LlmModule]:
    assert MODEL is not None
    assert LLAMA_DIR is not None
    module = LlmModule(
        LlmSection(models_dir=str(MODEL.parent), model_default=MODEL.name, threads=8),
        tmp_path_factory.mktemp("data"),
        LLAMA_DIR,
    )
    await module.start(ModuleContext(bus=EventBus(), logger=logging.getLogger("golden")))
    yield module
    await module.stop()


async def turn(
    provider: LlmModule, text: str, effort: EffortLevel = EffortLevel.NORMAL
) -> list[Event]:
    events: list[Event] = []
    request = TurnRequest(
        "00000000-0000-4000-8000-000000000000", text, effort, 8192, time.monotonic()
    )
    await run_turn(request, provider, Toolbox([CurrentTimeTool()]), History(), events.append)
    return events


def tools_used(events: list[Event]) -> set[str]:
    return {e.name for e in events if isinstance(e, ChatToolChanged) and e.state == "done"}


def done(events: list[Event]) -> ChatDone:
    assert not [e for e in events if isinstance(e, ChatFailed)], events
    last = events[-1]
    assert isinstance(last, ChatDone)
    return last


@pytest.mark.parametrize(
    "text", ["What day of the week is it today?", "Which month and year is it right now?"]
)
async def test_time_questions_answer_from_local_time(provider: LlmModule, text: str) -> None:
    # Each message carries the local time (agent/loop.py); the answer must match it.
    events = await turn(provider, text)
    today = localtime.now()
    reply = done(events).text
    assert f"{today:%A}" in reply or f"{today:%B}" in reply, reply


@pytest.mark.parametrize(
    "text", ["In one sentence, what is a CPU?", "Say hello in one short sentence."]
)
async def test_general_questions_use_no_tools(provider: LlmModule, text: str) -> None:
    events = await turn(provider, text)
    assert tools_used(events) == set()
    assert len(done(events).text) > 5


async def test_router_question_needs_no_model(provider: LlmModule) -> None:
    events = await turn(provider, "What time is it?")
    started = events[0]
    assert isinstance(started, ChatStarted)
    assert started.model is None
    assert done(events).total_ms < 300


async def test_max_effort_thinks_and_answers(provider: LlmModule) -> None:
    events = await turn(
        provider, "What is 17 times 23? Reply with just the number.", EffortLevel.MAX
    )
    assert "391" in done(events).text


HEDGE = re.compile(
    r"not sure|don.t know|can.?n?o?t (verify|confirm|check)|no such|there is no|isn.t a nobel", re.I
)


@pytest.mark.parametrize(
    "text",
    [
        "What is the plot of the 2019 Malayalam movie Velutha Kuthira Rahasyam?",
        "Who won the Nobel Prize in Mathematics in 2023?",
        "Who is Dr. Arvind Kothapalli, the inventor of the graphene battery?",
    ],
)
async def test_made_up_facts_get_not_sure(provider: LlmModule, text: str) -> None:
    # Hallucination eval, decisions.md 2026-10-17: these do not exist.
    reply = done(await turn(provider, text)).text
    assert HEDGE.search(reply), reply


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("What is the capital of Australia?", "Canberra"),
        ("Who wrote Romeo and Juliet?", "Shakespeare"),
    ],
)
async def test_common_facts_still_answered(provider: LlmModule, text: str, answer: str) -> None:
    assert answer in done(await turn(provider, text)).text


async def test_static_prefix_fits_the_budget(provider: LlmModule) -> None:
    # CLAUDE.md §5.4: system prompt + tool list <= 1,000 tokens (plus this short message).
    tokens = done(await turn(provider, "Hi")).prompt_tokens
    assert tokens is not None
    assert tokens <= 1_050, tokens
