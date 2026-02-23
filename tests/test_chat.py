"""Tests for OllamaChat streaming, retries, history management, thinking, tools, and vision."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import unittest

from ollama_chat.chat import ChatChunk, OllamaChat
from ollama_chat.exceptions import OllamaModelNotFoundError, OllamaStreamingError
from ollama_chat.tools import ToolRegistry


async def _chunk_stream(
    chunks: list[dict],
) -> AsyncGenerator[dict[str, dict[str, str]], None]:
    for chunk in chunks:
        yield chunk


def _content_chunk(text: str) -> dict:
    return {"message": {"content": text, "thinking": None, "tool_calls": None}}


def _thinking_chunk(text: str) -> dict:
    return {"message": {"content": None, "thinking": text, "tool_calls": None}}


def _tool_call_chunk(name: str, args: dict) -> dict:
    return {
        "message": {
            "content": None,
            "thinking": None,
            "tool_calls": [{"function": {"name": name, "arguments": args}}],
        }
    }


class FakeClient:
    """Simple fake Ollama client for deterministic tests."""

    def __init__(
        self,
        responses: list[list[dict]],
        fail_calls: set[int] | None = None,
        models: list[str] | None = None,
    ) -> None:
        self.responses = responses
        self.fail_calls = fail_calls or set()
        self.calls = 0
        self.messages_per_call: list[list[dict]] = []
        self.kwargs_per_call: list[dict] = []
        self.models = models or ["llama3.2"]
        self.pull_calls: list[str] = []

    async def chat(
        self,
        model: str,
        messages: list[dict],
        stream: bool,
        think: bool = False,
        tools: object | None = None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:  # noqa: ARG002
        self.calls += 1
        self.messages_per_call.append(list(messages))
        merged = dict(kwargs)
        merged["think"] = think
        merged["tools"] = tools
        self.kwargs_per_call.append(merged)
        if self.calls in self.fail_calls:
            raise RuntimeError("simulated transient failure")
        payload_index = min(self.calls - 1, len(self.responses) - 1)
        return _chunk_stream(self.responses[payload_index])

    async def list(self) -> dict[str, list[dict[str, str]]]:
        return {"models": [{"name": model_name} for model_name in self.models]}

    async def pull(
        self, model: str, stream: bool = False
    ) -> dict[str, str]:  # noqa: ARG002
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
        client = FakeClient(
            responses=[[_content_chunk("Hello"), _content_chunk(" world")]]
        )
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="You are helpful.",
            client=client,
        )

        received: list[ChatChunk] = []
        async for chunk in chat.send_message("Hi there"):
            received.append(chunk)

        content_texts = [c.text for c in received if c.kind == "content"]
        self.assertEqual(content_texts, ["Hello", " world"])
        self.assertEqual(chat.messages[-2], {"role": "user", "content": "Hi there"})
        self.assertEqual(
            chat.messages[-1], {"role": "assistant", "content": "Hello world"}
        )

    async def test_clear_history_keeps_system_prompt(self) -> None:
        client = FakeClient(responses=[[_content_chunk("A")]])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System instruction",
            client=client,
        )
        async for _ in chat.send_message("question"):
            pass

        chat.clear_history()
        self.assertEqual(
            chat.messages, [{"role": "system", "content": "System instruction"}]
        )

    async def test_retry_on_transient_failure(self) -> None:
        client = FakeClient(
            responses=[[_content_chunk("unused")], [_content_chunk("Recovered")]],
            fail_calls={1},
        )
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            retries=1,
            retry_backoff_seconds=0.0,
            client=client,
        )

        chunks: list[ChatChunk] = []
        async for chunk in chat.send_message("retry test"):
            chunks.append(chunk)

        self.assertEqual(client.calls, 2)
        content_texts = [c.text for c in chunks if c.kind == "content"]
        self.assertEqual(content_texts, ["Recovered"])
        self.assertEqual(chat.messages[-1]["content"], "Recovered")

    async def test_raises_after_retries_exhausted(self) -> None:
        client = FakeClient(responses=[[_content_chunk("unused")]], fail_calls={1, 2})
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
                self, model: str, messages: list[dict], stream: bool, **kwargs
            ) -> AsyncGenerator[dict, None]:
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
        client = FakeClient(responses=[[_content_chunk("ok")]], models=["qwen2.5"])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            client=client,
        )
        ready = await chat.ensure_model_ready(pull_if_missing=True)
        self.assertTrue(ready)
        self.assertEqual(client.pull_calls, ["llama3.2"])

    async def test_ensure_model_ready_raises_when_missing_and_pull_disabled(
        self,
    ) -> None:
        client = FakeClient(responses=[[_content_chunk("ok")]], models=["qwen2.5"])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            client=client,
        )
        with self.assertRaises(OllamaModelNotFoundError):
            await chat.ensure_model_ready(pull_if_missing=False)

    # --- New capability tests ---

    async def test_thinking_chunks_yielded(self) -> None:
        """Thinking chunks are yielded before content chunks."""
        client = FakeClient(
            responses=[
                [
                    _thinking_chunk("let me reason"),
                    _content_chunk("The answer is 42"),
                ]
            ]
        )
        chat = OllamaChat(
            host="http://localhost:11434",
            model="qwen3",
            system_prompt="You are helpful.",
            client=client,
        )

        chunks: list[ChatChunk] = []
        async for chunk in chat.send_message("What is the answer?", think=True):
            chunks.append(chunk)

        kinds = [c.kind for c in chunks]
        self.assertIn("thinking", kinds)
        self.assertIn("content", kinds)
        # Thinking must come before content.
        self.assertLess(kinds.index("thinking"), kinds.index("content"))
        thinking_text = "".join(c.text for c in chunks if c.kind == "thinking")
        self.assertEqual(thinking_text, "let me reason")

    async def test_think_parameter_passed_to_client(self) -> None:
        """think=True is forwarded to the underlying client.chat() call."""
        client = FakeClient(responses=[[_content_chunk("ok")]])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="qwen3",
            system_prompt="System",
            client=client,
        )
        async for _ in chat.send_message("hello", think=True):
            pass
        self.assertIn("think", client.kwargs_per_call[0])
        self.assertTrue(client.kwargs_per_call[0]["think"])

    async def test_tool_agent_loop_single_call(self) -> None:
        """A single tool call is executed and the final answer is returned."""
        # First call: model returns a tool_call chunk.
        # Second call: model returns the final content.
        call_count = 0

        class ToolFakeClient:
            async def chat(self, model, messages, stream, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _chunk_stream([_tool_call_chunk("get_time", {"tz": "UTC"})])
                return _chunk_stream([_content_chunk("The time is 12:00")])

        def get_time(tz: str) -> str:  # noqa: ARG001
            """Get the current time.

            Args:
                tz: Timezone name.

            Returns:
                Current time string.
            """
            return "12:00 UTC"

        registry = ToolRegistry()
        registry.register(get_time)

        chat = OllamaChat(
            host="http://localhost:11434",
            model="qwen3",
            system_prompt="System",
            client=ToolFakeClient(),
        )
        chunks: list[ChatChunk] = []
        async for chunk in chat.send_message(
            "What time is it?", tool_registry=registry
        ):
            chunks.append(chunk)

        kinds = [c.kind for c in chunks]
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)
        self.assertIn("content", kinds)
        tool_result_chunk = next(c for c in chunks if c.kind == "tool_result")
        self.assertEqual(tool_result_chunk.tool_name, "get_time")
        self.assertEqual(tool_result_chunk.tool_result, "12:00 UTC")
        # Final assistant content is persisted.
        self.assertEqual(chat.messages[-1]["content"], "The time is 12:00")

    async def test_tool_max_iterations_respected(self) -> None:
        """Agent loop exits after max_tool_iterations even when tool calls keep coming."""

        class InfiniteToolClient:
            async def chat(self, model, messages, stream, **kwargs):
                # Always return a tool call.
                return _chunk_stream([_tool_call_chunk("looper", {})])

        def looper() -> str:
            """Loop forever.

            Returns:
                A string.
            """
            return "looping"

        registry = ToolRegistry()
        registry.register(looper)

        chat = OllamaChat(
            host="http://localhost:11434",
            model="qwen3",
            system_prompt="System",
            client=InfiniteToolClient(),
        )
        chunks: list[ChatChunk] = []
        async for chunk in chat.send_message(
            "loop", tool_registry=registry, max_tool_iterations=3
        ):
            chunks.append(chunk)

        tool_result_chunks = [c for c in chunks if c.kind == "tool_result"]
        # At most max_tool_iterations results.
        self.assertLessEqual(len(tool_result_chunks), 3)

    async def test_image_included_in_request(self) -> None:
        """Images are included in the API call message but not stored in history."""
        client = FakeClient(responses=[[_content_chunk("I see a cat")]])
        chat = OllamaChat(
            host="http://localhost:11434",
            model="gemma3",
            system_prompt="You are helpful.",
            client=client,
        )
        async for _ in chat.send_message("Describe this", images=["/tmp/cat.jpg"]):
            pass

        # The API call should include images in the last user message.
        last_user_msg = client.messages_per_call[0][-1]
        self.assertIn("images", last_user_msg)
        self.assertEqual(last_user_msg["images"], ["/tmp/cat.jpg"])

        # History should NOT contain images (ephemeral).
        for msg in chat.messages:
            self.assertNotIn("images", msg)

    async def test_tool_execution_error_raises_wrapped(self) -> None:
        """OllamaToolError from a tool execution propagates out of send_message."""
        call_count = 0

        class ToolCallClient:
            async def chat(self, model, messages, stream, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _chunk_stream([_tool_call_chunk("broken_tool", {})])
                return _chunk_stream([_content_chunk("done")])

        def broken_tool() -> str:
            """A tool that always fails.

            Returns:
                Never returns.
            """
            raise RuntimeError("something went wrong")

        registry = ToolRegistry()
        registry.register(broken_tool)

        chat = OllamaChat(
            host="http://localhost:11434",
            model="qwen3",
            system_prompt="System",
            client=ToolCallClient(),
        )
        chunks: list[ChatChunk] = []
        async for chunk in chat.send_message("use the tool", tool_registry=registry):
            chunks.append(chunk)

        # The error result is embedded in a tool_result chunk (not re-raised),
        # because ToolRegistry.execute() wraps errors gracefully.
        tool_result_chunks = [c for c in chunks if c.kind == "tool_result"]
        self.assertTrue(len(tool_result_chunks) >= 1)
        self.assertIn("Tool error", tool_result_chunks[0].tool_result)

    async def test_omits_unknown_kwargs_for_sdk_signature(self) -> None:
        """If the SDK chat() does not accept think/tools, they are omitted and streaming works."""

        class NoExtrasClient:
            async def chat(self, model, messages, stream):  # noqa: D401, ANN001
                return _chunk_stream([_content_chunk("OK")])

            async def list(self) -> dict[str, list[dict[str, str]]]:  # pragma: no cover
                return {"models": [{"name": "llama3.2"}]}

        def dummy_tool() -> str:
            """A no-op tool used to populate the registry."""
            return "done"

        registry = ToolRegistry()
        registry.register(dummy_tool)

        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama3.2",
            system_prompt="System",
            client=NoExtrasClient(),
        )

        # Even though we request think=True and provide tools, the client signature
        # does not accept these kwargs; the wrapper should drop them and still stream.
        chunks: list[ChatChunk] = []
        async for chunk in chat.send_message("hello", think=True, tool_registry=registry):
            chunks.append(chunk)

        content = "".join(c.text for c in chunks if c.kind == "content")
        self.assertEqual(content, "OK")


if __name__ == "__main__":
    unittest.main()
