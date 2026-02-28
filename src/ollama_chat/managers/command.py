"""Slash command handling and menu UI management.

Processes and executes slash commands like /image, /file, /new, etc.
Extracted from OllamaChatApp during Phase 2.4 refactoring.
Expanded during Phase 2B to include menu UI management.

Integration required in app.py:
- Replace inline command processing in _handle_send()
- Register commands with manager
- Use manager for command execution and menu display
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.widgets import OptionList

LOGGER = logging.getLogger(__name__)

CommandHandler = Callable[[str], Awaitable[None]]


class CommandManager:
    """Manages slash command registration, execution, and UI menu.

    Handles commands like:
    - /image <path> - Attach image
    - /file <path> - Attach file
    - /new - Start new conversation
    - /save - Save conversation
    - /load - Load conversation
    - /model [name] - Switch model
    - /preset [name] - Switch prompt preset
    - /help - Show help

    Also manages:
    - Slash menu display and filtering
    - Command autocompletion
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandHandler] = {}
        self._command_help: dict[str, str] = {}
        self._slash_menu_visible: bool = False

    def register(self, name: str, handler: CommandHandler, help_text: str = "") -> None:
        """Register a slash command.

        Args:
            name: Command name (with or without leading /)
            handler: Async function that handles the command
            help_text: Help text for command palette and menu
        """
        # Normalize: remove leading / if present
        normalized_name = name.lstrip("/")

        self._commands[normalized_name] = handler
        self._command_help[normalized_name] = help_text or f"Execute /{normalized_name}"
        LOGGER.debug(f"Registered command: /{normalized_name}")

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
            List of (command, help_text) tuples with "/" prefix
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

    def show_slash_menu(
        self,
        option_list: OptionList,
        prefix: str,
    ) -> None:
        """Show slash menu with commands matching the prefix.

        Args:
            option_list: OptionList widget to populate with commands
            prefix: Current input prefix (e.g., "/h" or "/")
        """
        if self._slash_menu_visible:
            return

        # Normalize prefix (remove leading /)
        search_prefix = prefix.lstrip("/").lower()

        # Filter commands by prefix
        matches = [
            (f"/{name}", help_text)
            for name, help_text in self._command_help.items()
            if name.lower().startswith(search_prefix)
        ]

        if not matches:
            return

        # Populate menu
        option_list.clear_options()
        for cmd, desc in sorted(matches):
            option_list.add_option(f"{cmd} - {desc}")

        # Show menu
        option_list.styles.display = "block"
        self._slash_menu_visible = True

    def hide_slash_menu(self, option_list: OptionList) -> None:
        """Hide the slash command menu.

        Args:
            option_list: OptionList widget to hide
        """
        if not self._slash_menu_visible:
            return

        option_list.clear_options()
        option_list.styles.display = "none"
        self._slash_menu_visible = False

    def is_menu_visible(self) -> bool:
        """Check if slash menu is currently visible.

        Returns:
            True if menu is visible, False otherwise
        """
        return self._slash_menu_visible
