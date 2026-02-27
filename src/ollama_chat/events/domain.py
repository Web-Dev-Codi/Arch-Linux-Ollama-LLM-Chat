from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class FileEditedEvent:
    file_path: str
    timestamp: datetime


@dataclass
class FileWatcherUpdatedEvent:
    file_path: str
    event: str  # "change", "create", "delete"
    timestamp: datetime


@dataclass
class ConversationSavedEvent:
    path: str
    timestamp: datetime


@dataclass
class CommandExecutedEvent:
    command: str
    success: bool
    timestamp: datetime
