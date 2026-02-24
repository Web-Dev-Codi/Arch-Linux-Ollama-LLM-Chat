"""Tests for batched streaming rendering behavior."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import unittest

try:
    from ollama_chat.app import OllamaChatApp
except ModuleNotFoundError:
    OllamaChatApp = None  # type: ignore[assignment]


class _FakeConversation:
    def __init__(self) -> None:
        self.scroll_calls = 0

    def scroll_end(self, animate: bool = False) -> None:
        self.scroll_calls += 1


class _FakeBubble:
    def __init__(self) -> None:
        self.content = ""
        self.append_calls = 0
        self.set_calls = 0

    def append_content(self, content_chunk: str) -> None:
        self.content += content_chunk
        self.append_calls += 1

    def set_content(self, content: str) -> None:
        self.content = content
        self.set_calls += 1

    def append_thinking(self, chunk: str) -> None:  # noqa: ARG002
        pass

    def finalize_thinking(self) -> None:
        pass

    def append_tool_call(self, name: str, args: dict) -> None:  # noqa: ARG002
        pass

    def append_tool_result(self, name: str, result: str) -> None:  # noqa: ARG002
        pass

    async def finalize_content(self) -> None:
        pass


class _FakeChat:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def send_message(
        self, user_message: str, **kwargs
    ) -> AsyncGenerator:  # noqa: ARG002
        from ollama_chat.chat import ChatChunk

        for chunk in self._chunks:
            yield ChatChunk(kind="content", text=chunk)


class _FakeApp:
    def __init__(self, chunks: list[str], stream_chunk_size: int) -> None:
        self.config = {"ui": {"stream_chunk_size": stream_chunk_size}}
        self.chat = _FakeChat(chunks)
        self._conversation = _FakeConversation()
        self.sub_title = ""
        self._tool_registry = None
        from ollama_chat.capabilities import CapabilityContext
        from ollama_chat.task_manager import TaskManager

        self.capabilities = CapabilityContext(think=False, max_tool_iterations=10)
        self._effective_caps = self.capabilities
        self._w_conversation = self._conversation
        self._task_manager = TaskManager()

    def query_one(self, *_args, **_kwargs) -> _FakeConversation:
        return self._conversation

    def _update_status_bar(self) -> None:
        return

    async def _animate_response_placeholder(
        self, bubble: _FakeBubble
    ) -> None:  # noqa: ARG002
        """Stub: production version animates a placeholder until cancelled."""
        import asyncio

        await asyncio.sleep(9999)

    async def _stop_response_indicator_task(self) -> None:
        """Stub: cancel the indicator task if it is running."""
        await self._task_manager.cancel("response_indicator")


@unittest.skipIf(OllamaChatApp is None, "textual is not installed")
class RenderBatchingTests(unittest.IsolatedAsyncioTestCase):
    """Validate that stream updates are batched and flushed."""

    async def test_chunk_updates_are_batched(self) -> None:
        fake_app = _FakeApp(
            chunks=["a", "b", "c", "d", "e", "f", "g"], stream_chunk_size=3
        )
        bubble = _FakeBubble()

        await OllamaChatApp._stream_assistant_response(fake_app, "hello", bubble)  # type: ignore[arg-type]

        self.assertEqual(bubble.content, "abcdefg")
        self.assertEqual(bubble.append_calls, 3)
        # set_content("") is called once when the first chunk arrives to clear
        # the animated placeholder before appending streamed content.
        self.assertEqual(bubble.set_calls, 1)
        self.assertEqual(fake_app._conversation.scroll_calls, 3)

    async def test_empty_stream_sets_placeholder(self) -> None:
        fake_app = _FakeApp(chunks=[], stream_chunk_size=4)
        bubble = _FakeBubble()

        await OllamaChatApp._stream_assistant_response(fake_app, "hello", bubble)  # type: ignore[arg-type]

        self.assertEqual(bubble.content, "(No response from model.)")
        self.assertEqual(bubble.append_calls, 0)
        self.assertEqual(bubble.set_calls, 1)


if __name__ == "__main__":
    unittest.main()
