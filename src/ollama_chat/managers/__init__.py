"""Manager classes for separating concerns from the main app.

Available managers:
- CapabilityManager: Model capability detection and management
- CommandManager: Slash command registration and execution
- ConnectionManager: Connection state monitoring
- ConversationManager: Conversation persistence and export
- ThemeManager: Theme and styling management
- StreamManager: Streaming response handling
- MessageRenderer: Message bubble creation and rendering
- AttachmentManager: File/image attachment handling
"""

from __future__ import annotations

from .attachment import IMAGE_EXTENSIONS, AttachmentManager
from .capability import CapabilityManager
from .command import CommandManager
from .connection import ConnectionManager
from .conversation import ConversationManager
from .message_renderer import MessageRenderer
from .stream import StreamManager
from .theme import ThemeManager

__all__ = [
    "CapabilityManager",
    "CommandManager",
    "ConnectionManager",
    "ConversationManager",
    "ThemeManager",
    "StreamManager",
    "MessageRenderer",
    "AttachmentManager",
    "IMAGE_EXTENSIONS",
]
