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
        description="Folder with model files. Empty: the models folder inside EV's data folder.",
    )
    model_small: str = Field(
        default="",
        title="Small model",
        description="Small model file name (Instant effort). Empty: not installed.",
    )
    model_default: str = Field(
        default="",
        title="Default model",
        description="Default model file name (Normal effort). Empty: not installed.",
    )
    model_large: str = Field(
        default="",
        title="Large model",
        description="Large model file name (Deep and Max effort). Empty: not installed.",
    )
    threads: int = Field(
        default=0,
        ge=0,
        le=256,
        title="CPU threads",
        description="CPU threads for the model. 0: automatic (physical cores minus 2, at least 2).",
    )
    context: int = Field(
        default=8192,
        ge=2048,
        le=131072,
        title="Context window",
        description="How much of the conversation the model can read at once.",
        json_schema_extra={"unit": "tokens"},
    )
    idle_unload_minutes: int = Field(
        default=10,
        ge=0,
        le=1440,
        title="Unload when idle",
        description="Free the model's memory after this long without use. 0: never.",
        json_schema_extra={"unit": "min"},
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
        description="Opens the island panel from anywhere. Empty: no shortcut.",
        json_schema_extra={
            "rule": "Use one to three of Ctrl, Alt, Shift, Super and a key, like Ctrl+Space."
        },
    )


class IslandSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    reveal_distance: int = Field(
        default=6,
        ge=0,
        le=64,
        title="Reveal distance",
        description="How near the pointer must come to open the drop. 0: touch it.",
        json_schema_extra={"unit": "px"},
    )
    reveal_delay_ms: int = Field(
        default=150,
        ge=0,
        le=1000,
        title="Reveal delay",
        description="How long the pointer must stay that close before the drop opens.",
        json_schema_extra={"unit": "ms"},
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
        description="The drop at the top of the screen.",
        json_schema_extra=_nav(Nav.APPEARANCE),
    )
    hotkeys: HotkeysSection = Field(
        default_factory=HotkeysSection,
        description="Keyboard shortcuts.",
        json_schema_extra=_nav(Nav.HOTKEYS),
    )
