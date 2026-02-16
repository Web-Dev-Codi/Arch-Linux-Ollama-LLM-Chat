"""Runtime-style tests for the real Textual app class."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import unittest

from ollama_chat.exceptions import (
    OllamaChatError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStreamingError,
)

try:
    from textual.widgets import Input

    from ollama_chat.app import OllamaChatApp
except ModuleNotFoundError:
    Input = None  # type: ignore[assignment]
    OllamaChatApp = None  # type: ignore[assignment]


class _RuntimeFakePersistence:
    def __init__(self) -> None:
        self.enabled = True
        self.saved = False
        self.exported = False

    def save_conversation(self, messages: list[dict[str, str]], model: str) -> str:  # noqa: ARG002
        self.saved = True
        return "/tmp/runtime-save.json"

    def load_latest_conversation(self) -> dict[str, object]:
        return {
            "model": "qwen2.5",
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
            ],
        }

    def export_markdown(self, messages: list[dict[str, str]], model: str) -> str:  # noqa: ARG002
        self.exported = True
        return "/tmp/runtime-export.md"


class _RuntimeFakeChat:
    def __init__(self, failure: str = "") -> None:
        self.failure = failure
        self.model = "llama3.2"
        self.messages = [{"role": "system", "content": "system"}]

    @property
    def estimated_context_tokens(self) -> int:
        return 10 + len(self.messages)

    async def send_message(self, user_message: str) -> AsyncGenerator[str, None]:
        self.messages.append({"role": "user", "content": user_message})
        if self.failure == "connection":
            raise OllamaConnectionError("cannot connect")
        if self.failure == "model":
            raise OllamaModelNotFoundError("missing model")
        if self.failure == "stream":
            raise OllamaStreamingError("stream issue")
        if self.failure == "generic":
            raise OllamaChatError("generic")
        for chunk in ["hello", " world"]:
            yield chunk
        self.messages.append({"role": "assistant", "content": "hello world"})

    async def list_models(self) -> list[str]:
        return ["llama3.2", "qwen2.5"]

    async def check_connection(self) -> bool:
        return True

    def set_model(self, model_name: str) -> None:
        self.model = model_name

    def load_history(self, messages: list[dict[str, str]]) -> None:
        self.messages = list(messages)

    def clear_history(self) -> None:
        self.messages = [{"role": "system", "content": "system"}]


@unittest.skipIf(OllamaChatApp is None, "textual is not installed")
class AppRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Exercise actions against the real app class to increase confidence."""

    def _build_app(self, *, failure: str = "") -> OllamaChatApp:
        assert OllamaChatApp is not None
        app = OllamaChatApp()
        app.chat = _RuntimeFakeChat(failure=failure)  # type: ignore[assignment]
        app.persistence = _RuntimeFakePersistence()  # type: ignore[assignment]
        app._connection_state = "online"
        app.config["app"]["connection_check_interval_seconds"] = 999
        app._copied_text = ""
        app.copy_to_clipboard = lambda value: setattr(app, "_copied_text", value)  # type: ignore[method-assign]
        return app

    async def test_happy_path_actions(self) -> None:
        app = self._build_app()
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "hello"
            await app.action_send_message()
            self.assertNotEqual(app.sub_title, "Cannot send an empty message.")

            await app.action_save_conversation()
            self.assertTrue(app.persistence.saved)

            await app.action_load_conversation()
            self.assertEqual(app.chat.model, "qwen2.5")

            input_widget.value = "answer"
            await app.action_search_messages()
            self.assertIn("Search 1/1", app.sub_title)

            await app.action_copy_last_message()
            self.assertEqual(app._copied_text, "answer")

            await app.action_toggle_model_picker()
            self.assertEqual(app.chat.model, "llama3.2")

            await app.action_export_conversation()
            self.assertTrue(app.persistence.exported)

            await app.action_new_conversation()
            self.assertEqual(len(app.chat.messages), 1)

    async def test_send_message_connection_error_path(self) -> None:
        app = self._build_app(failure="connection")
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "hello"
            await app.action_send_message()
            self.assertEqual(app.sub_title, "Connection error")

    async def test_send_message_model_error_path(self) -> None:
        app = self._build_app(failure="model")
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "hello"
            await app.action_send_message()
            self.assertEqual(app.sub_title, "Model not found")

    async def test_send_message_streaming_error_path(self) -> None:
        app = self._build_app(failure="stream")
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "hello"
            await app.action_send_message()
            self.assertEqual(app.sub_title, "Streaming error")

    async def test_send_message_generic_error_path(self) -> None:
        app = self._build_app(failure="generic")
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "hello"
            await app.action_send_message()
            self.assertEqual(app.sub_title, "Chat error")


if __name__ == "__main__":
    unittest.main()
