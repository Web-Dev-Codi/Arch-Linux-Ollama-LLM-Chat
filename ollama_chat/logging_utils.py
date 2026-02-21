"""Logging bootstrap utilities with optional structured output."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

# Epoch used to convert LogRecord.created (POSIX float) to UTC datetime.
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_STANDARD_LOG_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    """Emit JSON lines for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        # Use the actual event time from the LogRecord, not the formatting time.
        ts = (_EPOCH + timedelta(seconds=record.created)).isoformat()
        data: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_ATTRS:
                continue
            data[key] = value
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _best_effort_private_permissions(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        path.chmod(0o600)
    except OSError:
        logging.getLogger(__name__).warning(
            "Unable to enforce 0600 permissions for %s", path
        )


def configure_logging(logging_config: dict[str, Any]) -> None:
    """Configure root logging according to app config."""
    level_name = str(logging_config.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    structured = bool(logging_config.get("structured", True))
    log_to_file = bool(logging_config.get("log_to_file", False))
    log_file_path = str(
        logging_config.get("log_file_path", "~/.local/state/ollama-chat/app.log")
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter: logging.Formatter
    if structured:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    for logger_name in ("httpx", "httpcore", "ollama"):
        library_logger = logging.getLogger(logger_name)
        library_logger.setLevel(logging.WARNING)
        library_logger.propagate = True

    def app_only_filter(record: logging.LogRecord) -> bool:
        return record.name.startswith("ollama_chat")

    console_level = max(level, logging.WARNING)
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(console_level)
    stderr_handler.addFilter(app_only_filter)
    root.addHandler(stderr_handler)

    if log_to_file:
        target = Path(log_file_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)
        _best_effort_private_permissions(target)
