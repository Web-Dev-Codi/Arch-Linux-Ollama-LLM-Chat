"""Scrollable conversation view widget."""

from __future__ import annotations

from textual.containers import VerticalScroll

from .message import MessageBubble


class ConversationView(VerticalScroll):
    """A scrollable container that hosts message bubbles."""

    async def add_message(self, content: str, role: str, timestamp: str = "") -> MessageBubble:
        """Create, mount, and scroll to a new message bubble."""
        bubble = MessageBubble(content=content, role=role, timestamp=timestamp)
        bubble.add_class(f"message-{role}")
        await self.mount(bubble)
        self.scroll_end(animate=True)
        return bubble
