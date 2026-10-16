"""Effort levels (CLAUDE.md §5.5, docs/FEATURES.md F-003)."""

import re
from dataclasses import dataclass
from typing import Final

from ev_core.config import EffortLevel
from ev_core.interfaces.llm import ModelRole


@dataclass(frozen=True, slots=True)
class EffortPolicy:
    role: ModelRole
    thinking: bool
    max_steps: int
    max_tokens: int
    """Per model call; thinking levels need room for reasoning."""


POLICIES: Final[dict[EffortLevel, EffortPolicy]] = {
    EffortLevel.INSTANT: EffortPolicy(ModelRole.SMALL, thinking=False, max_steps=1, max_tokens=512),
    EffortLevel.NORMAL: EffortPolicy(
        ModelRole.DEFAULT, thinking=False, max_steps=5, max_tokens=1024
    ),
    EffortLevel.DEEP: EffortPolicy(ModelRole.LARGE, thinking=True, max_steps=15, max_tokens=4096),
    EffortLevel.MAX: EffortPolicy(ModelRole.LARGE, thinking=True, max_steps=40, max_tokens=4096),
}

_PREFIX: Final = re.compile(
    r"^\s*(?P<level>instant|quick|normal|deep|max)\s+effort\s*[,:]\s*(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_ALIASES: Final = {"quick": EffortLevel.INSTANT}


def parse_prefix(text: str) -> tuple[EffortLevel | None, str]:
    """Split "max effort, plan my week" into (MAX, "plan my week").

    Text without a recognised prefix is returned unchanged with no level.
    """
    match = _PREFIX.match(text)
    if match is None:
        return None, text
    word = match["level"].lower()
    return _ALIASES.get(word) or EffortLevel(word), match["rest"].strip()
