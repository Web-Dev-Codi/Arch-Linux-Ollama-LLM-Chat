"""Status bar widget for connection and conversation telemetry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import Label, Static

if TYPE_CHECKING:
    pass


class StatusBar(Static):
    """Render compact runtime status information.

    Segments (left to right):
        🟢 online  |  Model: llama3.2  |  🔧 🧠 👁  |  Messages: 4  |  Est. tokens: 312
    The capability segment shows icons only for features that are *active* for
    the current model (effective capabilities, not raw config flags).
    """

    DEFAULT_CSS = """
    StatusBar {
        layout: horizontal;
        height: auto;
    }
    StatusBar Label {
        margin-right: 1;
    }
    StatusBar #status_caps {
        color: $text-muted;
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
        yield Label("", id="status_caps")
        yield Label("|", id="status_sep3")
        yield Label("Messages: 0", id="status_messages")
        yield Label("|", id="status_sep4")
        yield Label("Est. tokens: 0", id="status_tokens")

    def on_mount(self) -> None:
        """Cache label references once after the DOM is ready."""
        self._lbl_connection = self.query_one("#status_connection", Label)
        self._lbl_model = self.query_one("#status_model", Label)
        self._lbl_caps = self.query_one("#status_caps", Label)
        self._lbl_messages = self.query_one("#status_messages", Label)
        self._lbl_tokens = self.query_one("#status_tokens", Label)
        self._sep_caps = self.query_one("#status_sep2", Label)
        self._sep_msgs = self.query_one("#status_sep3", Label)

    @staticmethod
    def _build_caps_text(effective_caps: Any) -> str:
        """Return a compact icon string for the active model capabilities.

        Shows an icon for each feature that is ON for the current model.
        Returns an empty string when no capability info is available yet.
        """
        if effective_caps is None:
            return ""
        icons: list[str] = []
        if getattr(effective_caps, "tools_enabled", False):
            icons.append("🔧")
        if getattr(effective_caps, "think", False):
            icons.append("🧠")
        if getattr(effective_caps, "vision_enabled", False):
            icons.append("👁")
        return " ".join(icons)

    def set_status(
        self,
        *,
        connection_state: str,
        model: str,
        message_count: int,
        estimated_tokens: int,
        effective_caps: Any = None,
    ) -> None:
        """Update all status segment labels.

        ``effective_caps`` is an optional :class:`CapabilityContext` (or any object
        with ``tools_enabled``, ``think``, and ``vision_enabled`` bool attributes).
        When provided the capability icon row is updated; when ``None`` the row is
        left unchanged.
        """
        icon = "🟢" if connection_state == "online" else "🔴"
        self._lbl_connection.update(f"{icon} {connection_state}")
        self._lbl_model.update(f"Model: {model}")
        self._lbl_messages.update(f"Messages: {message_count}")
        self._lbl_tokens.update(f"Est. tokens: {estimated_tokens}")

        caps_text = self._build_caps_text(effective_caps)
        self._lbl_caps.update(caps_text)
        # Hide the caps label and its surrounding separators when there's nothing
        # to show, keeping the bar clean on startup before the first model check.
        visible = bool(caps_text)
        self._lbl_caps.display = visible
        self._sep_caps.display = visible
        self._sep_msgs.display = visible

    def on_click(self, event: events.Click) -> None:
        """Open model picker from status bar click."""
        event.stop()
        self.post_message(self.ModelPickerRequested())
