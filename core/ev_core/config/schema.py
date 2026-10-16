"""Config schema: every key, its type, default and description.

Adding a key is additive. Renaming or removing one needs a migration in
``ev_core.config.store.MIGRATIONS`` and a ``CURRENT_CONFIG_VERSION`` bump.
"""

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

CURRENT_CONFIG_VERSION: Final = 1


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LoggingSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Log detail level: debug, info, warning or error.",
    )


class LlmSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    enabled: bool = Field(default=True, description="Run the local language model.")
    models_dir: str = Field(
        default="",
        description="Folder with model files. Empty: the models folder inside EV's data folder.",
    )
    model_small: str = Field(
        default="", description="Small model file name (Instant effort). Empty: not installed."
    )
    model_default: str = Field(
        default="", description="Default model file name (Normal effort). Empty: not installed."
    )
    model_large: str = Field(
        default="", description="Large model file name (Deep and Max effort). Empty: not installed."
    )
    threads: int = Field(
        default=0,
        ge=0,
        le=256,
        description="CPU threads for the model. 0: automatic (physical cores minus 2, at least 2).",
    )
    context: int = Field(default=8192, ge=2048, le=131072, description="Context window in tokens.")
    idle_unload_minutes: int = Field(
        default=10,
        ge=0,
        le=1440,
        description="Unload the model after this many idle minutes. 0: never.",
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
        description="Effort when a request doesn't name one: instant, normal, deep or max.",
    )


class EvConfig(BaseModel):
    """Root of config.toml. Each field is one [section]."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    logging: LoggingSection = Field(
        default_factory=LoggingSection,
        description="Local log files in the logs folder.",
    )
    llm: LlmSection = Field(
        default_factory=LlmSection,
        description="Local language model (llama.cpp).",
    )
    agent: AgentSection = Field(
        default_factory=AgentSection,
        description="How EV answers.",
    )
