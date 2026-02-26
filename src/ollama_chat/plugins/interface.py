"""Plugin interface and manager.

Phase 4.2 implementation - allows dynamic loading of tools and extensions.

Usage:
    # Define a plugin
    class MyPlugin(Plugin):
        name = "my_plugin"
        version = "1.0.0"

        def initialize(self, context):
            # Setup plugin
            pass

        def get_tools(self):
            return [MyCustomTool()]

    # Load plugin
    manager = PluginManager()
    manager.register(MyPlugin())
    await manager.initialize_all()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import logging

LOGGER = logging.getLogger(__name__)


class Plugin(ABC):
    """Base class for plugins.

    Plugins can provide:
    - Custom tools
    - Event handlers
    - UI extensions
    - Configuration
    """

    name: str = "unknown"
    version: str = "0.0.0"
    description: str = ""

    @abstractmethod
    def initialize(self, context: dict[str, Any]) -> None:
        """Initialize the plugin.

        Args:
            context: Application context (config, event bus, etc.)
        """
        pass

    def get_tools(self) -> list:
        """Get tools provided by this plugin.

        Returns:
            List of Tool instances
        """
        return []

    def get_commands(self) -> dict[str, Any]:
        """Get slash commands provided by this plugin.

        Returns:
            Dict of command_name -> handler
        """
        return {}

    def shutdown(self) -> None:
        """Clean up plugin resources."""
        pass


class PluginManager:
    """Manages plugin loading and lifecycle.

    Responsibilities:
    - Discover plugins in plugin directory
    - Load and initialize plugins
    - Provide plugin tools to tool registry
    - Handle plugin lifecycle
    """

    def __init__(self, plugin_dir: Path | None = None) -> None:
        self.plugin_dir = (
            plugin_dir or Path.home() / ".config" / "ollamaterm" / "plugins"
        )
        self._plugins: dict[str, Plugin] = {}
        self._initialized = False

    def register(self, plugin: Plugin) -> None:
        """Register a plugin.

        Args:
            plugin: Plugin instance
        """
        if plugin.name in self._plugins:
            LOGGER.warning(f"Plugin {plugin.name} already registered, replacing")

        self._plugins[plugin.name] = plugin
        LOGGER.info(f"Registered plugin: {plugin.name} v{plugin.version}")

    async def initialize_all(self, context: dict[str, Any]) -> None:
        """Initialize all registered plugins.

        Args:
            context: Application context
        """
        if self._initialized:
            return

        for name, plugin in self._plugins.items():
            try:
                plugin.initialize(context)
                LOGGER.info(f"Initialized plugin: {name}")
            except Exception as e:
                LOGGER.error(f"Failed to initialize plugin {name}: {e}")

        self._initialized = True

    def get_all_tools(self) -> list:
        """Get tools from all plugins.

        Returns:
            Combined list of tools from all plugins
        """
        tools = []
        for plugin in self._plugins.values():
            tools.extend(plugin.get_tools())
        return tools

    def get_plugin(self, name: str) -> Plugin | None:
        """Get a specific plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None
        """
        return self._plugins.get(name)

    def shutdown_all(self) -> None:
        """Shutdown all plugins."""
        for name, plugin in self._plugins.items():
            try:
                plugin.shutdown()
                LOGGER.info(f"Shutdown plugin: {name}")
            except Exception as e:
                LOGGER.error(f"Error shutting down plugin {name}: {e}")
