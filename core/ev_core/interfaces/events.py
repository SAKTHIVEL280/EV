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
    """running | done | failed | blocked"""


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
