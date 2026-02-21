"""Tests for bounded message storage and context trimming."""

from __future__ import annotations

import json
import unittest

from ollama_chat.message_store import MessageStore


class MessageStoreTests(unittest.TestCase):
    """Validate Tier 1 message storage requirements."""

    def test_max_history_messages_is_enforced(self) -> None:
        store = MessageStore(
            system_prompt="system", max_history_messages=4, max_context_tokens=10_000
        )
        store.append("user", "one")
        store.append("assistant", "two")
        store.append("user", "three")
        store.append("assistant", "four")

        self.assertEqual(len(store.messages), 4)
        self.assertEqual(store.messages[0]["role"], "system")
        self.assertEqual(store.messages[1]["content"], "two")

    def test_context_trim_preserves_system_message(self) -> None:
        store = MessageStore(
            system_prompt="system", max_history_messages=10, max_context_tokens=10_000
        )
        store.append("user", "alpha beta gamma delta epsilon")
        store.append("assistant", "alpha beta gamma delta epsilon")
        store.append("user", "alpha beta gamma delta epsilon")
        context = store.build_api_context(max_context_tokens=6)

        self.assertGreaterEqual(len(context), 1)
        self.assertEqual(context[0]["role"], "system")
        self.assertLessEqual(store.estimated_tokens(context), 6)

    def test_token_estimation_is_deterministic(self) -> None:
        store = MessageStore(
            system_prompt="system", max_history_messages=10, max_context_tokens=10_000
        )
        store.append("user", "hello world")
        store.append("assistant", "hello world again")

        first = store.estimated_tokens(store.messages)
        second = store.estimated_tokens(store.messages)
        self.assertEqual(first, second)

    def test_export_json_uses_stable_structure(self) -> None:
        store = MessageStore(
            system_prompt="system", max_history_messages=10, max_context_tokens=10_000
        )
        store.append("user", "hello")
        raw = store.export_json()
        parsed = json.loads(raw)
        self.assertEqual(parsed[0], {"role": "system", "content": "system"})
        self.assertEqual(parsed[1], {"role": "user", "content": "hello"})


if __name__ == "__main__":
    unittest.main()
