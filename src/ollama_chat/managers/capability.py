"""Model capability management.

Manages detection and tracking of model capabilities (tools, vision, thinking).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..capabilities import CapabilityContext
    from ..chat import CapabilityReport, OllamaChat

LOGGER = logging.getLogger(__name__)


class CapabilityManager:
    """Manages model capability detection and effective capability computation.

    Tracks:
    - Model capabilities (from Ollama /api/show)
    - User preferences (from config)
    - Effective capabilities (intersection of both)
    """

    def __init__(
        self,
        chat_client: OllamaChat,
        user_preferences: dict,
    ) -> None:
        """Initialize capability manager.

        Args:
            chat_client: Ollama chat client
            user_preferences: User capability preferences from config
        """
        from ..capabilities import CapabilityContext
        from ..chat import CapabilityReport

        self.chat = chat_client
        self.user_preferences = user_preferences

        # Model capabilities from Ollama
        self._model_caps: CapabilityReport = CapabilityReport(known=False, caps={})

        # Effective capabilities (model + user preferences)
        self._effective_caps: CapabilityContext = CapabilityContext(
            think=False,
            show_thinking=False,
            tools_enabled=False,
            vision_enabled=False,
            web_search_enabled=False,
            max_tool_iterations=0,
        )

    @property
    def model_capabilities(self):
        """Model capabilities detected from Ollama."""
        return self._model_caps

    @property
    def effective_capabilities(self):
        """Effective capabilities (model + user preferences)."""
        return self._effective_caps

    async def detect_model_capabilities(self, model_name: str | None = None) -> None:
        """Detect capabilities for the current or specified model.

        Args:
            model_name: Model to check, or None for current model
        """
        try:
            self._model_caps = await self.chat.show_model_capabilities(model_name)
            self._update_effective_caps()
            LOGGER.info(
                "Model capabilities detected",
                extra={
                    "model": model_name or self.chat.model,
                    "known": self._model_caps.known,
                    "tools": self._effective_caps.tools_enabled,
                    "vision": self._effective_caps.vision_enabled,
                    "thinking": self._effective_caps.think,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to detect model capabilities: {e}")
            # Keep existing capabilities on error

    def _update_effective_caps(self) -> None:
        """Recompute effective capabilities from model + user preferences.

        Effective capabilities are the intersection of:
        1. What the model supports (from /api/show)
        2. What the user wants (from config)
        """
        from ..capabilities import CapabilityContext

        # If model caps are unknown, use conservative defaults
        if not self._model_caps.known:
            LOGGER.warning("Model capabilities unknown, using conservative defaults")
            self._effective_caps = CapabilityContext(
                think=True,
                show_thinking=self.user_preferences.get("show_thinking", True),
                tools_enabled=True,
                vision_enabled=True,
                web_search_enabled=self.user_preferences.get(
                    "web_search_enabled", False
                ),
                max_tool_iterations=self.user_preferences.get("max_tool_iterations", 10),
            )
            return

        # Compute effective capabilities
        caps_set = self._model_caps.caps

        # Model support + user preference
        self._effective_caps = CapabilityContext(
            think=("thinking" in caps_set),
            show_thinking=self.user_preferences.get("show_thinking", True),
            tools_enabled=("tools" in caps_set),
            vision_enabled=("vision" in caps_set),
            web_search_enabled=self.user_preferences.get("web_search_enabled", False),
            max_tool_iterations=self.user_preferences.get("max_tool_iterations", 10),
        )

    def get_unsupported_features(self) -> list[str]:
        """Get list of features the model doesn't support.

        Returns:
            List of feature names like "thinking", "tools", "vision"
        """
        if not self._model_caps.known:
            return []

        unsupported = []
        checks = [
            (self._effective_caps.think, "thinking"),
            (self._effective_caps.tools_enabled, "tools"),
            (self._effective_caps.vision_enabled, "vision"),
        ]

        for enabled, name in checks:
            if not enabled:
                unsupported.append(name)

        return unsupported

    def update_user_preferences(self, preferences: dict) -> None:
        """Update user preferences and recompute effective capabilities.

        Args:
            preferences: New user preferences
        """
        self.user_preferences.update(preferences)
        self._update_effective_caps()
