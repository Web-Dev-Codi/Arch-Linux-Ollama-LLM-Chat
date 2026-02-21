"""Tests for lock-protected conversation state transitions."""

from __future__ import annotations

import asyncio
import unittest

from ollama_chat.state import ConversationState, StateManager


class StateManagerTests(unittest.IsolatedAsyncioTestCase):
    """Validate state machine behavior for Tier 1 requirements."""

    async def test_can_send_only_when_idle(self) -> None:
        manager = StateManager()
        self.assertTrue(await manager.can_send_message())
        await manager.transition_to(ConversationState.STREAMING)
        self.assertFalse(await manager.can_send_message())
        await manager.transition_to(ConversationState.IDLE)
        self.assertTrue(await manager.can_send_message())

    async def test_transition_if_enforces_expected_state(self) -> None:
        manager = StateManager()
        changed = await manager.transition_if(
            ConversationState.STREAMING, ConversationState.ERROR
        )
        self.assertFalse(changed)
        self.assertEqual(await manager.get_state(), ConversationState.IDLE)

        changed = await manager.transition_if(
            ConversationState.IDLE, ConversationState.STREAMING
        )
        self.assertTrue(changed)
        self.assertEqual(await manager.get_state(), ConversationState.STREAMING)

    async def test_lock_prevents_double_stream_entry(self) -> None:
        manager = StateManager()

        async def try_enter_streaming() -> bool:
            await asyncio.sleep(0)
            return await manager.transition_if(
                ConversationState.IDLE, ConversationState.STREAMING
            )

        results = await asyncio.gather(*(try_enter_streaming() for _ in range(10)))
        self.assertEqual(sum(1 for result in results if result), 1)
        self.assertEqual(await manager.get_state(), ConversationState.STREAMING)


if __name__ == "__main__":
    unittest.main()
