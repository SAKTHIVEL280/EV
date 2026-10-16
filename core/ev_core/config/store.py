"""Load, validate, migrate and write config.toml (docs/ARCHITECTURE.md §4.3).

Guarantees:
- Never raises on bad user input. Invalid values fall back to their default and
  produce a ``ConfigWarning``; a file that is not valid TOML is left untouched
  and defaults are used in memory.
- Unknown keys and comments are preserved whenever the file is rewritten.
- Before a migration rewrites the file, the original is copied to
  ``config.toml.bak-v<N>``.
"""

import json
import logging
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import tomlkit
from pydantic import BaseModel, ValidationError
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

from ev_core.config.schema import CURRENT_CONFIG_VERSION, EvConfig

logger = logging.getLogger(__name__)

VERSION_KEY: Final = "config_version"
FILE_HEADER: Final = (
    "EV configuration. Changes apply instantly.",
    "Invalid values fall back to their defaults and show a warning in Settings > Diagnostics.",
)

type Migration = Callable[[TOMLDocument], None]
"""Mutates a document from version N to N + 1 in place (do not set config_version)."""

# Key N migrates a version-N document to version N + 1.
MIGRATIONS: Final[Mapping[int, Migration]] = {}


@dataclass(frozen=True, slots=True)
class ConfigWarning:
    key: str
    message: str


@dataclass(frozen=True, slots=True)
class LoadedConfig:
    config: EvConfig
    warnings: tuple[ConfigWarning, ...]


class ConfigStore:
    def __init__(
        self,
        path: Path,
        *,
        migrations: Mapping[int, Migration] = MIGRATIONS,
        current_version: int = CURRENT_CONFIG_VERSION,
    ) -> None:
        self.path = path
        self._migrations = migrations
        self._current_version = current_version

    def load(self) -> LoadedConfig:
        if not self.path.exists():
            self._write(default_document(self._current_version))
            return LoadedConfig(EvConfig(), ())

        try:
            doc = tomlkit.parse(self.path.read_text(encoding="utf-8"))
        except (TOMLKitError, UnicodeDecodeError) as exc:
            logger.warning("config.toml is not valid TOML", extra={"fields": {"error": str(exc)}})
            return LoadedConfig(
                EvConfig(),
                (
                    ConfigWarning(
                        "", "config.toml has a syntax error. Using defaults until it's fixed."
                    ),
                ),
            )

        warnings: list[ConfigWarning] = []
        version = self._read_version(doc, warnings)
        if version < self._current_version:
            migrated = self._migrate(doc, version, warnings)
            if not migrated:
                return LoadedConfig(EvConfig(), tuple(warnings))
        elif version > self._current_version:
            warnings.append(
                ConfigWarning(
                    VERSION_KEY,
                    "config.toml was written by a newer EV. Unknown settings are ignored.",
                )
            )

        config = validate(doc.unwrap(), warnings)
        return LoadedConfig(config, tuple(warnings))

    def _read_version(self, doc: TOMLDocument, warnings: list[ConfigWarning]) -> int:
        raw = doc.get(VERSION_KEY)
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1:
            return raw
        warnings.append(
            ConfigWarning(VERSION_KEY, f"Missing or invalid. Treated as {self._current_version}.")
        )
        return self._current_version

    def _migrate(self, doc: TOMLDocument, version: int, warnings: list[ConfigWarning]) -> bool:
        backup = self.path.with_name(f"{self.path.name}.bak-v{version}")
        shutil.copy2(self.path, backup)
        for step in range(version, self._current_version):
            migration = self._migrations.get(step)
            if migration is None:
                logger.error("config migration missing", extra={"fields": {"from": step}})
                warnings.append(
                    ConfigWarning(VERSION_KEY, "config.toml couldn't be upgraded. Using defaults.")
                )
                return False
            migration(doc)
        doc[VERSION_KEY] = self._current_version
        self._write(doc)
        logger.info(
            "config migrated",
            extra={"fields": {"from": version, "to": self._current_version, "backup": str(backup)}},
        )
        return True

    def _write(self, doc: TOMLDocument) -> None:
        """Atomic write: temp file in the same folder, then replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        tmp.write_text(tomlkit.dumps(doc), encoding="utf-8")
        tmp.replace(self.path)


def validate(data: Mapping[str, Any], warnings: list[ConfigWarning]) -> EvConfig:
    """Build an ``EvConfig``, replacing each invalid value with its default."""
    sections: dict[str, BaseModel] = {}
    for section_name, section_field in EvConfig.model_fields.items():
        section_cls = section_field.annotation
        if not (isinstance(section_cls, type) and issubclass(section_cls, BaseModel)):
            raise TypeError(f"config section {section_name!r} must be a pydantic model")
        raw = data.get(section_name, {})
        if not isinstance(raw, Mapping):
            warnings.append(ConfigWarning(section_name, "Must be a [section]. Using defaults."))
            raw = {}
        sections[section_name] = _validate_section(section_name, section_cls, raw, warnings)
    return EvConfig.model_validate(sections)


def _validate_section(
    section_name: str,
    section_cls: type[BaseModel],
    raw: Mapping[str, Any],
    warnings: list[ConfigWarning],
) -> BaseModel:
    values: dict[str, Any] = {}
    for key, field in section_cls.model_fields.items():
        if key not in raw:
            continue
        try:
            # Validate this key alone, in strict JSON mode: no "5" -> 5 or
            # true -> 1 coercion, but enum values given as strings are accepted.
            # TOML values map onto JSON types; any that don't (dates) are invalid
            # for every current key.
            single = section_cls.model_validate_json(json.dumps({key: raw[key]}), strict=True)
            values[key] = getattr(single, key)
        except (ValidationError, TypeError):
            default = field.get_default(call_default_factory=True)
            warnings.append(
                ConfigWarning(
                    f"{section_name}.{key}",
                    f"Invalid value {raw[key]!r}. Using default {_display(default)!r}.",
                )
            )
    return section_cls.model_validate(values)


def default_document(version: int = CURRENT_CONFIG_VERSION) -> TOMLDocument:
    """A commented config.toml holding every default value."""
    doc = tomlkit.document()
    for line in FILE_HEADER:
        doc.add(tomlkit.comment(line))
    doc.add(VERSION_KEY, version)
    defaults = EvConfig().model_dump(mode="json")
    for section_name, section_field in EvConfig.model_fields.items():
        section_cls = section_field.annotation
        if not (isinstance(section_cls, type) and issubclass(section_cls, BaseModel)):
            raise TypeError(f"config section {section_name!r} must be a pydantic model")
        table: Table = tomlkit.table()
        if section_field.description:
            table.comment(section_field.description)
        for key, field in section_cls.model_fields.items():
            if field.description:
                table.add(tomlkit.comment(field.description))
            table.add(key, defaults[section_name][key])
        doc.add(tomlkit.nl())
        doc.add(section_name, table)
    return doc


def _display(value: object) -> object:
    return value.value if hasattr(value, "value") else value
