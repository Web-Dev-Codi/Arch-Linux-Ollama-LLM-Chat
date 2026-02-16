"""Domain exception hierarchy for the Ollama chat application."""

from __future__ import annotations


class OllamaChatError(RuntimeError):
    """Base class for all domain-level chat errors."""


class OllamaConnectionError(OllamaChatError):
    """Raised when the Ollama host cannot be reached."""


class OllamaModelNotFoundError(OllamaChatError):
    """Raised when the configured model is unavailable."""


class OllamaStreamingError(OllamaChatError):
    """Raised when streaming fails for non-connectivity reasons."""


class ConfigValidationError(OllamaChatError):
    """Raised when configuration cannot be validated safely."""
