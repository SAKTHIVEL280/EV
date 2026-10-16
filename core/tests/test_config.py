from pathlib import Path

import tomlkit
from tomlkit.toml_document import TOMLDocument

from ev_core.config import CURRENT_CONFIG_VERSION, ConfigStore, EvConfig, LogLevel


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_missing_file_is_created_with_commented_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    loaded = ConfigStore(path).load()
    assert loaded.config == EvConfig()
    assert loaded.warnings == ()
    text = path.read_text(encoding="utf-8")
    assert f"config_version = {CURRENT_CONFIG_VERSION}" in text
    assert "# Log detail level" in text
    assert ConfigStore(path).load().warnings == ()


def test_valid_value_is_used(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, 'config_version = 1\n[logging]\nlevel = "debug"\n')
    assert ConfigStore(path).load().config.logging.level is LogLevel.DEBUG


def test_invalid_value_falls_back_with_warning(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, 'config_version = 1\n[logging]\nlevel = "loud"\n')
    loaded = ConfigStore(path).load()
    assert loaded.config.logging.level is LogLevel.INFO
    assert [w.key for w in loaded.warnings] == ["logging.level"]
    assert "'info'" in loaded.warnings[0].message


def test_wrong_type_is_not_coerced(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "config_version = 1\n[logging]\nlevel = 1\n")
    loaded = ConfigStore(path).load()
    assert loaded.config.logging.level is LogLevel.INFO
    assert [w.key for w in loaded.warnings] == ["logging.level"]


def test_section_that_is_not_a_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, 'config_version = 1\nlogging = "x"\n')
    loaded = ConfigStore(path).load()
    assert loaded.config == EvConfig()
    assert [w.key for w in loaded.warnings] == ["logging"]


def test_syntax_error_uses_defaults_and_leaves_file_untouched(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    broken = "config_version = 1\n[logging\nlevel = 'debug'\n"
    _write(path, broken)
    loaded = ConfigStore(path).load()
    assert loaded.config == EvConfig()
    assert len(loaded.warnings) == 1
    assert path.read_text(encoding="utf-8") == broken


def test_missing_version_warns_and_assumes_current(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, '[logging]\nlevel = "warning"\n')
    loaded = ConfigStore(path).load()
    assert loaded.config.logging.level is LogLevel.WARNING
    assert [w.key for w in loaded.warnings] == ["config_version"]


def test_newer_version_warns_and_does_not_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    text = 'config_version = 99\n[logging]\nlevel = "error"\n[future]\nx = 1\n'
    _write(path, text)
    loaded = ConfigStore(path).load()
    assert loaded.config.logging.level is LogLevel.ERROR
    assert [w.key for w in loaded.warnings] == ["config_version"]
    assert path.read_text(encoding="utf-8") == text


def test_migration_backs_up_preserves_unknown_keys_and_comments(tmp_path: Path) -> None:
    def v1_to_v2(doc: TOMLDocument) -> None:
        # Example rename: [log] verbosity -> [logging] level.
        old = doc.pop("log")
        doc["logging"] = {"level": old["verbosity"]}

    path = tmp_path / "config.toml"
    original = '# my note\nconfig_version = 1\nmystery = "keep me"\n[log]\nverbosity = "debug"\n'
    _write(path, original)

    loaded = ConfigStore(path, migrations={1: v1_to_v2}, current_version=2).load()

    assert loaded.config.logging.level is LogLevel.DEBUG
    assert loaded.warnings == ()
    assert (tmp_path / "config.toml.bak-v1").read_text(encoding="utf-8") == original
    migrated = path.read_text(encoding="utf-8")
    doc = tomlkit.parse(migrated)
    assert doc["config_version"] == 2
    assert doc["mystery"] == "keep me"
    assert "# my note" in migrated


def test_missing_migration_step_uses_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = 'config_version = 1\n[logging]\nlevel = "debug"\n'
    _write(path, original)
    loaded = ConfigStore(path, migrations={}, current_version=2).load()
    assert loaded.config == EvConfig()
    assert [w.key for w in loaded.warnings] == ["config_version"]
    assert path.read_text(encoding="utf-8") == original


def test_unknown_keys_are_ignored_without_warning(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, 'config_version = 1\n[logging]\nlevel = "info"\ncolor = true\n[plugins]\na = 1\n')
    assert ConfigStore(path).load().warnings == ()
