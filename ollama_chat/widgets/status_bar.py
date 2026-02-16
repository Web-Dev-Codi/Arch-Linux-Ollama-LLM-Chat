"""Status bar widget for connection and conversation telemetry."""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import Static


class StatusBar(Static):
    """Render compact runtime status information."""

    class ModelPickerRequested(Message):
        """Posted when the model segment is clicked."""

    def set_status(
        self,
        *,
        connection_state: str,
        model: str,
        message_count: int,
        estimated_tokens: int,
    ) -> None:
        self.update(
            f"Connection: {connection_state}  |  "
            f"Model: {model}  |  "
            f"Messages: {message_count}  |  "
            f"Est. tokens: {estimated_tokens}"
        )

    def on_click(self, event: events.Click) -> None:
        """Open model picker from status bar click."""
        event.stop()
        self.post_message(self.ModelPickerRequested())
