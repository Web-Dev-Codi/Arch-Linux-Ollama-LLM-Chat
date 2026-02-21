"""Tool registry for Ollama agent-loop tool calling."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from .exceptions import OllamaToolError

try:
    from ollama import web_fetch as _ollama_web_fetch
    from ollama import web_search as _ollama_web_search
except ModuleNotFoundError:  # pragma: no cover - optional dependency.
    _ollama_web_search = None  # type: ignore[assignment]
    _ollama_web_fetch = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of callable tools available to the model during an agent loop."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, fn: Callable[..., Any]) -> None:
        """Register a callable as a named tool.

        The function name is used as the tool name.
        """
        self._tools[fn.__name__] = fn
        LOGGER.debug(
            "tools.registered",
            extra={"event": "tools.registered", "tool": fn.__name__},
        )

    def build_tools_list(self) -> list[Callable[..., Any]]:
        """Return the list of tool callables for passing to the Ollama SDK."""
        return list(self._tools.values())

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a named tool and return its string result.

        Raises OllamaToolError if the tool is unknown or raises an exception.
        """
        fn = self._tools.get(name)
        if fn is None:
            raise OllamaToolError(f"Unknown tool requested by model: {name!r}")
        try:
            result = fn(**arguments)
            return str(result)
        except OllamaToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - tool functions can fail arbitrarily.
            raise OllamaToolError(f"Tool {name!r} raised an error: {exc}") from exc

    @property
    def is_empty(self) -> bool:
        """Return True when no tools are registered."""
        return not bool(self._tools)


def _web_search_tool(query: str, max_results: int = 5) -> str:
    """Search the web for a query and return relevant results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (1-10).

    Returns:
        Formatted search results as a string.
    """
    if _ollama_web_search is None:
        raise OllamaToolError(
            "web_search is unavailable: the ollama package is not installed."
        )
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if not api_key:
        raise OllamaToolError(
            "web_search requires OLLAMA_API_KEY to be set in the environment."
        )
    try:
        response = _ollama_web_search(query, max_results=max_results)
        return str(response)
    except Exception as exc:  # noqa: BLE001
        raise OllamaToolError(f"web_search failed: {exc}") from exc


def _web_fetch_tool(url: str) -> str:
    """Fetch the content of a web page by URL.

    Args:
        url: The URL to fetch.

    Returns:
        The page title and content as a string.
    """
    if _ollama_web_fetch is None:
        raise OllamaToolError(
            "web_fetch is unavailable: the ollama package is not installed."
        )
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if not api_key:
        raise OllamaToolError(
            "web_fetch requires OLLAMA_API_KEY to be set in the environment."
        )
    try:
        response = _ollama_web_fetch(url)
        return str(response)
    except Exception as exc:  # noqa: BLE001
        raise OllamaToolError(f"web_fetch failed: {exc}") from exc


def build_default_registry(
    web_search_enabled: bool = False,
    web_search_api_key: str = "",
) -> ToolRegistry:
    """Build and return a ToolRegistry with built-in tools based on config.

    When web_search_enabled is True, registers web_search and web_fetch.
    If web_search_api_key is provided it is injected into the environment
    before tool execution.
    """
    registry = ToolRegistry()
    if web_search_enabled:
        if web_search_api_key:
            os.environ.setdefault("OLLAMA_API_KEY", web_search_api_key)
        registry.register(_web_search_tool)
        registry.register(_web_fetch_tool)
        LOGGER.info(
            "tools.web_search.enabled",
            extra={"event": "tools.web_search.enabled"},
        )
    return registry
