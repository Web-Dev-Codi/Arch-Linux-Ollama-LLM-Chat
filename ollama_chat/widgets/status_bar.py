"""Status bar widget for connection and conversation telemetry."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import Label, Static


class StatusBar(Static):
    """Render compact runtime status information."""

    DEFAULT_CSS = """
    StatusBar {
        layout: horizontal;
        height: auto;
    }
    StatusBar Label {
        margin-right: 1;
    }
    """

    class ModelPickerRequested(Message):
        """Posted when the model segment is clicked."""

    def compose(self) -> ComposeResult:
        """Compose child labels for each status segment."""
        yield Label("🔴 offline", id="status_connection")
        yield Label("|", id="status_sep1")
        yield Label("Model: —", id="status_model")
        yield Label("|", id="status_sep2")
        yield Label("Messages: 0", id="status_messages")
        yield Label("|", id="status_sep3")
        yield Label("Est. tokens: 0", id="status_tokens")

    def on_mount(self) -> None:
        """Cache label references once after the DOM is ready."""
        self._lbl_connection = self.query_one("#status_connection", Label)
        self._lbl_model = self.query_one("#status_model", Label)
        self._lbl_messages = self.query_one("#status_messages", Label)
        self._lbl_tokens = self.query_one("#status_tokens", Label)

    def set_status(
        self,
        *,
        connection_state: str,
        model: str,
        message_count: int,
        estimated_tokens: int,
    ) -> None:
        """Update all status segment labels."""
        icon = "🟢" if connection_state == "online" else "🔴"
        self._lbl_connection.update(f"{icon} {connection_state}")
        self._lbl_model.update(f"Model: {model}")
        self._lbl_messages.update(f"Messages: {message_count}")
        self._lbl_tokens.update(f"Est. tokens: {estimated_tokens}")

    def on_click(self, event: events.Click) -> None:
        """Open model picker from status bar click."""
        event.stop()
        self.post_message(self.ModelPickerRequested())
