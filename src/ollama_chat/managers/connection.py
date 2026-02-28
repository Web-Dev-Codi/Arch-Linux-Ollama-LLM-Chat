"""Connection state management.

"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..chat import OllamaChat

LOGGER = logging.getLogger(__name__)


class ConnectionManager:
    """Manages connection state and monitoring."""

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
        from ..state import ConnectionState

        self.chat = chat_client
        self.check_interval = check_interval_seconds
        self._state = ConnectionState.UNKNOWN
        self._check_task: asyncio.Task | None = None
        self._on_state_change: list[Callable] = []
        self._ConnectionState = ConnectionState  # Store class for use in methods

    @property
    def state(self):
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

    async def check_connection(self):
        """Check connection and update state.

        Returns:
            Current connection state after check
        """
        try:
            is_connected = await self.chat.check_connection()
            new_state = (
                self._ConnectionState.ONLINE
                if is_connected
                else self._ConnectionState.OFFLINE
            )
        except Exception:
            new_state = self._ConnectionState.OFFLINE

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
        old_state,
        new_state,
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
