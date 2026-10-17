"""Rule router: instant answers without a model (docs/FEATURES.md F-002).

Rules are anchored to the whole request, so "what time is it in Tokyo" goes
to the model. Rules may only use `safe` tools.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class Rule:
    pattern: re.Pattern[str]
    tool: str
    reply: Callable[[Mapping[str, Any]], str]
    """Builds the answer from the tool's JSON result."""
    args: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuleMatch:
    rule: Rule


def _rule(pattern: str, tool: str, reply: Callable[[Mapping[str, Any]], str]) -> Rule:
    return Rule(re.compile(pattern), tool, reply)


RULES: Final[tuple[Rule, ...]] = (
    _rule(
        r"^(what time is it|what'?s the time|what is the time|tell me the time)( now| right now)?$",
        "current_time",
        lambda d: f"It's {d['time_text']}.",
    ),
    _rule(
        r"^(what'?s|what is) (the date|today'?s date)( today)?$|^what date is it( today)?$",
        "current_time",
        lambda d: f"It's {d['date_text']}.",
    ),
    _rule(
        r"^(what'?s|what is) (the )?(date and time|time and date)( now| right now| today)?$",
        "current_time",
        lambda d: f"It's {d['time_text']} on {d['date_text']}.",
    ),
    _rule(
        r"^what day is (it|today)( today)?$|^what'?s today$",
        "current_time",
        lambda d: f"It's {d['weekday']}.",
    ),
)


def normalize(text: str) -> str:
    """Lowercase, straight apostrophes, single spaces, no trailing punctuation."""
    text = text.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip("?.! ")


def match(text: str, rules: tuple[Rule, ...] = RULES) -> RuleMatch | None:
    normalized = normalize(text)
    for rule in rules:
        if rule.pattern.fullmatch(normalized):
            return RuleMatch(rule)
    return None
