"""Conversation management and persistence.

Handles conversation save/load, auto-save, and history management.
Extracted from OllamaChatApp during Phase 2.3 refactoring.

Integration required in app.py:
- Replace _load_conversation_* methods
- Replace _auto_save_on_exit() method
- Use manager for save/load actions
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..chat import OllamaChat
    from ..persistence import ConversationPersistence

LOGGER = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation state, persistence, and history.

    Responsibilities:
    - Load conversations from files
    - Save conversations
    - Auto-save on exit
    - Conversation history tracking
    """

    def __init__(
        self,
        chat_client: OllamaChat,
        persistence: ConversationPersistence,
        auto_save_enabled: bool = True,
    ) -> None:
        self.chat = chat_client
        self.persistence = persistence
        self.auto_save_enabled = auto_save_enabled
        self._current_conversation_path: Path | None = None

    async def load_from_path(self, path: Path) -> dict[str, Any]:
        """Load conversation from file path.

        Returns:
            Conversation payload with messages and metadata
        """
        try:
            payload = self.persistence.load(path)
            self._current_conversation_path = path
            LOGGER.info(f"Loaded conversation from {path}")
            return payload
        except Exception as e:
            LOGGER.error(f"Failed to load conversation: {e}")
            raise

    async def load_payload(self, payload: dict[str, Any]) -> None:
        """Load conversation from payload dict.

        Args:
            payload: Conversation data (messages, model, etc.)
        """
        # Apply payload to chat client
        self.chat.set_model(payload.get("model", self.chat.model))
        self.chat.set_messages(payload.get("messages", []))
        self.chat.set_system_message(payload.get("system_message", ""))

    async def save_current(self, path: Path | None = None) -> None:
        """Save current conversation.

        Args:
            path: File path, or None to use current path
        """
        save_path = path or self._current_conversation_path
        if not save_path:
            raise ValueError("No save path specified")

        payload = {
            "model": self.chat.model,
            "messages": self.chat.messages,
            "system_message": self.chat.system_message,
            "timestamp": self.persistence._timestamp(),
        }

        self.persistence.save(save_path, payload)
        self._current_conversation_path = save_path
        LOGGER.info(f"Saved conversation to {save_path}")

    def auto_save_on_exit(self) -> None:
        """Auto-save current conversation on application exit."""
        if not self.auto_save_enabled:
            return

        if not self.chat.messages:
            return  # Nothing to save

        try:
            # Use persistence auto-save
            path = self.persistence.auto_save_path()
            payload = {
                "model": self.chat.model,
                "messages": self.chat.messages,
                "system_message": self.chat.system_message,
            }
            self.persistence.save(path, payload)
            LOGGER.info(f"Auto-saved conversation to {path}")
        except Exception as e:
            LOGGER.error(f"Auto-save failed: {e}")

    def list_recent_conversations(self, limit: int = 10) -> list[Path]:
        """List recent conversation files.

        Returns:
            List of conversation file paths, most recent first
        """
        return self.persistence.list_conversations(limit=limit)
