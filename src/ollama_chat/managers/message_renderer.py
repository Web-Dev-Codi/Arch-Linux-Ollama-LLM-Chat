"""Message rendering and bubble management.

Extracted from app.py during Phase 2B refactoring.
Handles message bubble creation, styling, and conversation history rendering.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ollama_chat.widgets.conversation import ConversationView
    from ollama_chat.widgets.message import MessageBubble
    from ollama_chat.managers.theme import ThemeManager
    from ollama_chat.managers.capability import CapabilityManager


class MessageRenderer:
    """Manages message bubble creation, styling, and rendering.

    Responsibilities:
    - Creating and styling message bubbles
    - Rendering conversation history
    - Clearing conversation view
    - Timestamp generation

    Extracted from OllamaChatApp to improve separation of concerns.
    """

    def __init__(
        self,
        theme_manager: ThemeManager,
        capability_manager: CapabilityManager,
    ) -> None:
        """Initialize message renderer.

        Args:
            theme_manager: ThemeManager for bubble styling
            capability_manager: CapabilityManager for capability-based rendering
        """
        self.theme_manager = theme_manager
        self.capability_manager = capability_manager

    @staticmethod
    def generate_timestamp() -> str:
        """Generate formatted timestamp for messages.

        Returns:
            Formatted timestamp string (e.g., "3:45 PM")
        """
        now = datetime.now()
        if now.hour < 12:
            period = "AM"
            hour = now.hour if now.hour != 0 else 12
        else:
            period = "PM"
            hour = now.hour if now.hour <= 12 else now.hour - 12
        return f"{hour}:{now.minute:02d} {period}"

    async def add_message(
        self,
        conversation_view: ConversationView,
        content: str,
        role: str,
        timestamp: str = "",
    ) -> MessageBubble:
        """Add a styled message bubble to the conversation view.

        Args:
            conversation_view: ConversationView widget to add message to
            content: Message content text
            role: Message role ("user" or "assistant")
            timestamp: Optional timestamp (generated if not provided)

        Returns:
            Created and styled MessageBubble
        """
        if not timestamp:
            timestamp = self.generate_timestamp()

        bubble = await conversation_view.add_message(
            content=content,
            role=role,
            timestamp=timestamp,
            show_thinking=self.capability_manager.effective_capabilities.show_thinking,
        )
        self.style_bubble(bubble, role)
        return bubble

    def style_bubble(self, bubble: MessageBubble, role: str) -> None:
        """Apply theme styling to a message bubble.

        Args:
            bubble: MessageBubble to style
            role: Message role for styling context
        """
        self.theme_manager.apply_to_bubble(bubble, role)

    def restyle_all_bubbles(self, conversation_view: ConversationView) -> None:
        """Restyle all existing message bubbles.

        Used after theme changes to update all bubbles.

        Args:
            conversation_view: ConversationView containing bubbles to restyle
        """
        try:
            bubbles = [
                bubble
                for bubble in conversation_view.children
                if hasattr(bubble, "set_content")  # MessageBubble duck-type check
            ]
            self.theme_manager.restyle_all_bubbles(bubbles)
        except Exception:
            # Silently ignore errors during restyle
            pass

    async def clear_conversation(self, conversation_view: ConversationView) -> None:
        """Remove all message bubbles from conversation view.

        Args:
            conversation_view: ConversationView to clear
        """
        if hasattr(conversation_view, "remove_children"):
            result = conversation_view.remove_children()
            if inspect.isawaitable(result):
                await result
        else:
            # Fallback for views without remove_children
            for child in list(conversation_view.children):
                result = child.remove()
                if inspect.isawaitable(result):
                    await result

    async def render_history(
        self,
        conversation_view: ConversationView,
        messages: list[dict[str, Any]],
    ) -> None:
        """Render persisted message history into conversation view.

        Skips system messages and finalizes each bubble after rendering.

        Args:
            conversation_view: ConversationView to render into
            messages: List of message dicts from persistence layer
        """
        for message in messages:
            role = str(message.get("role", "")).strip().lower()

            # Skip system messages
            if role == "system":
                continue

            content = str(message.get("content", ""))
            timestamp = self.generate_timestamp()

            bubble = await self.add_message(
                conversation_view,
                content=content,
                role=role,
                timestamp=timestamp,
            )
            await bubble.finalize_content()
