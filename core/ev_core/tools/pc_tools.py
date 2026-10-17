"""PC tools (docs/FEATURES.md F-101 to F-107, F-110). Each tool groups related
actions under one `action` argument, so the tool list stays inside the cached
prompt budget. All OS work goes through `PcControl`."""

import asyncio
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Final

from ev_core.interfaces.pc import (
    MediaAction,
    PcControl,
    PcError,
    Placement,
    Radio,
    Rect,
    UiElement,
    WindowInfo,
    WindowState,
)
from ev_core.interfaces.tools import Risk, Tool, ToolContext, ToolResult
from ev_core.tools.helpers import best_match, placement

OPEN_WAIT_S: Final = 10.0
POLL_S: Final = 0.25


def _ok(content: Any, *, user: str | None = None, summary: str | None = None,
        undo: Mapping[str, Any] | None = None) -> ToolResult:  # fmt: skip
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return ToolResult(True, text, user_message=user, summary=summary, undo=undo)


def _fail(message: str) -> ToolResult:
    return ToolResult(False, f"error: {message}", user_message=message)


def _schema(properties: Mapping[str, Any], required: list[str]) -> Mapping[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


async def _find_window(pc: PcControl, name: str) -> WindowInfo | None:
    windows = await pc.windows()
    index = best_match(name, [f"{w.app} {w.title}" for w in windows], threshold=0.3)
    return windows[index] if index is not None else None


async def _wait_for(check: Callable[[], Any], timeout_s: float) -> Any:
    deadline = time.monotonic() + timeout_s
    while True:
        found = await check()
        if found or time.monotonic() >= deadline:
            return found
        await asyncio.sleep(POLL_S)


class AppsTool(Tool):
    name = "apps"
    description = "Open, switch to, close or list apps."
    parameters: ClassVar[Mapping[str, Any]] = _schema(
        {
            "action": {"type": "string", "enum": ["open", "switch", "close", "list"]},
            "name": {"type": "string"},
        },
        ["action"],
    )
    risk = Risk.CONFIRM

    def __init__(self, pc: PcControl) -> None:
        self._pc = pc

    def risk_for(self, args: Mapping[str, Any]) -> Risk:
        return Risk.CONFIRM if args.get("action") == "close" else Risk.SAFE

    def question(self, args: Mapping[str, Any]) -> str:
        return f"Close {args.get('name', 'that app')}?"

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        action = args.get("action")
        name = str(args.get("name", "")).strip()
        try:
            if action == "list":
                windows = await self._pc.windows()
                return _ok([{"app": w.app, "title": w.title} for w in windows])
            if not name:
                return _fail("Which app?")
            if action == "open":
                return await self._open(name)
            if action == "switch":
                window = await _find_window(self._pc, name)
                if window is None:
                    return await self._open(name)
                await self._pc.focus(window.id)
                front = await self._pc.windows()
                if not front or front[0].id != window.id:
                    return _fail(f"Couldn't bring {name} to the front.")
                return _ok(f"switched to {window.app}", user=f"Switched to {name}.")
            if action == "close":
                return await self._close(name)
        except PcError as exc:
            return _fail(exc.user_message)
        return _fail("Unknown action.")

    async def _open(self, name: str) -> ToolResult:
        apps = await self._pc.installed_apps()
        index = best_match(name, [a.name for a in apps])
        if index is None:
            return _fail(f"Couldn't find an app called {name}.")
        app = apps[index]
        before = {w.id for w in await self._pc.windows()}
        await self._pc.launch(app)

        async def opened() -> WindowInfo | None:
            for w in await self._pc.windows():
                if w.id not in before:
                    return w
            return None

        window = await _wait_for(opened, OPEN_WAIT_S)
        if window is None:
            return _fail(f"{app.name} didn't open.")
        return _ok(
            f"opened {app.name}",
            user=f"Opened {app.name}.",
            summary=f"Opened {app.name}",
            undo={"close": window.id},
        )

    async def _close(self, name: str) -> ToolResult:
        window = await _find_window(self._pc, name)
        if window is None:
            return _fail(f"{name} isn't open.")
        await self._pc.close(window.id)

        async def gone() -> bool:
            return all(w.id != window.id for w in await self._pc.windows())

        if not await _wait_for(gone, 3.0):
            return _fail(f"{name} is asking to save first.")
        return _ok(
            f"closed {window.app}",
            user=f"Closed {name}.",
            summary=f"Closed {window.title}",
            undo={"open": name},
        )

    async def undo(self, data: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            if "close" in data:
                await self._pc.close(int(data["close"]))
                return _ok("closed")
            if "open" in data:
                return await self._open(str(data["open"]))
        except PcError as exc:
            return _fail(exc.user_message)
        return _fail("Nothing to undo.")


class WindowTool(Tool):
    name = "window"
    description = "Snap or resize a window. No app: the user's window."
    parameters: ClassVar[Mapping[str, Any]] = _schema(
        {
            "position": {"type": "string", "enum": [p.value for p in Placement]},
            "app": {"type": "string"},
        },
        ["position"],
    )
    risk = Risk.SAFE

    def __init__(self, pc: PcControl) -> None:
        self._pc = pc

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            where = Placement(str(args.get("position")))
        except ValueError:
            return _fail("Unknown position.")
        try:
            app = str(args.get("app", "")).strip()
            if app:
                window = await _find_window(self._pc, app)
            else:
                windows = await self._pc.windows()
                window = windows[0] if windows else None
            if window is None:
                return _fail("Couldn't find that window.")
            rect, state = placement(await self._pc.work_area(window.id), where)
            await self._pc.move(window.id, rect, state)
            after = next((w for w in await self._pc.windows() if w.id == window.id), None)
            if after is None or after.state is not state:
                return _fail("The window didn't move.")
        except PcError as exc:
            return _fail(exc.user_message)
        undo = {"id": window.id, "rect": asdict(window.rect), "state": window.state.value}
        label = where.value.replace("-", " ")
        return _ok(
            f"{window.app}: {label}",
            user="Done.",
            summary=f"Moved {window.title} ({label})",
            undo=undo,
        )

    async def undo(self, data: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            await self._pc.move(
                int(data["id"]), Rect(**data["rect"]), WindowState(str(data["state"]))
            )
        except PcError as exc:
            return _fail(exc.user_message)
        return _ok("restored")


class SystemTool(Tool):
    name = "system"
    description = "Volume, mute, brightness, media keys, Wi-Fi or Bluetooth."
    parameters: ClassVar[Mapping[str, Any]] = _schema(
        {
            "action": {
                "type": "string",
                "enum": ["volume", "mute", "unmute", "brightness", "media", "wifi", "bluetooth"],
            },
            "level": {"type": "integer"},
            "change": {"type": "integer"},
            "media": {"type": "string", "enum": [m.value for m in MediaAction]},
            "on": {"type": "boolean"},
        },
        ["action"],
    )
    risk = Risk.CONFIRM

    def __init__(self, pc: PcControl) -> None:
        self._pc = pc

    def risk_for(self, args: Mapping[str, Any]) -> Risk:
        wifi_off = args.get("action") == "wifi" and args.get("on") is False
        return Risk.CONFIRM if wifi_off else Risk.SAFE

    def question(self, args: Mapping[str, Any]) -> str:
        return "Turn Wi-Fi off? Your connection and EV's web search stop."

    @staticmethod
    def _target(current: int, args: Mapping[str, Any]) -> int:
        if isinstance(args.get("level"), int):
            return max(0, min(100, int(args["level"])))
        change = int(args["change"]) if isinstance(args.get("change"), int) else 10
        return max(0, min(100, current + change))

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        action = args.get("action")
        try:
            if action in ("volume", "mute", "unmute"):
                return await self._volume(str(action), args)
            if action == "brightness":
                return await self._brightness(args)
            if action == "media":
                media = MediaAction(str(args.get("media", "play_pause")))
                await self._pc.media(media)
                return _ok(f"sent {media.value}", user="Done.")
            if action in ("wifi", "bluetooth"):
                return await self._radio(Radio(str(action)), args)
        except PcError as exc:
            return _fail(exc.user_message)
        except ValueError:
            return _fail("I didn't understand that setting.")
        return _fail("Unknown action.")

    async def _volume(self, action: str, args: Mapping[str, Any]) -> ToolResult:
        before = await self._pc.volume()
        if action == "volume":
            await self._pc.set_volume(level=self._target(before.level, args), muted=False)
        else:
            await self._pc.set_volume(muted=action == "mute")
        after = await self._pc.volume()
        text = "Muted." if after.muted else f"Volume {after.level}%."
        return _ok(
            {"level": after.level, "muted": after.muted},
            user=text,
            summary=text.rstrip("."),
            undo={"volume": before.level, "muted": before.muted},
        )

    async def _brightness(self, args: Mapping[str, Any]) -> ToolResult:
        before = await self._pc.brightness()
        if before is None:
            return _fail("This screen's brightness can't be changed from Windows.")
        await self._pc.set_brightness(self._target(before, args))
        after = await self._pc.brightness()
        return _ok(
            {"brightness": after},
            user=f"Brightness {after}%.",
            summary=f"Brightness {after}%",
            undo={"brightness": before},
        )

    async def _radio(self, kind: Radio, args: Mapping[str, Any]) -> ToolResult:
        label = "Wi-Fi" if kind is Radio.WIFI else "Bluetooth"
        before = await self._pc.radio(kind)
        if before is None:
            return _fail(f"This PC has no {label}.")
        on = bool(args.get("on", not before))
        await self._pc.set_radio(kind, on)
        if await self._pc.radio(kind) is not on:
            return _fail(f"Windows didn't allow EV to change {label}.")
        text = f"{label} {'on' if on else 'off'}"
        return _ok(text, user=f"{text}.", summary=text, undo={"radio": kind.value, "on": before})

    async def undo(self, data: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            if "volume" in data:
                await self._pc.set_volume(int(data["volume"]), bool(data["muted"]))
            elif "brightness" in data:
                await self._pc.set_brightness(int(data["brightness"]))
            elif "radio" in data:
                await self._pc.set_radio(Radio(str(data["radio"])), bool(data["on"]))
            else:
                return _fail("Nothing to undo.")
        except PcError as exc:
            return _fail(exc.user_message)
        return _ok("restored")


class ScreenshotTool(Tool):
    name = "screenshot"
    description = "Save a screenshot to Pictures."
    parameters: ClassVar[Mapping[str, Any]] = _schema(
        {"area": {"type": "string", "enum": ["screen", "window"]}}, []
    )
    risk = Risk.SAFE

    def __init__(self, pc: PcControl, now: Callable[[], datetime] = datetime.now) -> None:
        self._pc = pc
        self._now = now

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        stamp = self._now().strftime("%Y-%m-%d %H.%M.%S")
        path = self._pc.screenshots_folder() / f"EV {stamp}.png"
        try:
            window_id = None
            if args.get("area") == "window":
                windows = await self._pc.windows()
                window_id = windows[0].id if windows else None
            await self._pc.screenshot(path, window_id)
        except PcError as exc:
            return _fail(exc.user_message)
        return _ok(
            {"saved": str(path)},
            user=f"Saved to Pictures\\Screenshots as {path.name}.",
            summary=f"Screenshot {path.name}",
            undo={"recycle": str(path)},
        )

    async def undo(self, data: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            await self._pc.recycle(Path(str(data["recycle"])))
        except (PcError, OSError) as exc:
            return _fail(getattr(exc, "user_message", "Couldn't remove the screenshot."))
        return _ok("moved to the Recycle Bin")


MAX_FOUND: Final = 10
MAX_SCANNED: Final = 20_000
SEARCH_TIME_S: Final = 3.0


def search_files(roots: list[Path], query: str) -> list[Path]:
    """Files whose name contains every word of `query`, newest first (blocking)."""
    words = re.findall(r"[a-z0-9]+", query.lower())
    if not words:
        return []
    found: list[tuple[float, Path]] = []
    scanned = 0
    deadline = time.monotonic() + SEARCH_TIME_S
    for root in roots:
        stack = [root]
        while stack and scanned < MAX_SCANNED and time.monotonic() < deadline:
            folder = stack.pop()
            try:
                entries = list(folder.iterdir())
            except OSError:
                continue
            for entry in entries:
                scanned += 1
                if entry.name.startswith(".") or entry.is_symlink():
                    continue
                if entry.is_dir():
                    stack.append(entry)
                    continue
                name = entry.name.lower()
                if all(w in name for w in words):
                    try:
                        found.append((entry.stat().st_mtime, entry))
                    except OSError:
                        continue
    found.sort(key=lambda item: item[0], reverse=True)
    return [p for _, p in found[:MAX_FOUND]]


class FilesTool(Tool):
    name = "files"
    description = "Find, open, move or delete (to Recycle Bin) files in the user's folders."
    parameters: ClassVar[Mapping[str, Any]] = _schema(
        {
            "action": {"type": "string", "enum": ["find", "open", "move", "delete"]},
            "query": {"type": "string"},
            "path": {"type": "string"},
            "destination": {"type": "string"},
        },
        ["action"],
    )
    risk = Risk.DANGEROUS
    untrusted_output = True

    def __init__(self, pc: PcControl) -> None:
        self._pc = pc

    def risk_for(self, args: Mapping[str, Any]) -> Risk:
        return {"move": Risk.CONFIRM, "delete": Risk.DANGEROUS}.get(
            str(args.get("action")), Risk.SAFE
        )

    def question(self, args: Mapping[str, Any]) -> str:
        name = Path(str(args.get("path", ""))).name or "that file"
        if args.get("action") == "delete":
            return f"Delete {name}? It goes to the Recycle Bin."
        return f"Move {name} to {args.get('destination', 'that folder')}?"

    @staticmethod
    def _path(raw: str) -> Path:
        return Path(raw).expanduser()

    def _inside(self, path: Path) -> bool:
        resolved = path.expanduser().resolve()
        return any(resolved.is_relative_to(r.resolve()) for r in self._pc.user_folders())

    def _folder(self, destination: str) -> Path | None:
        folders = self._pc.user_folders()
        index = best_match(destination, [f.name for f in folders], threshold=0.8)
        if index is not None:
            return folders[index]
        candidate = Path(destination).expanduser()
        return candidate if self._inside(candidate) else None

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        action = args.get("action")
        try:
            if action == "find":
                query = str(args.get("query", ""))
                found = await asyncio.to_thread(search_files, self._pc.user_folders(), query)
                if not found:
                    return _fail(f"Couldn't find {query}.")
                return _ok([str(p) for p in found])
            path = self._path(str(args.get("path", "")))
            if not self._inside(path) or not await asyncio.to_thread(path.is_file):
                return _fail("That file isn't in your folders.")
            if action == "open":
                await self._pc.open_path(path)
                return _ok(f"opened {path.name}", user=f"Opened {path.name}.")
            if action == "move":
                return await self._move(path, str(args.get("destination", "")))
            if action == "delete":
                await self._pc.recycle(path)
                return _ok(
                    f"{path.name} is in the Recycle Bin",
                    user=f"Deleted {path.name}. It's in the Recycle Bin.",
                    summary=f"Deleted {path.name} (Recycle Bin)",
                )
        except PcError as exc:
            return _fail(exc.user_message)
        except OSError:
            return _fail("That file is in use.")
        return _fail("Unknown action.")

    async def _move(self, path: Path, destination: str) -> ToolResult:
        folder = self._folder(destination)
        if folder is None:
            return _fail("I can only move files within your folders.")
        target = folder / path.name
        if await asyncio.to_thread(target.exists):
            return _fail(f"{folder.name} already has a file called {path.name}.")
        await asyncio.to_thread(path.rename, target)
        return _ok(
            {"moved_to": str(target)},
            user=f"Moved {path.name} to {folder.name}.",
            summary=f"Moved {path.name} to {folder.name}",
            undo={"from": str(target), "to": str(path)},
        )

    async def undo(self, data: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        source, target = Path(str(data["from"])), Path(str(data["to"]))
        try:
            await asyncio.to_thread(source.rename, target)
        except OSError:
            return _fail("Couldn't move it back.")
        return _ok("moved back")


DANGEROUS_NAMES: Final = re.compile(
    r"\b(send|buy|pay|purchase|order|checkout|delete|remove|install|post|publish|submit|transfer)\b",
    re.IGNORECASE,
)


class UiTool(Tool):
    name = "ui"
    description = "Control an app: snapshot its controls, then click, type or press keys by id."
    parameters: ClassVar[Mapping[str, Any]] = _schema(
        {
            "action": {"type": "string", "enum": ["snapshot", "click", "type", "keys"]},
            "app": {"type": "string"},
            "element": {"type": "integer"},
            "text": {"type": "string"},
            "keys": {"type": "string"},
        },
        ["action"],
    )
    risk = Risk.DANGEROUS
    untrusted_output = True
    confirm_once = True

    def __init__(self, pc: PcControl) -> None:
        self._pc = pc
        self._window: WindowInfo | None = None
        self._elements: dict[int, UiElement] = {}

    def _name(self, args: Mapping[str, Any]) -> str:
        element = self._elements.get(int(args.get("element", -1)))
        return element.name if element else ""

    def risk_for(self, args: Mapping[str, Any]) -> Risk:
        action = args.get("action")
        if action == "snapshot":
            return Risk.SAFE
        if action == "click" and DANGEROUS_NAMES.search(self._name(args)):
            return Risk.DANGEROUS
        return Risk.CONFIRM

    def question(self, args: Mapping[str, Any]) -> str:
        app = self._window.app if self._window else "that app"
        match args.get("action"):
            case "click":
                return f"Click “{self._name(args) or 'that'}” in {app}?"
            case "type":
                text = str(args.get("text", ""))
                shown = text if len(text) <= 60 else text[:57] + "..."
                return f"Type “{shown}” in {app}?"
            case _:
                return f"Press {args.get('keys', 'keys')} in {app}?"

    async def _target(self, app: str) -> WindowInfo | None:
        if app:
            return await _find_window(self._pc, app)
        windows = await self._pc.windows()
        return windows[0] if windows else None

    async def _snapshot(self, window: WindowInfo) -> list[UiElement]:
        elements = await self._pc.ui_elements(window.id)
        self._window = window
        self._elements = {e.id: e for e in elements}
        return elements

    @staticmethod
    def _view(elements: list[UiElement]) -> list[dict[str, Any]]:
        """Short for the model: no empty value, `enabled` only when false."""
        view = []
        for e in elements:
            item: dict[str, Any] = {"id": e.id, "role": e.role, "name": e.name}
            if e.value:
                item["value"] = e.value
            if not e.enabled:
                item["enabled"] = False
            view.append(item)
        return view

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        action = args.get("action")
        try:
            if action == "snapshot":
                window = await self._target(str(args.get("app", "")).strip())
                if window is None:
                    return _fail("Couldn't find that window.")
                elements = await self._snapshot(window)
                return _ok({"window": window.title, "elements": self._view(elements)})
            if self._window is None:
                return _fail("Take a snapshot first.")
            window = self._window
            before = self._view(list(self._elements.values()))
            if action == "click":
                await self._pc.ui_click(window.id, int(args["element"]))
                summary = f"Clicked “{self._name(args)}” in {window.app}"
            elif action == "type":
                await self._pc.ui_type(window.id, int(args["element"]), str(args.get("text", "")))
                summary = f"Typed in {window.app}"
            elif action == "keys":
                await self._pc.ui_keys(window.id, str(args.get("keys", "")))
                summary = f"Pressed {args.get('keys')} in {window.app}"
            else:
                return _fail("Unknown action.")
            # Verification: read the window again and report what changed.
            after = self._view(await self._snapshot(window))
            changed = [e for e in after if e not in before]
            return _ok({"changed": changed or "nothing visible changed"}, summary=summary)
        except PcError as exc:
            return _fail(exc.user_message)
        except (KeyError, ValueError):
            return _fail("Which control? Use an id from the snapshot.")
