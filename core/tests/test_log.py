import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ev_core.log import BACKUP_COUNT, MAX_BYTES, JsonFormatter, set_level, setup_logging


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        "ev_core.test", logging.INFO, __file__, 1, "hello %s", ("world",), None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formats_one_json_object() -> None:
    entry = json.loads(JsonFormatter().format(_record()))
    assert entry["level"] == "info"
    assert entry["logger"] == "ev_core.test"
    assert entry["msg"] == "hello world"
    assert entry["ts"].endswith("+00:00")


def test_fields_are_merged_without_overriding_base_keys() -> None:
    entry = json.loads(JsonFormatter().format(_record(fields={"port": 5, "msg": "spoof"})))
    assert entry["port"] == 5
    assert entry["msg"] == "hello world"


def _raise() -> None:
    raise ValueError("boom")


def test_exception_is_included() -> None:
    record = _record()
    try:
        _raise()
    except ValueError:
        record.exc_info = sys.exc_info()
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in entry["exc"]


def test_setup_writes_rotating_file_and_level_changes(tmp_path: Path) -> None:
    setup_logging(tmp_path / "logs", "info")
    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].maxBytes == MAX_BYTES
    assert file_handlers[0].backupCount == BACKUP_COUNT

    logging.getLogger("ev_core.test").debug("hidden")
    logging.getLogger("ev_core.test").info("shown")
    set_level("debug")
    logging.getLogger("ev_core.test").debug("now shown")
    file_handlers[0].flush()

    lines = [
        json.loads(line)["msg"]
        for line in (tmp_path / "logs" / "core.log").read_text().splitlines()
    ]
    assert lines == ["shown", "now shown"]
