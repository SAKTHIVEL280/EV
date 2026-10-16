import json
import logging
from datetime import UTC, datetime, timedelta, timezone

import pytest

from ev_core.interfaces.tools import Risk, ToolContext
from ev_core.tools.clock import CurrentTimeTool

CTX = ToolContext(logger=logging.getLogger("test"))


@pytest.mark.parametrize(
    ("moment", "time_text"),
    [
        (datetime(2026, 10, 17, 0, 5, tzinfo=UTC), "12:05 AM"),
        (datetime(2026, 10, 17, 9, 0, tzinfo=UTC), "9:00 AM"),
        (datetime(2026, 10, 17, 12, 30, tzinfo=UTC), "12:30 PM"),
        (datetime(2026, 10, 17, 23, 59, tzinfo=UTC), "11:59 PM"),
    ],
)
async def test_time_text(moment: datetime, time_text: str) -> None:
    result = await CurrentTimeTool(now=lambda: moment).run({}, CTX)
    assert result.ok
    assert json.loads(result.content)["time_text"] == time_text


async def test_full_payload() -> None:
    ist = timezone(timedelta(hours=5, minutes=30), "IST")
    moment = datetime(2026, 10, 17, 15, 41, 7, tzinfo=ist)
    data = json.loads((await CurrentTimeTool(now=lambda: moment).run({}, CTX)).content)
    assert data == {
        "iso": "2026-10-17T15:41:07+05:30",
        "time_text": "3:41 PM",
        "date_text": "Saturday, October 17, 2026",
        "weekday": "Saturday",
        "timezone": "IST",
    }


def test_declaration() -> None:
    assert CurrentTimeTool.risk is Risk.SAFE
    assert len(CurrentTimeTool.description.split()) <= 25
