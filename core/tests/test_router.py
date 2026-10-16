import pytest

from ev_core.agent.router import match, normalize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What time is it?", "It's {time}."),
        ("what's the time", "It's {time}."),
        ("What\N{RIGHT SINGLE QUOTATION MARK}s the time now?", "It's {time}."),
        ("  tell me   the time ", "It's {time}."),
        ("what is the date today?", "It's {date}."),
        ("What's today's date", "It's {date}."),
        ("what date is it", "It's {date}."),
        ("What day is it?", "It's {weekday}."),
        ("what's today", "It's {weekday}."),
    ],
)
def test_matches(text: str, expected: str) -> None:
    rule = match(text)
    assert rule is not None
    data = {
        "time_text": "3:41 PM",
        "date_text": "Saturday, October 17, 2026",
        "weekday": "Saturday",
    }
    reply = rule.rule.reply(data)
    assert reply == expected.format(
        time="3:41 PM", date="Saturday, October 17, 2026", weekday="Saturday"
    )
    assert rule.rule.tool == "current_time"


@pytest.mark.parametrize(
    "text",
    [
        "what time is it in Tokyo",
        "what time is the meeting",
        "remind me what time it is later",
        "what's the date of the election",
        "time",
        "",
    ],
)
def test_no_match(text: str) -> None:
    assert match(text) is None


def test_normalize() -> None:
    assert normalize("  What\N{RIGHT SINGLE QUOTATION MARK}S   THE time?! ") == "what's the time"
