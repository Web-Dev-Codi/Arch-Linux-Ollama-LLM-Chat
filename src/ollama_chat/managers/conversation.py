"""Conversation management and persistence.

Handles conversation save/load, auto-save, and history management.

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
            payload = self.persistence.load_conversation(path)
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
        model = payload.get("model", self.chat.model)
        if isinstance(model, str) and model.strip():
            self.chat.set_model(model.strip())

        messages = payload.get("messages", [])
        if isinstance(messages, list):
            self.chat.load_history(messages)

        # Backcompat: update system prompt if provided explicitly
        sys_msg = payload.get("system_message")
        if isinstance(sys_msg, str) and sys_msg.strip():
            try:
                self.chat.system_prompt = sys_msg.strip()
                self.chat.message_store = self.chat.message_store.__class__(
                    system_prompt=sys_msg.strip(),
                    max_history_messages=self.chat.message_store.max_history_messages,
                    max_context_tokens=self.chat.message_store.max_context_tokens,
                )
            except Exception:
                # Non-fatal; continue with loaded history
                pass

    async def save_snapshot(self, name: str = "") -> Path:
        """Save current conversation using persistence's snapshot format.

        Args:
            name: Optional friendly name for the snapshot

        Returns:
            Path to the saved snapshot
        """
        target = self.persistence.save_conversation(
            self.chat.messages,
            self.chat.model,
            name=name,
        )
        self._current_conversation_path = target
        LOGGER.info(f"Saved conversation to {target}")
        return target

    def auto_save_on_exit(self) -> None:
        """Auto-save current conversation on application exit."""
        if not self.auto_save_enabled:
            return

        if not getattr(self.persistence, "enabled", True):
            return

        if not self.chat.messages:
            return  # Nothing to save

        try:
            target = self.persistence.save_conversation(
                self.chat.messages, self.chat.model, name="Auto-save"
            )
            self._current_conversation_path = target
            LOGGER.info(f"Auto-saved conversation to {target}")
        except Exception as e:
            LOGGER.error(f"Auto-save failed: {e}")

    def list_recent_conversations(self, limit: int = 10) -> list[Path]:
        """List recent conversation files.

        Returns:
            List of conversation file paths, most recent first
        """
        rows = self.persistence.list_conversations()
        paths: list[Path] = []
        for row in rows[: max(0, limit)]:
            raw = row.get("path") if isinstance(row, dict) else None
            if isinstance(raw, str) and raw.strip():
                try:
                    paths.append(Path(raw).expanduser())
                except Exception:
                    continue
        return paths

    async def load_latest(self) -> dict[str, Any] | None:
        """Load the most recent conversation payload (if any)."""
        try:
            return self.persistence.load_latest_conversation()
        except Exception as e:
            LOGGER.error(f"Failed to load latest conversation: {e}")
            raise
