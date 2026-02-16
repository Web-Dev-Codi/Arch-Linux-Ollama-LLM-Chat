"""Message bubble widget for conversation rendering."""

from __future__ import annotations

from typing import Any

from rich.markdown import Markdown
from textual.widgets import Static


class MessageBubble(Static):
    """Render a single chat message with role and optional timestamp."""

    def __init__(self, content: str, role: str, timestamp: str = "", **kwargs: Any) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self.message_content = content
        self.role = role
        self.timestamp = timestamp
        self.add_class(f"role-{role}")
        self._refresh_render()

    @property
    def role_prefix(self) -> str:
        """Return a human-friendly role label."""
        return "You" if self.role == "user" else "Assistant"

    def _compose_header(self) -> str:
        if self.timestamp:
            return f"**{self.role_prefix}**  _{self.timestamp}_\n\n"
        return f"**{self.role_prefix}**\n\n"

    def _refresh_render(self) -> None:
        full_text = f"{self._compose_header()}{self.message_content}".rstrip()
        self.update(Markdown(full_text))

    def set_content(self, content: str) -> None:
        """Update message content and rerender."""
        self.message_content = content
        self._refresh_render()

    def append_content(self, content_chunk: str) -> None:
        """Append streamed content and rerender once per batch."""
        self.message_content += content_chunk
        self._refresh_render()
