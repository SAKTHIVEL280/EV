"""PC control on Windows (docs/FEATURES.md Phase 3 specs).

- Windows and monitors: Win32 through ctypes (per-monitor DPI aware, so
  rectangles are real pixels); snapping accounts for the invisible resize
  borders of Windows 10/11 frames.
- Apps: the Start menu's own list (`Get-StartApps`), launched through
  `shell:AppsFolder`, which covers desktop and Store apps alike.
- Volume: Core Audio (pycaw). Brightness and radios: WMI and the WinRT radio
  API through Windows PowerShell 5.1, which ships with Windows.
- Screenshots: mss. Recycle Bin: send2trash. UI Automation: pywinauto (uia).

Blocking calls run in worker threads; COM is initialised per thread.
"""

import sys

assert sys.platform == "win32"  # noqa: S101 -- tells mypy this module is Windows-only

import asyncio
import contextlib
import ctypes
import json
import os
import subprocess
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import psutil

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
from ev_core.platform.keys import escape_text, pywinauto_keys

user32: Final = ctypes.WinDLL("user32", use_last_error=True)
kernel32: Final = ctypes.WinDLL("kernel32", use_last_error=True)
shell32: Final = ctypes.WinDLL("shell32", use_last_error=True)
ole32: Final = ctypes.WinDLL("ole32", use_last_error=True)
dwmapi: Final = ctypes.WinDLL("dwmapi")

CREATE_NO_WINDOW: Final = 0x0800_0000
APPS_CACHE_S: Final = 600.0
MAX_ELEMENTS: Final = 60
CF_UNICODETEXT: Final = 13
GMEM_MOVEABLE: Final = 0x0002
GWL_EXSTYLE: Final = -20
WS_EX_TOOLWINDOW: Final = 0x0000_0080
GW_OWNER: Final = 4
DWMWA_EXTENDED_FRAME_BOUNDS: Final = 9
DWMWA_CLOAKED: Final = 14
MONITOR_DEFAULTTONEAREST: Final = 2
SW_MAXIMIZE: Final = 3
SW_MINIMIZE: Final = 6
SW_RESTORE: Final = 9
SWP_NOZORDER: Final = 0x0004
SWP_NOACTIVATE: Final = 0x0010
WM_CLOSE: Final = 0x0010
KEYEVENTF_KEYUP: Final = 0x0002
VK_MENU: Final = 0x12
MEDIA_KEYS: Final = {
    MediaAction.PLAY_PAUSE: 0xB3,
    MediaAction.NEXT: 0xB0,
    MediaAction.PREVIOUS: 0xB1,
    MediaAction.STOP: 0xB2,
}
SHELL_CLASSES: Final = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
INTERACTIVE_TYPES: Final = {
    "Button", "Edit", "Document", "CheckBox", "ComboBox", "MenuItem", "Hyperlink",
    "ListItem", "TabItem", "RadioButton", "SplitButton", "TreeItem",
}  # fmt: skip
KNOWN_FOLDERS: Final = {
    "Desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "Documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "Downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "Pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "Music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "Videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}
SCREENSHOTS_FOLDER: Final = "B7BEDE81-DF94-4682-A7D8-57A52620B86F"


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> "GUID":
        u = UUID(text)
        data4 = (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:])
        return cls(u.time_low, u.time_mid, u.time_hi_version, data4)


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _signatures() -> None:
    """64-bit safe argument and result types for every call used below."""
    H = wintypes.HWND  # noqa: N806
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [H]
    user32.GetWindowTextLengthW.argtypes = [H]
    user32.GetWindowTextW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowLongW.argtypes = [H, ctypes.c_int]
    user32.GetWindow.argtypes = [H, wintypes.UINT]
    user32.GetWindow.restype = H
    user32.IsIconic.argtypes = [H]
    user32.IsZoomed.argtypes = [H]
    user32.IsWindow.argtypes = [H]
    user32.GetWindowRect.argtypes = [H, ctypes.POINTER(RECT)]
    user32.ShowWindow.argtypes = [H, ctypes.c_int]
    user32.SetWindowPos.argtypes = [
        H,
        H,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetForegroundWindow.argtypes = [H]
    user32.PostMessageW.argtypes = [H, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.MonitorFromWindow.argtypes = [H, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
    user32.OpenClipboard.argtypes = [H]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)
    ]  # fmt: skip
    ole32.CoTaskMemFree.argtypes = [wintypes.LPVOID]
    dwmapi.DwmGetWindowAttribute.argtypes = [H, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]


_signatures()
with contextlib.suppress(AttributeError, OSError):
    # Per-monitor DPI aware v2: rectangles in physical pixels on every monitor.
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def _text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _cloaked(hwnd: int) -> bool:
    value = wintypes.DWORD()
    hr = dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
    )
    return hr == 0 and value.value != 0


def _rects(hwnd: int) -> tuple[Rect, Rect]:
    """(visible frame, window rect including the invisible resize borders)."""
    outer = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(outer))
    frame = RECT()
    hr = dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(frame), ctypes.sizeof(frame)
    )
    if hr != 0:
        frame = outer

    def rect(r: RECT) -> Rect:
        return Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)

    return rect(frame), rect(outer)


def _app_name(hwnd: int) -> str:
    try:
        name = Path(psutil.Process(_pid(hwnd)).name()).stem.lower()
    except (psutil.Error, OSError):
        return ""
    if name == "applicationframehost":
        # Store apps run inside a frame host; the title names the app.
        return _text(hwnd).rsplit(" - ", 1)[-1].strip().lower()
    return name


def _powershell(script: str, timeout_s: float = 15.0) -> str:
    """Run Windows PowerShell 5.1 (it has the WinRT projection) without a window."""
    done = subprocess.run(  # noqa: S603 -- fixed executable and our own script
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout_s,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if done.returncode != 0:
        raise PcError("Windows didn't allow that.", done.stderr.strip()[-300:])
    return done.stdout.strip()


RADIO_SCRIPT: Final = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
  $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$all = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$radio = $all | Where-Object { $_.Kind -eq '__KIND__' } | Select-Object -First 1
if ($null -eq $radio) { 'none'; exit 0 }
if ('__SET__' -ne '') {
  Await ($radio.SetStateAsync('__SET__')) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
}
$radio.State.ToString()
"""


@dataclass
class _Snapshot:
    window: int
    wrappers: dict[int, Any]


def _in_thread[T](work: Callable[[], T]) -> "asyncio.Future[T]":
    def run() -> T:
        import comtypes

        comtypes.CoInitialize()
        try:
            return work()
        finally:
            comtypes.CoUninitialize()

    return asyncio.ensure_future(asyncio.to_thread(run))


class WindowsPcControl(PcControl):
    def __init__(self) -> None:
        own = os.getpid()
        try:
            parent = psutil.Process(own).parent()
            self._ev_pids = {own, parent.pid if parent else own}
        except psutil.Error:
            self._ev_pids = {own}
        self._apps: list[AppEntry] = []
        self._apps_at = 0.0
        self._snapshot: _Snapshot | None = None
        self._selection_window: int | None = None

    # --- apps and windows
    async def installed_apps(self) -> list[AppEntry]:
        if self._apps and time.monotonic() - self._apps_at < APPS_CACHE_S:
            return list(self._apps)

        def read() -> list[AppEntry]:
            raw = _powershell(
                "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
            )
            items = json.loads(raw) if raw else []
            items = items if isinstance(items, list) else [items]
            return [
                AppEntry(str(i["Name"]), str(i["AppID"]))
                for i in items
                if i.get("Name") and i.get("AppID")
            ]

        try:
            self._apps = await asyncio.to_thread(read)
        except (PcError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise PcError("Couldn't read the list of apps.", str(exc)) from exc
        self._apps_at = time.monotonic()
        return list(self._apps)

    async def launch(self, app: AppEntry) -> None:
        def start() -> None:
            subprocess.Popen(  # noqa: S603 -- explorer opening a Start menu app id
                ["explorer.exe", f"shell:AppsFolder\\{app.target}"],  # noqa: S607
                creationflags=CREATE_NO_WINDOW,
            )

        await asyncio.to_thread(start)

    async def windows(self) -> list[WindowInfo]:
        def collect() -> list[WindowInfo]:
            found: list[WindowInfo] = []

            def visit(hwnd: int, _lparam: int) -> bool:
                if not user32.IsWindowVisible(hwnd) or _cloaked(hwnd):
                    return True
                if user32.GetWindow(hwnd, GW_OWNER):
                    return True
                if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                    return True
                title = _text(hwnd)
                if not title or _class(hwnd) in SHELL_CLASSES or _pid(hwnd) in self._ev_pids:
                    return True
                frame, _ = _rects(hwnd)
                state = (
                    WindowState.MINIMIZED
                    if user32.IsIconic(hwnd)
                    else WindowState.MAXIMIZED
                    if user32.IsZoomed(hwnd)
                    else WindowState.NORMAL
                )
                found.append(WindowInfo(int(hwnd), title, _app_name(hwnd), frame, state))
                return True

            user32.EnumWindows(WNDENUMPROC(visit), 0)  # z-order: front to back
            return found

        return await asyncio.to_thread(collect)

    def _check(self, window_id: int) -> None:
        if not user32.IsWindow(window_id):
            raise PcError("Couldn't find that window.", f"no window {window_id}")

    async def focus(self, window_id: int) -> None:
        def bring() -> None:
            self._check(window_id)
            if user32.IsIconic(window_id):
                user32.ShowWindow(window_id, SW_RESTORE)
            # A background process may not take the foreground; a synthetic Alt
            # press lifts the restriction (the same trick tao and pywinauto use).
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            user32.SetForegroundWindow(window_id)

        await asyncio.to_thread(bring)

    async def close(self, window_id: int) -> None:
        self._check(window_id)
        await asyncio.to_thread(user32.PostMessageW, window_id, WM_CLOSE, 0, 0)

    async def work_area(self, window_id: int) -> Rect:
        def read() -> Rect:
            self._check(window_id)
            monitor = user32.MonitorFromWindow(window_id, MONITOR_DEFAULTTONEAREST)
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            user32.GetMonitorInfoW(monitor, ctypes.byref(info))
            w = info.rcWork
            return Rect(w.left, w.top, w.right - w.left, w.bottom - w.top)

        return await asyncio.to_thread(read)

    async def move(self, window_id: int, rect: Rect | None, state: WindowState) -> None:
        def apply() -> None:
            self._check(window_id)
            if state is WindowState.MAXIMIZED:
                user32.ShowWindow(window_id, SW_MAXIMIZE)
                return
            if state is WindowState.MINIMIZED:
                user32.ShowWindow(window_id, SW_MINIMIZE)
                return
            if user32.IsIconic(window_id) or user32.IsZoomed(window_id):
                user32.ShowWindow(window_id, SW_RESTORE)
            if rect is None:
                return
            # The window rectangle includes invisible resize borders; grow the
            # target by them so the visible frame lands exactly on `rect`.
            frame, outer = _rects(window_id)
            left = frame.left - outer.left
            top = frame.top - outer.top
            right = (outer.left + outer.width) - (frame.left + frame.width)
            bottom = (outer.top + outer.height) - (frame.top + frame.height)
            user32.SetWindowPos(
                window_id,
                None,
                rect.left - left,
                rect.top - top,
                rect.width + left + right,
                rect.height + top + bottom,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )

        await asyncio.to_thread(apply)

    # --- sound, screen, media, radios
    @staticmethod
    def _endpoint() -> Any:
        from pycaw.pycaw import AudioUtilities

        speakers = AudioUtilities.GetSpeakers()
        if speakers is None:
            raise PcError("This PC has no speakers turned on.", "no default render device")
        endpoint = getattr(speakers, "EndpointVolume", None)
        if endpoint is not None:
            return endpoint
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume

        interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return interface.QueryInterface(IAudioEndpointVolume)

    async def volume(self) -> Volume:
        def read() -> Volume:
            endpoint = self._endpoint()
            level = round(float(endpoint.GetMasterVolumeLevelScalar()) * 100)
            return Volume(level, bool(endpoint.GetMute()))

        return await _in_thread(read)

    async def set_volume(self, level: int | None = None, muted: bool | None = None) -> None:
        def apply() -> None:
            endpoint = self._endpoint()
            if level is not None:
                endpoint.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)
            if muted is not None:
                endpoint.SetMute(int(muted), None)

        await _in_thread(apply)

    async def brightness(self) -> int | None:
        script = (
            "$b = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
            "-ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($b) { $b.CurrentBrightness } else { 'none' }"
        )
        out = await asyncio.to_thread(_powershell, script)
        return None if out in ("", "none") else int(out)

    async def set_brightness(self, level: int) -> None:
        value = max(0, min(100, level))
        script = (
            "$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods "
            "-ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if (-not $m) { 'none'; exit 0 }; "
            "Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness "
            f"-Arguments @{{Timeout=0; Brightness={value}}} | Out-Null; 'ok'"
        )
        if await asyncio.to_thread(_powershell, script) == "none":
            raise PcError("This screen's brightness can't be changed from Windows.", "no WMI")

    async def media(self, action: MediaAction) -> None:
        key = MEDIA_KEYS[action]

        def press() -> None:
            user32.keybd_event(key, 0, 0, 0)
            user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)

        await asyncio.to_thread(press)

    async def _radio(self, kind: Radio, set_to: bool | None) -> bool | None:
        script = RADIO_SCRIPT.replace("__KIND__", "WiFi" if kind is Radio.WIFI else "Bluetooth")
        script = script.replace("__SET__", "" if set_to is None else ("On" if set_to else "Off"))
        out = await asyncio.to_thread(_powershell, script, 30.0)
        last = out.splitlines()[-1].strip() if out else "none"
        return None if last == "none" else last == "On"

    async def radio(self, kind: Radio) -> bool | None:
        return await self._radio(kind, None)

    async def set_radio(self, kind: Radio, on: bool) -> None:
        if await self._radio(kind, on) is None:
            label = "Wi-Fi" if kind is Radio.WIFI else "Bluetooth"
            raise PcError(f"This PC has no {label}.", f"no {kind}")

    # --- screenshots, clipboard, files
    async def screenshot(self, path: Path, window_id: int | None = None) -> None:
        def grab() -> None:
            import mss
            import mss.tools

            path.parent.mkdir(parents=True, exist_ok=True)
            with mss.mss() as sct:
                if window_id is not None:
                    frame, _ = _rects(window_id)
                    area = {
                        "left": frame.left,
                        "top": frame.top,
                        "width": frame.width,
                        "height": frame.height,
                    }
                else:
                    area = sct.monitors[1]  # the primary monitor
                shot = sct.grab(area)
                mss.tools.to_png(shot.rgb, shot.size, output=str(path))

        await asyncio.to_thread(grab)

    @staticmethod
    def _open_clipboard() -> None:
        for _ in range(10):
            if user32.OpenClipboard(None):
                return
            time.sleep(0.05)
        raise PcError("Another app is using the clipboard. Try again.", "OpenClipboard failed")

    async def clipboard_text(self) -> str | None:
        def read() -> str | None:
            self._open_clipboard()
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                pointer = kernel32.GlobalLock(handle)
                try:
                    return ctypes.wstring_at(pointer) if pointer else None
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()

        return await asyncio.to_thread(read)

    async def set_clipboard_text(self, text: str) -> None:
        def write() -> None:
            data = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(data)
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not handle:
                raise PcError("Couldn't copy that.", "GlobalAlloc failed")
            pointer = kernel32.GlobalLock(handle)
            ctypes.memmove(pointer, data, size)
            kernel32.GlobalUnlock(handle)
            self._open_clipboard()
            try:
                user32.EmptyClipboard()
                if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                    kernel32.GlobalFree(handle)
                    raise PcError("Couldn't copy that.", "SetClipboardData failed")
            finally:
                user32.CloseClipboard()

        await asyncio.to_thread(write)

    @staticmethod
    def _known_folder(guid: str) -> Path | None:
        out = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(GUID.parse(guid)), 0, None, ctypes.byref(out)):
            return None
        try:
            return Path(out.value) if out.value else None
        finally:
            ole32.CoTaskMemFree(out)

    def user_folders(self) -> list[Path]:
        folders = [self._known_folder(g) for g in KNOWN_FOLDERS.values()]
        return [f for f in folders if f is not None and f.is_dir()]

    def screenshots_folder(self) -> Path:
        found = self._known_folder(SCREENSHOTS_FOLDER)
        if found is not None:
            return found
        pictures = self._known_folder(KNOWN_FOLDERS["Pictures"]) or Path.home() / "Pictures"
        return pictures / "Screenshots"

    async def open_path(self, path: Path) -> None:
        if not await asyncio.to_thread(path.exists):
            raise PcError("Couldn't find that file.", str(path))
        await asyncio.to_thread(os.startfile, path)

    async def recycle(self, path: Path) -> None:
        def trash() -> None:
            from send2trash import send2trash

            send2trash(str(path))

        try:
            await asyncio.to_thread(trash)
        except OSError as exc:
            raise PcError("That file is in use.", str(exc)) from exc

    # --- UI automation and "this"
    @staticmethod
    def _uia_window(window_id: int) -> Any:
        from pywinauto import Desktop

        return Desktop(backend="uia").window(handle=window_id)

    async def ui_elements(self, window_id: int) -> list[UiElement]:
        def read() -> list[UiElement]:
            self._check(window_id)
            window = self._uia_window(window_id)
            wrappers: dict[int, Any] = {}
            elements: list[UiElement] = []
            for wrapper in window.descendants():
                info = wrapper.element_info
                if info.control_type not in INTERACTIVE_TYPES or not info.visible:
                    continue
                element_id = len(elements) + 1
                value = ""
                with contextlib.suppress(Exception):
                    if info.control_type in ("Edit", "Document", "ComboBox"):
                        value = str(wrapper.window_text() or "")[:200]
                elements.append(
                    UiElement(
                        element_id,
                        info.control_type.lower(),
                        (info.name or "")[:80],
                        value,
                        bool(info.enabled),
                    )
                )
                wrappers[element_id] = wrapper
                if len(elements) >= MAX_ELEMENTS:
                    break
            self._snapshot = _Snapshot(window_id, wrappers)
            return elements

        return await _in_thread(read)

    def _wrapper(self, window_id: int, element_id: int) -> Any:
        snapshot = self._snapshot
        if snapshot is None or snapshot.window != window_id or element_id not in snapshot.wrappers:
            raise PcError("That part of the window is gone.", f"no element {element_id}")
        return snapshot.wrappers[element_id]

    async def ui_click(self, window_id: int, element_id: int) -> None:
        def click() -> None:
            wrapper = self._wrapper(window_id, element_id)
            try:
                wrapper.invoke()
            except Exception:  # noqa: BLE001 -- not every control supports Invoke
                wrapper.click_input()

        await _in_thread(click)

    async def ui_type(self, window_id: int, element_id: int, text: str) -> None:
        def type_() -> None:
            wrapper = self._wrapper(window_id, element_id)
            if wrapper.element_info.control_type not in ("Edit", "Document", "ComboBox"):
                raise PcError("That part of the window doesn't take text.", "not editable")
            wrapper.set_focus()
            wrapper.type_keys(escape_text(text), with_spaces=True, with_newlines=True, pause=0.005)

        await _in_thread(type_)

    async def ui_keys(self, window_id: int, keys: str) -> None:
        sequence = pywinauto_keys(keys)

        def press() -> None:
            self._check(window_id)
            self._uia_window(window_id).type_keys(sequence, set_foreground=True)

        await _in_thread(press)

    async def selection(self) -> Selection | None:
        windows = await self.windows()
        if not windows:
            return None
        target = windows[0]  # front-most window that isn't EV: the one the user was in

        def read() -> str | None:
            window = self._uia_window(target.id)
            for wrapper in window.descendants():
                if wrapper.element_info.control_type not in ("Edit", "Document"):
                    continue
                with contextlib.suppress(Exception):
                    ranges = wrapper.iface_text.GetSelection()
                    texts = [ranges.GetElement(i).GetText(-1) for i in range(ranges.Length)]
                    text = "".join(texts).strip()
                    if text:
                        return text
            return None

        text = await _in_thread(read)
        if not text:
            return None
        self._selection_window = target.id
        return Selection(text, target.app, target.title)

    async def replace_selection(self, text: str) -> bool:
        window_id = self._selection_window
        if window_id is None:
            return False

        def replace() -> bool:
            if not user32.IsWindow(window_id):
                return False
            window = self._uia_window(window_id)
            window.set_focus()
            window.type_keys(escape_text(text), with_spaces=True, with_newlines=True, pause=0.005)
            return True

        return await _in_thread(replace)
