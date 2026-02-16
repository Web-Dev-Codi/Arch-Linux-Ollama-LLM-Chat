"""Application state machine and lock-protected transitions."""

from __future__ import annotations

import asyncio
from enum import Enum


class ConversationState(str, Enum):
    """Finite state machine for the active conversation lifecycle."""

    IDLE = "IDLE"
    STREAMING = "STREAMING"
    ERROR = "ERROR"
    CANCELLING = "CANCELLING"


class StateManager:
    """Manage state transitions with async lock semantics."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state = ConversationState.IDLE

    async def get_state(self) -> ConversationState:
        """Return the current state under lock."""
        async with self._lock:
            return self._state

    async def transition_to(self, new_state: ConversationState) -> ConversationState:
        """Transition to a new state and return it."""
        async with self._lock:
            self._state = new_state
            return self._state

    async def transition_if(
        self,
        expected_state: ConversationState,
        new_state: ConversationState,
    ) -> bool:
        """Transition only when current state matches expected state."""
        async with self._lock:
            if self._state != expected_state:
                return False
            self._state = new_state
            return True

    async def can_send_message(self) -> bool:
        """Return True when message submission is allowed."""
        async with self._lock:
            return self._state == ConversationState.IDLE
