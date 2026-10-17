"""PC control (docs/FEATURES.md Phase 3 specs): everything EV's tools do to the
PC goes through this interface. Windows has the real implementation
(`ev_core.platform.windows_pc`); development on Linux uses
`ev_core.platform.fake_pc`, which keeps state in memory and records calls.

Methods are async; implementations run blocking OS calls in threads.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ev_core.errors import EvError


class PcError(EvError):
    """An action the PC refused or could not do; `user_message` says why, plainly."""


@dataclass(frozen=True, slots=True)
class AppEntry:
    """An installed app that can be started."""

    name: str
    target: str
    """Platform launch target: a shortcut path or an app id."""


@dataclass(frozen=True, slots=True)
class Rect:
    left: int
    top: int
    width: int
    height: int


class WindowState(StrEnum):
    NORMAL = "normal"
    MAXIMIZED = "maximized"
    MINIMIZED = "minimized"


@dataclass(frozen=True, slots=True)
class WindowInfo:
    id: int
    title: str
    app: str
    """Executable name without extension, e.g. "notepad"."""
    rect: Rect
    state: WindowState


class Placement(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"
    CENTER = "center"
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"
    RESTORE = "restore"


class MediaAction(StrEnum):
    PLAY_PAUSE = "play_pause"
    NEXT = "next"
    PREVIOUS = "previous"
    STOP = "stop"


class Radio(StrEnum):
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"


@dataclass(frozen=True, slots=True)
class Volume:
    level: int
    """0 to 100."""
    muted: bool


@dataclass(frozen=True, slots=True)
class UiElement:
    id: int
    """Valid only for the snapshot it came from."""
    role: str
    name: str
    value: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class Selection:
    text: str
    app: str
    title: str


class PcControl(ABC):
    # --- apps and windows (F-101, F-102)
    @abstractmethod
    async def installed_apps(self) -> list[AppEntry]: ...

    @abstractmethod
    async def launch(self, app: AppEntry) -> None: ...

    @abstractmethod
    async def windows(self) -> list[WindowInfo]:
        """Visible top-level windows, front to back, EV's own excluded."""

    @abstractmethod
    async def focus(self, window_id: int) -> None: ...

    @abstractmethod
    async def close(self, window_id: int) -> None:
        """Ask the window to close normally (the app may ask to save)."""

    @abstractmethod
    async def work_area(self, window_id: int) -> Rect:
        """Work area of the monitor the window is on."""

    @abstractmethod
    async def move(self, window_id: int, rect: Rect | None, state: WindowState) -> None:
        """Set the window's state; with NORMAL, also its rectangle (when given)."""

    # --- sound, screen, media, radios (F-103, F-104)
    @abstractmethod
    async def volume(self) -> Volume: ...

    @abstractmethod
    async def set_volume(self, level: int | None = None, muted: bool | None = None) -> None: ...

    @abstractmethod
    async def brightness(self) -> int | None:
        """0 to 100, or None when this screen's brightness can't be read."""

    @abstractmethod
    async def set_brightness(self, level: int) -> None: ...

    @abstractmethod
    async def media(self, action: MediaAction) -> None: ...

    @abstractmethod
    async def radio(self, kind: Radio) -> bool | None:
        """On/off, or None when the PC has no such radio."""

    @abstractmethod
    async def set_radio(self, kind: Radio, on: bool) -> None: ...

    # --- screenshots, clipboard, files (F-105, F-106, F-107)
    @abstractmethod
    async def screenshot(self, path: Path, window_id: int | None = None) -> None: ...

    @abstractmethod
    async def clipboard_text(self) -> str | None: ...

    @abstractmethod
    async def set_clipboard_text(self, text: str) -> None: ...

    @abstractmethod
    def user_folders(self) -> list[Path]:
        """Desktop, Documents, Downloads, Pictures, Music, Videos (those that exist)."""

    @abstractmethod
    def screenshots_folder(self) -> Path: ...

    @abstractmethod
    async def open_path(self, path: Path) -> None:
        """Open a file or folder with its default app."""

    @abstractmethod
    async def recycle(self, path: Path) -> None:
        """Move to the Recycle Bin (never a permanent delete)."""

    # --- UI automation and "this" (F-110, F-201)
    @abstractmethod
    async def ui_elements(self, window_id: int) -> list[UiElement]:
        """Interactive elements of the window, in reading order, at most 60."""

    @abstractmethod
    async def ui_click(self, window_id: int, element_id: int) -> None: ...

    @abstractmethod
    async def ui_type(self, window_id: int, element_id: int, text: str) -> None: ...

    @abstractmethod
    async def ui_keys(self, window_id: int, keys: str) -> None:
        """Key presses such as "ctrl+s" or "enter", sent to the window."""

    @abstractmethod
    async def selection(self) -> Selection | None:
        """Text selected in the app the user was in before EV, if any."""

    @abstractmethod
    async def replace_selection(self, text: str) -> bool:
        """Replace the selection captured last; False when that app doesn't accept it."""
