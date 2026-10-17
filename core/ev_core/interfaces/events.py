"""Bus events shared by the server, agent and llm modules.

Inbound (from the app): ChatRequested, ChatCancelRequested, ConfigGetRequested,
ConfigSetRequested, ConfigResetRequested, ModelsGetRequested,
ModelDownloadRequested, ModelCancelRequested.
Outbound (to the app): ChatStarted, ChatDelta, ChatToolChanged, ChatDone,
ChatFailed, LlmStatusChanged, ConfigStateChanged, ConfigRejected,
ModelsStateChanged.
Internal: ModelInstalled (the composition root fills the model's config slot).
The server forwards outbound events in publish order (the bus starts
handlers in publish order).
"""

from dataclasses import dataclass

from ev_core.bus import Event
from ev_core.config import ConfigWarning, EffortLevel
from ev_core.config.settings import SettingItem


@dataclass(frozen=True, slots=True)
class ChatRequested(Event):
    turn_id: str
    text: str
    effort: EffortLevel | None


@dataclass(frozen=True, slots=True)
class ChatCancelRequested(Event):
    turn_id: str


@dataclass(frozen=True, slots=True)
class ChatResetRequested(Event):
    """New chat (F-414): cancel any running turn and forget the conversation."""


@dataclass(frozen=True, slots=True)
class ChatStarted(Event):
    turn_id: str
    effort: EffortLevel
    model: str | None


@dataclass(frozen=True, slots=True)
class ChatDelta(Event):
    turn_id: str
    text: str


@dataclass(frozen=True, slots=True)
class ChatToolChanged(Event):
    turn_id: str
    name: str
    state: str
    """running | done | failed | blocked | asking | declined"""


@dataclass(frozen=True, slots=True)
class ChatDone(Event):
    turn_id: str
    text: str
    effort: EffortLevel
    model: str | None
    total_ms: int
    cancelled: bool
    first_token_ms: int | None = None
    prompt_tokens: int | None = None
    generated_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ChatFailed(Event):
    turn_id: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LlmStatusChanged(Event):
    state: str
    """unloaded | loading | ready | failed"""
    model: str | None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigGetRequested(Event):
    request_id: str


@dataclass(frozen=True, slots=True)
class ConfigSetRequested(Event):
    request_id: str
    section: str
    key: str
    value: bool | int | str


@dataclass(frozen=True, slots=True)
class ConfigResetRequested(Event):
    request_id: str
    section: str
    key: str


@dataclass(frozen=True, slots=True)
class ConfigStateChanged(Event):
    """Every setting with its value (docs/FEATURES.md F-410)."""

    path: str
    items: tuple[SettingItem, ...]
    warnings: tuple[ConfigWarning, ...]
    reply_to: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigRejected(Event):
    section: str
    key: str
    message: str
    reply_to: str | None = None


@dataclass(frozen=True, slots=True)
class ModelsGetRequested(Event):
    request_id: str


@dataclass(frozen=True, slots=True)
class ModelDownloadRequested(Event):
    request_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class ModelCancelRequested(Event):
    request_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """One catalog model and its state on this PC (docs/FEATURES.md F-403)."""

    id: str
    name: str
    summary: str
    role: str
    """small | default | large"""
    recommended: bool
    file: str
    size_bytes: int
    state: str
    """available | partial | downloading | verifying | installed | failed"""
    received_bytes: int
    bytes_per_second: int
    error: str | None


@dataclass(frozen=True, slots=True)
class ModelsStateChanged(Event):
    models_dir: str
    models: tuple[ModelInfo, ...]
    reply_to: str | None = None
    other_files: tuple[str, ...] = ()
    """``.gguf`` files in the models folder that are not catalog models."""


@dataclass(frozen=True, slots=True)
class ModelInstalled(Event):
    model_id: str
    file: str
    role: str


@dataclass(frozen=True, slots=True)
class ToolConfirmRequested(Event):
    """A confirm/dangerous step waits for the user's yes or no (F-418)."""

    turn_id: str
    request_id: str
    tool: str
    question: str
    risk: str
    """confirm | dangerous"""


@dataclass(frozen=True, slots=True)
class ToolAnswered(Event):
    request_id: str
    allowed: bool


@dataclass(frozen=True, slots=True)
class ToolConfirmClosed(Event):
    """The question is gone: answered, timed out or its request was cancelled."""

    request_id: str
    allowed: bool


@dataclass(frozen=True, slots=True)
class ActionRecorded(Event):
    """An action that changed something was logged (F-111)."""

    turn_id: str
    action_id: int
    tool: str
    summary: str
    undoable: bool


@dataclass(frozen=True, slots=True)
class UndoRequested(Event):
    """Undo one action (the island's Undo button), or the latest when None."""

    action_id: int | None


@dataclass(frozen=True, slots=True)
class FocusModeChanged(Event):
    on: bool
    minutes: int | None


@dataclass(frozen=True, slots=True)
class TimerFired(Event):
    """A timer, reminder or alarm came due (F-108). `missed`: it came due while EV was off."""

    timer_id: int
    kind: str
    label: str
    missed: bool


@dataclass(frozen=True, slots=True)
class ActionUndone(Event):
    """Result of an undo the island asked for (F-111)."""

    action_id: int
    ok: bool
    message: str
