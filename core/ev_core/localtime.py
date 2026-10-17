"""The PC's local date and time, worded for the model and for replies."""

from datetime import datetime


def now() -> datetime:
    return datetime.now().astimezone()


def time_text(moment: datetime) -> str:
    """'3:41 PM'"""
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment.minute:02d} {'AM' if moment.hour < 12 else 'PM'}"


def date_text(moment: datetime) -> str:
    """'Saturday, October 17, 2026'"""
    return f"{moment:%A}, {moment:%B} {moment.day}, {moment.year}"


def stamp(moment: datetime) -> str:
    """One line placed before the user's message, so the model never guesses
    the date (beta test 2026-10-17: a small model answered with a made-up date)."""
    zone = moment.tzname() or ""
    return f"[Local time: {date_text(moment)}, {time_text(moment)}{f', {zone}' if zone else ''}]"
