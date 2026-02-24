"""Tests for the registry-based slash command dispatcher."""

from __future__ import annotations

import asyncio
import unittest

try:
    from ollama_chat.app import OllamaChatApp
except Exception:  # pragma: no cover
    OllamaChatApp = None  # type: ignore[assignment,misc]

from ollama_chat.state import ConnectionState, StateManager
from ollama_chat.capabilities import AttachmentState, SearchState
from ollama_chat.task_manager import TaskManager


class _FakeInput:
    def __init__(self) -> None:
        self.value = ""
        self.has_focus = True


class _FakeStatusBar:
    def set_status(self, **_kwargs: object) -> None:
        pass


class _FakeConversation:
    def __init__(self) -> None:
        self.children: list[object] = []

    def scroll_end(self, **_kwargs: object) -> None:
        pass

    async def remove_children(self) -> None:
        self.children.clear()


class _FakeBubble:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.role = "assistant"

    def set_content(self, text: str) -> None:
        self.content = text

    async def finalize_content(self) -> None:
        pass


class _FakeChat:
    def __init__(self) -> None:
        self.model = "llama3.2"
        self.messages: list[dict[str, str]] = [{"role": "system", "content": "system"}]
        self.estimated_context_tokens = 0

    def clear_history(self) -> None:
        self.messages = [{"role": "system", "content": "system"}]

    def set_model(self, model: str) -> None:
        self.model = model

    async def ensure_model_ready(self, **_kwargs: object) -> None:
        pass


@unittest.skipIf(OllamaChatApp is None, "textual is not installed")
class SlashCommandTests(unittest.IsolatedAsyncioTestCase):
    """Validate the registry-based slash command dispatcher."""

    async def asyncSetUp(self) -> None:
        assert OllamaChatApp is not None
        self.app = type(
            "FakeApp",
            (),
            {
                "_update_status_bar": OllamaChatApp._update_status_bar,
                "_clear_conversation_view": OllamaChatApp._clear_conversation_view,
                "_transition_state": OllamaChatApp._transition_state,
                "_activate_selected_model": OllamaChatApp._activate_selected_model,
                "_build_slash_registry": OllamaChatApp._build_slash_registry,
                "_dispatch_slash_command": OllamaChatApp._dispatch_slash_command,
                "register_slash_command": OllamaChatApp.register_slash_command,
                "action_new_conversation": OllamaChatApp.action_new_conversation,
                "_open_configured_model_picker": lambda self: None,
            },
        )()
        self.app.config = {"ui": {"show_timestamps": False}}
        self.app.chat = _FakeChat()
        self.app.state = StateManager()
        self.app._task_manager = TaskManager()
        self.app._connection_state = ConnectionState.ONLINE
        self.app._search = SearchState()
        self.app._attachments = AttachmentState()
        self.app._configured_models = ["llama3.2", "qwen2.5"]
        self.app.sub_title = ""
        self.app._conversation = _FakeConversation()
        self.app._input = _FakeInput()
        self.app._status = _FakeStatusBar()
        # Widget cache refs expected by app methods.
        self.app._w_conversation = self.app._conversation
        self.app._w_input = self.app._input
        self.app._w_status = self.app._status
        self.app._w_send = None
        self.app._w_file = None
        self.app._w_activity = None
        self.app._set_idle_sub_title = lambda text: setattr(self.app, "sub_title", text)
        self.app._hide_slash_menu = lambda: None

        # Mock command palette as a flag.
        self.app._palette_opened = False

        async def _fake_command_palette() -> None:
            self.app._palette_opened = True

        self.app.action_command_palette = _fake_command_palette

        def query_one(selector: str, _widget_type: object = None) -> object:
            if selector == "#message_input":
                return self.app._input
            if selector == "#status_bar":
                return self.app._status
            return self.app._conversation

        async def add_message(
            content: str, role: str, timestamp: str = ""
        ) -> _FakeBubble:  # noqa: ARG001
            bubble = _FakeBubble(content=content)
            self.app._conversation.children.append(bubble)
            return bubble

        self.app.query_one = query_one
        self.app._add_message = add_message
        self.app._timestamp = lambda: ""
        self.app._slash_registry = OllamaChatApp._build_slash_registry(self.app)

    async def test_slash_new(self) -> None:
        self.app._input.value = "/new"
        handled = await self.app._dispatch_slash_command("/new")
        self.assertTrue(handled)
        self.assertEqual(self.app._input.value, "")

    async def test_slash_clear(self) -> None:
        self.app._input.value = "/clear"
        handled = await self.app._dispatch_slash_command("/clear")
        self.assertTrue(handled)
        self.assertEqual(self.app._input.value, "")
        self.assertEqual(self.app.sub_title, "Input cleared.")

    async def test_slash_help(self) -> None:
        handled = await self.app._dispatch_slash_command("/help")
        self.assertTrue(handled)
        self.assertTrue(self.app._palette_opened)

    async def test_slash_model_with_name(self) -> None:
        handled = await self.app._dispatch_slash_command("/model qwen2.5")
        self.assertTrue(handled)
        self.assertEqual(self.app._input.value, "")
        # Give the background task a chance to run.
        await asyncio.sleep(0)

    async def test_slash_model_no_arg(self) -> None:
        self.app._picker_opened = False

        async def _mock_picker() -> None:
            self.app._picker_opened = True

        self.app._open_configured_model_picker = _mock_picker
        handled = await self.app._dispatch_slash_command("/model")
        self.assertTrue(handled)
        self.assertTrue(self.app._picker_opened)

    async def test_unknown_slash_command_not_handled(self) -> None:
        handled = await self.app._dispatch_slash_command("/foo")
        self.assertFalse(handled)

    async def test_custom_registered_command(self) -> None:
        result: list[str] = []

        async def _handle_ping(args: str) -> None:
            result.append(f"pong:{args}")

        self.app.register_slash_command("/ping", _handle_ping)
        handled = await self.app._dispatch_slash_command("/ping hello")
        self.assertTrue(handled)
        self.assertEqual(result, ["pong:hello"])


if __name__ == "__main__":
    unittest.main()
