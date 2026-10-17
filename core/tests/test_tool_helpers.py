from datetime import date, datetime, timedelta, timezone

import pytest

from ev_core.interfaces.pc import Placement, Rect, WindowState
from ev_core.tools.helpers import (
    best_match,
    match_score,
    parse_day,
    parse_when,
    placement,
    say_duration,
)

APPS = ["Notepad", "Google Chrome", "Visual Studio Code", "Barcode Scanner", "Calculator"]
IST = timezone(timedelta(hours=5, minutes=30))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("notepad", "Notepad"),
        ("Chrome", "Google Chrome"),
        ("vs code", "Visual Studio Code"),
        ("code", "Visual Studio Code"),
        ("calc", "Calculator"),
        ("the calculator", "Calculator"),
        ("spotify", None),
        ("", None),
    ],
)
def test_app_names(query: str, expected: str | None) -> None:
    index = best_match(query, APPS)
    assert (APPS[index] if index is not None else None) == expected


def test_words_not_letters() -> None:
    assert match_score("code", "Barcode Scanner") == 0
    assert match_score("Notepad", "notepad") == 1


WORK = Rect(0, 0, 1920, 1032)


@pytest.mark.parametrize(
    ("where", "rect", "state"),
    [
        (Placement.LEFT, Rect(0, 0, 960, 1032), WindowState.NORMAL),
        (Placement.RIGHT, Rect(960, 0, 960, 1032), WindowState.NORMAL),
        (Placement.TOP, Rect(0, 0, 1920, 516), WindowState.NORMAL),
        (Placement.BOTTOM_RIGHT, Rect(960, 516, 960, 516), WindowState.NORMAL),
        (Placement.CENTER, Rect(320, 172, 1280, 688), WindowState.NORMAL),
        (Placement.MAXIMIZE, None, WindowState.MAXIMIZED),
        (Placement.MINIMIZE, None, WindowState.MINIMIZED),
        (Placement.RESTORE, None, WindowState.NORMAL),
    ],
)
def test_placement(where: Placement, rect: Rect | None, state: WindowState) -> None:
    assert placement(WORK, where) == (rect, state)


def test_placement_on_a_second_monitor_with_odd_size() -> None:
    rect, _ = placement(Rect(1920, 0, 1281, 721), Placement.RIGHT)
    assert rect == Rect(2560, 0, 641, 721)


def test_days() -> None:
    today = date(2026, 10, 17)
    assert parse_day("today", today) == today
    assert parse_day("Tomorrow", today) == date(2026, 10, 18)
    assert parse_day("2026-12-25", today) == date(2026, 12, 25)
    with pytest.raises(ValueError, match="Invalid isoformat"):
        parse_day("someday", today)


NOW = datetime(2026, 10, 17, 15, 41, tzinfo=IST)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("17:00", datetime(2026, 10, 17, 17, 0, tzinfo=IST)),
        ("5 pm", datetime(2026, 10, 17, 17, 0, tzinfo=IST)),
        ("9", datetime(2026, 10, 18, 9, 0, tzinfo=IST)),  # 9:00 has passed: tomorrow
        ("12 am", datetime(2026, 10, 18, 0, 0, tzinfo=IST)),
        ("tomorrow 9:30", datetime(2026, 10, 18, 9, 30, tzinfo=IST)),
        ("tomorrow at 7 am", datetime(2026, 10, 18, 7, 0, tzinfo=IST)),
        ("2026-10-20T08:15", datetime(2026, 10, 20, 8, 15, tzinfo=IST)),
    ],
)
def test_when(text: str, expected: datetime) -> None:
    assert parse_when(text, NOW) == expected


def test_when_rejects_nonsense() -> None:
    with pytest.raises(ValueError, match="not a time"):
        parse_when("whenever", NOW)


def test_durations() -> None:
    assert say_duration(600) == "10 minutes"
    assert say_duration(5400) == "1 hour 30 minutes"
    assert say_duration(45) == "45 seconds"
    assert say_duration(61) == "1 minute 1 second"
    assert say_duration(3601) == "1 hour"
