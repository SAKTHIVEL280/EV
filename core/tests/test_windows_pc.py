"""The real Windows PC control (CLAUDE.md §10.4: tool tests on windows-latest
against Notepad). Skipped elsewhere. CI runners have no speakers, radios or
brightness control; those checks accept the plain "not available" answer."""

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)
assert sys.platform == "win32"  # for mypy: the rest is Windows-only

import asyncio
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import psutil

from ev_core.interfaces.pc import PcError, Rect, WindowInfo, WindowState
from ev_core.platform.windows_pc import WindowsPcControl


async def _notepad(pc: WindowsPcControl) -> tuple[WindowInfo, subprocess.Popen[bytes]]:
    before = {w.id for w in await pc.windows()}
    proc = await asyncio.to_thread(subprocess.Popen, ["notepad.exe"])
    for _ in range(80):
        for window in await pc.windows():
            if window.id not in before and "notepad" in (window.app + window.title).lower():
                return window, proc
        await asyncio.sleep(0.25)
    proc.kill()
    proc.wait(timeout=10)
    pytest.fail("Notepad didn't open")


def _probe(window_id: int) -> list[str]:
    """Temporary: what the selection read sees (remove once the CI check passes)."""
    import comtypes
    from pywinauto import Desktop

    comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    out = []
    for w in Desktop(backend="uia").window(handle=window_id).descendants():
        info = w.element_info
        if info.control_type not in ("Edit", "Document"):
            continue
        row = (
            f"{info.control_type}/{info.class_name}/h={info.handle}/focus={info.has_keyboard_focus}"
        )
        try:
            ranges = w.iface_text.GetSelection()
            row += f" n={ranges.Length} " + repr(
                [ranges.GetElement(i).GetText(-1) for i in range(ranges.Length)]
            )
        except Exception as exc:  # noqa: BLE001
            row += f" err={exc!r}"
        out.append(row)
    return out


@pytest.fixture
async def notepad() -> AsyncIterator[tuple[WindowsPcControl, WindowInfo]]:
    pc = WindowsPcControl()
    window, launcher = await _notepad(pc)
    yield pc, window
    for proc in psutil.process_iter(["name"]):
        if (proc.info["name"] or "").lower() == "notepad.exe":
            proc.kill()
    # Reap the launched process (it may be Notepad itself or a stub that exited).
    launcher.wait(timeout=10)


async def test_windows_are_listed_front_to_back(
    notepad: tuple[WindowsPcControl, WindowInfo],
) -> None:
    pc, window = notepad
    listed = await pc.windows()
    assert any(w.id == window.id for w in listed)
    assert window.rect.width > 0


async def test_type_into_notepad_and_read_it_back(
    notepad: tuple[WindowsPcControl, WindowInfo],
) -> None:
    pc, window = notepad
    elements = await pc.ui_elements(window.id)
    editor = next(e for e in elements if e.role in ("edit", "document"))
    await pc.ui_type(window.id, editor.id, "hello EV (test) 100%")
    after = await pc.ui_elements(window.id)
    text = next(e for e in after if e.role in ("edit", "document")).value
    assert "hello EV (test) 100%" in text
    # Selecting it makes it "this" (F-201).
    await pc.focus(window.id)
    await pc.ui_keys(window.id, "ctrl+a")
    front = (await pc.windows())[0]
    assert front.id == window.id, f"front-most window is {front}"
    selection = await pc.selection()
    assert selection is not None, (
        f"no selection; probe: {await asyncio.to_thread(_probe, window.id)}"
    )
    assert "hello EV" in selection.text


async def test_snap_left_and_restore(notepad: tuple[WindowsPcControl, WindowInfo]) -> None:
    pc, window = notepad
    work = await pc.work_area(window.id)
    target = Rect(work.left, work.top, work.width // 2, work.height)
    await pc.move(window.id, target, WindowState.NORMAL)
    moved = next(w for w in await pc.windows() if w.id == window.id)
    assert abs(moved.rect.left - target.left) <= 2
    assert abs(moved.rect.width - target.width) <= 2
    await pc.move(window.id, None, WindowState.MAXIMIZED)
    maxed = next(w for w in await pc.windows() if w.id == window.id)
    assert maxed.state is WindowState.MAXIMIZED


async def test_clipboard_round_trip() -> None:
    pc = WindowsPcControl()
    before = await pc.clipboard_text()
    await pc.set_clipboard_text("EV clipboard test ✓")
    assert await pc.clipboard_text() == "EV clipboard test ✓"
    if before is not None:
        await pc.set_clipboard_text(before)


async def test_screenshot_is_a_png(tmp_path: Path) -> None:
    path = tmp_path / "shot.png"
    await WindowsPcControl().screenshot(path)
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


async def test_recycle_and_folders(tmp_path: Path) -> None:
    pc = WindowsPcControl()
    assert pc.user_folders(), "no known folders found"
    victim = tmp_path / "ev-recycle-test.txt"
    victim.write_text("x")
    await pc.recycle(victim)
    assert not victim.exists()


async def test_devices_answer_plainly_when_missing() -> None:
    pc = WindowsPcControl()
    message = ""
    try:
        volume = await pc.volume()
    except PcError as exc:
        message = exc.user_message  # e.g. no speakers on a CI runner
    else:
        assert 0 <= volume.level <= 100
        message = "ok"
    assert message
    brightness = await pc.brightness()
    assert brightness is None or 0 <= brightness <= 100


async def test_start_menu_apps() -> None:
    try:
        apps = await WindowsPcControl().installed_apps()
    except PcError as exc:
        pytest.skip(f"Get-StartApps unavailable here: {exc.detail}")
    assert apps
