"""PC tools against the fake backend (F-101 to F-107, F-110)."""

import json
import logging
from datetime import datetime
from pathlib import Path

import pytest

from ev_core.interfaces.pc import MediaAction, Radio, Selection, WindowState
from ev_core.interfaces.tools import Risk, ToolContext
from ev_core.platform.fake_pc import WORK_AREA, FakePcControl
from ev_core.tools import pc_tools
from ev_core.tools.pc_tools import (
    AppsTool,
    FilesTool,
    ScreenshotTool,
    SystemTool,
    UiTool,
    WindowTool,
    search_files,
)

CTX = ToolContext(logger=logging.getLogger("test"))


@pytest.fixture
def pc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakePcControl:
    monkeypatch.setattr(pc_tools, "OPEN_WAIT_S", 0.5)
    monkeypatch.setattr(pc_tools, "POLL_S", 0.01)
    return FakePcControl(tmp_path / "home")


# --- apps


async def test_open_switch_close_and_undo(pc: FakePcControl) -> None:
    apps = AppsTool(pc)
    opened = await apps.run({"action": "open", "name": "notepad"}, CTX)
    assert (opened.ok, opened.user_message, opened.summary) == (
        True,
        "Opened Notepad.",
        "Opened Notepad",
    )
    await apps.run({"action": "open", "name": "chrome"}, CTX)
    switched = await apps.run({"action": "switch", "name": "notepad"}, CTX)
    assert switched.ok
    assert (await pc.windows())[0].app == "notepad"
    listed = json.loads((await apps.run({"action": "list"}, CTX)).content)
    assert [w["app"] for w in listed] == ["notepad", "chrome"]
    closed = await apps.run({"action": "close", "name": "Notepad"}, CTX)
    assert closed.ok
    assert [w.app for w in await pc.windows()] == ["chrome"]
    assert closed.undo is not None
    await apps.undo(closed.undo, CTX)
    assert {w.app for w in await pc.windows()} == {"chrome", "notepad"}


async def test_unknown_app_and_risk(pc: FakePcControl) -> None:
    apps = AppsTool(pc)
    missing = await apps.run({"action": "open", "name": "photoshop"}, CTX)
    assert missing.user_message == "Couldn't find an app called photoshop."
    assert apps.risk_for({"action": "close", "name": "x"}) is Risk.CONFIRM
    assert apps.risk_for({"action": "open", "name": "x"}) is Risk.SAFE
    assert apps.question({"action": "close", "name": "Notepad"}) == "Close Notepad?"
    not_open = await apps.run({"action": "close", "name": "Spotify"}, CTX)
    assert not_open.user_message == "Spotify isn't open."


async def test_switch_opens_an_app_that_isnt_running(pc: FakePcControl) -> None:
    result = await AppsTool(pc).run({"action": "switch", "name": "calculator"}, CTX)
    assert result.user_message == "Opened Calculator."


# --- windows


async def test_snap_left_and_undo(pc: FakePcControl) -> None:
    await AppsTool(pc).run({"action": "open", "name": "notepad"}, CTX)
    tool = WindowTool(pc)
    result = await tool.run({"position": "left"}, CTX)
    assert result.ok
    window = (await pc.windows())[0]
    assert window.rect.width == WORK_AREA.width // 2
    assert result.undo is not None
    await tool.undo(result.undo, CTX)
    assert (await pc.windows())[0].rect.width == 900
    maximized = await tool.run({"position": "maximize", "app": "notepad"}, CTX)
    assert maximized.ok
    assert (await pc.windows())[0].state is WindowState.MAXIMIZED


async def test_snap_without_windows(pc: FakePcControl) -> None:
    result = await WindowTool(pc).run({"position": "left"}, CTX)
    assert result.user_message == "Couldn't find that window."


# --- system


async def test_volume_levels_mute_and_undo(pc: FakePcControl) -> None:
    tool = SystemTool(pc)
    up = await tool.run({"action": "volume", "change": 20}, CTX)
    assert up.user_message == "Volume 70%."
    to = await tool.run({"action": "volume", "level": 130}, CTX)
    assert to.user_message == "Volume 100%."
    muted = await tool.run({"action": "mute"}, CTX)
    assert muted.user_message == "Muted."
    assert muted.undo is not None
    await tool.undo(muted.undo, CTX)
    assert (await pc.volume()).muted is False


async def test_brightness_and_missing_control(pc: FakePcControl) -> None:
    tool = SystemTool(pc)
    result = await tool.run({"action": "brightness", "level": 40}, CTX)
    assert result.user_message == "Brightness 40%."
    pc.without_brightness()
    missing = await tool.run({"action": "brightness", "level": 40}, CTX)
    assert missing.user_message == "This screen's brightness can't be changed from Windows."


async def test_radios_and_wifi_off_asks(pc: FakePcControl) -> None:
    tool = SystemTool(pc)
    assert tool.risk_for({"action": "wifi", "on": False}) is Risk.CONFIRM
    assert tool.risk_for({"action": "wifi", "on": True}) is Risk.SAFE
    on = await tool.run({"action": "bluetooth", "on": True}, CTX)
    assert on.user_message == "Bluetooth on."
    assert await pc.radio(Radio.BLUETOOTH) is True
    pc.without_radio(Radio.BLUETOOTH)
    none = await tool.run({"action": "bluetooth", "on": True}, CTX)
    assert none.user_message == "This PC has no Bluetooth."


async def test_media_keys(pc: FakePcControl) -> None:
    await SystemTool(pc).run({"action": "media", "media": "next"}, CTX)
    assert pc.media_actions == [MediaAction.NEXT]


# --- screenshots


async def test_screenshot_saved_and_undone(pc: FakePcControl) -> None:
    tool = ScreenshotTool(pc, now=lambda: datetime(2026, 10, 17, 15, 41, 7))
    result = await tool.run({}, CTX)
    path = pc.screenshots_folder() / "EV 2026-10-17 15.41.07.png"
    assert path.is_file()
    assert result.user_message == "Saved to Pictures\\Screenshots as EV 2026-10-17 15.41.07.png."
    assert result.undo is not None
    await tool.undo(result.undo, CTX)
    assert not path.exists()


# --- files


def _tree(pc: FakePcControl) -> dict[str, Path]:
    folders = {f.name: f for f in pc.user_folders()}
    (folders["Documents"] / "Taxes").mkdir()
    files = {
        "report": folders["Documents"] / "Quarterly Report.pdf",
        "old": folders["Documents"] / "Taxes" / "report-2025.pdf",
        "song": folders["Music"] / "song.mp3",
    }
    for i, path in enumerate(files.values()):
        path.write_text("x")
        import os

        os.utime(path, (1_700_000_000 + i, 1_700_000_000 + i))
    (folders["Documents"] / ".hidden report.pdf").write_text("x")
    return files


async def test_find_open_move_delete(pc: FakePcControl) -> None:
    files = _tree(pc)
    tool = FilesTool(pc)
    found = json.loads((await tool.run({"action": "find", "query": "report"}, CTX)).content)
    assert found == [str(files["old"]), str(files["report"])]  # newest first, hidden skipped
    opened = await tool.run({"action": "open", "path": str(files["song"])}, CTX)
    assert opened.ok
    assert pc.opened == [files["song"]]
    moved = await tool.run(
        {"action": "move", "path": str(files["report"]), "destination": "downloads"}, CTX
    )
    assert moved.user_message == "Moved Quarterly Report.pdf to Downloads."
    assert moved.undo is not None
    await tool.undo(moved.undo, CTX)
    assert files["report"].is_file()
    deleted = await tool.run({"action": "delete", "path": str(files["song"])}, CTX)
    assert deleted.user_message == "Deleted song.mp3. It's in the Recycle Bin."
    assert not files["song"].exists()
    assert (pc.home / ".trash" / "song.mp3").is_file()


async def test_files_stay_inside_user_folders(pc: FakePcControl, tmp_path: Path) -> None:
    _tree(pc)
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    tool = FilesTool(pc)
    result = await tool.run({"action": "delete", "path": str(outside)}, CTX)
    assert result.user_message == "That file isn't in your folders."
    assert outside.exists()
    risk = {a: tool.risk_for({"action": a}) for a in ("find", "open", "move", "delete")}
    assert risk == {
        "find": Risk.SAFE,
        "open": Risk.SAFE,
        "move": Risk.CONFIRM,
        "delete": Risk.DANGEROUS,
    }
    assert tool.question({"action": "delete", "path": "/x/a.pdf"}) == (
        "Delete a.pdf? It goes to the Recycle Bin."
    )


def test_search_needs_every_word(tmp_path: Path) -> None:
    (tmp_path / "budget 2026 final.xlsx").write_text("x")
    (tmp_path / "budget draft.xlsx").write_text("x")
    assert [p.name for p in search_files([tmp_path], "final budget")] == ["budget 2026 final.xlsx"]
    assert search_files([tmp_path], "!!") == []


# --- ui


async def test_ui_snapshot_type_and_verify(pc: FakePcControl) -> None:
    await AppsTool(pc).run({"action": "open", "name": "notepad"}, CTX)
    tool = UiTool(pc)
    snap = json.loads((await tool.run({"action": "snapshot"}, CTX)).content)
    assert snap["window"] == "Untitled - Notepad"
    assert [e["name"] for e in snap["elements"]] == ["Text editor", "Save"]
    typed = await tool.run({"action": "type", "element": 1, "text": "hello"}, CTX)
    assert typed.ok
    changed = json.loads(typed.content)["changed"]
    assert changed == [{"id": 1, "role": "edit", "name": "Text editor", "value": "hello"}]
    assert tool.question({"action": "type", "text": "hello"}) == "Type “hello” in notepad?"


async def test_ui_risk_by_element_name(pc: FakePcControl) -> None:
    await AppsTool(pc).run({"action": "open", "name": "notepad"}, CTX)
    tool = UiTool(pc)
    assert tool.risk_for({"action": "snapshot"}) is Risk.SAFE
    await tool.run({"action": "snapshot"}, CTX)
    assert tool.risk_for({"action": "click", "element": 2}) is Risk.CONFIRM
    tool._elements[2] = tool._elements[2].__class__(2, "button", "Send", "", enabled=True)
    assert tool.risk_for({"action": "click", "element": 2}) is Risk.DANGEROUS
    assert tool.question({"action": "click", "element": 2}) == "Click “Send” in notepad?"


async def test_ui_needs_a_snapshot_first(pc: FakePcControl) -> None:
    result = await UiTool(pc).run({"action": "click", "element": 1}, CTX)
    assert result.user_message == "Take a snapshot first."


async def test_fake_selection(pc: FakePcControl) -> None:
    assert await pc.selection() is None
    pc.selected = Selection("teh text", "notepad", "notes.txt - Notepad")
    assert await pc.replace_selection("the text")
    assert pc.replaced == "the text"
