"""Status bar widget for connection and conversation telemetry."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static


class StatusBar(Horizontal):
    """Render compact runtime status information."""

    class ModelPickerRequested(Message):
        """Posted when the model segment is clicked."""

    class _ModelSegment(Static):
        """Clickable model segment."""

        def on_click(self, event: events.Click) -> None:
            event.stop()
            self.post_message(StatusBar.ModelPickerRequested())

    def compose(self) -> ComposeResult:
        yield Static("🟡 Connection: unknown", id="status_connection", classes="status-segment")
        yield Static("|", classes="status-separator")
        yield self._ModelSegment("Model: -  ▼", id="status_model", classes="status-segment status-model")
        yield Static("|", classes="status-separator")
        yield Static("Messages: 0", id="status_messages", classes="status-segment")
        yield Static("|", classes="status-separator")
        yield Static("Est. tokens: 0", id="status_tokens", classes="status-segment")

    def set_status(
        self,
        *,
        connection_state: str,
        model: str,
        message_count: int,
        estimated_tokens: int,
    ) -> None:
        normalized_state = connection_state.strip().lower()
        traffic_lights = {
            "online": "🟢",
            "offline": "🔴",
            "unknown": "🟡",
        }
        indicator = traffic_lights.get(normalized_state, "🟡")

        self.query_one("#status_connection", Static).update(f"{indicator} Connection: {normalized_state}")
        self.query_one("#status_model", Static).update(f"Model: {model}  ▼")
        self.query_one("#status_messages", Static).update(f"Messages: {message_count}")
        self.query_one("#status_tokens", Static).update(f"Est. tokens: {estimated_tokens}")
