"""Connection state management.

Proof-of-concept manager extracted from app.py to demonstrate
the manager pattern for reducing god class complexity.

Full implementation would require:
- Integrating with app.py lifecycle
- Handling state change callbacks
- Managing the monitoring task
- ~150 LOC total

This is a Phase 2 foundation - full extraction would continue with:
- CapabilityManager
- ConversationManager
- CommandHandler
- ThemeManager
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..chat import OllamaChat

LOGGER = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection status."""

    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"


class ConnectionManager:
    """Manages connection state and monitoring.

    Extracted from OllamaChatApp to reduce god class complexity.
    This demonstrates the pattern - full integration requires
    refactoring app.py to use this manager.
    """

    def __init__(
        self,
        chat_client: OllamaChat,
        check_interval_seconds: int = 15,
    ) -> None:
        """Initialize connection manager.

        Args:
            chat_client: Ollama chat client
            check_interval_seconds: How often to check connection
        """
        self.chat = chat_client
        self.check_interval = check_interval_seconds
        self._state = ConnectionState.UNKNOWN
        self._check_task: asyncio.Task | None = None
        self._on_state_change: list[Callable] = []

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    def on_state_change(self, callback: Callable) -> None:
        """Register callback for state changes.

        Args:
            callback: Function called with (old_state, new_state)
        """
        self._on_state_change.append(callback)

    async def start_monitoring(self) -> None:
        """Start background connection monitoring."""
        if self._check_task is None:
            self._check_task = asyncio.create_task(self._monitor_loop())
            LOGGER.info("Connection monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop background connection monitoring."""
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            self._check_task = None
            LOGGER.info("Connection monitoring stopped")

    async def check_connection(self) -> ConnectionState:
        """Check connection and update state.

        Returns:
            Current connection state after check
        """
        try:
            is_connected = await self.chat.check_connection()
            new_state = (
                ConnectionState.ONLINE if is_connected else ConnectionState.OFFLINE
            )
        except Exception:
            new_state = ConnectionState.OFFLINE

        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            await self._notify_change(old_state, new_state)
            LOGGER.info(
                "Connection state changed",
                extra={"old": old_state.value, "new": new_state.value},
            )

        return self._state

    async def _monitor_loop(self) -> None:
        """Background task that polls connection status."""
        while True:
            try:
                await self.check_connection()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.error(f"Connection check error: {e}")
                await asyncio.sleep(self.check_interval)

    async def _notify_change(
        self,
        old_state: ConnectionState,
        new_state: ConnectionState,
    ) -> None:
        """Notify callbacks of state change."""
        for callback in self._on_state_change:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(old_state, new_state)
                else:
                    callback(old_state, new_state)
            except Exception as e:
                LOGGER.error(f"State change callback error: {e}")
