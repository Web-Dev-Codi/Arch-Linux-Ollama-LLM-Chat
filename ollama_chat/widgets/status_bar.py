"""Status bar widget for connection and conversation telemetry."""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import Static


class StatusBar(Static):
    """Render compact runtime status information."""

    class ModelPickerRequested(Message):
        """Posted when the model segment is clicked."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._model_start = 0
        self._model_end = 0

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
        connection_segment = f"{indicator} Connection: {normalized_state}"
        model_segment = f"Model: {model}"
        prefix = f"{connection_segment}  |  "
        suffix = f"  |  Messages: {message_count}  |  Est. tokens: {estimated_tokens}"
        self._model_start = len(prefix)
        self._model_end = self._model_start + len(model_segment)
        self.update(f"{prefix}{model_segment}{suffix}")

    def on_click(self, event: events.Click) -> None:
        """Open model picker when model text is clicked."""
        if self._model_start <= int(event.x) < self._model_end:
            event.stop()
            self.post_message(self.ModelPickerRequested())
