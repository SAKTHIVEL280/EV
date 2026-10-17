"""Settings descriptors: everything the Settings window needs to render a key
(docs/FEATURES.md F-410), derived from the config schema so a new key needs no UI code."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from ev_core.config.schema import EvConfig, Nav
from ev_core.config.store import bounds

type SettingValue = bool | int | str
type SettingKind = Literal["boolean", "choice", "integer", "text"]


@dataclass(frozen=True, slots=True)
class SettingItem:
    section: str
    key: str
    nav: Nav
    label: str
    description: str
    kind: SettingKind
    default: SettingValue
    value: SettingValue
    options: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    unit: str | None = None
    """Shown after integer values (px, ms, min, tokens)."""


def _plain(value: object) -> SettingValue:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool | int | str):
        return value
    raise TypeError(f"unsupported setting value {value!r}")


def _declared_nav(extra: object) -> Nav | None:
    if isinstance(extra, dict) and isinstance(nav := extra.get("nav"), str):
        return Nav(nav)
    return None


def _declared_unit(extra: object) -> str | None:
    if isinstance(extra, dict) and isinstance(unit := extra.get("unit"), str):
        return unit
    return None


def describe(config: EvConfig) -> list[SettingItem]:
    """One item per config key, in schema order."""
    items: list[SettingItem] = []
    defaults = EvConfig()
    for section, section_field in EvConfig.model_fields.items():
        section_cls = section_field.annotation
        if not (isinstance(section_cls, type) and issubclass(section_cls, BaseModel)):
            raise TypeError(f"config section {section!r} must be a pydantic model")
        section_nav = _declared_nav(section_field.json_schema_extra) or Nav.ADVANCED
        for key, field in section_cls.model_fields.items():
            nav = _declared_nav(field.json_schema_extra) or section_nav
            annotation = field.annotation
            options: tuple[str, ...] = ()
            kind: SettingKind
            if annotation is bool:
                kind = "boolean"
            elif isinstance(annotation, type) and issubclass(annotation, Enum):
                kind = "choice"
                options = tuple(str(m.value) for m in annotation)
            elif annotation is int:
                kind = "integer"
            else:
                kind = "text"
            low, high = bounds(field)
            items.append(
                SettingItem(
                    section=section,
                    key=key,
                    nav=nav,
                    label=field.title or key,
                    description=field.description or "",
                    kind=kind,
                    default=_plain(getattr(getattr(defaults, section), key)),
                    value=_plain(getattr(getattr(config, section), key)),
                    options=options,
                    minimum=low,
                    maximum=high,
                    unit=_declared_unit(field.json_schema_extra),
                )
            )
    return items
