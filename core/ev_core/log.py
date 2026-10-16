"""Structured, rotating, local-only logging (docs/ARCHITECTURE.md §4.5).

Records are JSON lines. Pass structured fields with ``extra={"fields": {...}}``.
Personal content (transcripts, prompts, file contents, clipboard) is only ever
logged at DEBUG.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

LOG_FILE_NAME: Final = "core.log"
MAX_BYTES: Final = 5 * 1024 * 1024
# core.log plus 4 rotated files = 5 files kept.
BACKUP_COUNT: Final = 4

_BASE_KEYS: Final = frozenset({"ts", "level", "logger", "msg", "exc"})


class JsonFormatter(logging.Formatter):
    """Formats a record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                if isinstance(key, str) and key not in _BASE_KEYS:
                    entry[key] = value
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(log_dir: Path, level: str) -> None:
    """Configure the root logger: rotating JSON file, plus warnings on stderr.

    stdout is reserved for the startup handshake line and is never used here.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter()

    file_handler = RotatingFileHandler(
        log_dir / LOG_FILE_NAME,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.addHandler(file_handler)
    root.addHandler(stderr_handler)
    set_level(level)


def set_level(level: str) -> None:
    """Change the root log level at runtime (config hot reload)."""
    logging.getLogger().setLevel(level.upper())
