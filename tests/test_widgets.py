"""Unit tests for individual widget classes."""

from __future__ import annotations

import unittest

try:
    from textual.widgets import Input, Button, Label

    from ollama_chat.widgets.conversation import ConversationView
    from ollama_chat.widgets.input_box import InputBox
    from ollama_chat.widgets.message import MessageBubble
    from ollama_chat.widgets.status_bar import StatusBar
except ModuleNotFoundError:
    MessageBubble = None  # type: ignore[assignment,misc]
    ConversationView = None  # type: ignore[assignment,misc]
    InputBox = None  # type: ignore[assignment,misc]
    StatusBar = None  # type: ignore[assignment,misc]
    Input = None  # type: ignore[assignment]
    Button = None  # type: ignore[assignment]
    Label = None  # type: ignore[assignment]


@unittest.skipIf(MessageBubble is None, "textual is not installed")
class MessageBubbleTests(unittest.TestCase):
    """Validate MessageBubble content management and rendering."""

    def _make_bubble(self, content: str = "", role: str = "user") -> MessageBubble:
        assert MessageBubble is not None
        return MessageBubble(content=content, role=role)

    def test_initial_content_stored(self) -> None:
        bubble = self._make_bubble(content="hello", role="user")
        self.assertEqual(bubble.message_content, "hello")

    def test_role_class_applied(self) -> None:
        bubble = self._make_bubble(role="assistant")
        self.assertIn("role-assistant", bubble.classes)

    def test_user_role_class(self) -> None:
        bubble = self._make_bubble(role="user")
        self.assertIn("role-user", bubble.classes)

    def test_role_prefix_user(self) -> None:
        bubble = self._make_bubble(role="user")
        self.assertEqual(bubble.role_prefix, "You")

    def test_role_prefix_assistant(self) -> None:
        bubble = self._make_bubble(role="assistant")
        self.assertEqual(bubble.role_prefix, "Assistant")

    def test_set_content_updates_message_content(self) -> None:
        bubble = self._make_bubble(content="initial")
        bubble.set_content("updated")
        self.assertEqual(bubble.message_content, "updated")

    def test_append_content_accumulates(self) -> None:
        bubble = self._make_bubble(content="hello")
        bubble.append_content(" world")
        self.assertEqual(bubble.message_content, "hello world")

    def test_append_content_multiple_chunks(self) -> None:
        bubble = self._make_bubble(content="")
        bubble.append_content("foo")
        bubble.append_content("bar")
        bubble.append_content("baz")
        self.assertEqual(bubble.message_content, "foobarbaz")

    def test_set_content_to_empty(self) -> None:
        bubble = self._make_bubble(content="something")
        bubble.set_content("")
        self.assertEqual(bubble.message_content, "")

    def test_timestamp_stored(self) -> None:
        assert MessageBubble is not None
        bubble = MessageBubble(content="hi", role="user", timestamp="12:00:00")
        self.assertEqual(bubble.timestamp, "12:00:00")

    def test_header_with_timestamp(self) -> None:
        assert MessageBubble is not None
        bubble = MessageBubble(content="hi", role="user", timestamp="09:15:00")
        header = bubble._compose_header()
        self.assertIn("09:15:00", header)
        self.assertIn("You", header)

    def test_header_without_timestamp(self) -> None:
        bubble = self._make_bubble(role="assistant")
        header = bubble._compose_header()
        self.assertNotIn("_", header)
        self.assertIn("Assistant", header)


@unittest.skipIf(InputBox is None, "textual is not installed")
class InputBoxTests(unittest.TestCase):
    """Validate InputBox composition."""

    def test_input_box_is_vertical(self) -> None:
        from textual.containers import Vertical

        assert InputBox is not None
        self.assertTrue(issubclass(InputBox, Vertical))

    def test_compose_yields_input_and_buttons(self) -> None:
        assert InputBox is not None
        assert Input is not None
        assert Button is not None
        box = InputBox()
        children = list(box.compose())
        widget_types = [type(w) for w in children]
        self.assertIn(Input, widget_types)
        self.assertIn(Button, widget_types)

    def test_input_has_correct_id(self) -> None:
        assert InputBox is not None
        box = InputBox()
        inputs = [w for w in box.compose() if isinstance(w, Input)]
        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0].id, "message_input")

    def test_button_has_correct_id(self) -> None:
        assert InputBox is not None
        box = InputBox()
        buttons = [w for w in box.compose() if isinstance(w, Button)]
        send_buttons = [b for b in buttons if b.id == "send_button"]
        self.assertEqual(len(send_buttons), 1)

    def test_attach_and_file_buttons_present(self) -> None:
        assert InputBox is not None
        box = InputBox()
        buttons = [w for w in box.compose() if isinstance(w, Button)]
        attach_buttons = [b for b in buttons if b.id == "attach_button"]
        self.assertEqual(len(attach_buttons), 1)
        file_buttons = [b for b in buttons if b.id == "file_button"]
        self.assertEqual(len(file_buttons), 1)

    def test_slash_menu_present(self) -> None:
        from textual.widgets import OptionList

        assert InputBox is not None
        box = InputBox()
        option_lists = [w for w in box.compose() if isinstance(w, OptionList)]
        self.assertEqual(len(option_lists), 1)
        self.assertEqual(option_lists[0].id, "slash_menu")


@unittest.skipIf(StatusBar is None, "textual is not installed")
class StatusBarTests(unittest.IsolatedAsyncioTestCase):
    """Validate StatusBar child labels and set_status logic."""

    async def _mount_status_bar(self) -> StatusBar:
        """Mount a StatusBar inside a minimal Textual app and return it."""
        from textual.app import App, ComposeResult

        assert StatusBar is not None

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield StatusBar(id="sb")

        self._app = _TestApp()
        await self._app._process_messages()  # type: ignore[attr-defined]
        return self._app.query_one("#sb", StatusBar)

    def test_status_bar_is_static_subclass(self) -> None:
        from textual.widgets import Static

        assert StatusBar is not None
        self.assertTrue(issubclass(StatusBar, Static))

    def test_compose_produces_connection_label(self) -> None:
        assert StatusBar is not None
        bar = StatusBar()
        children = list(bar.compose())
        ids = [getattr(w, "id", None) for w in children]
        self.assertIn("status_connection", ids)

    def test_compose_produces_model_label(self) -> None:
        assert StatusBar is not None
        bar = StatusBar()
        children = list(bar.compose())
        ids = [getattr(w, "id", None) for w in children]
        self.assertIn("status_model", ids)

    def test_compose_produces_messages_label(self) -> None:
        assert StatusBar is not None
        bar = StatusBar()
        children = list(bar.compose())
        ids = [getattr(w, "id", None) for w in children]
        self.assertIn("status_messages", ids)

    def test_compose_produces_tokens_label(self) -> None:
        assert StatusBar is not None
        bar = StatusBar()
        children = list(bar.compose())
        ids = [getattr(w, "id", None) for w in children]
        self.assertIn("status_tokens", ids)

    def test_model_picker_requested_is_message(self) -> None:
        from textual.message import Message

        assert StatusBar is not None
        self.assertTrue(issubclass(StatusBar.ModelPickerRequested, Message))


@unittest.skipIf(ConversationView is None, "textual is not installed")
class ConversationViewTests(unittest.IsolatedAsyncioTestCase):
    """Validate ConversationView message mounting behavior."""

    async def test_add_message_returns_bubble(self) -> None:
        from textual.app import App, ComposeResult

        assert ConversationView is not None
        assert MessageBubble is not None

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ConversationView(id="conv")

        app = _TestApp()
        async with app.run_test():
            conv = app.query_one("#conv", ConversationView)
            bubble = await conv.add_message(content="hello", role="user")
            self.assertIsInstance(bubble, MessageBubble)

    async def test_add_message_stores_content(self) -> None:
        from textual.app import App, ComposeResult

        assert ConversationView is not None
        assert MessageBubble is not None

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ConversationView(id="conv")

        app = _TestApp()
        async with app.run_test():
            conv = app.query_one("#conv", ConversationView)
            bubble = await conv.add_message(content="test content", role="assistant")
            self.assertEqual(bubble.message_content, "test content")

    async def test_add_message_mounts_bubble_as_child(self) -> None:
        from textual.app import App, ComposeResult

        assert ConversationView is not None
        assert MessageBubble is not None

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ConversationView(id="conv")

        app = _TestApp()
        async with app.run_test():
            conv = app.query_one("#conv", ConversationView)
            await conv.add_message(content="a", role="user")
            await conv.add_message(content="b", role="assistant")
            bubbles = list(conv.query(MessageBubble))
            self.assertEqual(len(bubbles), 2)

    async def test_add_message_applies_role_class(self) -> None:
        from textual.app import App, ComposeResult

        assert ConversationView is not None
        assert MessageBubble is not None

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ConversationView(id="conv")

        app = _TestApp()
        async with app.run_test():
            conv = app.query_one("#conv", ConversationView)
            bubble = await conv.add_message(content="hi", role="user")
            self.assertIn("message-user", bubble.classes)


if __name__ == "__main__":
    unittest.main()
