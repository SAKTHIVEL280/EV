from pathlib import Path

import pytest

from ev_core.errors import StartupError
from ev_core.paths import data_dir


def test_override_wins_everywhere() -> None:
    env = {"EV_DATA_DIR": "/custom", "APPDATA": "C:/x", "XDG_DATA_HOME": "/xdg"}
    assert data_dir(env, "win32") == Path("/custom")
    assert data_dir(env, "linux") == Path("/custom")


def test_windows_uses_appdata() -> None:
    assert data_dir({"APPDATA": "C:/Users/u/AppData/Roaming"}, "win32") == Path(
        "C:/Users/u/AppData/Roaming/EV"
    )


def test_windows_without_appdata_raises() -> None:
    with pytest.raises(StartupError):
        data_dir({}, "win32")


def test_linux_uses_absolute_xdg() -> None:
    assert data_dir({"XDG_DATA_HOME": "/xdg"}, "linux") == Path("/xdg/EV")


def test_linux_ignores_relative_xdg_and_defaults() -> None:
    expected = Path.home() / ".local" / "share" / "EV"
    assert data_dir({"XDG_DATA_HOME": "relative"}, "linux") == expected
    assert data_dir({}, "linux") == expected
