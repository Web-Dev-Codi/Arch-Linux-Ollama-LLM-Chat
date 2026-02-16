"""Tests for Tier 2 and Tier 3 app actions."""

from __future__ import annotations

import unittest

from ollama_chat.state import StateManager

try:
    from ollama_chat.app import OllamaChatApp
except ModuleNotFoundError:
    OllamaChatApp = None  # type: ignore[assignment]


class _FakeBubble:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.visible = False

    def scroll_visible(self, animate: bool = False) -> None:  # noqa: ARG002
        self.visible = True


class _FakeConversation:
    def __init__(self) -> None:
        self.children: list[_FakeBubble] = []
        self.scroll_y = 0

    def scroll_end(self, animate: bool = False) -> None:  # noqa: ARG002
        self.scroll_y = 999

    def scroll_relative(self, y: int, animate: bool = False) -> None:  # noqa: ARG002
        self.scroll_y += y

    def remove_children(self) -> None:
        self.children = []


class _FakeInput:
    def __init__(self) -> None:
        self.value = ""
        self.disabled = False
        self.focused = False

    def focus(self) -> None:
        self.focused = True


class _FakeStatusBar:
    def __init__(self) -> None:
        self.last_status: dict[str, object] = {}

    def set_status(self, **kwargs: object) -> None:
        self.last_status = kwargs


class _FakeChat:
    def __init__(self) -> None:
        self.model = "llama3.2"
        self.messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]

    @property
    def estimated_context_tokens(self) -> int:
        return 42

    async def list_models(self) -> list[str]:
        return ["llama3.2", "qwen2.5"]

    async def ensure_model_ready(self, pull_if_missing: bool = True) -> bool:  # noqa: ARG002
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
        self.messages = [{"role": "system", "content": "You are helpful."}]


class _FakePersistence:
    def __init__(self) -> None:
        self.enabled = True
        self.saved = False
        self.exported = False

    def save_conversation(self, messages: list[dict[str, str]], model: str) -> str:  # noqa: ARG002
        self.saved = True
        return "/tmp/conv.json"

    def load_latest_conversation(self) -> dict[str, object]:
        return {
            "model": "qwen2.5",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
            ],
        }

    def export_markdown(self, messages: list[dict[str, str]], model: str) -> str:  # noqa: ARG002
        self.exported = True
        return "/tmp/conv.md"


@unittest.skipIf(OllamaChatApp is None, "textual is not installed")
class AppActionTests(unittest.IsolatedAsyncioTestCase):
    """Validate Tier 2/Tier 3 actions with lightweight fakes."""

    async def asyncSetUp(self) -> None:
        assert OllamaChatApp is not None
        self.app = type(
            "FakeApp",
            (),
            {
                "_update_status_bar": OllamaChatApp._update_status_bar,
                "_clear_conversation_view": OllamaChatApp._clear_conversation_view,
                "_render_messages_from_history": OllamaChatApp._render_messages_from_history,
                "_jump_to_search_result": OllamaChatApp._jump_to_search_result,
                "_transition_state": OllamaChatApp._transition_state,
                "action_toggle_model_picker": OllamaChatApp.action_toggle_model_picker,
                "action_save_conversation": OllamaChatApp.action_save_conversation,
                "action_load_conversation": OllamaChatApp.action_load_conversation,
                "action_export_conversation": OllamaChatApp.action_export_conversation,
                "action_search_messages": OllamaChatApp.action_search_messages,
                "action_copy_last_message": OllamaChatApp.action_copy_last_message,
                "action_new_conversation": OllamaChatApp.action_new_conversation,
            },
        )()
        self.app.config = {"ui": {"show_timestamps": False}}
        self.app.chat = _FakeChat()
        self.app.persistence = _FakePersistence()
        self.app.state = StateManager()
        self.app._active_stream_task = None
        self.app._background_tasks = set()
        self.app._connection_state = "online"
        self.app._search_query = ""
        self.app._search_results = []
        self.app._search_position = -1
        self.app.sub_title = ""
        self.app._conversation = _FakeConversation()
        self.app._input = _FakeInput()
        self.app._status = _FakeStatusBar()
        self.app.clipboard = ""

        def query_one(selector, _widget_type=None):
            if selector == "#message_input":
                return self.app._input
            if selector == "#status_bar":
                return self.app._status
            return self.app._conversation

        async def add_message(content: str, role: str, timestamp: str = "") -> _FakeBubble:  # noqa: ARG001
            bubble = _FakeBubble(content=content)
            self.app._conversation.children.append(bubble)
            return bubble

        def copy_to_clipboard(value: str) -> None:
            self.app.clipboard = value

        self.app.query_one = query_one
        self.app._add_message = add_message
        self.app.copy_to_clipboard = copy_to_clipboard
        self.app._timestamp = lambda: ""

    async def test_model_switch_save_load_export(self) -> None:
        await self.app.action_toggle_model_picker()
        self.assertEqual(self.app.chat.model, "qwen2.5")

        await self.app.action_save_conversation()
        self.assertTrue(self.app.persistence.saved)

        await self.app.action_load_conversation()
        self.assertEqual(self.app.chat.model, "qwen2.5")
        self.assertEqual(len(self.app._conversation.children), 2)

        await self.app.action_export_conversation()
        self.assertTrue(self.app.persistence.exported)

    async def test_search_and_copy_last_message(self) -> None:
        self.app._input.value = "answer"
        await self.app.action_load_conversation()
        await self.app.action_search_messages()
        self.assertIn("Search 1/1", self.app.sub_title)

        await self.app.action_copy_last_message()
        self.assertEqual(self.app.clipboard, "answer")

    async def test_new_conversation_clears_ui_and_history(self) -> None:
        await self.app.action_load_conversation()
        self.assertGreater(len(self.app._conversation.children), 0)
        await self.app.action_new_conversation()
        self.assertEqual(len(self.app._conversation.children), 0)
        self.assertEqual(len(self.app.chat.messages), 1)


if __name__ == "__main__":
    unittest.main()
