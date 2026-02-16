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

    def __init__(
        self,
        responses: list[list[str]],
        fail_calls: set[int] | None = None,
        models: list[str] | None = None,
    ) -> None:
        self.responses = responses
        self.fail_calls = fail_calls or set()
        self.calls = 0
        self.messages_per_call: list[list[dict[str, str]]] = []
        self.models = models or ["llama3.2"]
        self.pull_calls: list[str] = []

    async def chat(self, model: str, messages: list[dict[str, str]], stream: bool) -> AsyncGenerator[dict[str, dict[str, str]], None]:
        self.calls += 1
        self.messages_per_call.append(list(messages))
        if self.calls in self.fail_calls:
            raise RuntimeError("simulated transient failure")
        payload_index = min(self.calls - 1, len(self.responses) - 1)
        return _chunk_stream(self.responses[payload_index])

    async def list(self) -> dict[str, list[dict[str, str]]]:
        return {"models": [{"name": model_name} for model_name in self.models]}

    async def pull(self, model: str, stream: bool = False) -> dict[str, str]:  # noqa: ARG002
        self.pull_calls.append(model)
        self.models.append(model)
        return {"status": "success"}


class _ChunkMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _ChunkObject:
    def __init__(self, content: str) -> None:
        self.message = _ChunkMessage(content)


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

    async def test_extract_chunk_text_from_object_payload(self) -> None:
        client = FakeClient(responses=[[]])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            client=client,
        )
        content = chat._extract_chunk_text(_ChunkObject("hello"))
        self.assertEqual(content, "hello")

    async def test_ensure_model_ready_pulls_when_missing(self) -> None:
        client = FakeClient(responses=[["ok"]], models=["qwen2.5"])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            client=client,
        )
        ready = await chat.ensure_model_ready(pull_if_missing=True)
        self.assertTrue(ready)
        self.assertEqual(client.pull_calls, ["llama3.2"])

    async def test_ensure_model_ready_raises_when_missing_and_pull_disabled(self) -> None:
        client = FakeClient(responses=[["ok"]], models=["qwen2.5"])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            client=client,
        )
        with self.assertRaises(OllamaModelNotFoundError):
            await chat.ensure_model_ready(pull_if_missing=False)


if __name__ == "__main__":
    unittest.main()
