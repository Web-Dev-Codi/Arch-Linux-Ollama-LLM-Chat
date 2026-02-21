"""Input row containing message field, send button, and image attach button."""

from __future__ import annotations

from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Input


class InputBox(Horizontal):
    """Horizontal input region for message composition and send action."""

    class AttachRequested(Message):
        """Posted when the user clicks the attach button."""

    def compose(self):  # type: ignore[override]
        yield Input(
            placeholder="Type your message... (or /image <path> to attach)",
            id="message_input",
        )
        yield Button("Attach", id="attach_button", variant="default")
        yield Button("Send", id="send_button", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Forward attach button clicks as AttachRequested messages."""
        if event.button.id == "attach_button":
            event.stop()
            self.post_message(self.AttachRequested())
