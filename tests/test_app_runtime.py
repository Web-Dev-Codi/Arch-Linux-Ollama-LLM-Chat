"""Runtime-style tests for the real Textual app class."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import os
import unittest

from ollama_chat.exceptions import (
    OllamaChatError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStreamingError,
)
from ollama_chat.state import ConversationState

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

    def save_conversation(
        self, messages: list[dict[str, str]], model: str
    ) -> str:  # noqa: ARG002
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

    def export_markdown(
        self, messages: list[dict[str, str]], model: str
    ) -> str:  # noqa: ARG002
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

    async def send_message(
        self, user_message: str, **kwargs
    ) -> AsyncGenerator:  # noqa: ARG002
        from ollama_chat.chat import ChatChunk

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
            yield ChatChunk(kind="content", text=chunk)
        self.messages.append({"role": "assistant", "content": "hello world"})

    async def list_models(self) -> list[str]:
        return ["llama3.2", "qwen2.5"]

    async def ensure_model_ready(
        self, pull_if_missing: bool = True
    ) -> bool:  # noqa: ARG002
        return True

    async def check_connection(self) -> bool:
        return True

    @staticmethod
    def _model_name_matches(requested_model: str, available_model: str) -> bool:
        requested = requested_model.strip().lower()
        available = available_model.strip().lower()
        if requested == available:
            return True
        if ":" not in requested and available.startswith(f"{requested}:"):
            return True
        return False

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
        app._configured_models = ["llama3.2", "qwen2.5"]
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

            await app._activate_selected_model("llama3.2")
            self.assertEqual(app.chat.model, "llama3.2")

            await app.action_export_conversation()
            self.assertTrue(app.persistence.exported)

            await app.action_new_conversation()
            self.assertEqual(len(app.chat.messages), 1)

            status_connection = app.query_one("#status_connection")
            self.assertIn("🟢", str(status_connection.render()))

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

    async def test_model_switch_rejected_when_not_idle(self) -> None:
        app = self._build_app()
        async with app.run_test():
            await app.state.transition_to(ConversationState.STREAMING)
            current_model = app.chat.model
            await app._activate_selected_model("qwen2.5")
            self.assertEqual(app.chat.model, current_model)
            self.assertEqual(app.sub_title, "Model switch is available only when idle.")

    async def test_parse_file_prefixes(self) -> None:
        app = self._build_app()
        cleaned, paths = app._parse_file_prefixes("/file ~/notes.txt and more /file /tmp/x")
        self.assertTrue(cleaned.startswith("and more"))
        self.assertIn(os.path.expanduser("~/notes.txt"), paths)
        self.assertIn("/tmp/x", paths)

    async def test_extract_paths_from_paste(self) -> None:
        app = self._build_app()
        paths = app._extract_paths_from_paste("file:///tmp/a.png /home/user/b.txt")
        self.assertEqual(paths, ["/tmp/a.png", "/home/user/b.txt"])

    async def test_last_prompt_recall_on_up_key(self) -> None:
        app = self._build_app()

        class _DummyKey:
            def __init__(self) -> None:
                self.key = "up"
                self.stopped = False

            def stop(self) -> None:  # pragma: no cover - simple flag setter
                self.stopped = True

        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "hello"
            app._last_prompt = "previous prompt"
            input_widget.value = ""
            input_widget.focus()
            event = _DummyKey()
            app.on_key(event)
            self.assertEqual(input_widget.value, "previous prompt")
            self.assertTrue(event.stopped)

    async def test_on_unmount_cancels_background_tasks(self) -> None:
        """on_unmount() must cancel all background tasks without hanging."""
        import asyncio

        app = self._build_app()
        cancelled_flags: list[bool] = []

        async def _long_running() -> None:
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                cancelled_flags.append(True)
                raise

        async with app.run_test():
            task = asyncio.create_task(_long_running())
            app._background_tasks.add(task)

        # After the context manager exits, on_unmount has been called.
        self.assertTrue(task.done(), "Long-running task should be done after unmount.")
        self.assertTrue(
            cancelled_flags, "Long-running task should have been cancelled."
        )

    async def test_auto_save_on_exit_called_when_enabled(self) -> None:
        """_auto_save_on_exit() triggers persistence.save_conversation when enabled."""
        app = self._build_app()
        # Inject non-empty chat history so auto-save has something to save.
        app.chat.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        app.config["persistence"]["enabled"] = True
        app.config["persistence"]["auto_save"] = True

        app._auto_save_on_exit()

        self.assertTrue(app.persistence.saved)

    async def test_auto_save_skipped_when_disabled(self) -> None:
        """_auto_save_on_exit() does nothing when persistence is disabled."""
        app = self._build_app()
        app.chat.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        app.config["persistence"]["enabled"] = False

        app._auto_save_on_exit()

        self.assertFalse(app.persistence.saved)

    async def test_auto_save_skipped_when_auto_save_false(self) -> None:
        """_auto_save_on_exit() does nothing when auto_save flag is False."""
        app = self._build_app()
        app.chat.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        app.config["persistence"]["enabled"] = True
        app.config["persistence"]["auto_save"] = False

        app._auto_save_on_exit()

        self.assertFalse(app.persistence.saved)


    async def test_slash_new_dispatches_new_conversation(self) -> None:
        app = self._build_app()
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "/new"
            await app.send_user_message()
            self.assertEqual(input_widget.value, "")
            self.assertEqual(len(app.chat.messages), 1)

    async def test_slash_clear_clears_input(self) -> None:
        app = self._build_app()
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "/clear"
            await app.send_user_message()
            self.assertEqual(input_widget.value, "")
            self.assertEqual(app.sub_title, "Input cleared.")

    async def test_slash_model_bare_dispatches(self) -> None:
        app = self._build_app()
        async with app.run_test():
            picker_called = []

            async def _fake_picker() -> None:
                picker_called.append(True)

            app._open_configured_model_picker = _fake_picker  # type: ignore[assignment]
            handled = await app._dispatch_slash_command("/model")
            self.assertTrue(handled)
            self.assertTrue(picker_called)

    async def test_slash_model_with_name_switches(self) -> None:
        app = self._build_app()
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "/model qwen2.5"
            await app.send_user_message()
            self.assertEqual(input_widget.value, "")

    async def test_unknown_slash_falls_through_to_llm(self) -> None:
        app = self._build_app()
        async with app.run_test():
            input_widget = app.query_one("#message_input", Input)
            input_widget.value = "/image ~/photo.png describe this"
            await app.send_user_message()
            self.assertNotEqual(app.sub_title, "Input cleared.")


class NativeFileDialogTests(unittest.IsolatedAsyncioTestCase):
    """Validate _open_native_file_dialog fallback behaviour."""

    async def test_returns_none_when_no_picker_available(self) -> None:
        from unittest.mock import patch

        from ollama_chat.app import _open_native_file_dialog

        with patch("ollama_chat.app.shutil.which", return_value=None):
            result = await _open_native_file_dialog(title="Test")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
