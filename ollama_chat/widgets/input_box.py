"""Input row containing message field, send button, attach buttons, and slash menu."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, OptionList


class InputBox(Vertical):
    """Input region with message field, attach buttons, send button, and slash menu."""

    class AttachRequested(Message):
        """Posted when the user clicks the image attach button."""

    class FileAttachRequested(Message):
        """Posted when the user clicks the file attach button."""

    def compose(self):  # type: ignore[override]
        with Horizontal(id="input_row"):
            yield Input(
                placeholder="Type your message... (/ for commands, drag/drop files)",
                id="message_input",
            )
            yield Button("Image", id="attach_button", variant="default")
            yield Button("File", id="file_button", variant="default")
            yield Button("Send", id="send_button", variant="success")
        yield OptionList(id="slash_menu", classes="hidden")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Forward attach button clicks as AttachRequested messages."""
        if event.button.id == "attach_button":
            event.stop()
            self.post_message(self.AttachRequested())
        elif event.button.id == "file_button":
            event.stop()
            self.post_message(self.FileAttachRequested())
