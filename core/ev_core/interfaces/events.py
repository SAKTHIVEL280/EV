"""Bus events shared by the server, agent and llm modules.

Inbound (from the app): ChatRequested, ChatCancelRequested, ConfigGetRequested,
ConfigSetRequested, ConfigResetRequested.
Outbound (to the app): ChatStarted, ChatDelta, ChatToolChanged, ChatDone,
ChatFailed, LlmStatusChanged, ConfigStateChanged, ConfigRejected.
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
