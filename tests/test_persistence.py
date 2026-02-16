"""Tests for conversation persistence workflows."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from ollama_chat.persistence import ConversationPersistence


class PersistenceTests(unittest.TestCase):
    """Validate save, list, load, and export behavior."""

    def test_save_and_load_latest_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = ConversationPersistence(
                enabled=True,
                directory=str(base / "conversations"),
                metadata_path=str(base / "conversations" / "index.json"),
            )
            payload = [
                {"role": "system", "content": "You are a helper."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ]

            saved_path = persistence.save_conversation(payload, "llama3.2")
            self.assertTrue(saved_path.exists())

            listed = persistence.list_conversations()
            self.assertEqual(len(listed), 1)
            latest = persistence.load_latest_conversation()
            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest["model"], "llama3.2")
            self.assertEqual(latest["messages"][-1]["content"], "Hi")

    def test_export_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = ConversationPersistence(
                enabled=True,
                directory=str(base / "conversations"),
                metadata_path=str(base / "conversations" / "index.json"),
            )
            payload = [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Answer"},
            ]
            output = persistence.export_markdown(payload, "llama3.2")
            content = output.read_text(encoding="utf-8")
            self.assertIn("# Conversation Export (llama3.2)", content)
            self.assertIn("## User", content)
            self.assertIn("## Assistant", content)


if __name__ == "__main__":
    unittest.main()
