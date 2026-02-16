"""Tests for structured logging behavior."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json
import logging
import unittest

from ollama_chat.chat import OllamaChat
from ollama_chat.logging_utils import JsonFormatter


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


if __name__ == "__main__":
    unittest.main()
