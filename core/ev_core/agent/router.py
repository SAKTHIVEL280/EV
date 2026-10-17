"""Rule router: instant answers without a model (docs/FEATURES.md F-002).

Rules are anchored to the whole request, so "what time is it in Tokyo" goes
to the model. A rule names a tool and builds its arguments from the match; the
call goes through the toolbox like any other, so permissions still apply, and
only calls whose risk is `safe` are made from here (anything else goes to the
model, which asks).
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from ev_core.interfaces.tools import ToolResult

type Args = Callable[[re.Match[str]], Mapping[str, Any]]
type Reply = Callable[[ToolResult], str]


def _said(result: ToolResult) -> str:
    return result.user_message or "Done."


def _clock(field: str, template: str) -> Reply:
    def reply(result: ToolResult) -> str:
        data = json.loads(result.content)
        return template.format(**{k: data[k] for k in ("time_text", "date_text", "weekday")})

    reply.__name__ = f"clock_{field}"
    return reply


@dataclass(frozen=True, slots=True)
class Rule:
    pattern: re.Pattern[str]
    tool: str
    args: Args
    reply: Reply = _said


@dataclass(frozen=True, slots=True)
class RuleMatch:
    rule: Rule
    args: Mapping[str, Any]


def _rule(pattern: str, tool: str, args: Args | None = None, reply: Reply = _said) -> Rule:
    return Rule(re.compile(pattern), tool, args or (lambda _m: {}), reply)


_UNITS: Final = {"second": 1 / 60, "minute": 1, "hour": 60}
_NUMBERS: Final = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10,
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty five": 45, "half an": 0.5,
}  # fmt: skip


def _minutes(m: re.Match[str]) -> Mapping[str, Any]:
    raw = m["n"]
    amount = float(raw) if raw[0].isdigit() else _NUMBERS[raw]
    unit = m["unit"].rstrip("s")
    return {"action": "timer", "minutes": round(amount * _UNITS[unit], 3)}


_APP = r"(?P<app>[a-z0-9][a-z0-9 .+'-]{0,40}?)"
_PLEASE = r"(?: please)?"

RULES: Final[tuple[Rule, ...]] = (
    # Date and time (the clock tool; every message also carries the time).
    _rule(
        r"^(what time is it|what'?s the time|what is the time|tell me the time)( now| right now)?$",
        "current_time",
        reply=_clock("time", "It's {time_text}."),
    ),
    _rule(
        r"^(what'?s|what is) (the date|today'?s date)( today)?$|^what date is it( today)?$",
        "current_time",
        reply=_clock("date", "It's {date_text}."),
    ),
    _rule(
        r"^(what'?s|what is) (the )?(date and time|time and date)( now| right now| today)?$",
        "current_time",
        reply=_clock("both", "It's {time_text} on {date_text}."),
    ),
    _rule(
        r"^what day is (it|today)( today)?$|^what'?s today$",
        "current_time",
        reply=_clock("day", "It's {weekday}."),
    ),
    # Apps (F-101).
    _rule(
        rf"^(open|launch|start|run) {_APP}{_PLEASE}$",
        "apps",
        lambda m: {"action": "open", "name": m["app"]},
    ),
    _rule(
        rf"^(switch to|go to|bring up|show me) {_APP}{_PLEASE}$",
        "apps",
        lambda m: {"action": "switch", "name": m["app"]},
    ),
    # Sound, screen, media (F-103).
    _rule(
        r"^(turn (the )?volume up|volume up|louder|turn it up)$",
        "system",
        lambda _m: {"action": "volume", "change": 10},
    ),
    _rule(
        r"^(turn (the )?volume down|volume down|quieter|turn it down)$",
        "system",
        lambda _m: {"action": "volume", "change": -10},
    ),
    _rule(
        r"^(set (the )?volume to|volume( to)?) (?P<n>\d{1,3})( ?%| percent)?$",
        "system",
        lambda m: {"action": "volume", "level": int(m["n"])},
    ),
    _rule(r"^(mute|mute (the )?(sound|volume|audio))$", "system", lambda _m: {"action": "mute"}),
    _rule(
        r"^(unmute|unmute (the )?(sound|volume|audio))$", "system", lambda _m: {"action": "unmute"}
    ),
    _rule(
        r"^(set (the )?brightness to|brightness( to)?) (?P<n>\d{1,3})( ?%| percent)?$",
        "system",
        lambda m: {"action": "brightness", "level": int(m["n"])},
    ),
    _rule(
        r"^(brightness up|brighter|turn (the )?brightness up)$",
        "system",
        lambda _m: {"action": "brightness", "change": 10},
    ),
    _rule(
        r"^(brightness down|dimmer|dim the screen|turn (the )?brightness down)$",
        "system",
        lambda _m: {"action": "brightness", "change": -10},
    ),
    _rule(
        r"^(pause|play|resume|play music|pause (the )?music|pause it|play it)$",
        "system",
        lambda _m: {"action": "media", "media": "play_pause"},
    ),
    _rule(
        r"^(next|skip|next (song|track)|skip (this )?(song|track))$",
        "system",
        lambda _m: {"action": "media", "media": "next"},
    ),
    _rule(
        r"^(previous|previous (song|track)|go back a (song|track))$",
        "system",
        lambda _m: {"action": "media", "media": "previous"},
    ),
    # Screenshots, timers, undo (F-105, F-108, F-111).
    _rule(
        r"^(take a )?screenshot$|^take a screenshot$", "screenshot", lambda _m: {"area": "screen"}
    ),
    _rule(
        r"^(set (a )?timer (for )?|timer (for )?)(?P<n>\d+(\.\d+)?|a|an|one|two|three|four|five|ten"
        r"|fifteen|twenty|thirty|forty five|half an) (?P<unit>seconds?|minutes?|hours?)$",
        "timer",
        _minutes,
    ),
    _rule(r"^undo( that| it| the last (one|thing|change))?$", "undo_last"),
)


def normalize(text: str) -> str:
    """Lowercase, straight apostrophes, single spaces, no trailing punctuation."""
    text = text.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip("?.! ")


def match(text: str, rules: tuple[Rule, ...] = RULES) -> RuleMatch | None:
    normalized = normalize(text)
    for rule in rules:
        found = rule.pattern.fullmatch(normalized)
        if found:
            return RuleMatch(rule, rule.args(found))
    return None
