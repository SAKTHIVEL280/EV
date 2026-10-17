"""The model catalog (CLAUDE.md §10.6, docs/FEATURES.md F-403).

``manifest.json`` (next to this file, bundled with core) lists every model EV
offers: pinned Hugging Face URL, size and SHA-256. Loading validates it
strictly, so a bad entry fails tests and the build, never a user's download.
"""

import json
from importlib import resources
from typing import Annotated, Final, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ev_core.interfaces.llm import ModelRole

MANIFEST_VERSION: Final = 1
ALLOWED_HOST: Final = "huggingface.co"


class CatalogModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.\-]{1,63}$")]
    name: Annotated[str, Field(min_length=1, max_length=40)]
    summary: Annotated[str, Field(min_length=1, max_length=80)]
    role: ModelRole
    recommended: bool
    file: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,200}\.gguf$")]
    url: str
    size_bytes: Annotated[int, Field(gt=0)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    license: str

    @field_validator("url")
    @classmethod
    def _pinned_hugging_face(cls, url: str) -> str:
        parts = urlparse(url)
        if parts.scheme != "https" or parts.hostname != ALLOWED_HOST:
            raise ValueError(f"model URLs must be https://{ALLOWED_HOST}/...")
        if "/resolve/main/" in parts.path:
            raise ValueError("model URLs must pin a revision, not main")
        return url


class Catalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_version: Literal[1]
    models: tuple[CatalogModel, ...]

    @field_validator("models")
    @classmethod
    def _unique(cls, models: tuple[CatalogModel, ...]) -> tuple[CatalogModel, ...]:
        for field in ("id", "file"):
            values = [getattr(m, field) for m in models]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate model {field}")
        if sum(m.recommended for m in models) != 1:
            raise ValueError("exactly one model must be recommended")
        return models

    def get(self, model_id: str) -> CatalogModel | None:
        return next((m for m in self.models if m.id == model_id), None)


def load_catalog(text: str | None = None) -> Catalog:
    """The bundled catalog, or one parsed from ``text`` (tests)."""
    if text is None:
        text = resources.files("ev_core.models").joinpath("manifest.json").read_text("utf-8")
    return Catalog.model_validate(json.loads(text))
