"""Data directory resolution (docs/ARCHITECTURE.md §4.4)."""

import sys
from collections.abc import Mapping
from pathlib import Path

from ev_core.errors import StartupError

APP_DIR_NAME = "EV"


def data_dir(env: Mapping[str, str], platform: str = sys.platform) -> Path:
    """Return EV's data directory without creating it.

    Order: ``EV_DATA_DIR`` override, then ``%APPDATA%\\EV`` on Windows, then
    ``$XDG_DATA_HOME/EV`` (default ``~/.local/share/EV``) elsewhere.
    """
    override = env.get("EV_DATA_DIR")
    if override:
        return Path(override)
    if platform == "win32":
        appdata = env.get("APPDATA")
        if not appdata:
            raise StartupError(
                "EV can't find its data folder.",
                "APPDATA environment variable is not set",
            )
        return Path(appdata) / APP_DIR_NAME
    xdg = env.get("XDG_DATA_HOME")
    # The XDG spec says relative paths must be ignored.
    if xdg and Path(xdg).is_absolute():
        return Path(xdg) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME
