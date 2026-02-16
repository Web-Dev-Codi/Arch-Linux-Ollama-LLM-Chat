"""Tests for domain exception hierarchy."""

from __future__ import annotations

import unittest

from ollama_chat.exceptions import (
    ConfigValidationError,
    OllamaChatError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStreamingError,
)


class ExceptionHierarchyTests(unittest.TestCase):
    """Validate exception inheritance contract."""

    def test_exception_hierarchy(self) -> None:
        self.assertTrue(issubclass(OllamaConnectionError, OllamaChatError))
        self.assertTrue(issubclass(OllamaModelNotFoundError, OllamaChatError))
        self.assertTrue(issubclass(OllamaStreamingError, OllamaChatError))
        self.assertTrue(issubclass(ConfigValidationError, OllamaChatError))


if __name__ == "__main__":
    unittest.main()
