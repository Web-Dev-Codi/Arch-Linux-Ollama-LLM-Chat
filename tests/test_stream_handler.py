"""Tests for the StreamHandler chunk processor."""

from __future__ import annotations

from typing import Any
import unittest

from ollama_chat.stream_handler import StreamHandler


class _FakeBubble:
    def __init__(self) -> None:
        self.content = ""
        self.thinking_chunks: list[str] = []
        self.thinking_finalized = False
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.tool_results: list[tuple[str, str]] = []
        self.finalized = False

    def set_content(self, text: str) -> None:
        self.content = text

    def append_content(self, text: str) -> None:
        self.content += text

    def append_thinking(self, text: str) -> None:
        self.thinking_chunks.append(text)

    def finalize_thinking(self) -> None:
        self.thinking_finalized = True

    def append_tool_call(self, name: str, args: dict[str, Any]) -> None:
        self.tool_calls.append((name, args))

    def append_tool_result(self, name: str, result: str) -> None:
        self.tool_results.append((name, result))

    async def finalize_content(self) -> None:
        self.finalized = True


class StreamHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Validate StreamHandler chunk processing and batching."""

    async def _noop_stop(self) -> None:
        pass

    async def test_content_batching(self) -> None:
        bubble = _FakeBubble()
        scrolls: list[bool] = []
        handler = StreamHandler(bubble, lambda: scrolls.append(True), chunk_size=3)

        for char in "abcde":
            await handler.handle_content(char, self._noop_stop)

        # After 5 chars with chunk_size=3: one flush at 3, remaining 2 still buffered.
        self.assertEqual(bubble.content, "abc")
        self.assertEqual(len(scrolls), 1)

        await handler.finalize()
        self.assertEqual(bubble.content, "abcde")
        self.assertTrue(bubble.finalized)

    async def test_thinking_then_content(self) -> None:
        bubble = _FakeBubble()
        handler = StreamHandler(bubble, lambda: None, chunk_size=1)

        await handler.handle_thinking("hmm", self._noop_stop)
        self.assertTrue(handler.thinking_started)
        self.assertTrue(handler.response_started)
        self.assertEqual(handler.status, "Thinking...")

        await handler.handle_content("answer", self._noop_stop)
        self.assertTrue(bubble.thinking_finalized)
        self.assertFalse(handler.thinking_started)
        self.assertEqual(handler.status, "Streaming response...")

    async def test_tool_call_flushes_buffer(self) -> None:
        bubble = _FakeBubble()
        handler = StreamHandler(bubble, lambda: None, chunk_size=10)

        await handler.handle_content("partial", self._noop_stop)
        # Buffer not yet flushed (chunk_size=10).
        self.assertEqual(bubble.content, "")

        await handler.handle_tool_call("search", {"q": "test"}, self._noop_stop)
        # Buffer flushed before tool call.
        self.assertEqual(bubble.content, "partial")
        self.assertEqual(bubble.tool_calls, [("search", {"q": "test"})])
        self.assertIn("search", handler.status)

    async def test_tool_result(self) -> None:
        bubble = _FakeBubble()
        handler = StreamHandler(bubble, lambda: None, chunk_size=1)

        handler.handle_tool_result("calc", "42")
        self.assertEqual(bubble.tool_results, [("calc", "42")])
        self.assertEqual(handler.status, "Processing tool result...")

    async def test_finalize_no_response_sets_placeholder(self) -> None:
        bubble = _FakeBubble()
        handler = StreamHandler(bubble, lambda: None, chunk_size=1)

        await handler.finalize()
        self.assertEqual(bubble.content, "(No response from model.)")
        self.assertTrue(bubble.finalized)

    async def test_stop_indicator_called_on_first_chunk(self) -> None:
        bubble = _FakeBubble()
        stop_called: list[bool] = []

        async def _stop() -> None:
            stop_called.append(True)

        handler = StreamHandler(bubble, lambda: None, chunk_size=1)
        await handler.handle_content("a", _stop)
        await handler.handle_content("b", _stop)

        # Only called once (on the first chunk that starts the response).
        self.assertEqual(len(stop_called), 1)


if __name__ == "__main__":
    unittest.main()
