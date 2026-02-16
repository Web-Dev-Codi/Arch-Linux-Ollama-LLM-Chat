"""Status bar widget for connection and conversation telemetry."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Render compact runtime status information."""

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
