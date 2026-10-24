"""Config schema: every key, its type, default, label and description.

Adding a key is additive. Renaming or removing one needs a migration in
``ev_core.config.store.MIGRATIONS`` and a ``CURRENT_CONFIG_VERSION`` bump.

Each section field declares the Settings section it appears in (``nav``); a
key may override it. ``title`` is the label, ``description`` the one-line
explanation (docs/FEATURES.md F-410).
"""

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

CURRENT_CONFIG_VERSION: Final = 1


class Nav(StrEnum):
    """Settings sections, in order (CLAUDE.md §6.5)."""

    GENERAL = "general"
    VOICE = "voice"
    MODELS = "models"
    PERSONALITY = "personality"
    APPEARANCE = "appearance"
    HOTKEYS = "hotkeys"
    PERMISSIONS = "permissions"
    MEMORY = "memory"
    ROUTINES = "routines"
    WEB = "web"
    ADVANCED = "advanced"
    DIAGNOSTICS = "diagnostics"
    ABOUT = "about"


def _nav(nav: Nav) -> JsonDict:
    return {"nav": nav.value}


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LoggingSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    level: LogLevel = Field(
        default=LogLevel.INFO,
        title="Log detail",
        description="Log detail level: debug, info, warning or error.",
    )


class LlmSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    enabled: bool = Field(
        default=True, title="Language model", description="Run the local language model."
    )
    models_dir: str = Field(
        default="",
        title="Models folder",
        description="Where model files are kept. Default: the models folder in EV's data folder.",
        json_schema_extra={"widget": "folder"},
    )
    model_small: str = Field(
        default="",
        title="Small model",
        description="Fastest model. Used for quick commands and when nothing larger is installed.",
        json_schema_extra={"widget": "model", "role": "small"},
    )
    model_default: str = Field(
        default="",
        title="Default model",
        description="Answers most requests (Normal effort).",
        json_schema_extra={"widget": "model", "role": "default"},
    )
    model_large: str = Field(
        default="",
        title="Large model",
        description="Best answers, slower (Deep and Max effort).",
        json_schema_extra={"widget": "model", "role": "large"},
    )
    threads: int = Field(
        default=0,
        ge=0,
        le=256,
        title="CPU threads",
        description="CPU threads for the model. Automatic leaves two cores free for you.",
        json_schema_extra={"widget": "slider", "steps": [0, 2, 3, 4, 6, 8, 10, 12, 16, 24, 32]},
    )
    context: int = Field(
        default=8192,
        ge=2048,
        le=131072,
        title="Context window",
        description="How much of the conversation the model can read at once.",
        json_schema_extra={
            "unit": "tokens",
            "widget": "slider",
            "steps": [2048, 4096, 8192, 16384, 32768, 65536, 131072],
        },
    )
    idle_unload_minutes: int = Field(
        default=10,
        ge=0,
        le=1440,
        title="Unload when idle",
        description="Free the model's memory after this long without use.",
        json_schema_extra={
            "unit": "min",
            "widget": "slider",
            "steps": [0, 1, 2, 5, 10, 15, 30, 60, 120, 240, 480, 1440],
        },
    )


class EffortLevel(StrEnum):
    INSTANT = "instant"
    NORMAL = "normal"
    DEEP = "deep"
    MAX = "max"


class AgentSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    default_effort: EffortLevel = Field(
        default=EffortLevel.NORMAL,
        title="Default effort",
        description="Effort when a request doesn't name one: instant, normal, deep or max.",
    )


SHORTCUT_PATTERN: Final = (
    r"^$|^((?i:ctrl|alt|shift|super)\+){1,3}(?i:space|[a-z0-9]|f([1-9]|1[0-2]))$"
)


class HotkeysSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    open_panel: str = Field(
        default="Ctrl+Space",
        pattern=SHORTCUT_PATTERN,
        title="Open EV",
        description="Opens the island panel from anywhere.",
        json_schema_extra={
            "rule": "Use one to three of Ctrl, Alt, Shift, Super and a key, like Ctrl+Space.",
            "widget": "shortcut",
        },
    )


class Permission(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    BLOCK = "block"


def _permission(title: str, description: str, default: Permission = Permission.ASK) -> Permission:
    return Field(default=default, title=title, description=description)


class PermissionsSection(BaseModel):
    """Per-tool permissions (F-418). Allow runs actions that normally ask; actions that
    could lose data (deleting files, typing "Send" or "Buy") always ask."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    apps: Permission = _permission(
        "Apps", "Open, switch to and close apps. Closing asks unless allowed."
    )
    window: Permission = _permission(
        "Windows", "Move, snap, maximize and minimize windows.", Permission.ALLOW
    )
    system: Permission = _permission(
        "Sound, screen and radios",
        "Volume, brightness, media keys, Wi-Fi and Bluetooth. Turning Wi-Fi off asks.",
    )
    screenshot: Permission = _permission(
        "Screenshots", "Save screenshots to your Pictures folder.", Permission.ALLOW
    )
    clipboard: Permission = _permission(
        "Clipboard", "Read and replace the text you copied.", Permission.ALLOW
    )
    files: Permission = _permission(
        "Files", "Find, open and move files. Deleting always asks and goes to the Recycle Bin."
    )
    timer: Permission = _permission(
        "Timers and reminders",
        "Set, list and cancel timers, reminders and alarms.",
        Permission.ALLOW,
    )
    focus_mode: Permission = _permission(
        "Focus mode", "Keep EV quiet for a while.", Permission.ALLOW
    )
    ui: Permission = _permission(
        "Control apps",
        "Click, type and press keys in other apps. Asks once per request.",
    )


class ClipboardSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    history: bool = Field(
        default=True,
        title="Clipboard history",
        description="Remember the last 25 texts you copied, in memory only, for this session.",
    )
    actions: bool = Field(
        default=False,
        title="Clipboard actions",
        description="Offer to fix, shorten or translate text right after you copy it.",
    )


class IslandSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    reveal_distance: int = Field(
        default=6,
        ge=0,
        le=64,
        title="Reveal distance",
        description="How near the pointer must come to open the island.",
        json_schema_extra={"unit": "px", "widget": "slider"},
    )
    reveal_delay_ms: int = Field(
        default=150,
        ge=0,
        le=1000,
        title="Reveal delay",
        description="How long the pointer must stay that close before the island opens.",
        json_schema_extra={
            "unit": "ms",
            "widget": "slider",
            "steps": [0, 50, 100, 150, 200, 300, 400, 500, 750, 1000],
        },
    )
    arc_width: int = Field(
        default=56,
        ge=24,
        le=160,
        title="Island width",
        description="Width of the arc at the top of the screen when EV is resting.",
        json_schema_extra={"unit": "px", "widget": "slider"},
    )
    arc_depth: int = Field(
        default=7,
        ge=3,
        le=24,
        title="Island depth",
        description="How far the arc reaches down from the top edge.",
        json_schema_extra={"unit": "px", "widget": "slider"},
    )


class SpeakReplies(StrEnum):
    WHEN_SPOKEN = "when_spoken"
    ALWAYS = "always"
    NEVER = "never"


class Recognizer(StrEnum):
    SMALL = "small"
    TINY = "tiny"


class Voice(StrEnum):
    """Kokoro's American English voices (F-008)."""

    HEART = "af_heart"
    BELLA = "af_bella"
    NICOLE = "af_nicole"
    SARAH = "af_sarah"
    SKY = "af_sky"
    NOVA = "af_nova"
    RIVER = "af_river"
    JESSICA = "af_jessica"
    ALLOY = "af_alloy"
    AOEDE = "af_aoede"
    KORE = "af_kore"
    MICHAEL = "am_michael"
    ADAM = "am_adam"
    ERIC = "am_eric"
    LIAM = "am_liam"
    ONYX = "am_onyx"
    ECHO = "am_echo"
    FENRIR = "am_fenrir"
    PUCK = "am_puck"


def _voice_label(voice: Voice) -> str:
    gender = "female" if voice.value.startswith("af_") else "male"
    return f"{voice.name.title()} ({gender})"


class VoiceSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    enabled: bool = Field(
        default=True,
        title="Voice",
        description="Talk to EV with the hotkey or the mic button, and hear its replies.",
    )
    speak_replies: SpeakReplies = Field(
        default=SpeakReplies.WHEN_SPOKEN,
        title="Spoken replies",
        description="When EV answers out loud.",
        json_schema_extra={
            "labels": {"when_spoken": "When I speak", "always": "Always", "never": "Never"}
        },
    )
    voice: Voice = Field(
        default=Voice.HEART,
        title="Voice",
        description="How EV sounds.",
        json_schema_extra={
            "widget": "menu",
            "labels": {v.value: _voice_label(v) for v in Voice},
        },
    )
    speed: int = Field(
        default=100,
        ge=70,
        le=150,
        title="Speaking speed",
        description="How fast EV talks.",
        json_schema_extra={
            "unit": "%",
            "widget": "slider",
            "steps": [70, 80, 90, 100, 110, 120, 130, 140, 150],
        },
    )
    volume: int = Field(
        default=80,
        ge=0,
        le=100,
        title="Speaking volume",
        description="How loud EV talks, on top of the Windows volume.",
        json_schema_extra={"unit": "%", "widget": "slider"},
    )
    recognizer: Recognizer = Field(
        default=Recognizer.SMALL,
        title="Speech recognition",
        description="Small understands more; Tiny uses less memory.",
        json_schema_extra={"labels": {"small": "Small", "tiny": "Tiny"}},
    )
    follow_up: bool = Field(
        default=True,
        title="Listen for a follow-up",
        description="After a spoken reply, keep listening for 5 seconds.",
    )
    earcons_volume: int = Field(
        default=50,
        ge=0,
        le=100,
        title="Sounds",
        description="Volume of the listening, done and error sounds. 0 turns them off.",
        json_schema_extra={"unit": "%", "widget": "slider"},
    )


class EvConfig(BaseModel):
    """Root of config.toml. Each field is one [section]."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    logging: LoggingSection = Field(
        default_factory=LoggingSection,
        description="Local log files in the logs folder.",
        json_schema_extra=_nav(Nav.DIAGNOSTICS),
    )
    llm: LlmSection = Field(
        default_factory=LlmSection,
        description="Local language model (llama.cpp).",
        json_schema_extra=_nav(Nav.MODELS),
    )
    agent: AgentSection = Field(
        default_factory=AgentSection,
        description="How EV answers.",
        json_schema_extra=_nav(Nav.GENERAL),
    )
    island: IslandSection = Field(
        default_factory=IslandSection,
        description="The island at the top of the screen.",
        json_schema_extra=_nav(Nav.APPEARANCE),
    )
    hotkeys: HotkeysSection = Field(
        default_factory=HotkeysSection,
        description="Keyboard shortcuts.",
        json_schema_extra=_nav(Nav.HOTKEYS),
    )
    permissions: PermissionsSection = Field(
        default_factory=PermissionsSection,
        description="What EV may do on this PC.",
        json_schema_extra=_nav(Nav.PERMISSIONS),
    )
    clipboard: ClipboardSection = Field(
        default_factory=ClipboardSection,
        description="Copied text.",
        json_schema_extra=_nav(Nav.MEMORY),
    )
    voice: VoiceSection = Field(
        default_factory=VoiceSection,
        description="Talking with EV.",
        json_schema_extra=_nav(Nav.VOICE),
    )
