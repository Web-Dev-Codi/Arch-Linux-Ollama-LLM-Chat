"""Input row containing message field and send button."""

from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Button, Input


class InputBox(Horizontal):
    """Horizontal input region for message composition and send action."""

    def compose(self):  # type: ignore[override]
        yield Input(placeholder="Type your message...", id="message_input")
        yield Button("Send", id="send_button", variant="success")
