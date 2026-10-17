"""PC control for development and tests: state in memory, files in a sandbox
folder, every call recorded. Lets the agent, confirmations, verification and
the action log run end to end on Linux (CLAUDE.md §10.5)."""

import asyncio
import itertools
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from ev_core.interfaces.pc import (
    AppEntry,
    MediaAction,
    PcControl,
    PcError,
    Radio,
    Rect,
    Selection,
    UiElement,
    Volume,
    WindowInfo,
    WindowState,
)

WORK_AREA: Final = Rect(0, 0, 1920, 1032)
USER_FOLDERS: Final = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")
# A 1x1 transparent PNG, enough for a screenshot file to exist.
_PNG: Final = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000000000200015e2d2b5b0000000049454e44ae426082"
)


@dataclass
class _Window:
    info: WindowInfo
    elements: list[UiElement] = field(default_factory=list)
    text: str = ""


class FakePcControl(PcControl):
    def __init__(self, home: Path) -> None:
        self.home = home
        self.calls: list[str] = []
        self.apps = [
            AppEntry("Notepad", "notepad"),
            AppEntry("Calculator", "calc"),
            AppEntry("Google Chrome", "chrome"),
            AppEntry("File Explorer", "explorer"),
            AppEntry("Spotify", "spotify"),
            AppEntry("Visual Studio Code", "code"),
        ]
        self._windows: dict[int, _Window] = {}
        self._ids = itertools.count(100)
        self._volume = Volume(50, muted=False)
        self._brightness: int | None = 70
        self._radios: dict[Radio, bool | None] = {Radio.WIFI: True, Radio.BLUETOOTH: False}
        self._clipboard: str | None = None
        self.selected: Selection | None = None
        self.replaced: str | None = None
        self.opened: list[Path] = []
        self.media_actions: list[MediaAction] = []

    # --- apps and windows
    async def installed_apps(self) -> list[AppEntry]:
        return list(self.apps)

    async def launch(self, app: AppEntry) -> None:
        self.calls.append(f"launch {app.target}")
        window_id = next(self._ids)
        elements = [
            UiElement(1, "edit", "Text editor", "", enabled=True),
            UiElement(2, "button", "Save", "", enabled=True),
        ]
        self._windows = {
            window_id: _Window(
                WindowInfo(
                    window_id,
                    f"Untitled - {app.name}",
                    app.target,
                    Rect(200, 120, 900, 640),
                    WindowState.NORMAL,
                ),
                elements,
            ),
            **self._windows,
        }

    async def windows(self) -> list[WindowInfo]:
        return [w.info for w in self._windows.values()]

    def _window(self, window_id: int) -> _Window:
        window = self._windows.get(window_id)
        if window is None:
            raise PcError("Couldn't find that window.", f"no window {window_id}")
        return window

    async def focus(self, window_id: int) -> None:
        window = self._window(window_id)
        self.calls.append(f"focus {window_id}")
        rest = {k: v for k, v in self._windows.items() if k != window_id}
        self._windows = {window_id: window, **rest}

    async def close(self, window_id: int) -> None:
        self._window(window_id)
        self.calls.append(f"close {window_id}")
        del self._windows[window_id]

    async def work_area(self, window_id: int) -> Rect:
        self._window(window_id)
        return WORK_AREA

    async def move(self, window_id: int, rect: Rect | None, state: WindowState) -> None:
        window = self._window(window_id)
        self.calls.append(f"move {window_id} {state.value} {rect}")
        info = replace(window.info, state=state)
        if state is WindowState.NORMAL and rect is not None:
            info = replace(info, rect=rect)
        window.info = info

    # --- sound, screen, media, radios
    async def volume(self) -> Volume:
        return self._volume

    async def set_volume(self, level: int | None = None, muted: bool | None = None) -> None:
        self.calls.append(f"volume {level} {muted}")
        self._volume = Volume(
            self._volume.level if level is None else max(0, min(100, level)),
            self._volume.muted if muted is None else muted,
        )

    async def brightness(self) -> int | None:
        return self._brightness

    async def set_brightness(self, level: int) -> None:
        if self._brightness is None:
            raise PcError("This screen's brightness can't be changed from Windows.", "no control")
        self.calls.append(f"brightness {level}")
        self._brightness = max(0, min(100, level))

    def without_brightness(self) -> None:
        self._brightness = None

    async def media(self, action: MediaAction) -> None:
        self.media_actions.append(action)

    async def radio(self, kind: Radio) -> bool | None:
        return self._radios.get(kind)

    async def set_radio(self, kind: Radio, on: bool) -> None:
        if self._radios.get(kind) is None:
            raise PcError("This PC has no Bluetooth.", f"no {kind}")
        self.calls.append(f"radio {kind.value} {on}")
        self._radios[kind] = on

    def without_radio(self, kind: Radio) -> None:
        self._radios[kind] = None

    # --- screenshots, clipboard, files
    async def screenshot(self, path: Path, window_id: int | None = None) -> None:
        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_PNG)

        await asyncio.to_thread(_write)

    async def clipboard_text(self) -> str | None:
        return self._clipboard

    async def set_clipboard_text(self, text: str) -> None:
        self._clipboard = text

    def user_folders(self) -> list[Path]:
        folders = [self.home / name for name in USER_FOLDERS]
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
        return folders

    def screenshots_folder(self) -> Path:
        return self.home / "Pictures" / "Screenshots"

    async def open_path(self, path: Path) -> None:
        if not await asyncio.to_thread(path.exists):
            raise PcError("Couldn't find that file.", str(path))
        self.opened.append(path)

    async def recycle(self, path: Path) -> None:
        def _move() -> None:
            trash = self.home / ".trash"
            trash.mkdir(parents=True, exist_ok=True)
            path.rename(trash / path.name)

        await asyncio.to_thread(_move)

    # --- UI automation and "this"
    async def ui_elements(self, window_id: int) -> list[UiElement]:
        window = self._window(window_id)
        return [replace(e, value=window.text) if e.role == "edit" else e for e in window.elements]

    def _element(self, window: _Window, element_id: int) -> UiElement:
        for element in window.elements:
            if element.id == element_id:
                return element
        raise PcError("That part of the window is gone.", f"no element {element_id}")

    async def ui_click(self, window_id: int, element_id: int) -> None:
        element = self._element(self._window(window_id), element_id)
        self.calls.append(f"click {window_id} {element.name}")

    async def ui_type(self, window_id: int, element_id: int, text: str) -> None:
        window = self._window(window_id)
        element = self._element(window, element_id)
        if element.role != "edit":
            raise PcError("That part of the window doesn't take text.", element.role)
        window.text += text

    async def ui_keys(self, window_id: int, keys: str) -> None:
        self._window(window_id)
        self.calls.append(f"keys {window_id} {keys}")

    async def selection(self) -> Selection | None:
        return self.selected

    async def replace_selection(self, text: str) -> bool:
        if self.selected is None:
            return False
        self.replaced = text
        return True
