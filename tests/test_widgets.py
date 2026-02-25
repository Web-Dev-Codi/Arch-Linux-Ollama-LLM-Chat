"""Unit tests for individual widget classes."""

from __future__ import annotations

import unittest

try:
    from textual.widgets import Button, Input, Label

    from ollama_chat.widgets.activity_bar import ActivityBar
    from ollama_chat.widgets.code_block import CodeBlock, split_message
    from ollama_chat.widgets.conversation import ConversationView
    from ollama_chat.widgets.input_box import InputBox
    from ollama_chat.widgets.message import MessageBubble
    from ollama_chat.widgets.status_bar import StatusBar
except ModuleNotFoundError:
    ActivityBar = None  # type: ignore[assignment,misc]
    CodeBlock = None  # type: ignore[assignment,misc]
    split_message = None  # type: ignore[assignment]
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
class InputBoxTests(unittest.IsolatedAsyncioTestCase):
    """Validate InputBox composition."""

    async def test_input_box_is_vertical(self) -> None:
        from textual.containers import Vertical

        assert InputBox is not None
        self.assertTrue(issubclass(InputBox, Vertical))

    async def test_compose_yields_input_and_buttons(self) -> None:
        assert InputBox is not None
        assert Input is not None
        assert Button is not None

        from textual.app import App, ComposeResult

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield InputBox(id="ib")

        app = _TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#message_input", Input)
            app.query_one("#send_button", Button)

    async def test_input_has_correct_id(self) -> None:
        assert InputBox is not None

        from textual.app import App, ComposeResult

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield InputBox(id="ib")

        app = _TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            input_widget = app.query_one("#message_input", Input)
            self.assertEqual(input_widget.id, "message_input")

    async def test_button_has_correct_id(self) -> None:
        assert InputBox is not None

        from textual.app import App, ComposeResult

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield InputBox(id="ib")

        app = _TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            button = app.query_one("#send_button", Button)
            self.assertEqual(button.id, "send_button")

    async def test_attach_and_file_buttons_present(self) -> None:
        assert InputBox is not None

        from textual.app import App, ComposeResult

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield InputBox(id="ib")

        app = _TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#attach_button", Button)
            app.query_one("#file_button", Button)

    async def test_slash_menu_present(self) -> None:
        from textual.widgets import OptionList

        assert InputBox is not None

        from textual.app import App, ComposeResult

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield InputBox(id="ib")

        app = _TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            menu = app.query_one("#slash_menu", OptionList)
            self.assertEqual(menu.id, "slash_menu")


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


@unittest.skipIf(CodeBlock is None, "textual is not installed")
class SplitMessageTests(unittest.TestCase):
    """Validate the split_message helper."""

    def test_plain_text_returns_single_prose_segment(self) -> None:
        assert split_message is not None
        segments = split_message("Hello world")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0][1], None)

    def test_code_block_extracted(self) -> None:
        assert split_message is not None
        text = "Before\n```python\nprint('hi')\n```\nAfter"
        segments = split_message(text)
        langs = [lang for _, lang in segments]
        self.assertIn("python", langs)
        self.assertIn(None, langs)

    def test_code_content_correct(self) -> None:
        assert split_message is not None
        text = "```js\nconsole.log(1)\n```"
        segments = split_message(text)
        code_segs = [(c, l) for c, l in segments if l is not None]
        self.assertEqual(len(code_segs), 1)
        self.assertIn("console.log(1)", code_segs[0][0])
        self.assertEqual(code_segs[0][1], "js")

    def test_no_lang_fence_uses_empty_string(self) -> None:
        assert split_message is not None
        text = "```\nsome code\n```"
        segments = split_message(text)
        code_segs = [(c, l) for c, l in segments if l is not None]
        self.assertEqual(code_segs[0][1], "")

    def test_multiple_code_blocks(self) -> None:
        assert split_message is not None
        text = "```py\na = 1\n```\nmiddle\n```bash\necho hi\n```"
        segments = split_message(text)
        code_segs = [l for _, l in segments if l is not None]
        self.assertEqual(len(code_segs), 2)


@unittest.skipIf(CodeBlock is None, "textual is not installed")
class CodeBlockWidgetTests(unittest.IsolatedAsyncioTestCase):
    """Validate CodeBlock widget composition and copy message."""

    def test_code_and_lang_stored(self) -> None:
        assert CodeBlock is not None
        cb = CodeBlock(code="print('hi')", lang="python")
        self.assertEqual(cb._code, "print('hi')")
        self.assertEqual(cb._lang, "python")

    async def test_copy_requested_message_posted(self) -> None:
        from textual.app import App, ComposeResult

        assert CodeBlock is not None
        received: list[str] = []

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield CodeBlock(code="x = 1", lang="python", id="cb")

            def on_code_block_copy_requested(
                self, event: CodeBlock.CopyRequested
            ) -> None:
                received.append(event.code)

        app = _TestApp()
        async with app.run_test() as pilot:
            await pilot.click("#copy-btn")
            await pilot.pause()
        self.assertEqual(received, ["x = 1"])


@unittest.skipIf(ActivityBar is None, "textual is not installed")
class ActivityBarTests(unittest.IsolatedAsyncioTestCase):
    """Validate ActivityBar animation state changes."""

    def test_activity_bar_is_static_subclass(self) -> None:
        from textual.widgets import Static

        assert ActivityBar is not None
        self.assertTrue(issubclass(ActivityBar, Static))

    def test_compose_produces_left_and_right_labels(self) -> None:
        assert ActivityBar is not None
        bar = ActivityBar(shortcut_hints="ctrl+p commands")
        children = list(bar.compose())
        ids = [getattr(w, "id", None) for w in children]
        self.assertIn("activity_left", ids)
        self.assertIn("activity_right", ids)

    def test_shortcut_hints_stored(self) -> None:
        assert ActivityBar is not None
        bar = ActivityBar(shortcut_hints="ctrl+p commands")
        self.assertEqual(bar._shortcut_hints, "ctrl+p commands")

    def test_start_sets_running_flag(self) -> None:
        """start_activity sets the running flag (animation needs event loop)."""
        from textual.app import App, ComposeResult

        assert ActivityBar is not None

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ActivityBar(shortcut_hints="ctrl+p commands", id="ab")

        async def _run() -> None:
            app = _TestApp()
            async with app.run_test():
                ab = app.query_one("#ab", ActivityBar)
                ab.start_activity()
                self.assertTrue(ab._running)
                ab.stop_activity()
                self.assertFalse(ab._running)

        import asyncio

        asyncio.get_event_loop().run_until_complete(_run())

    async def test_stop_clears_running_flag(self) -> None:
        from textual.app import App, ComposeResult

        assert ActivityBar is not None

        class _TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield ActivityBar(shortcut_hints="ctrl+p commands", id="ab")

        app = _TestApp()
        async with app.run_test():
            ab = app.query_one("#ab", ActivityBar)
            ab.start_activity()
            self.assertTrue(ab._running)
            ab.stop_activity()
            self.assertFalse(ab._running)
            self.assertIsNone(ab._animation_timer)


if __name__ == "__main__":
    unittest.main()
