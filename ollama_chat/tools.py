"""Tool registry for Ollama agent-loop tool calling."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
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

# Serialise all temporary env-var mutations so that concurrent threads
# (e.g. when tool execution is offloaded via asyncio.to_thread) cannot
# observe each other's transient OLLAMA_API_KEY value.
_env_lock = threading.Lock()


def _with_temp_env(key: str, value: str, fn: Callable[[], str]) -> str:
    """Temporarily set an environment variable, call fn(), then restore.

    Protected by a module-level lock so that concurrent threads do not
    observe each other's transient environment changes.
    """
    with _env_lock:
        old_value = os.environ.get(key)
        os.environ[key] = value
        try:
            return fn()
        finally:
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


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
        This method is synchronous; callers in an async context should use
        ``asyncio.to_thread(registry.execute, name, args)`` to avoid blocking
        the event loop.
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


@dataclass(frozen=True)
class ToolRegistryOptions:
    """Options used to build a ToolRegistry without boolean flags.

    If ``web_search_api_key`` is a non-empty string, web_search and web_fetch
    tools are registered with the provided key. If it is empty or None, no web
    tools are added.
    """

    web_search_api_key: str | None = None


def build_registry(options: ToolRegistryOptions | None = None) -> ToolRegistry:
    """Build a ToolRegistry based on provided options.

    - When ``options.web_search_api_key`` is a non-empty string, register
      web_search and web_fetch tools with that key.
    - Otherwise return an empty registry.
    """
    registry = ToolRegistry()
    if options is None:
        return registry

    api_key = (options.web_search_api_key or "").strip()
    if not api_key:
        return registry

    # Validate and register tools with the provided key
    registry.register(_make_web_search_tool(api_key))
    registry.register(_make_web_fetch_tool(api_key))
    LOGGER.info(
        "tools.web_search.enabled",
        extra={"event": "tools.web_search.enabled"},
    )
    return registry


def _make_web_search_tool(api_key: str) -> Callable[..., str]:
    """Return a web_search callable with the API key bound at creation time."""

    if _ollama_web_search is None:
        raise OllamaToolError(
            "web_search is unavailable: the ollama package is not installed."
        )

    def _web_search_tool(query: str, max_results: int = 5) -> str:
        """Search the web for a query and return relevant results.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return (1-10).

        Returns:
            Formatted search results as a string.
        """
        try:
            return _with_temp_env(
                "OLLAMA_API_KEY",
                api_key,
                lambda: str(_ollama_web_search(query, max_results=max_results)),
            )
        except Exception as exc:  # noqa: BLE001
            raise OllamaToolError(f"web_search failed: {exc}") from exc

    return _web_search_tool


def _make_web_fetch_tool(api_key: str) -> Callable[..., str]:
    """Return a web_fetch callable with the API key bound at creation time."""

    if _ollama_web_fetch is None:
        raise OllamaToolError(
            "web_fetch is unavailable: the ollama package is not installed."
        )

    def _web_fetch_tool(url: str) -> str:
        """Fetch the content of a web page by URL.

        Args:
            url: The URL to fetch.

        Returns:
            The page title and content as a string.
        """
        try:
            return _with_temp_env(
                "OLLAMA_API_KEY",
                api_key,
                lambda: str(_ollama_web_fetch(url)),
            )
        except Exception as exc:  # noqa: BLE001
            raise OllamaToolError(f"web_fetch failed: {exc}") from exc

    return _web_fetch_tool


def build_default_registry(
    web_search_enabled: bool = False,
    web_search_api_key: str = "",
) -> ToolRegistry:
    """Compatibility wrapper for legacy API with a boolean flag.

    Prefer ``build_registry(ToolRegistryOptions(web_search_api_key=...))``.
    """
    if not web_search_enabled:
        return ToolRegistry()

    # Resolve API key: explicit config value takes precedence over env var.
    api_key = web_search_api_key or os.environ.get("OLLAMA_API_KEY", "").strip()
    if not api_key:
        raise OllamaToolError(
            "web_search_enabled is True but no OLLAMA_API_KEY was found. "
            "Set web_search_api_key in [capabilities] or export OLLAMA_API_KEY."
        )

    return build_registry(ToolRegistryOptions(web_search_api_key=api_key))
