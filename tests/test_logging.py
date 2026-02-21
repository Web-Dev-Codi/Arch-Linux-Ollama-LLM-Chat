"""Tests for structured logging behavior."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json
import logging
import tempfile
from pathlib import Path
import unittest

from ollama_chat.chat import OllamaChat
from ollama_chat.logging_utils import JsonFormatter, configure_logging


class RetryClient:
    """Fake client that fails once and then succeeds."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self, model: str, messages: list[dict[str, str]], stream: bool
    ) -> AsyncGenerator[dict[str, dict[str, str]], None]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")

        async def stream_response() -> AsyncGenerator[dict[str, dict[str, str]], None]:
            yield {"message": {"content": "ok"}}

        return stream_response()


class LoggingTests(unittest.IsolatedAsyncioTestCase):
    """Validate log format and required retry event emission."""

    async def test_chat_retry_log_event_emitted(self) -> None:
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            retries=1,
            retry_backoff_seconds=0.0,
            client=RetryClient(),
        )

        with self.assertLogs("ollama_chat.chat", level="WARNING") as logs:
            chunks: list[str] = []
            async for chunk in chat.send_message("hello"):
                chunks.append(chunk)

        self.assertEqual(chunks, ["ok"])
        self.assertTrue(any("chat.request.retry" in line for line in logs.output))

    async def test_json_formatter_includes_structured_fields(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="ollama_chat.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="state transition",
            args=(),
            exc_info=None,
        )
        record.event = "app.state.transition"
        record.from_state = "IDLE"
        record.to_state = "STREAMING"

        data = json.loads(formatter.format(record))
        self.assertEqual(data["event"], "app.state.transition")
        self.assertEqual(data["from_state"], "IDLE")
        self.assertEqual(data["to_state"], "STREAMING")
        self.assertEqual(data["level"], "INFO")


class ConfigureLoggingTests(unittest.TestCase):
    """Validate configure_logging() handler setup behavior."""

    def setUp(self) -> None:
        # Preserve root logger state so tests do not pollute each other.
        root = logging.getLogger()
        self._original_level = root.level
        self._original_handlers = list(root.handlers)

    def tearDown(self) -> None:
        root = logging.getLogger()
        root.setLevel(self._original_level)
        root.handlers.clear()
        root.handlers.extend(self._original_handlers)

    def test_configure_logging_adds_stderr_handler(self) -> None:
        configure_logging({"level": "DEBUG", "structured": False, "log_to_file": False})
        root = logging.getLogger()
        stream_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        self.assertTrue(len(stream_handlers) >= 1)

    def test_configure_logging_structured_uses_json_formatter(self) -> None:
        configure_logging({"level": "DEBUG", "structured": True, "log_to_file": False})
        root = logging.getLogger()
        formatters = [h.formatter for h in root.handlers]
        self.assertTrue(any(isinstance(f, JsonFormatter) for f in formatters))

    def test_configure_logging_plain_formatter_when_not_structured(self) -> None:
        configure_logging({"level": "DEBUG", "structured": False, "log_to_file": False})
        root = logging.getLogger()
        formatters = [h.formatter for h in root.handlers]
        self.assertFalse(any(isinstance(f, JsonFormatter) for f in formatters))

    def test_configure_logging_sets_root_level(self) -> None:
        configure_logging({"level": "DEBUG", "structured": False, "log_to_file": False})
        root = logging.getLogger()
        self.assertEqual(root.level, logging.DEBUG)

    def test_configure_logging_noisy_loggers_set_to_warning(self) -> None:
        configure_logging({"level": "DEBUG", "structured": False, "log_to_file": False})
        for name in ("httpx", "httpcore", "ollama"):
            self.assertEqual(logging.getLogger(name).level, logging.WARNING)

    def test_configure_logging_file_handler_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = str(Path(tmp) / "test.log")
            configure_logging(
                {
                    "level": "DEBUG",
                    "structured": False,
                    "log_to_file": True,
                    "log_file_path": log_path,
                }
            )
            root = logging.getLogger()
            file_handlers = [
                h for h in root.handlers if isinstance(h, logging.FileHandler)
            ]
            self.assertTrue(len(file_handlers) >= 1)
            self.assertTrue(Path(log_path).exists())

    def test_configure_logging_stderr_handler_filters_to_ollama_chat(self) -> None:
        configure_logging({"level": "DEBUG", "structured": False, "log_to_file": False})
        root = logging.getLogger()
        stream_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        self.assertTrue(len(stream_handlers) >= 1)
        handler = stream_handlers[0]
        # Filters may be stored as callables (plain functions) or Filter objects.
        # logging.Handler.filter() applies all filters correctly regardless.
        chat_record = logging.LogRecord(
            name="ollama_chat.app",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="ok",
            args=(),
            exc_info=None,
        )
        other_record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="noise",
            args=(),
            exc_info=None,
        )
        # handler.filter() returns truthy when all filters pass.
        self.assertTrue(handler.filter(chat_record))
        self.assertFalse(handler.filter(other_record))


if __name__ == "__main__":
    unittest.main()
