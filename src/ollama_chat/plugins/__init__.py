"""Plugin system for extensibility.

Plugin architecture for dynamic tool loading and extensions.
"""

from .interface import Plugin, PluginManager

__all__ = ["Plugin", "PluginManager"]
