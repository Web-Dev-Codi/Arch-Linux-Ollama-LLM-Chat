"""Logging bootstrap utilities with optional structured output."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

import structlog



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
    """Configure root logging according to app config using structlog."""
    level_name = str(logging_config.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    structured = bool(logging_config.get("structured", True))
    log_to_file = bool(logging_config.get("log_to_file", False))
    log_file_path = str(
        logging_config.get("log_file_path", "~/.local/state/ollamaterm/app.log")
    )

    # Reset stdlib root logger handlers and level.
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Common filter: only show our app logs on stderr to reduce noise.
    def app_only_filter(record: logging.LogRecord) -> bool:
        return record.name.startswith("ollama_chat")

    # Configure structlog to integrate with stdlib logging. This allows both
    # logging.getLogger(__name__) and structlog.get_logger() to produce JSON.
    if structured:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        processor_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(
                ensure_ascii=False, separators=(",", ":")
            ),
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
            ],
        )

        console_level = max(level, logging.WARNING)
        stderr_handler = logging.StreamHandler()
        stderr_handler.setLevel(console_level)
        stderr_handler.setFormatter(processor_formatter)
        stderr_handler.addFilter(app_only_filter)
        root.addHandler(stderr_handler)

        if log_to_file:
            target = Path(log_file_path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(target, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(processor_formatter)
            root.addHandler(file_handler)
            _best_effort_private_permissions(target)
    else:
        # Plain-text fallback compatible with stdlib logging.
        plain_formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )

        console_level = max(level, logging.WARNING)
        stderr_handler = logging.StreamHandler()
        stderr_handler.setLevel(console_level)
        stderr_handler.setFormatter(plain_formatter)
        stderr_handler.addFilter(app_only_filter)
        root.addHandler(stderr_handler)

        if log_to_file:
            target = Path(log_file_path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(target, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(plain_formatter)
            root.addHandler(file_handler)
            _best_effort_private_permissions(target)

    # Quieten noisy third-party libraries regardless of structured/plain mode.
    for logger_name in ("httpx", "httpcore", "ollama"):
        library_logger = logging.getLogger(logger_name)
        library_logger.setLevel(logging.WARNING)
        library_logger.propagate = True
