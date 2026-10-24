from pathlib import Path

import pytest
import tomlkit

from ev_core.config import ConfigStore, EffortLevel, LogLevel
from ev_core.config.schema import Nav
from ev_core.config.settings import describe
from ev_core.config.store import SYNTAX_REFUSAL, UNKNOWN_SETTING, ConfigEditError


def store(tmp_path: Path, text: str | None = None) -> ConfigStore:
    path = tmp_path / "config.toml"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    return ConfigStore(path)


def test_set_writes_value_and_keeps_comments_and_unknown_keys(tmp_path: Path) -> None:
    s = store(tmp_path, "# mine\nconfig_version = 1\nmystery = 1\n[llm]\n# note\ncontext = 4096\n")
    loaded = s.set_value("llm", "context", 16384)
    assert loaded.config.llm.context == 16384
    text = s.path.read_text(encoding="utf-8")
    assert "# mine" in text
    assert "# note" in text
    assert tomlkit.parse(text)["mystery"] == 1


def test_set_creates_missing_file_and_section(tmp_path: Path) -> None:
    s = store(tmp_path)
    assert (
        s.set_value("agent", "default_effort", "deep").config.agent.default_effort
        is EffortLevel.DEEP
    )
    s.path.write_text("config_version = 1\n", encoding="utf-8")
    assert s.set_value("logging", "level", "debug").config.logging.level is LogLevel.DEBUG


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("llm", "context", 99, "That value isn't allowed. Use 2048 to 131072."),
        ("llm", "context", "8192", "That value isn't allowed. Use 2048 to 131072."),
        ("llm", "enabled", 1, "That value isn't allowed. Use on or off."),
        (
            "agent",
            "default_effort",
            "extreme",
            "That value isn't allowed. Use one of: instant, normal, deep, max.",
        ),
        ("llm", "nope", 1, UNKNOWN_SETTING),
        ("nope", "x", 1, UNKNOWN_SETTING),
    ],
)
def test_invalid_changes_are_refused_and_file_unchanged(
    tmp_path: Path, section: str, key: str, value: object, message: str
) -> None:
    original = "config_version = 1\n[llm]\ncontext = 4096\n"
    s = store(tmp_path, original)
    with pytest.raises(ConfigEditError) as caught:
        s.set_value(section, key, value)
    assert caught.value.user_message == message
    assert s.path.read_text(encoding="utf-8") == original


def test_syntax_error_refuses_edits(tmp_path: Path) -> None:
    broken = "config_version = 1\n[llm\n"
    s = store(tmp_path, broken)
    with pytest.raises(ConfigEditError) as caught:
        s.set_value("llm", "context", 4096)
    assert caught.value.user_message == SYNTAX_REFUSAL
    assert s.path.read_text(encoding="utf-8") == broken


def test_reset_removes_the_key(tmp_path: Path) -> None:
    s = store(tmp_path, "config_version = 1\n[llm]\ncontext = 4096\nthreads = 4\n")
    loaded = s.reset_value("llm", "context")
    assert loaded.config.llm.context == 8192
    assert loaded.config.llm.threads == 4
    assert "context" not in s.path.read_text(encoding="utf-8")
    # Resetting an absent key is a no-op.
    assert s.reset_value("llm", "context").config.llm.context == 8192
    with pytest.raises(ConfigEditError):
        s.reset_value("llm", "nope")


def test_descriptors_cover_every_key_with_metadata(tmp_path: Path) -> None:
    loaded = store(tmp_path, "config_version = 1\n[llm]\ncontext = 4096\n").load()
    items = {f"{i.section}.{i.key}": i for i in describe(loaded.config)}
    assert set(items) == {
        "logging.level",
        "llm.enabled",
        "llm.models_dir",
        "llm.model_small",
        "llm.model_default",
        "llm.model_large",
        "llm.threads",
        "llm.context",
        "llm.idle_unload_minutes",
        "agent.default_effort",
        "hotkeys.open_panel",
        "island.reveal_distance",
        "island.reveal_delay_ms",
        "island.arc_width",
        "island.arc_depth",
        "permissions.apps",
        "permissions.window",
        "permissions.system",
        "permissions.screenshot",
        "permissions.clipboard",
        "permissions.files",
        "permissions.timer",
        "permissions.focus_mode",
        "permissions.ui",
        "clipboard.history",
        "clipboard.actions",
        "voice.enabled",
        "voice.speak_replies",
        "voice.voice",
        "voice.speed",
        "voice.volume",
        "voice.recognizer",
        "voice.follow_up",
        "voice.earcons_volume",
    }
    assert items["permissions.files"].options == ("allow", "ask", "block")
    assert items["permissions.files"].nav is Nav.PERMISSIONS
    assert items["clipboard.actions"].default is False
    assert items["voice.voice"].widget == "menu"
    assert items["voice.voice"].labels[0] == "Heart (female)"
    assert len(items["voice.voice"].labels) == len(items["voice.voice"].options)
    assert items["voice.speak_replies"].labels == ("When I speak", "Always", "Never")
    assert items["permissions.files"].labels == ()
    assert items["island.reveal_distance"].nav is Nav.APPEARANCE
    assert (items["island.reveal_distance"].unit, items["island.reveal_delay_ms"].unit) == (
        "px",
        "ms",
    )
    assert items["llm.context"].unit == "tokens"
    assert items["agent.default_effort"].unit is None
    context = items["llm.context"]
    assert (context.kind, context.minimum, context.maximum) == ("integer", 2048, 131072)
    assert (context.default, context.value, context.nav) == (8192, 4096, Nav.MODELS)
    assert items["agent.default_effort"].options == ("instant", "normal", "deep", "max")
    assert items["agent.default_effort"].nav is Nav.GENERAL
    assert items["logging.level"].nav is Nav.DIAGNOSTICS
    assert items["llm.enabled"].kind == "boolean"
    # Controls (F-415): nothing that needs knowing exact text is a plain text box.
    assert {k: (i.widget, i.role) for k, i in items.items() if i.widget == "model"} == {
        "llm.model_small": ("model", "small"),
        "llm.model_default": ("model", "default"),
        "llm.model_large": ("model", "large"),
    }
    assert items["llm.models_dir"].widget == "folder"
    assert items["hotkeys.open_panel"].widget == "shortcut"
    assert context.widget == "slider"
    assert context.steps == (2048, 4096, 8192, 16384, 32768, 65536, 131072)
    assert (items["island.arc_width"].minimum, items["island.arc_width"].maximum) == (24, 160)
    assert [i.key for i in items.values() if i.kind == "integer" and i.widget != "slider"] == []
    for item in items.values():
        for step in item.steps:
            assert item.minimum is not None
            assert item.maximum is not None
            assert item.minimum <= step <= item.maximum, (item.key, step)
        assert list(item.steps) == sorted(item.steps)
        assert item.label
        assert item.description
        assert item.label != item.key


@pytest.mark.parametrize(
    "value", ["Ctrl+Space", "ctrl+shift+space", "Alt+F12", "Ctrl+Alt+K", "Super+1", ""]
)
def test_valid_shortcuts(tmp_path: Path, value: str) -> None:
    assert (
        store(tmp_path).set_value("hotkeys", "open_panel", value).config.hotkeys.open_panel == value
    )


@pytest.mark.parametrize(
    "value",
    [
        "Space",
        "a",
        "space+a",
        "Ctrl+",
        "Ctrl+Space+X",
        "Ctrl+Shift+Alt+Super+A",
        "Ctrl+F13",
        "Hyper+A",
    ],
)
def test_invalid_shortcuts(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigEditError) as caught:
        store(tmp_path).set_value("hotkeys", "open_panel", value)
    assert caught.value.user_message == (
        "That value isn't allowed. "
        "Use one to three of Ctrl, Alt, Shift, Super and a key, like Ctrl+Space."
    )
