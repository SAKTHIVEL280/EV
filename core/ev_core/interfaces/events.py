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
    spoken: bool = False
    """The user said it (F-008): the reply is spoken too."""


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
class VoicePackInfo:
    """One voice pack and its state on this PC (F-010)."""

    id: str
    name: str
    summary: str
    kind: str
    """recognizer | speech"""
    option: str
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
    voice: tuple[VoicePackInfo, ...] = ()


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


@dataclass(frozen=True, slots=True)
class ContextCaptureRequested(Event):
    """The hotkey opened EV: read the selection in the app the user was in (F-201)."""


@dataclass(frozen=True, slots=True)
class ContextCaptured(Event):
    text: str | None
    app: str = ""
    title: str = ""


@dataclass(frozen=True, slots=True)
class ContextClearRequested(Event):
    """The user removed the selection chip."""


@dataclass(frozen=True, slots=True)
class ContextReplaceRequested(Event):
    text: str


@dataclass(frozen=True, slots=True)
class ContextReplaced(Event):
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class VoiceStartRequested(Event):
    """Open the mic (F-008): hotkey, mic button or push-to-talk."""

    source: str
    """hotkey | button | push_to_talk"""


@dataclass(frozen=True, slots=True)
class VoiceStopRequested(Event):
    reason: str
    """typing (mic off, speech stops) | closed (mic off, speech goes on) |
    button (mic off) | send (push-to-talk released: send what was heard now) |
    silence (stop speaking, keep the mic as it is)"""


@dataclass(frozen=True, slots=True)
class VoiceStateChanged(Event):
    mic: bool
    """The microphone is open (the island shows the mic indicator)."""
    speaking: bool
    message: str | None = None
    """Why voice stopped or couldn't start, in plain words."""
    code: str | None = None
    """not_installed | no_mic | mic_blocked | no_speaker | failed | no_speech"""


@dataclass(frozen=True, slots=True)
class VoiceLevel(Event):
    level: float
    """Mic level, 0..1, about 15 times a second while the mic is open."""


@dataclass(frozen=True, slots=True)
class VoiceHeard(Event):
    text: str
    final: bool
    """True once the user stopped talking: the app sends ``text`` as a spoken chat message."""
