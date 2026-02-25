"""Tests for conversation persistence workflows."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from ollama_chat.persistence import (
    ConversationPersistence,
    PersistenceDisabledError,
    PersistenceFormatError,
)


def _make_persistence(base: Path) -> ConversationPersistence:
    return ConversationPersistence(
        enabled=True,
        directory=str(base / "conversations"),
        metadata_path=str(base / "conversations" / "index.json"),
    )


class PersistenceTests(unittest.TestCase):
    """Validate save, list, load, and export behavior."""

    def test_save_and_load_latest_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = _make_persistence(base)
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
            persistence = _make_persistence(base)
            payload = [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Answer"},
            ]
            output = persistence.export_markdown(payload, "llama3.2")
            content = output.read_text(encoding="utf-8")
            self.assertIn("# Conversation Export (llama3.2)", content)
            self.assertIn("## User", content)
            self.assertIn("## Assistant", content)

    def test_list_conversations_newest_first(self) -> None:
        """list_conversations() should return items sorted newest-first."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = _make_persistence(base)
            messages: list[dict[str, str]] = [{"role": "user", "content": "x"}]
            persistence.save_conversation(messages, "model-a")
            # Ensure distinct timestamps even on fast machines.
            time.sleep(0.01)
            persistence.save_conversation(messages, "model-b")

            listed = persistence.list_conversations()
            self.assertEqual(len(listed), 2)
            # Newest (model-b) must appear first because created_at is larger.
            self.assertGreater(listed[0]["created_at"], listed[1]["created_at"])

    def test_load_latest_returns_none_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = _make_persistence(base)
            result = persistence.load_latest_conversation()
            self.assertIsNone(result)

    def test_load_latest_returns_none_when_file_missing(self) -> None:
        """load_latest_conversation returns None if indexed file was deleted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = _make_persistence(base)
            messages: list[dict[str, str]] = [{"role": "user", "content": "hi"}]
            saved_path = persistence.save_conversation(messages, "llama3.2")
            saved_path.unlink()  # Delete the file after saving.

            result = persistence.load_latest_conversation()
            self.assertIsNone(result)

    def test_load_conversation_raises_on_invalid_payload(self) -> None:
        """load_conversation() raises PersistenceFormatError if payload is not a dict."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = _make_persistence(base)
            bad_file = base / "bad.json"
            bad_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            with self.assertRaises(PersistenceFormatError):
                persistence.load_conversation(bad_file)

    def test_save_raises_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = ConversationPersistence(
                enabled=False,
                directory=str(base / "conversations"),
                metadata_path=str(base / "conversations" / "index.json"),
            )
            with self.assertRaises(PersistenceDisabledError):
                persistence.save_conversation([{"role": "user", "content": "hi"}], "m")

    def test_export_raises_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = ConversationPersistence(
                enabled=False,
                directory=str(base / "conversations"),
                metadata_path=str(base / "conversations" / "index.json"),
            )
            with self.assertRaises(PersistenceDisabledError):
                persistence.export_markdown([{"role": "user", "content": "hi"}], "m")

    def test_load_latest_ignores_index_paths_outside_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = _make_persistence(base)
            persistence._ensure_paths()
            # Index points outside persistence.directory; should be ignored.
            outside = base / "outside.json"
            outside.write_text(json.dumps({"messages": []}), encoding="utf-8")
            persistence.metadata_path.write_text(
                json.dumps(
                    [
                        {
                            "path": str(outside),
                            "created_at": "2099-01-01T00:00:00+00:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            self.assertIsNone(persistence.load_latest_conversation())

    def test_save_multiple_and_list_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = _make_persistence(base)
            messages: list[dict[str, str]] = [{"role": "user", "content": "hi"}]
            for _ in range(3):
                persistence.save_conversation(messages, "llama3.2")
            listed = persistence.list_conversations()
            self.assertEqual(len(listed), 3)

    def test_corrupted_index_returns_empty_list(self) -> None:
        """A corrupted index file is handled gracefully — returns empty list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            persistence = _make_persistence(base)
            # Force-create index dir then corrupt it.
            persistence._ensure_paths()
            persistence.metadata_path.write_text("not valid json{{", encoding="utf-8")
            listed = persistence.list_conversations()
            self.assertEqual(listed, [])


if __name__ == "__main__":
    unittest.main()
