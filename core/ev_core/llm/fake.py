"""Scripted model for tests (CLAUDE.md §5.3: every module has a fake)."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from ev_core.interfaces.llm import (
    ChatMessage,
    LlmBackend,
    LlmError,
    LlmEvent,
    LlmProvider,
    ModelRole,
    ToolSpec,
)


@dataclass
class FakeCall:
    messages: list[ChatMessage]
    tools: list[ToolSpec]
    thinking: bool
    max_tokens: int


@dataclass
class FakeBackend(LlmBackend):
    """Each stream() call plays the next script; a script item may be an exception."""

    scripts: list[list[LlmEvent | Exception]]
    name: str = "fake.gguf"
    calls: list[FakeCall] = field(default_factory=list)

    @property
    def model_name(self) -> str:
        return self.name

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec],
        thinking: bool,
        max_tokens: int,
    ) -> AsyncIterator[LlmEvent]:
        self.calls.append(FakeCall(list(messages), list(tools), thinking, max_tokens))
        if not self.scripts:
            raise LlmError(
                "model_error", "The model stopped responding. Try again.", "script exhausted"
            )
        for item in self.scripts.pop(0):
            if isinstance(item, Exception):
                raise item
            yield item


@dataclass
class FakeProvider(LlmProvider):
    backend: FakeBackend | None
    roles: list[ModelRole] = field(default_factory=list)

    async def acquire(self, role: ModelRole) -> LlmBackend:
        self.roles.append(role)
        if self.backend is None:
            raise LlmError("no_model", "No model installed. Add one in Settings.")
        return self.backend
