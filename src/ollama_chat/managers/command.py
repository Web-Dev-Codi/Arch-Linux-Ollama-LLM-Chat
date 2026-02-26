"""Slash command handling.

Processes and executes slash commands like /image, /file, /new, etc.
Extracted from OllamaChatApp during Phase 2.4 refactoring.

Integration required in app.py:
- Replace inline command processing in _handle_send()
- Register commands with manager
- Use manager for command execution
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    pass

LOGGER = logging.getLogger(__name__)

CommandHandler = Callable[[str], Awaitable[None]]


class CommandManager:
    """Manages slash command registration and execution.

    Handles commands like:
    - /image <path> - Attach image
    - /file <path> - Attach file
    - /new - Start new conversation
    - /save - Save conversation
    - /load - Load conversation
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandHandler] = {}
        self._command_help: dict[str, str] = {}

    def register(self, name: str, handler: CommandHandler, help_text: str) -> None:
        """Register a slash command.

        Args:
            name: Command name (without /)
            handler: Async function that handles the command
            help_text: Help text for command palette
        """
        self._commands[name] = handler
        self._command_help[name] = help_text
        LOGGER.debug(f"Registered command: /{name}")

    async def execute(self, command_line: str) -> bool:
        """Execute a slash command.

        Args:
            command_line: Full command line (e.g., "/image /path/to/file.png")

        Returns:
            True if command was handled, False otherwise
        """
        if not command_line.startswith("/"):
            return False

        parts = command_line.split(maxsplit=1)
        command_name = parts[0][1:]  # Remove leading /
        args = parts[1] if len(parts) > 1 else ""

        handler = self._commands.get(command_name)
        if not handler:
            LOGGER.warning(f"Unknown command: /{command_name}")
            return False

        try:
            await handler(args)
            return True
        except Exception as e:
            LOGGER.error(f"Command /{command_name} failed: {e}")
            raise

    def get_commands(self) -> list[tuple[str, str]]:
        """Get list of available commands with help text.

        Returns:
            List of (command, help_text) tuples
        """
        return [
            (f"/{name}", help_text) for name, help_text in self._command_help.items()
        ]

    def is_command(self, text: str) -> bool:
        """Check if text is a slash command.

        Args:
            text: Text to check

        Returns:
            True if text starts with / and matches a registered command
        """
        if not text.startswith("/"):
            return False

        command_name = text.split()[0][1:]
        return command_name in self._commands
