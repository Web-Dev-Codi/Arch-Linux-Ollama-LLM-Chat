"""Top-level package for ollama-chat-tui."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import OllamaChatApp
    from .chat import OllamaChat
    from .config import ensure_config_dir, load_config
    from .exceptions import (
        ConfigValidationError,
        OllamaChatError,
        OllamaConnectionError,
        OllamaModelNotFoundError,
        OllamaStreamingError,
    )
    from .message_store import MessageStore
    from .persistence import ConversationPersistence
    from .state import ConversationState, StateManager

__all__ = [
    "ConfigValidationError",
    "ConversationState",
    "MessageStore",
    "ConversationPersistence",
    "OllamaChat",
    "OllamaChatApp",
    "OllamaChatError",
    "OllamaConnectionError",
    "OllamaModelNotFoundError",
    "OllamaStreamingError",
    "StateManager",
    "ensure_config_dir",
    "load_config",
]


def __getattr__(name: str) -> Any:
    """Lazily import symbols to keep optional UI dependencies optional at import time."""
    if name == "OllamaChat":
        from .chat import OllamaChat

        return OllamaChat
    if name in {"ensure_config_dir", "load_config"}:
        from .config import ensure_config_dir, load_config

        return {"ensure_config_dir": ensure_config_dir, "load_config": load_config}[name]
    if name in {
        "ConfigValidationError",
        "OllamaChatError",
        "OllamaConnectionError",
        "OllamaModelNotFoundError",
        "OllamaStreamingError",
    }:
        from .exceptions import (
            ConfigValidationError,
            OllamaChatError,
            OllamaConnectionError,
            OllamaModelNotFoundError,
            OllamaStreamingError,
        )

        return {
            "ConfigValidationError": ConfigValidationError,
            "OllamaChatError": OllamaChatError,
            "OllamaConnectionError": OllamaConnectionError,
            "OllamaModelNotFoundError": OllamaModelNotFoundError,
            "OllamaStreamingError": OllamaStreamingError,
        }[name]
    if name in {"ConversationState", "StateManager"}:
        from .state import ConversationState, StateManager

        return {"ConversationState": ConversationState, "StateManager": StateManager}[name]
    if name == "MessageStore":
        from .message_store import MessageStore

        return MessageStore
    if name == "ConversationPersistence":
        from .persistence import ConversationPersistence

        return ConversationPersistence
    if name == "OllamaChatApp":
        from .app import OllamaChatApp

        return OllamaChatApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
