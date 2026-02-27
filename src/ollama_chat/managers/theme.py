"""Theme and styling management.

Handles theme application, custom colors, and widget styling.
Extracted from OllamaChatApp during Phase 2.5 refactoring.

Integration required in app.py:
- Replace _apply_theme() method
- Replace _style_bubble() method
- Replace _restyle_rendered_bubbles() method
- Use manager for theme switching
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

LOGGER = logging.getLogger(__name__)


class ThemeManager:
    """Manages application theme and widget styling.

    Responsibilities:
    - Apply theme colors
    - Style message bubbles
    - Refresh widget styles
    - Handle theme switching
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.ui_config = config.get("ui", {})
        self._using_textual_theme = bool(config.get("theme"))

    def apply_to_bubble(self, bubble, role: str) -> None:
        """Apply theme styling to a message bubble.

        Args:
            bubble: MessageBubble widget
            role: Message role ("user" or "assistant")
        """
        if self._using_textual_theme:
            # Let Textual theme handle it
            return

        # Apply custom colors
        if role == "user":
            bubble.styles.background = self.ui_config.get(
                "user_message_color", "#2a2a2a"
            )
        elif role == "assistant":
            bubble.styles.background = self.ui_config.get(
                "assistant_message_color", "#1a1a1a"
            )

        # Apply border
        border_color = self.ui_config.get("border_color", "#444444")
        if hasattr(bubble, "styles") and hasattr(bubble.styles, "border"):
            bubble.styles.border = ("round", border_color)

    def restyle_all_bubbles(self, bubbles: list) -> None:
        """Refresh styling on all message bubbles.

        Args:
            bubbles: List of MessageBubble widgets
        """
        for bubble in bubbles:
            role = getattr(bubble, "role", None)
            if role:
                self.apply_to_bubble(bubble, role)

    def get_background_color(self) -> str:
        """Get application background color.

        Returns:
            Color string (hex or Textual variable)
        """
        if self._using_textual_theme:
            return "$background"
        return self.ui_config.get("background_color", "#000000")

    def switch_theme(self, theme_name: str | None) -> None:
        """Switch to a different theme.

        Args:
            theme_name: Theme name, or None for custom colors
        """
        self._using_textual_theme = bool(theme_name)
        self.config["theme"] = theme_name
        LOGGER.info(f"Switched to theme: {theme_name or 'custom'}")
