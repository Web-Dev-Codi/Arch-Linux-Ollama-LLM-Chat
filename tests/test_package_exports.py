"""Tests for top-level package lazy exports."""

from __future__ import annotations

import unittest

import ollama_chat


class PackageExportTests(unittest.TestCase):
    """Ensure __getattr__ and exported symbols behave as expected."""

    def test_lazy_exports_resolve_known_symbols(self) -> None:
        self.assertTrue(callable(ollama_chat.load_config))
        self.assertTrue(callable(ollama_chat.ensure_config_dir))
        self.assertIsNotNone(ollama_chat.OllamaChat)
        self.assertIsNotNone(ollama_chat.OllamaChatError)
        self.assertIsNotNone(ollama_chat.OllamaConnectionError)
        self.assertIsNotNone(ollama_chat.OllamaModelNotFoundError)
        self.assertIsNotNone(ollama_chat.OllamaStreamingError)
        self.assertIsNotNone(ollama_chat.ConfigValidationError)
        self.assertIsNotNone(ollama_chat.StateManager)
        self.assertIsNotNone(ollama_chat.ConversationState)
        self.assertIsNotNone(ollama_chat.MessageStore)
        self.assertIsNotNone(ollama_chat.ConversationPersistence)

    def test_unknown_symbol_raises_attribute_error(self) -> None:
        with self.assertRaises(AttributeError):
            getattr(ollama_chat, "THIS_DOES_NOT_EXIST")


if __name__ == "__main__":
    unittest.main()
