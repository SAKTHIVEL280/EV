"""Language model interface: chat messages in, a stream of events out."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from ev_core.errors import EvError


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool as the model sees it."""

    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str
    """JSON text exactly as the model produced it."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int | None = None
    generated_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ReasoningDelta:
    """Thinking text (Deep and Max). Shown as 'thinking', never spoken."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolCallsReady:
    calls: tuple[ToolCall, ...]


@dataclass(frozen=True, slots=True)
class Finished:
    reason: str
    usage: Usage = field(default_factory=Usage)


type LlmEvent = TextDelta | ReasoningDelta | ToolCallsReady | Finished


class ModelRole(StrEnum):
    SMALL = "small"
    DEFAULT = "default"
    LARGE = "large"


class LlmError(EvError):
    """The model could not answer. ``code`` is a stable protocol error code."""

    def __init__(self, code: str, user_message: str, detail: str = "") -> None:
        super().__init__(user_message, detail)
        self.code = code


class LlmBackend(ABC):
    """One loaded model."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec],
        thinking: bool,
        max_tokens: int,
    ) -> AsyncIterator[LlmEvent]:
        """Stream one completion. Raises ``LlmError`` on failure. Cancelling the
        consuming task stops generation."""


class LlmProvider(ABC):
    """Gives the agent a ready model for a role, loading or switching as needed."""

    @abstractmethod
    async def acquire(self, role: ModelRole) -> LlmBackend:
        """Raises ``LlmError`` (code ``no_model`` or ``model_load_failed``)."""
