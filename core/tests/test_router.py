import json
from typing import Any

import pytest

from ev_core.agent.router import match, normalize
from ev_core.interfaces.tools import ToolResult


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
        ("What's the date and time?", "It's {time} on {date}."),
        ("what is the time and date now", "It's {time} on {date}."),
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
    reply = rule.rule.reply(ToolResult(True, json.dumps(data)))
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


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("Open Notepad", "apps", {"action": "open", "name": "notepad"}),
        ("launch google chrome please", "apps", {"action": "open", "name": "google chrome"}),
        ("switch to Spotify", "apps", {"action": "switch", "name": "spotify"}),
        ("volume up", "system", {"action": "volume", "change": 10}),
        ("Turn the volume down.", "system", {"action": "volume", "change": -10}),
        ("set volume to 30%", "system", {"action": "volume", "level": 30}),
        ("mute", "system", {"action": "mute"}),
        ("unmute the sound", "system", {"action": "unmute"}),
        ("brightness 70", "system", {"action": "brightness", "level": 70}),
        ("dimmer", "system", {"action": "brightness", "change": -10}),
        ("pause", "system", {"action": "media", "media": "play_pause"}),
        ("next song", "system", {"action": "media", "media": "next"}),
        ("previous track", "system", {"action": "media", "media": "previous"}),
        ("take a screenshot", "screenshot", {"area": "screen"}),
        ("set a timer for 10 minutes", "timer", {"action": "timer", "minutes": 10.0}),
        ("timer for half an hour", "timer", {"action": "timer", "minutes": 30.0}),
        ("set timer 90 seconds", "timer", {"action": "timer", "minutes": 1.5}),
        ("undo that", "undo_last", {}),
    ],
)
def test_pc_commands(text: str, tool: str, args: dict[str, Any]) -> None:
    found = match(text)
    assert found is not None, text
    assert (found.rule.tool, dict(found.args)) == (tool, args)


@pytest.mark.parametrize(
    "text",
    [
        "open the file I downloaded yesterday and summarize it for me in three bullet points",
        "set a timer",
        "volume",
        "what should I play next",
    ],
)
def test_pc_commands_that_go_to_the_model(text: str) -> None:
    assert match(text) is None


def test_replies_use_the_tool_message() -> None:
    found = match("mute")
    assert found is not None
    assert found.rule.reply(ToolResult(True, "{}", user_message="Muted.")) == "Muted."
    assert found.rule.reply(ToolResult(True, "{}")) == "Done."
