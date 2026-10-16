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


class EvConfig(BaseModel):
    """Root of config.toml. Each field is one [section]."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    logging: LoggingSection = Field(
        default_factory=LoggingSection,
        description="Local log files in the logs folder.",
    )
