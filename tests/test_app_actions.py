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

    async def finalize_content(self) -> None:
        pass


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

    async def ensure_model_ready(
        self, pull_if_missing: bool = True
    ) -> bool:  # noqa: ARG002
        return True

    async def check_connection(self) -> bool:
        return True

    async def show_model_capabilities(
        self, model_name: str | None = None
    ):  # noqa: ARG002, ANN001
        """Fake: returns unknown caps so effective caps fall back to config."""
        from ollama_chat.chat import CapabilityReport

        return CapabilityReport(caps=frozenset(), known=False)

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

    def save_conversation(
        self, messages: list[dict[str, str]], model: str, name: str = ""
    ) -> str:  # noqa: ARG002
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

    def export_markdown(
        self, messages: list[dict[str, str]], model: str
    ) -> str:  # noqa: ARG002
        self.exported = True
        return "/tmp/conv.md"


@unittest.skipIf(OllamaChatApp is None, "textual is not installed")
class AppActionTests(unittest.IsolatedAsyncioTestCase):
    """Validate Tier 2/Tier 3 actions with lightweight fakes."""

    async def asyncSetUp(self) -> None:
        assert OllamaChatApp is not None

        async def _no_prompt(self) -> str:  # noqa: ANN001
            return ""

        self.app = type(
            "FakeApp",
            (),
            {
                "_update_status_bar": OllamaChatApp._update_status_bar,
                "_clear_conversation_view": OllamaChatApp._clear_conversation_view,
                "_render_messages_from_history": OllamaChatApp._render_messages_from_history,
                "_jump_to_search_result": OllamaChatApp._jump_to_search_result,
                "_transition_state": OllamaChatApp._transition_state,
                "_activate_selected_model": OllamaChatApp._activate_selected_model,
                "_update_effective_caps": OllamaChatApp._update_effective_caps,
                "action_toggle_model_picker": OllamaChatApp.action_toggle_model_picker,
                "action_save_conversation": OllamaChatApp.action_save_conversation,
                "action_load_conversation": OllamaChatApp.action_load_conversation,
                "_load_conversation_payload": OllamaChatApp._load_conversation_payload,
                "action_export_conversation": OllamaChatApp.action_export_conversation,
                "action_search_messages": OllamaChatApp.action_search_messages,
                "action_copy_last_message": OllamaChatApp.action_copy_last_message,
                "action_new_conversation": OllamaChatApp.action_new_conversation,
                "_prompt_conversation_name": _no_prompt,
            },
        )()
        self.app.config = {"ui": {"show_timestamps": False}}
        self.app.chat = _FakeChat()
        self.app.persistence = _FakePersistence()
        self.app.state = StateManager()
        from ollama_chat.capabilities import AttachmentState, SearchState
        from ollama_chat.state import ConnectionState
        from ollama_chat.task_manager import TaskManager

        self.app._task_manager = TaskManager()
        self.app._connection_state = ConnectionState.ONLINE
        self.app._search = SearchState()
        self.app._attachments = AttachmentState()
        self.app._configured_models = ["llama3.2", "qwen2.5"]
        from ollama_chat.capabilities import CapabilityContext

        self.app.capabilities = CapabilityContext()
        from ollama_chat.chat import CapabilityReport

        self.app._model_caps = CapabilityReport(caps=frozenset(), known=False)
        self.app._effective_caps = CapabilityContext()
        self.app.sub_title = ""
        self.app._conversation = _FakeConversation()
        self.app._input = _FakeInput()
        self.app._status = _FakeStatusBar()
        # Widget cache refs (match on_mount() pattern in the real app).
        self.app._w_conversation = self.app._conversation
        self.app._w_input = self.app._input
        self.app._w_status = self.app._status
        self.app._w_send = None
        self.app._w_file = None
        self.app._w_activity = None
        self.app.clipboard = ""
        self.app._set_idle_sub_title = lambda text: setattr(self.app, "sub_title", text)

        def query_one(selector, _widget_type=None):
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

        def copy_to_clipboard(value: str) -> None:
            self.app.clipboard = value

        self.app.query_one = query_one
        self.app._add_message = add_message
        self.app.copy_to_clipboard = copy_to_clipboard
        self.app._timestamp = lambda: ""

    async def test_model_switch_save_load_export(self) -> None:
        await self.app._activate_selected_model("qwen2.5")
        self.assertEqual(self.app.chat.model, "qwen2.5")

        await self.app.action_save_conversation()
        self.assertTrue(self.app.persistence.saved)

        await self.app.action_load_conversation()
        self.assertEqual(self.app.chat.model, "qwen2.5")
        self.assertEqual(len(self.app._conversation.children), 2)

        await self.app.action_export_conversation()
        self.assertTrue(self.app.persistence.exported)

    async def test_model_switch_rejects_unconfigured_model(self) -> None:
        await self.app._activate_selected_model("mistral")
        self.assertEqual(self.app.chat.model, "llama3.2")
        self.assertIn("not configured", self.app.sub_title)

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
