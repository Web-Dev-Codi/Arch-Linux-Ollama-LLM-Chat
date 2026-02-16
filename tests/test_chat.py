"""Tests for OllamaChat streaming, retries, and history management."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import unittest

from ollama_chat.chat import OllamaChat
from ollama_chat.exceptions import OllamaModelNotFoundError, OllamaStreamingError


async def _chunk_stream(chunks: list[str]) -> AsyncGenerator[dict[str, dict[str, str]], None]:
    for chunk in chunks:
        yield {"message": {"content": chunk}}


class FakeClient:
    """Simple fake Ollama client for deterministic tests."""

    def __init__(self, responses: list[list[str]], fail_calls: set[int] | None = None) -> None:
        self.responses = responses
        self.fail_calls = fail_calls or set()
        self.calls = 0
        self.messages_per_call: list[list[dict[str, str]]] = []

    async def chat(self, model: str, messages: list[dict[str, str]], stream: bool) -> AsyncGenerator[dict[str, dict[str, str]], None]:
        self.calls += 1
        self.messages_per_call.append(list(messages))
        if self.calls in self.fail_calls:
            raise RuntimeError("simulated transient failure")
        payload_index = min(self.calls - 1, len(self.responses) - 1)
        return _chunk_stream(self.responses[payload_index])


class ChatTests(unittest.IsolatedAsyncioTestCase):
    """Async chat behavior tests with deterministic fakes."""

    async def test_streaming_yields_chunks_and_persists_history(self) -> None:
        client = FakeClient(responses=[["Hello", " world"]])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="You are helpful.",
            client=client,
        )

        received: list[str] = []
        async for chunk in chat.send_message("Hi there"):
            received.append(chunk)

        self.assertEqual(received, ["Hello", " world"])
        self.assertEqual(chat.messages[-2], {"role": "user", "content": "Hi there"})
        self.assertEqual(chat.messages[-1], {"role": "assistant", "content": "Hello world"})

    async def test_clear_history_keeps_system_prompt(self) -> None:
        client = FakeClient(responses=[["A"]])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System instruction",
            client=client,
        )
        async for _ in chat.send_message("question"):
            pass

        chat.clear_history()
        self.assertEqual(chat.messages, [{"role": "system", "content": "System instruction"}])

    async def test_retry_on_transient_failure(self) -> None:
        client = FakeClient(responses=[["unused"], ["Recovered"]], fail_calls={1})
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            retries=1,
            retry_backoff_seconds=0.0,
            client=client,
        )

        chunks: list[str] = []
        async for chunk in chat.send_message("retry test"):
            chunks.append(chunk)

        self.assertEqual(client.calls, 2)
        self.assertEqual(chunks, ["Recovered"])
        self.assertEqual(chat.messages[-1]["content"], "Recovered")

    async def test_raises_after_retries_exhausted(self) -> None:
        client = FakeClient(responses=[["unused"]], fail_calls={1, 2})
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            retries=1,
            retry_backoff_seconds=0.0,
            client=client,
        )

        with self.assertRaises(OllamaStreamingError):
            async for _ in chat.send_message("this should fail"):
                pass

    async def test_model_not_found_error_is_mapped(self) -> None:
        class MissingModelClient:
            async def chat(
                self, model: str, messages: list[dict[str, str]], stream: bool
            ) -> AsyncGenerator[dict[str, dict[str, str]], None]:
                raise RuntimeError("model not found")

        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            retries=0,
            client=MissingModelClient(),
        )

        with self.assertRaises(OllamaModelNotFoundError):
            async for _ in chat.send_message("where are you"):
                pass


if __name__ == "__main__":
    unittest.main()
