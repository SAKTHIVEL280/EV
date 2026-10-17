"""Pure helpers shared by the PC tools: name matching, window placement math,
dates. No OS calls, so every rule is unit-tested."""

import re
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Final

from ev_core.interfaces.pc import Placement, Rect, WindowState

# Spoken names that differ from the app's own name.
ALIASES: Final[dict[str, str]] = {
    "chrome": "google chrome",
    "browser": "google chrome",
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "code": "visual studio code",
    "explorer": "file explorer",
    "files": "file explorer",
    "file manager": "file explorer",
    "word": "microsoft word",
    "excel": "microsoft excel",
    "powerpoint": "microsoft powerpoint",
    "edge": "microsoft edge",
    "calc": "calculator",
    "terminal": "windows terminal",
    "settings": "settings",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def match_score(query: str, candidate: str) -> float:
    """0 (no match) to 1 (same name). Word-based, so "code" doesn't match "barcode"."""
    q = " ".join(_words(ALIASES.get(query.strip().lower(), query)))
    c = " ".join(_words(candidate))
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    q_words, c_words = q.split(), c.split()
    if c.startswith(q + " ") or c.endswith(" " + q):
        return 0.9
    common = len(set(q_words) & set(c_words))
    if common == 0:
        return 0.0
    return 0.8 * common / max(len(q_words), len(c_words))


def best_match(query: str, candidates: Sequence[str], threshold: float = 0.4) -> int | None:
    """Index of the best-matching candidate, or None when nothing is close enough."""
    scored = [(match_score(query, c), -len(c), i) for i, c in enumerate(candidates)]
    if not scored:
        return None
    score, _, index = max(scored)
    return index if score >= threshold else None


def placement(work: Rect, where: Placement) -> tuple[Rect | None, WindowState]:
    """Target rectangle (None: keep) and state for snapping a window in `work`."""
    w, h = work.width, work.height
    half_w, half_h = w // 2, h // 2
    x, y = work.left, work.top
    match where:
        case Placement.MAXIMIZE:
            return None, WindowState.MAXIMIZED
        case Placement.MINIMIZE:
            return None, WindowState.MINIMIZED
        case Placement.RESTORE:
            return None, WindowState.NORMAL
        case Placement.LEFT:
            return Rect(x, y, half_w, h), WindowState.NORMAL
        case Placement.RIGHT:
            return Rect(x + half_w, y, w - half_w, h), WindowState.NORMAL
        case Placement.TOP:
            return Rect(x, y, w, half_h), WindowState.NORMAL
        case Placement.BOTTOM:
            return Rect(x, y + half_h, w, h - half_h), WindowState.NORMAL
        case Placement.TOP_LEFT:
            return Rect(x, y, half_w, half_h), WindowState.NORMAL
        case Placement.TOP_RIGHT:
            return Rect(x + half_w, y, w - half_w, half_h), WindowState.NORMAL
        case Placement.BOTTOM_LEFT:
            return Rect(x, y + half_h, half_w, h - half_h), WindowState.NORMAL
        case Placement.BOTTOM_RIGHT:
            return Rect(x + half_w, y + half_h, w - half_w, h - half_h), WindowState.NORMAL
        case Placement.CENTER:
            cw, ch = w * 2 // 3, h * 2 // 3
            return Rect(x + (w - cw) // 2, y + (h - ch) // 2, cw, ch), WindowState.NORMAL


def parse_day(text: str, today: date) -> date:
    """ "today", "tomorrow", "yesterday" or YYYY-MM-DD."""
    word = text.strip().lower()
    if word in ("", "today", "now"):
        return today
    if word == "tomorrow":
        return today + timedelta(days=1)
    if word == "yesterday":
        return today - timedelta(days=1)
    return date.fromisoformat(word)


def parse_when(text: str, now: datetime) -> datetime:
    """A local time for reminders: "17:00", "5 pm", "tomorrow 9:00", or ISO
    "2026-10-17T17:00". A bare time already past today means tomorrow."""
    raw = text.strip().lower()
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        pass
    else:
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=now.tzinfo)
    day = now.date()
    explicit_day = False
    for word, offset in (("tomorrow", 1), ("today", 0)):
        if raw.startswith(word):
            day += timedelta(days=offset)
            raw = raw[len(word) :].strip().removeprefix("at").strip()
            explicit_day = True
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw)
    if match is None:
        raise ValueError(f"not a time: {text!r}")
    hour, minute = int(match[1]), int(match[2] or 0)
    if match[3] == "pm" and hour < 12:
        hour += 12
    if match[3] == "am" and hour == 12:
        hour = 0
    when = datetime.combine(day, time(hour, minute), tzinfo=now.tzinfo)
    if not explicit_day and when <= now:
        when += timedelta(days=1)
    return when


def say_duration(seconds: float) -> str:
    """ "10 minutes", "1 hour 30 minutes", "45 seconds"."""
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs and not hours:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return " ".join(parts) or "0 seconds"
